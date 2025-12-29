#!/usr/bin/env python3
"""
Delete the most recent week's data to prepare for re-upload
"""
import os
import psycopg2

def main():
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    cur = conn.cursor()

    # Find latest week
    cur.execute('SELECT week_id FROM weeks ORDER BY week_id DESC LIMIT 1')
    latest_week = cur.fetchone()

    if not latest_week:
        print("No weeks found in database")
        conn.close()
        return

    week_id = latest_week[0]

    print(f"=== DELETING WEEK: {week_id} ===\n")

    # Count records to be deleted
    cur.execute('SELECT COUNT(*) FROM weekly_player_status WHERE week_id = %s', (week_id,))
    status_count = cur.fetchone()[0]

    cur.execute('SELECT COUNT(*) FROM manual_slips WHERE week_id = %s', (week_id,))
    slips_count = cur.fetchone()[0]

    cur.execute('SELECT COUNT(*) FROM weekly_raw WHERE week_id = %s', (week_id,))
    raw_count = cur.fetchone()[0]

    print(f"Records to delete:")
    print(f"  weekly_player_status: {status_count}")
    print(f"  manual_slips: {slips_count}")
    print(f"  weekly_raw: {raw_count}")
    print(f"  weeks: 1")
    print()

    # Show sample of what will be deleted
    print("Sample of weekly_raw data being deleted:")
    cur.execute('''
        SELECT pi.player_id, pi.display_name, a.name as agent, wr.week_amount
        FROM weekly_raw wr
        JOIN player_instances pi ON pi.id = wr.player_instance_id
        JOIN agents a ON a.id = pi.agent_id
        WHERE wr.week_id = %s
        ORDER BY a.name, pi.display_name
        LIMIT 10
    ''', (week_id,))

    for row in cur.fetchall():
        print(f"  {row[0]:<10} {row[1]:<30} {row[2]:<8} ${row[3]:>10.2f}")

    if raw_count > 10:
        print(f"  ... and {raw_count - 10} more")

    print()
    response = input(f"Delete week {week_id} and all related data? (yes/no): ").strip().lower()

    if response != 'yes':
        print("❌ Cancelled")
        conn.close()
        return

    # Delete in order of foreign key constraints
    print("\nDeleting...")

    cur.execute('DELETE FROM weekly_player_status WHERE week_id = %s', (week_id,))
    print(f"  Deleted {cur.rowcount} weekly_player_status records")

    cur.execute('DELETE FROM manual_slips WHERE week_id = %s', (week_id,))
    print(f"  Deleted {cur.rowcount} manual_slips records")

    cur.execute('DELETE FROM weekly_raw WHERE week_id = %s', (week_id,))
    print(f"  Deleted {cur.rowcount} weekly_raw records")

    cur.execute('DELETE FROM weeks WHERE week_id = %s', (week_id,))
    print(f"  Deleted {cur.rowcount} weeks records")

    conn.commit()
    print(f"\n✅ Week {week_id} deleted successfully!")
    print("\nYou can now re-upload the Excel file for this week.")

    conn.close()

if __name__ == '__main__':
    main()
