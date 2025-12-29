#!/usr/bin/env python3
"""
Test the compute logic to verify sign conventions
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.compute import compute_dashboard
import psycopg2

conn = psycopg2.connect(os.getenv('DATABASE_URL'))

# Get latest week
cur = conn.cursor()
cur.execute('SELECT week_id FROM weeks ORDER BY week_id DESC LIMIT 1')
week_id = cur.fetchone()[0]

print(f"=== TESTING COMPUTE LOGIC FOR WEEK {week_id} ===\n")

# Fetch rows like the dashboard does
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
""", (week_id,))
cols = [c[0] for c in cur.description]
rows = [dict(zip(cols, r)) for r in cur.fetchall()]

# Run compute
agents, book_total, avg_final_balance, transfers, split_info = compute_dashboard(rows, conn)

print("=== RAW DATABASE (Sample) ===")
cur.execute('''
    SELECT pi.player_id, pi.display_name, a.name as agent, wr.week_amount
    FROM weekly_raw wr
    JOIN player_instances pi ON pi.id = wr.player_instance_id
    JOIN agents a ON a.id = pi.agent_id
    WHERE wr.week_id = %s
    ORDER BY wr.week_amount DESC
    LIMIT 5
''', (week_id,))

for row in cur.fetchall():
    player_id, name, agent, week_amt = row
    agent_net = -week_amt  # What we compute
    action = "Request" if agent_net > 0 else "Pay"
    print(f"  DB: {name:<20} {agent:<6} week_amt={week_amt:>8.2f} → agent_net={agent_net:>8.2f} ({action})")

print("\n=== COMPUTED AGENT NETS ===")
for agent_name in sorted(agents.keys()):
    agent = agents[agent_name]
    print(f"{agent_name:>6}: net=${agent['net']:>10.2f}  final=${agent['final_balance']:>10.2f}  settlement=${agent['settlement']:>10.2f}")

print(f"\n=== BOOK TOTAL (should be close to 0) ===")
print(f"Book Total: ${book_total:.2f}")

print("\n=== TRANSFERS ===")
for t in transfers:
    print(f"{t['from']:>6} → {t['to']:>6}: ${t['amount']:>8.2f}")

print("\n=== PLAYER ACTIONS (Sample from Gabe) ===")
if 'Gabe' in agents:
    for p in agents['Gabe']['players'][:5]:
        print(f"  {p.get('display_name', 'Unknown'):<20} {p['action']:<8} ${p['abs_amount']:>8.2f}")

conn.close()
