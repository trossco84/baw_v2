"""
Import historical weekly data from CSV files in weekly_outputs directory.

Expected CSV format:
Agent,Player,Name,Action,Amount

Where:
- Agent: Agent name (Trev, Gabe, Orso, etc.)
- Player: Player ID (pyr###)
- Name: Display name for the player
- Action: "Pay" or "Request"
- Amount: Dollar amount

The script will:
1. Create agents if they don't exist
2. Create players if they don't exist
3. Convert Action/Amount to week_amount (house perspective)
   - "Request" (player owes) = positive week_amount
   - "Pay" (house owes player) = negative week_amount
4. Import all weekly_raw data
"""

import os
import sys
import csv
import psycopg2
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

def get_db():
    """Get database connection"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable not set")
    return psycopg2.connect(db_url)


def ensure_agent(cur, agent_name: str) -> int:
    """Ensure agent exists, create if not. Returns agent_id."""
    # Check if agent exists
    cur.execute("SELECT id FROM agents WHERE name = %s", (agent_name,))
    result = cur.fetchone()

    if result:
        return result[0]

    # Create agent
    cur.execute(
        "INSERT INTO agents (name) VALUES (%s) RETURNING id",
        (agent_name,)
    )
    agent_id = cur.fetchone()[0]
    print(f"  Created agent: {agent_name} (ID: {agent_id})")
    return agent_id


def ensure_player(cur, player_id: str, display_name: str, agent_id: int):
    """Ensure player exists, create if not."""
    player_id_lower = player_id.lower()

    # Check if player exists
    cur.execute("SELECT id FROM players WHERE player_id = %s", (player_id_lower,))
    result = cur.fetchone()

    if result:
        # Update display name if provided and different
        if display_name:
            cur.execute(
                "UPDATE players SET display_name = %s, agent_id = %s WHERE player_id = %s",
                (display_name, agent_id, player_id_lower)
            )
        return

    # Create player
    cur.execute(
        "INSERT INTO players (player_id, display_name, agent_id) VALUES (%s, %s, %s)",
        (player_id_lower, display_name, agent_id)
    )
    print(f"  Created player: {player_id_lower} - {display_name} (Agent: {agent_id})")


def action_to_week_amount(action: str, amount: float) -> float:
    """
    Convert Action/Amount to week_amount from house perspective.

    - "Request" means player owes house -> positive week_amount
    - "Pay" means house owes player -> negative week_amount
    """
    if action == "Request":
        return amount
    elif action == "Pay":
        return -amount
    else:
        raise ValueError(f"Unknown action: {action}")


def import_csv_file(csv_path: Path, conn, dry_run: bool = False):
    """Import a single CSV file."""
    # Extract week_id from filename (YYYY-MM-DD.csv)
    week_id = csv_path.stem  # Gets filename without extension

    try:
        datetime.strptime(week_id, '%Y-%m-%d')
    except ValueError:
        print(f"  Skipping {csv_path.name} - invalid date format")
        return 0

    cur = conn.cursor()

    # Read CSV
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print(f"  Skipping {csv_path.name} - empty file")
        return 0

    # Ensure week exists
    if not dry_run:
        cur.execute(
            "INSERT INTO weeks (week_id) VALUES (%s) ON CONFLICT (week_id) DO NOTHING",
            (week_id,)
        )

    # Process each row
    players_imported = 0
    for row in rows:
        agent_name = row['Agent']
        player_id = row['Player']
        display_name = row['Name']
        action = row['Action']
        amount = float(row['Amount'])

        # Ensure agent exists
        agent_id = ensure_agent(cur, agent_name)

        # Ensure player exists
        ensure_player(cur, player_id, display_name, agent_id)

        # Calculate week_amount
        week_amount = action_to_week_amount(action, amount)

        # Insert weekly data
        if not dry_run:
            cur.execute("""
                INSERT INTO weekly_raw (week_id, player_id, week_amount, pending, scraped_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (week_id, player_id)
                DO UPDATE SET
                    week_amount = EXCLUDED.week_amount,
                    pending = EXCLUDED.pending,
                    scraped_at = now()
            """, (week_id, player_id.lower(), week_amount, 0))

        players_imported += 1

    if not dry_run:
        conn.commit()

    return players_imported


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Import historical weekly data from CSV files')
    parser.add_argument(
        'directory',
        help='Directory containing CSV files (default: weekly_outputs)',
        nargs='?',
        default='/Users/trevorross/Desktop/My Projects/bettingatwork/weekly_outputs'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview what would be imported without making changes'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of files to import (for testing)'
    )
    parser.add_argument(
        '--start-date',
        help='Only import files from this date onwards (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--end-date',
        help='Only import files up to this date (YYYY-MM-DD)'
    )

    args = parser.parse_args()

    csv_dir = Path(args.directory)
    if not csv_dir.exists():
        print(f"Error: Directory not found: {csv_dir}")
        sys.exit(1)

    # Get all CSV files
    csv_files = sorted(csv_dir.glob('*.csv'))

    # Filter by date range if specified
    if args.start_date:
        csv_files = [f for f in csv_files if f.stem >= args.start_date]
    if args.end_date:
        csv_files = [f for f in csv_files if f.stem <= args.end_date]

    # Limit number of files if specified
    if args.limit:
        csv_files = csv_files[:args.limit]

    print(f"\nFound {len(csv_files)} CSV files to import")

    if args.dry_run:
        print("\n*** DRY RUN MODE - No changes will be made ***\n")

    # Connect to database
    conn = get_db()

    # Import each file
    total_players = 0
    successful_imports = 0

    for csv_file in csv_files:
        print(f"\nProcessing: {csv_file.name}")
        try:
            count = import_csv_file(csv_file, conn, dry_run=args.dry_run)
            total_players += count
            successful_imports += 1
            print(f"  ✓ Imported {count} player records")
        except Exception as e:
            print(f"  ✗ Error: {e}")
            if not args.dry_run:
                conn.rollback()

    conn.close()

    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Files processed: {successful_imports}/{len(csv_files)}")
    print(f"  Total player records: {total_players}")

    if args.dry_run:
        print(f"\n*** This was a dry run. Run without --dry-run to import data. ***")
    else:
        print(f"\n✓ Import complete!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
