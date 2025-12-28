import os
import psycopg2
import tempfile
from pathlib import Path
from fastapi import FastAPI, Request, Depends, Query, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from app.auth import basic_auth
from app.models import (
    Agent, AgentCreate, AgentUpdate,
    Player, PlayerCreate, PlayerUpdate,
    ManualSlip, ManualSlipCreate,
    UploadResponse, ErrorResponse
)
from engine.compute import compute_dashboard
from engine.translate import translate_admin_export

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

def get_db():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, agent: str | None = Query(default=None), user=Depends(basic_auth)):
    conn = get_db()
    cur = conn.cursor()

    # Get the most recent week
    cur.execute("SELECT week_id FROM weeks ORDER BY week_id DESC LIMIT 1")
    week_result = cur.fetchone()
    current_week = week_result[0] if week_result else None

    # Aggregate weekly_raw + manual_slips to compute final week_amount
    cur.execute("""
            select
            w.week_id,
            p.player_id,
            p.display_name,
            a.name as agent,
            coalesce(wr.week_amount, 0) + coalesce(slips.total_adjustment, 0) as week_amount,
            coalesce(s.engaged, false) as engaged,
            coalesce(s.paid, false) as paid
            from weekly_raw wr
            join players p on p.player_id = wr.player_id
            join agents a on a.id = p.agent_id
            join weeks w on w.week_id = wr.week_id
            left join weekly_player_status s
                on s.week_id = wr.week_id and s.player_id = wr.player_id
            left join (
                select week_id, player_id, sum(amount) as total_adjustment
                from manual_slips
                group by week_id, player_id
            ) slips on slips.week_id = wr.week_id and slips.player_id = wr.player_id
            order by agent, p.player_id
    """)
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    # Also fetch manual slips for display
    slips = []
    if current_week:
        cur.execute("""
            SELECT m.id, m.week_id, m.player_id, m.amount, m.note, m.created_at,
                   p.display_name, a.name as agent_name
            FROM manual_slips m
            LEFT JOIN players p ON p.player_id = m.player_id
            LEFT JOIN agents a ON a.id = p.agent_id
            WHERE m.week_id = %s
            ORDER BY m.created_at DESC
        """, (current_week,))
        slip_cols = [c[0] for c in cur.description]
        slips = [dict(zip(slip_cols, r)) for r in cur.fetchall()]

    # Get all players for betslip form
    cur.execute("""
        SELECT p.player_id, p.display_name, a.name as agent_name
        FROM players p
        LEFT JOIN agents a ON a.id = p.agent_id
        ORDER BY a.name, p.player_id
    """)
    player_cols = [c[0] for c in cur.description]
    all_players = [dict(zip(player_cols, r)) for r in cur.fetchall()]

    conn.close()

    agents, book_total, final_balance, transfers = compute_dashboard(rows)

    agent_names = sorted(list(agents.keys()))
    selected_agent = agent if agent in agents else (agent_names[0] if agent_names else None)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "agents": agents,
            "agent_names": agent_names,
            "selected_agent": selected_agent,
            "book_total": book_total,
            "final_balance": final_balance,
            "transfers": transfers,
            "slips": slips,
            "current_week": current_week,
            "all_players": all_players,
        },
    )

@app.post("/status/toggle", response_class=JSONResponse)
def toggle_status(
    week_id: str = Form(...),
    player_id: str = Form(...),
    field: str = Form(...),
    value: str = Form(...),
    user=Depends(basic_auth),
):
    if field not in ("engaged", "paid"):
        return {"ok": False, "error": "Invalid field"}

    val = True if value == "true" else False

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
      insert into weekly_player_status (week_id, player_id, engaged, paid)
      values (%s, %s, false, false)
      on conflict (week_id, player_id) do nothing
    """, (week_id, player_id))

    cur.execute(f"""
      update weekly_player_status
      set {field} = %s, updated_at = now()
      where week_id = %s and player_id = %s
    """, (val, week_id, player_id))

    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/health/auth-config")
def auth_config(user=Depends(basic_auth)):
    return {
        "ADMIN_PASSWORD_set": bool(os.getenv("ADMIN_PASSWORD")),
        "ADMIN_SITE_PASSWORD_set": bool(os.getenv("ADMIN_SITE_PASSWORD")),
    }


# ============================================================================
# EXCEL UPLOAD
# ============================================================================

@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request, user=Depends(basic_auth)):
    """Render the upload page"""
    return templates.TemplateResponse("upload.html", {"request": request})


@app.get("/manage", response_class=HTMLResponse)
def manage_page(request: Request, user=Depends(basic_auth)):
    """Render the player/agent management page"""
    return templates.TemplateResponse("manage.html", {"request": request})


@app.post("/upload/weekly")
async def upload_weekly_excel(
    file: UploadFile = File(...),
    user=Depends(basic_auth)
) -> UploadResponse:
    """Upload and process weekly Excel export"""

    # Validate file type
    if not file.filename or not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="File must be an Excel file (.xlsx or .xls)")

    # Save uploaded file temporarily
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Process the Excel file
        df = translate_admin_export(tmp_path)

        if df.empty:
            raise HTTPException(status_code=400, detail="No valid player data found in Excel file")

        week_id = df['week_id'].iloc[0]

        # Insert data into database
        conn = get_db()
        cur = conn.cursor()

        # Insert week if not exists
        cur.execute(
            "INSERT INTO weeks (week_id) VALUES (%s) ON CONFLICT (week_id) DO NOTHING",
            (week_id,)
        )

        # Upsert weekly_raw data
        players_imported = 0
        for _, row in df.iterrows():
            cur.execute("""
                INSERT INTO weekly_raw (week_id, player_id, week_amount, pending, scraped_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (week_id, player_id)
                DO UPDATE SET
                    week_amount = EXCLUDED.week_amount,
                    pending = EXCLUDED.pending,
                    scraped_at = now()
            """, (row['week_id'], row['player_id'], row['week_amount'], row['pending']))
            players_imported += 1

        conn.commit()
        conn.close()

        return UploadResponse(
            success=True,
            message=f"Successfully imported {players_imported} player records for week {week_id}",
            week_id=week_id,
            players_imported=players_imported
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

    finally:
        # Clean up temp file
        if 'tmp_path' in locals():
            Path(tmp_path).unlink(missing_ok=True)


# ============================================================================
# PLAYER MANAGEMENT
# ============================================================================

@app.get("/players")
def list_players(user=Depends(basic_auth)):
    """List all players"""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT p.id, p.player_id, p.display_name, p.agent_id, a.name as agent_name
        FROM players p
        LEFT JOIN agents a ON a.id = p.agent_id
        ORDER BY p.player_id
    """)

    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()

    return rows


@app.post("/players", response_model=Player)
def create_player(player: PlayerCreate, user=Depends(basic_auth)):
    """Create a new player"""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO players (player_id, display_name, agent_id)
            VALUES (%s, %s, %s)
            RETURNING id, player_id, display_name, agent_id
        """, (player.player_id, player.display_name, player.agent_id))

        result = cur.fetchone()
        conn.commit()

        return Player(
            id=result[0],
            player_id=result[1],
            display_name=result[2],
            agent_id=result[3]
        )

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Player {player.player_id} already exists")
    except psycopg2.errors.ForeignKeyViolation:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Agent ID {player.agent_id} does not exist")
    finally:
        conn.close()


@app.put("/players/{player_id}")
def update_player(player_id: str, player: PlayerUpdate, user=Depends(basic_auth)):
    """Update a player"""
    conn = get_db()
    cur = conn.cursor()

    # Build dynamic update query
    updates = []
    params = []

    if player.player_id is not None:
        updates.append("player_id = %s")
        params.append(player.player_id)
    if player.display_name is not None:
        updates.append("display_name = %s")
        params.append(player.display_name)
    if player.agent_id is not None:
        updates.append("agent_id = %s")
        params.append(player.agent_id)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(player_id)

    try:
        cur.execute(f"""
            UPDATE players
            SET {', '.join(updates)}
            WHERE player_id = %s
            RETURNING id, player_id, display_name, agent_id
        """, params)

        result = cur.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail=f"Player {player_id} not found")

        conn.commit()

        return Player(
            id=result[0],
            player_id=result[1],
            display_name=result[2],
            agent_id=result[3]
        )

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Player ID {player.player_id} already exists")
    except psycopg2.errors.ForeignKeyViolation:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Agent ID {player.agent_id} does not exist")
    finally:
        conn.close()


@app.delete("/players/{player_id}")
def delete_player(player_id: str, user=Depends(basic_auth)):
    """Delete a player"""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM players WHERE player_id = %s", (player_id,))

    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found")

    conn.commit()
    conn.close()

    return {"success": True, "message": f"Player {player_id} deleted"}


# ============================================================================
# AGENT MANAGEMENT
# ============================================================================

@app.get("/agents")
def list_agents(user=Depends(basic_auth)):
    """List all agents"""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id, name FROM agents ORDER BY name")

    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()

    return rows


@app.post("/agents", response_model=Agent)
def create_agent(agent: AgentCreate, user=Depends(basic_auth)):
    """Create a new agent"""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO agents (name)
            VALUES (%s)
            RETURNING id, name
        """, (agent.name,))

        result = cur.fetchone()
        conn.commit()

        return Agent(id=result[0], name=result[1])

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Agent '{agent.name}' already exists")
    finally:
        conn.close()


@app.put("/agents/{agent_id}")
def update_agent(agent_id: int, agent: AgentUpdate, user=Depends(basic_auth)):
    """Update an agent"""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE agents
            SET name = %s
            WHERE id = %s
            RETURNING id, name
        """, (agent.name, agent_id))

        result = cur.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail=f"Agent ID {agent_id} not found")

        conn.commit()

        return Agent(id=result[0], name=result[1])

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Agent name '{agent.name}' already exists")
    finally:
        conn.close()


@app.delete("/agents/{agent_id}")
def delete_agent(agent_id: int, user=Depends(basic_auth)):
    """Delete an agent"""
    conn = get_db()
    cur = conn.cursor()

    # Check if agent has players
    cur.execute("SELECT COUNT(*) FROM players WHERE agent_id = %s", (agent_id,))
    player_count = cur.fetchone()[0]

    if player_count > 0:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete agent with {player_count} players. Reassign or delete players first."
        )

    cur.execute("DELETE FROM agents WHERE id = %s", (agent_id,))

    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Agent ID {agent_id} not found")

    conn.commit()
    conn.close()

    return {"success": True, "message": f"Agent ID {agent_id} deleted"}


# ============================================================================
# MANUAL BETSLIPS
# ============================================================================

@app.get("/slips/{week_id}")
def list_slips(week_id: str, user=Depends(basic_auth)):
    """List all manual slips for a week"""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT m.id, m.week_id, m.player_id, m.amount, m.note, m.created_at,
               p.display_name, a.name as agent_name
        FROM manual_slips m
        LEFT JOIN players p ON p.player_id = m.player_id
        LEFT JOIN agents a ON a.id = p.agent_id
        WHERE m.week_id = %s
        ORDER BY m.created_at DESC
    """, (week_id,))

    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()

    return rows


@app.post("/slips", response_model=ManualSlip)
def create_slip(slip: ManualSlipCreate, user=Depends(basic_auth)):
    """Add a manual betslip"""
    conn = get_db()
    cur = conn.cursor()

    try:
        # Ensure week exists
        cur.execute(
            "INSERT INTO weeks (week_id) VALUES (%s) ON CONFLICT (week_id) DO NOTHING",
            (slip.week_id,)
        )

        cur.execute("""
            INSERT INTO manual_slips (week_id, player_id, amount, note, created_at)
            VALUES (%s, %s, %s, %s, now())
            RETURNING id, week_id, player_id, amount, note, created_at
        """, (slip.week_id, slip.player_id, slip.amount, slip.note))

        result = cur.fetchone()
        conn.commit()

        return ManualSlip(
            id=result[0],
            week_id=result[1],
            player_id=result[2],
            amount=result[3],
            note=result[4],
            created_at=result[5]
        )

    except psycopg2.errors.ForeignKeyViolation:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Player {slip.player_id} or week {slip.week_id} does not exist")
    finally:
        conn.close()


@app.delete("/slips/{slip_id}")
def delete_slip(slip_id: int, user=Depends(basic_auth)):
    """Delete a manual betslip"""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM manual_slips WHERE id = %s", (slip_id,))

    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Slip ID {slip_id} not found")

    conn.commit()
    conn.close()

    return {"success": True, "message": f"Slip ID {slip_id} deleted"}

