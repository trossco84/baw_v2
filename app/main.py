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

    # Aggregate weekly_raw + manual_slips for CURRENT WEEK ONLY
    # Updated for v2 schema: use player_instances instead of players
    # Filter out Dro from calculations (only show Gabe, Trev, Orso)
    cur.execute("""
            select
            w.week_id,
            pi.player_id,
            pi.display_name,
            a.name as agent,
            coalesce(wr.week_amount, 0) + coalesce(slips.total_adjustment, 0) as week_amount,
            coalesce(s.engaged, false) as engaged,
            coalesce(s.paid, false) as paid
            from weekly_raw wr
            join player_instances pi on pi.id = wr.player_instance_id
            join agents a on a.id = pi.agent_id
            join weeks w on w.week_id = wr.week_id
            left join weekly_player_status s
                on s.week_id = wr.week_id and s.player_instance_id = wr.player_instance_id
            left join (
                select week_id, player_instance_id, sum(amount) as total_adjustment
                from manual_slips
                group by week_id, player_instance_id
            ) slips on slips.week_id = wr.week_id and slips.player_instance_id = wr.player_instance_id
            where w.week_id = %s
              and a.name != 'Dro'
            order by a.name, pi.player_id
    """, (current_week,) if current_week else (None,))
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    # Also fetch manual slips for display
    # Updated for v2 schema: use player_instances
    slips = []
    if current_week:
        cur.execute("""
            SELECT m.id, m.week_id, m.player_instance_id, pi.player_id, m.amount, m.note, m.created_at,
                   pi.display_name, a.name as agent_name
            FROM manual_slips m
            LEFT JOIN player_instances pi ON pi.id = m.player_instance_id
            LEFT JOIN agents a ON a.id = pi.agent_id
            WHERE m.week_id = %s
            ORDER BY m.created_at DESC
        """, (current_week,))
        slip_cols = [c[0] for c in cur.description]
        slips = [dict(zip(slip_cols, r)) for r in cur.fetchall()]

    # Get all current players for betslip form
    # Updated for v2 schema: only show current players
    cur.execute("""
        SELECT pi.player_id, pi.display_name, a.name as agent_name
        FROM player_instances pi
        LEFT JOIN agents a ON a.id = pi.agent_id
        WHERE pi.is_current = true
        ORDER BY a.name, pi.player_id
    """)
    player_cols = [c[0] for c in cur.description]
    all_players = [dict(zip(player_cols, r)) for r in cur.fetchall()]

    # Compute dashboard with connection (for Kevin bubble logic)
    agents, book_total, final_balance, transfers, split_info = compute_dashboard(rows, conn)

    conn.close()

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
            "split_info": split_info,
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

    # v2 schema: Get player_instance_id for current player
    cur.execute("""
        SELECT id FROM player_instances
        WHERE player_id = %s AND is_current = true
    """, (player_id,))
    result = cur.fetchone()
    if not result:
        conn.close()
        return {"ok": False, "error": f"Player {player_id} not found"}

    player_instance_id = result[0]

    cur.execute("""
      insert into weekly_player_status (week_id, player_instance_id, engaged, paid)
      values (%s, %s, false, false)
      on conflict (week_id, player_instance_id) do nothing
    """, (week_id, player_instance_id))

    cur.execute(f"""
      update weekly_player_status
      set {field} = %s, updated_at = now()
      where week_id = %s and player_instance_id = %s
    """, (val, week_id, player_instance_id))

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
        # v2 schema: Use get_or_create_player_instance function
        # Note: Excel upload needs agent_id - assuming it's in the dataframe or needs to be looked up
        players_imported = 0
        for _, row in df.iterrows():
            player_id = row['player_id']

            # TODO: Get display_name and agent_id from player lookup or Excel
            # For now, get from existing player_instances or use defaults
            cur.execute("""
                SELECT id, display_name, agent_id
                FROM player_instances
                WHERE player_id = %s AND is_current = true
                LIMIT 1
            """, (player_id,))

            existing = cur.fetchone()
            if existing:
                player_instance_id = existing[0]
                display_name = existing[1]
                agent_id = existing[2]
            else:
                # Player doesn't exist - need to create instance
                # For now, use a default agent (Agent ID 1) and player_id as display_name
                # This should be improved to parse agent from Excel or use proper lookup
                display_name = player_id
                agent_id = 1  # Default agent - should be determined from Excel data

                cur.execute("""
                    SELECT get_or_create_player_instance(%s, %s, %s, %s)
                """, (player_id, display_name, agent_id, week_id))
                player_instance_id = cur.fetchone()[0]

            # Insert weekly_raw data with player_instance_id
            cur.execute("""
                INSERT INTO weekly_raw (week_id, player_instance_id, week_amount, pending, scraped_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (week_id, player_instance_id)
                DO UPDATE SET
                    week_amount = EXCLUDED.week_amount,
                    pending = EXCLUDED.pending,
                    scraped_at = now()
            """, (row['week_id'], player_instance_id, row['week_amount'], row['pending']))
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
    """List all current players (v2 schema: only is_current=true)"""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT pi.id, pi.player_id, pi.display_name, pi.agent_id, a.name as agent_name
        FROM player_instances pi
        LEFT JOIN agents a ON a.id = pi.agent_id
        WHERE pi.is_current = true
        ORDER BY pi.player_id
    """)

    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()

    return rows


@app.post("/players", response_model=Player)
def create_player(player: PlayerCreate, user=Depends(basic_auth)):
    """Create a new player (v2 schema: creates player_instance)"""
    conn = get_db()
    cur = conn.cursor()

    try:
        # Use get_or_create_player_instance function
        from datetime import date
        cur.execute("""
            SELECT get_or_create_player_instance(%s, %s, %s, %s)
        """, (player.player_id, player.display_name, player.agent_id, date.today()))

        player_instance_id = cur.fetchone()[0]

        # Fetch the created instance
        cur.execute("""
            SELECT id, player_id, display_name, agent_id
            FROM player_instances
            WHERE id = %s
        """, (player_instance_id,))

        result = cur.fetchone()
        conn.commit()

        return Player(
            id=result[0],
            player_id=result[1],
            display_name=result[2],
            agent_id=result[3]
        )

    except psycopg2.errors.ForeignKeyViolation:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Agent ID {player.agent_id} does not exist")
    finally:
        conn.close()


@app.put("/players/{player_id}")
def update_player(player_id: str, player: PlayerUpdate, user=Depends(basic_auth)):
    """Update a player (v2 schema: updates current player_instance)"""
    conn = get_db()
    cur = conn.cursor()

    # Build dynamic update query
    updates = []
    params = []

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
            UPDATE player_instances
            SET {', '.join(updates)}
            WHERE player_id = %s AND is_current = true
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

    except psycopg2.errors.ForeignKeyViolation:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Agent ID {player.agent_id} does not exist")
    finally:
        conn.close()


@app.delete("/players/{player_id}")
def delete_player(player_id: str, user=Depends(basic_auth)):
    """Delete a player (v2 schema: marks current player_instance as not current)"""
    conn = get_db()
    cur = conn.cursor()

    # Mark as not current instead of deleting (preserves history)
    from datetime import date
    cur.execute("""
        UPDATE player_instances
        SET is_current = false, last_seen = %s
        WHERE player_id = %s AND is_current = true
    """, (date.today(), player_id))

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
    """Delete an agent (v2 schema: checks current player_instances)"""
    conn = get_db()
    cur = conn.cursor()

    # Check if agent has current players
    cur.execute("""
        SELECT COUNT(*) FROM player_instances
        WHERE agent_id = %s AND is_current = true
    """, (agent_id,))
    player_count = cur.fetchone()[0]

    if player_count > 0:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete agent with {player_count} current players. Reassign or delete players first."
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
    """List all manual slips for a week (v2 schema: uses player_instances)"""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT m.id, m.week_id, m.player_instance_id, pi.player_id, m.amount, m.note, m.created_at,
               pi.display_name, a.name as agent_name
        FROM manual_slips m
        LEFT JOIN player_instances pi ON pi.id = m.player_instance_id
        LEFT JOIN agents a ON a.id = pi.agent_id
        WHERE m.week_id = %s
        ORDER BY m.created_at DESC
    """, (week_id,))

    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()

    return rows


@app.post("/slips", response_model=ManualSlip)
def create_slip(slip: ManualSlipCreate, user=Depends(basic_auth)):
    """Add a manual betslip (v2 schema: converts player_id to player_instance_id)"""
    conn = get_db()
    cur = conn.cursor()

    try:
        # Ensure week exists
        cur.execute(
            "INSERT INTO weeks (week_id) VALUES (%s) ON CONFLICT (week_id) DO NOTHING",
            (slip.week_id,)
        )

        # Get player_instance_id for current player
        cur.execute("""
            SELECT id FROM player_instances
            WHERE player_id = %s AND is_current = true
        """, (slip.player_id,))

        player_result = cur.fetchone()
        if not player_result:
            raise HTTPException(status_code=404, detail=f"Player {slip.player_id} not found")

        player_instance_id = player_result[0]

        cur.execute("""
            INSERT INTO manual_slips (week_id, player_instance_id, amount, note, created_at)
            VALUES (%s, %s, %s, %s, now())
            RETURNING id, week_id, player_instance_id, amount, note, created_at
        """, (slip.week_id, player_instance_id, slip.amount, slip.note))

        result = cur.fetchone()
        conn.commit()

        return ManualSlip(
            id=result[0],
            week_id=result[1],
            player_instance_id=result[2],
            player_id=slip.player_id,
            amount=result[3],
            note=result[4],
            created_at=result[5]
        )

    except psycopg2.errors.ForeignKeyViolation:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Week {slip.week_id} does not exist")
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

