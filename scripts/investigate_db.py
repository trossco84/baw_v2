#!/usr/bin/env python3
"""
Investigate database state and compare with source of truth CSV
"""
import os
import sys
import csv
import psycopg2
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def main():
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    cur = conn.cursor()

    # Load source of truth from CSV
    csv_path = Path(__file__).parent.parent / 'sample_data' / 'players_and_agents.csv'
    source_of_truth = {}

    print("=== SOURCE OF TRUTH (from CSV) ===")
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            player_id = row['Player']
            name = row['Name']
            agent = row['Agent']
            source_of_truth[player_id] = {'name': name, 'agent': agent}
            print(f"{player_id:<10} {name:<30} {agent}")

    print(f"\n=== TOTAL PLAYERS IN CSV: {len(source_of_truth)} ===\n")

    # Check most recent weeks
    print("=== MOST RECENT WEEKS IN DB ===")
    cur.execute('SELECT week_id FROM weeks ORDER BY week_id DESC LIMIT 5')
    weeks = cur.fetchall()
    for row in weeks:
        print(f"  {row[0]}")

    most_recent_week = weeks[0][0] if weeks else None
    print(f"\nMost recent week: {most_recent_week}\n")

    # Check all player instances in DB
    print("=== ALL PLAYER INSTANCES IN DB ===")
    cur.execute('''
        SELECT pi.id, pi.player_id, pi.display_name, a.name as agent, pi.is_current, pi.first_seen, pi.last_seen
        FROM player_instances pi
        JOIN agents a ON a.id = pi.agent_id
        ORDER BY pi.player_id, pi.id
    ''')

    db_instances = cur.fetchall()
    print(f"Total player instances in DB: {len(db_instances)}\n")

    # Group by player_id to see duplicates
    by_player_id = {}
    for row in db_instances:
        instance_id, player_id, display_name, agent, is_current, first_seen, last_seen = row
        if player_id not in by_player_id:
            by_player_id[player_id] = []
        by_player_id[player_id].append({
            'instance_id': instance_id,
            'name': display_name,
            'agent': agent,
            'is_current': is_current,
            'first_seen': first_seen,
            'last_seen': last_seen
        })

    # Show all instances
    for player_id in sorted(by_player_id.keys()):
        instances = by_player_id[player_id]
        csv_info = source_of_truth.get(player_id, {'name': 'NOT IN CSV', 'agent': 'N/A'})

        if len(instances) > 1:
            print(f"\n🔴 {player_id} - MULTIPLE INSTANCES (CSV: {csv_info['name']} / {csv_info['agent']})")
        else:
            instance = instances[0]
            if instance['name'] != csv_info['name'] or instance['agent'] != csv_info['agent']:
                print(f"\n⚠️  {player_id} - MISMATCH")
                print(f"   CSV:  {csv_info['name']:<30} {csv_info['agent']}")
                print(f"   DB:   {instance['name']:<30} {instance['agent']} (current={instance['is_current']})")
            else:
                # Match - only show if verbose
                pass

        if len(instances) > 1:
            for inst in instances:
                current_flag = '✓ CURRENT' if inst['is_current'] else '✗ old'
                print(f"   [{inst['instance_id']}] {inst['name']:<30} {inst['agent']:<8} {current_flag} ({inst['first_seen']} to {inst['last_seen']})")

    # Check for players in CSV but not in DB
    print("\n=== PLAYERS IN CSV BUT NOT IN DB ===")
    for player_id in source_of_truth:
        if player_id not in by_player_id:
            csv_info = source_of_truth[player_id]
            print(f"{player_id:<10} {csv_info['name']:<30} {csv_info['agent']}")

    # Check weekly_raw for most recent week
    if most_recent_week:
        print(f"\n=== WEEKLY_RAW DATA FOR {most_recent_week} ===")
        cur.execute('''
            SELECT pi.player_id, pi.display_name, a.name as agent, wr.week_amount
            FROM weekly_raw wr
            JOIN player_instances pi ON pi.id = wr.player_instance_id
            JOIN agents a ON a.id = pi.agent_id
            WHERE wr.week_id = %s
            ORDER BY a.name, pi.display_name
        ''', (most_recent_week,))

        for row in cur.fetchall():
            player_id, name, agent, amount = row
            csv_info = source_of_truth.get(player_id, {'name': 'NOT IN CSV', 'agent': 'N/A'})
            match = '✓' if csv_info['name'] == name and csv_info['agent'] == agent else '✗ MISMATCH'
            print(f"{match} {player_id:<10} {name:<30} {agent:<8} ${amount:>10.2f}")

    conn.close()

if __name__ == '__main__':
    main()
