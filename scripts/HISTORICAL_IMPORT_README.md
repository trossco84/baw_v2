# Historical Data Import Guide

## Overview

This guide explains how to import historical weekly data from the CSV files in `/Users/trevorross/Desktop/My Projects/bettingatwork/weekly_outputs`.

## CSV Format

The historical CSV files have the following structure:

```csv
Agent,Player,Name,Action,Amount
Trev,pyr103,Jalen,Request,47.0
Trev,pyr125,Casey Grieves,Pay,60.0
```

- **Agent**: Agent name (Trev, Gabe, Orso, Dro)
- **Player**: Player ID (pyr###)
- **Name**: Display name for the player
- **Action**: "Pay" (house owes player) or "Request" (player owes house)
- **Amount**: Dollar amount

## How It Works

The import script (`import_historical.py`) will:

1. **Create missing agents** - Automatically creates any agent that doesn't exist in the database
2. **Create missing players** - Automatically creates players and associates them with their agent
3. **Convert amounts** - Converts Action/Amount to `week_amount` from house perspective:
   - "Request" (player owes) → positive `week_amount`
   - "Pay" (house owes player) → negative `week_amount`
4. **Import weekly data** - Inserts or updates `weekly_raw` records for each week

## Running the Import

### Prerequisites

Make sure you have:
- Database connection configured (DATABASE_URL environment variable)
- Python dependencies installed (`pip install -r requirements.txt`)

### Dry Run (Recommended First)

**Always run a dry run first** to preview what will be imported:

```bash
# Preview first 5 files
python3 scripts/import_historical.py --dry-run --limit 5

# Preview all files
python3 scripts/import_historical.py --dry-run

# Preview specific date range
python3 scripts/import_historical.py --dry-run --start-date 2024-01-01 --end-date 2024-12-31
```

### Actual Import

Once you're satisfied with the dry run results:

```bash
# Import first 10 files (for testing)
python3 scripts/import_historical.py --limit 10

# Import all files
python3 scripts/import_historical.py

# Import specific date range
python3 scripts/import_historical.py --start-date 2024-01-01

# Import from custom directory
python3 scripts/import_historical.py /path/to/csv/directory
```

### Options

- `--dry-run` - Preview changes without modifying database
- `--limit N` - Only import first N files (useful for testing)
- `--start-date YYYY-MM-DD` - Only import weeks from this date onwards
- `--end-date YYYY-MM-DD` - Only import weeks up to this date
- `directory` - Path to directory containing CSV files (optional, defaults to weekly_outputs)

## Expected Results

For **~248 CSV files** in the weekly_outputs directory:

- Creates 3-4 agents (Trev, Gabe, Orso, Dro)
- Creates ~100-150 unique players
- Imports ~248 weeks of data
- Each week will have 10-30 player records

## Verification

After import, you can verify the data:

```sql
-- Check number of weeks imported
SELECT COUNT(*) FROM weeks;

-- Check number of players
SELECT COUNT(*) FROM players;

-- Check number of agents
SELECT COUNT(*) FROM agents;

-- Check total weekly records
SELECT COUNT(*) FROM weekly_raw;

-- View sample data
SELECT w.week_id, COUNT(*) as player_count, SUM(wr.week_amount) as total
FROM weekly_raw wr
JOIN weeks w ON w.week_id = wr.week_id
GROUP BY w.week_id
ORDER BY w.week_id DESC
LIMIT 10;
```

## Troubleshooting

### "Module not found" errors
Make sure you're in the correct Python virtual environment and have installed dependencies:
```bash
pip install -r requirements.txt
```

### "DATABASE_URL not set"
Set your database connection string:
```bash
export DATABASE_URL="postgresql://user:password@host:port/database"
```

### Duplicate data
The script uses `ON CONFLICT DO UPDATE`, so re-running it will update existing records rather than creating duplicates.

## Notes

- File names must be in `YYYY-MM-DD.csv` format to be recognized as valid week dates
- The script will skip files that don't match this format
- Player IDs are automatically lowercased (pyr103 → pyr103)
- Display names will be updated if they differ from existing records
- Pending amounts are set to 0 for historical imports (not captured in original CSVs)
