import os
import psycopg2
from fastapi import FastAPI, Request, Depends, Query, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from app.auth import basic_auth
from engine.compute import compute_dashboard

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

def get_db():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def get_active_week_id(conn) -> str:
    cur = conn.cursor()
    cur.execute("select value from app_config where key='active_week_id'")
    row = cur.fetchone()
    if row and row[0]:
        return row[0]
    cur.execute("select max(week_id)::text from weeks")
    row = cur.fetchone()
    return row[0]



@app.get("/", response_class=HTMLResponse)
def live_view(request: Request, agent: str | None = Query(default=None), user=Depends(basic_auth)):
    conn = get_db()
    cur = conn.cursor()

    active_week_id = get_active_week_id(conn)

    # NOTE: no weekly_player_status join (no engaged/paid)
    cur.execute("""
        select
          w.week_id,
          p.player_id,
          p.display_name,
          a.name as agent,
          wr.week_amount
        from weekly_raw wr
        join players p on p.player_id = wr.player_id
        join agents a on a.id = p.agent_id
        join weeks w on w.week_id = wr.week_id
        where w.week_id = %s
        order by agent, p.player_id
    """, (active_week_id,))
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()

    agents, book_total, final_balance, transfers = compute_dashboard(rows)

    agent_names = sorted(list(agents.keys()))
    selected_agent = agent if agent in agents else (agent_names[0] if agent_names else None)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "mode": "live",
            "week_id": active_week_id,
            "agents": agents,
            "agent_names": agent_names,
            "selected_agent": selected_agent,
            "book_total": book_total,
            "final_balance": final_balance,
            # live mode: don’t show settlement even if computed
            "transfers": [],
        },
    )

@app.get("/close", response_class=HTMLResponse)
def week_close_view(
    request: Request,
    week_id: str | None = Query(default=None),
    agent: str | None = Query(default=None),
    user=Depends(basic_auth),
):
    conn = get_db()
    cur = conn.cursor()

    # default: most recent available week (closed)
    if not week_id:
        cur.execute("select max(week_id)::text from weeks")
        week_id = cur.fetchone()[0]

    cur.execute("""
        select
          w.week_id,
          p.player_id,
          p.display_name,
          a.name as agent,
          wr.week_amount,
          coalesce(s.engaged, false) as engaged,
          coalesce(s.paid, false) as paid
        from weekly_raw wr
        join players p on p.player_id = wr.player_id
        join agents a on a.id = p.agent_id
        join weeks w on w.week_id = wr.week_id
        left join weekly_player_status s
          on s.week_id = wr.week_id and s.player_id = wr.player_id
        where w.week_id = %s
        order by agent, p.player_id
    """, (week_id,))
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()

    agents, book_total, final_balance, transfers = compute_dashboard(rows)

    agent_names = sorted(list(agents.keys()))
    selected_agent = agent if agent in agents else (agent_names[0] if agent_names else None)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "mode": "close",
            "week_id": week_id,
            "agents": agents,
            "agent_names": agent_names,
            "selected_agent": selected_agent,
            "book_total": book_total,
            "final_balance": final_balance,
            "transfers": transfers,
        },
    )

@app.get("/agents", response_class=HTMLResponse)
def agents_page(request: Request, user=Depends(basic_auth)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
      select a.id, a.name,
             p.player_id, p.display_name, p.active
      from agents a
      left join players p on p.agent_id = a.id
      order by a.name, p.player_id
    """)
    rows = cur.fetchall()
    conn.close()

    # reshape simply for template
    agents = {}
    for a_id, a_name, pid, dname, active in rows:
        agents.setdefault(a_name, {"id": a_id, "players": []})
        if pid:
            agents[a_name]["players"].append({"player_id": pid, "display_name": dname, "active": active})

    return templates.TemplateResponse("agents.html", {"request": request, "agents": agents})


@app.post("/players/update", response_class=JSONResponse)
def update_player(
    player_id: str = Form(...),
    display_name: str = Form(""),
    active: str = Form("true"),
    user=Depends(basic_auth),
):
    is_active = True if active == "true" else False
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
      update players
      set display_name = %s,
          active = %s
      where player_id = %s
    """, (display_name.strip(), is_active, player_id))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/player/{player_id}", response_class=HTMLResponse)
def player_page(player_id: str, request: Request, user=Depends(basic_auth)):
    conn = get_db()
    cur = conn.cursor()

    # basic identity + agent
    cur.execute("""
      select p.player_id, p.display_name, a.name
      from players p join agents a on a.id = p.agent_id
      where p.player_id = %s
    """, (player_id,))
    base = cur.fetchone()
    if not base:
        conn.close()
        return HTMLResponse("Not found", status_code=404)

    # last 52 weeks (or all available)
    cur.execute("""
      select wr.week_id::text, wr.week_amount
      from weekly_raw wr
      where wr.player_id = %s
      order by wr.week_id desc
      limit 52
    """, (player_id,))
    history = [{"week_id": r[0], "week_amount": float(r[1])} for r in cur.fetchall()]

    conn.close()

    return templates.TemplateResponse(
        "player.html",
        {
            "request": request,
            "player": {"player_id": base[0], "display_name": base[1], "agent": base[2]},
            "history": history,
        },
    )

@app.get("/betslips", response_class=JSONResponse)
def get_betslips(
    week_id: str | None = Query(default=None),
    user=Depends(basic_auth),
):
    conn = get_db()
    cur = conn.cursor()

    if not week_id:
        week_id = get_active_week_id(conn)

    cur.execute("""
      select id, week_id::text, direction, note, created_at
      from betslips
      where week_id = %s
      order by created_at desc
    """, (week_id,))

    rows = cur.fetchall()
    conn.close()

    slips = [
        {
            "id": r[0],
            "week_id": r[1],
            "direction": r[2],
            "note": r[3],
            "created_at": r[4].isoformat(),
        }
        for r in rows
    ]

    return {"ok": True, "week_id": week_id, "slips": slips}

@app.post("/betslips/add", response_class=JSONResponse)
def add_betslip(
    week_id: str = Form(...),
    direction: str = Form(...),  # past | upcoming
    note: str = Form(...),
    user=Depends(basic_auth),
):
    if direction not in ("past", "upcoming"):
        return {"ok": False, "error": "Invalid direction"}

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
      insert into betslips (week_id, direction, note)
      values (%s, %s, %s)
      returning id
    """, (week_id, direction, note.strip()))

    slip_id = cur.fetchone()[0]
    conn.commit()
    conn.close()

    return {"ok": True, "id": slip_id}


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

