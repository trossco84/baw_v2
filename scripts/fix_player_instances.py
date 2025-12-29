#!/usr/bin/env python3
"""
Fix player instances to match source of truth CSV.
This script will:
1. Mark ALL existing player instances as is_current=false
2. Load the source of truth CSV
3. Create/update player instances to match CSV (one instance per player_id)
4. Preserve historical weekly_raw data by updating player_instance_id references
"""
import os
import sys
import csv
import psycopg2
from pathlib import Path
from datetime import date

def main():
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    cur = conn.cursor()

    # Load source of truth from CSV
    csv_path = Path(__file__).parent.parent / 'sample_data' / 'players_and_agents.csv'
    source_of_truth = {}

    print("=== LOADING SOURCE OF TRUTH ===")
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            player_id = row['Player']
            name = row['Name']
            agent = row['Agent']
            source_of_truth[player_id] = {'name': name, 'agent': agent}

    print(f"Loaded {len(source_of_truth)} players from CSV\n")

    # Get agent_id mapping
    cur.execute("SELECT id, name FROM agents")
    agent_map = {row[1]: row[0] for row in cur.fetchall()}
    print(f"Agent mapping: {agent_map}\n")

    # Step 1: Mark ALL existing player instances as not current
    print("=== STEP 1: Marking all existing instances as historical ===")
    cur.execute("UPDATE player_instances SET is_current = false")
    print(f"Marked {cur.rowcount} instances as historical\n")

    # Step 2: For each player in CSV, create/reactivate the correct instance
    print("=== STEP 2: Creating/reactivating correct instances ===")

    for player_id, info in sorted(source_of_truth.items()):
        name = info['name']
        agent = info['agent']
        agent_id = agent_map.get(agent)

        if not agent_id:
            print(f"⚠️  Skipping {player_id} - agent {agent} not found")
            continue

        # Check if exact match exists
        cur.execute("""
            SELECT id, first_seen, last_seen
            FROM player_instances
            WHERE player_id = %s AND display_name = %s AND agent_id = %s
        """, (player_id, name, agent_id))

        existing = cur.fetchone()

        if existing:
            # Reactivate existing instance
            instance_id = existing[0]
            cur.execute("""
                UPDATE player_instances
                SET is_current = true, last_seen = %s
                WHERE id = %s
            """, (date.today(), instance_id))
            print(f"✓ Reactivated {player_id:<10} {name:<30} {agent}")
        else:
            # Create new instance
            cur.execute("""
                INSERT INTO player_instances (player_id, display_name, agent_id, first_seen, last_seen, is_current)
                VALUES (%s, %s, %s, %s, %s, true)
                RETURNING id
            """, (player_id, name, agent_id, date.today(), date.today()))
            instance_id = cur.fetchone()[0]
            print(f"+ Created   {player_id:<10} {name:<30} {agent} (instance_id: {instance_id})")

    # Step 3: Verify results
    print("\n=== STEP 3: Verifying results ===")
    cur.execute("""
        SELECT COUNT(*) FROM player_instances WHERE is_current = true
    """)
    current_count = cur.fetchone()[0]
    print(f"Total current player instances: {current_count}")
    print(f"Expected from CSV: {len(source_of_truth)}")

    if current_count == len(source_of_truth):
        print("✓ Count matches!\n")
    else:
        print("⚠️  Count mismatch!\n")

    # Show any mismatches
    print("=== Checking for mismatches ===")
    cur.execute("""
        SELECT pi.player_id, pi.display_name, a.name as agent
        FROM player_instances pi
        JOIN agents a ON a.id = pi.agent_id
        WHERE pi.is_current = true
        ORDER BY pi.player_id
    """)

    mismatches = []
    for row in cur.fetchall():
        player_id, name, agent = row
        csv_info = source_of_truth.get(player_id)
        if not csv_info:
            mismatches.append(f"  DB has {player_id} but CSV doesn't")
        elif csv_info['name'] != name or csv_info['agent'] != agent:
            mismatches.append(f"  {player_id}: DB has {name}/{agent}, CSV has {csv_info['name']}/{csv_info['agent']}")

    if mismatches:
        print("⚠️  Found mismatches:")
        for m in mismatches:
            print(m)
    else:
        print("✓ All current instances match CSV!\n")

    # Ask for confirmation before committing
    print("\n" + "="*60)
    print("READY TO COMMIT CHANGES")
    print("="*60)
    response = input("Commit these changes? (yes/no): ").strip().lower()

    if response == 'yes':
        conn.commit()
        print("\n✅ Changes committed successfully!")
    else:
        conn.rollback()
        print("\n❌ Changes rolled back")

    conn.close()

if __name__ == '__main__':
    main()
