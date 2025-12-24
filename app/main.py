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

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, agent: str | None = Query(default=None), user=Depends(basic_auth)):
    conn = get_db()
    cur = conn.cursor()

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
            order by agent, p.player_id
    """)
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
            "agents": agents,
            "agent_names": agent_names,
            "selected_agent": selected_agent,
            "book_total": book_total,
            "final_balance": final_balance,
            "transfers": transfers,
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

