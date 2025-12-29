#!/usr/bin/env python3
import os
import psycopg2

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

# Check what week we have
cur.execute('SELECT week_id FROM weeks ORDER BY week_id DESC LIMIT 1')
week_id = cur.fetchone()[0]
print(f'Latest week: {week_id}\n')

# Get a few sample players with their raw DB values
print('=== RAW DATABASE VALUES (2025-12-08) ===')
cur.execute('''
    SELECT pi.player_id, pi.display_name, a.name as agent, wr.week_amount
    FROM weekly_raw wr
    JOIN player_instances pi ON pi.id = wr.player_instance_id
    JOIN agents a ON a.id = pi.agent_id
    WHERE wr.week_id = %s
    ORDER BY wr.week_amount DESC
    LIMIT 5
''', (week_id,))

print('Top positive amounts (players won):')
for row in cur.fetchall():
    pid, name, agent, amt = row
    print(f'  {name:<25} {agent:<6} ${amt:>8.2f} (player won, agent should PAY)')

cur.execute('''
    SELECT pi.player_id, pi.display_name, a.name as agent, wr.week_amount
    FROM weekly_raw wr
    JOIN player_instances pi ON pi.id = wr.player_instance_id
    JOIN agents a ON a.id = pi.agent_id
    WHERE wr.week_id = %s
    ORDER BY wr.week_amount ASC
    LIMIT 5
''', (week_id,))

print('\nTop negative amounts (players lost):')
for row in cur.fetchall():
    pid, name, agent, amt = row
    print(f'  {name:<25} {agent:<6} ${amt:>8.2f} (player lost, agent should REQUEST)')

# Calculate what the totals SHOULD be
print('\n=== AGENT TOTALS (what they SHOULD be) ===')
cur.execute('''
    SELECT a.name as agent,
           SUM(wr.week_amount) as player_perspective,
           SUM(-wr.week_amount) as agent_perspective
    FROM weekly_raw wr
    JOIN player_instances pi ON pi.id = wr.player_instance_id
    JOIN agents a ON a.id = pi.agent_id
    WHERE wr.week_id = %s AND a.name != 'Dro'
    GROUP BY a.name
    ORDER BY a.name
''', (week_id,))

for row in cur.fetchall():
    agent, player_persp, agent_persp = row
    print(f'{agent}: player_total=${player_persp:>10.2f}  →  agent_net=${agent_persp:>10.2f}')

print('\n(agent_net positive = agent made money = good)')
print('(agent_net negative = agent lost money = bad)')

conn.close()
