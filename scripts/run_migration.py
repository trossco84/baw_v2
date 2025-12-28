#!/usr/bin/env python3
"""Run the v2 schema migration"""

import os
import sys
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in environment")
    sys.exit(1)

# Read migration SQL
migration_file = Path(__file__).parent / "migrate_to_v2.sql"
if not migration_file.exists():
    print(f"ERROR: Migration file not found: {migration_file}")
    sys.exit(1)

print(f"Reading migration script: {migration_file.name}")
with open(migration_file, 'r') as f:
    migration_sql = f.read()

print(f"\n{'='*60}")
print("BAW v2 Schema Migration")
print(f"{'='*60}\n")

print("This will:")
print("  1. Create player_instances table")
print("  2. Migrate existing players to player instances")
print("  3. Add player_instance_id columns to related tables")
print("  4. Update all foreign keys and constraints")
print("  5. Create helper views and functions")
print(f"\n{'='*60}\n")

# Connect and run migration
try:
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False  # We want manual transaction control

    print("Running migration SQL...\n")

    with conn.cursor() as cur:
        # Execute the migration
        cur.execute(migration_sql)

    # Commit the transaction
    conn.commit()
    print(f"\n{'='*60}")
    print("✓ Migration completed successfully!")
    print(f"{'='*60}\n")

    # Show verification stats
    print("Verification:")
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM player_instances")
        instances_count = cur.fetchone()[0]
        print(f"  player_instances: {instances_count} rows")

        cur.execute("SELECT COUNT(*) FROM weekly_raw WHERE player_instance_id IS NULL")
        unmapped_weekly = cur.fetchone()[0]
        print(f"  unmapped weekly_raw: {unmapped_weekly} rows")

        cur.execute("SELECT COUNT(*) FROM manual_slips WHERE player_instance_id IS NULL")
        unmapped_slips = cur.fetchone()[0]
        print(f"  unmapped manual_slips: {unmapped_slips} rows")

    if unmapped_weekly > 0 or unmapped_slips > 0:
        print(f"\n⚠️  WARNING: Some records were not mapped!")
    else:
        print(f"\n✓ All records successfully mapped!")

    conn.close()

    print(f"\n{'='*60}")
    print("Next steps:")
    print("  1. Review migration results above")
    print("  2. Update models.py to use v2 schema")
    print("  3. Update API endpoints in main.py")
    print("  4. Test with historical import")
    print(f"{'='*60}\n")

except psycopg2.Error as e:
    print(f"\n✗ Migration FAILED!")
    print(f"Error: {e}")
    print("\nRolling back changes...")
    if conn:
        conn.rollback()
        conn.close()
    print("Rollback complete. Database unchanged.")
    sys.exit(1)
except Exception as e:
    print(f"\n✗ Unexpected error: {e}")
    if conn:
        conn.rollback()
        conn.close()
    sys.exit(1)
