import os
import psycopg2
import pandas as pd
from engine.translate import translate_admin_export
from dotenv import load_dotenv
load_dotenv()


conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

# load agents + players
pyragt = pd.read_csv("sample_data/players_and_agents.csv")

for agent in pyragt["Agent"].unique():
    cur.execute(
        "insert into agents (name) values (%s) on conflict do nothing",
        (agent,)
    )

conn.commit()

cur.execute("select id, name from agents")
agent_map = {name: id for id, name in cur.fetchall()}

for _, row in pyragt.iterrows():
    cur.execute("""
        insert into players (player_id, display_name, agent_id)
        values (%s, %s, %s)
        on conflict (player_id) do update
        set display_name = excluded.display_name,
            agent_id = excluded.agent_id
    """, (row.Player.lower(), row.Name, agent_map[row.Agent]))

conn.commit()

# load weekly data
weekly = translate_admin_export("sample_data/weekly_admin_export.xlsx")
week_id = weekly.week_id.iloc[0]

cur.execute(
    "insert into weeks (week_id) values (%s) on conflict do nothing",
    (week_id,)
)

for _, r in weekly.iterrows():
    cur.execute("""
        insert into weekly_raw (week_id, player_id, week_amount, pending)
        values (%s, %s, %s, %s)
        on conflict (week_id, player_id)
        do update set week_amount = excluded.week_amount
    """, (week_id, r.player_id, r.week_amount, r.pending))

conn.commit()
conn.close()

print("Sample data loaded for week", week_id)
