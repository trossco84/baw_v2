# Schema v2 Migration Guide

## Overview

The v2 schema introduces **player instance tracking** to handle the fact that player IDs (like `pyr103`) get reused over time for different people. This migration preserves all historical data while enabling accurate player tracking and analytics.

## Key Changes

### What's Different

**Old Schema (v1):**
- `players` table with unique `player_id` constraint
- When importing historical data, old players get overwritten
- Can't distinguish between different people who used the same `player_id`

**New Schema (v2):**
- `player_instances` table with composite unique key `(player_id, display_name, agent_id)`
- Same `player_id` can exist multiple times with different names/agents
- Tracks `first_seen` and `last_seen` dates for each instance
- `is_current` flag distinguishes active vs historical players
- Helper function `get_or_create_player_instance()` handles reuse logic automatically

### Database Changes

1. **New Table:** `player_instances` replaces `players` as the source of truth
2. **Updated Tables:** `weekly_raw`, `manual_slips`, `weekly_player_status` now reference `player_instance_id` instead of `player_id`
3. **New Views:** `current_players` and `player_history` for easy querying
4. **New Function:** `get_or_create_player_instance()` for automatic instance management

## Migration Steps

### Step 1: Backup Your Database

```bash
# Export current database
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Step 2: Run Migration Script

```bash
# Run the migration (this modifies your database)
psql $DATABASE_URL -f scripts/migrate_to_v2.sql
```

The migration script will:
- Create `player_instances` table
- Migrate existing players to player instances
- Add `player_instance_id` columns to all related tables
- Populate `player_instance_id` for all existing data
- Update constraints and indexes
- Create helper views and functions

### Step 3: Verify Migration

```sql
-- Check that all players were migrated
SELECT COUNT(*) FROM players;
SELECT COUNT(*) FROM player_instances;
-- These should match

-- Check that all weekly_raw records have player_instance_id
SELECT COUNT(*) FROM weekly_raw WHERE player_instance_id IS NULL;
-- Should be 0

-- View player history
SELECT * FROM player_history ORDER BY player_id, first_seen;
```

### Step 4: Update Application Code

Replace `app/models.py` with `app/models_v2.py`:

```bash
mv app/models.py app/models_v1_backup.py
mv app/models_v2.py app/models.py
```

### Step 5: Update API Endpoints

The API endpoints need to be updated to work with player instances. Here are the key changes needed in `app/main.py`:

#### Player Endpoints Changes

**GET /players** - List current players
```python
# OLD:
cur.execute("""
    SELECT p.id, p.player_id, p.display_name, p.agent_id, a.name as agent_name
    FROM players p
    JOIN agents a ON a.id = p.agent_id
    ORDER BY p.player_id
""")

# NEW:
cur.execute("""
    SELECT pi.id, pi.player_id, pi.display_name, pi.agent_id, a.name as agent_name
    FROM player_instances pi
    JOIN agents a ON a.id = pi.agent_id
    WHERE pi.is_current = true
    ORDER BY pi.player_id
""")
```

**POST /players** - Create new player
```python
# OLD:
cur.execute(
    "INSERT INTO players (player_id, display_name, agent_id) VALUES (%s, %s, %s) RETURNING id",
    (player.player_id, player.display_name, player.agent_id)
)

# NEW:
cur.execute(
    "INSERT INTO player_instances (player_id, display_name, agent_id, first_seen, is_current) VALUES (%s, %s, %s, CURRENT_DATE, true) RETURNING id",
    (player.player_id, player.display_name, player.agent_id)
)
```

**PUT /players/{player_id}** - Update player
```python
# OLD:
cur.execute(
    "UPDATE players SET display_name = %s, agent_id = %s WHERE player_id = %s",
    (updates.display_name, updates.agent_id, player_id)
)

# NEW:
cur.execute(
    "UPDATE player_instances SET display_name = %s, agent_id = %s WHERE player_id = %s AND is_current = true",
    (updates.display_name, updates.agent_id, player_id)
)
```

**DELETE /players/{player_id}** - Delete player
```python
# OLD:
cur.execute("DELETE FROM players WHERE player_id = %s", (player_id,))

# NEW:
# Mark as not current instead of deleting (preserves history)
cur.execute(
    "UPDATE player_instances SET is_current = false, last_seen = CURRENT_DATE WHERE player_id = %s AND is_current = true",
    (player_id,)
)
```

#### Manual Slip Endpoints Changes

**POST /slips** - Create manual slip
```python
# OLD:
cur.execute(
    "INSERT INTO manual_slips (week_id, player_id, amount, note) VALUES (%s, %s, %s, %s) RETURNING id",
    (slip.week_id, slip.player_id, slip.amount, slip.note)
)

# NEW:
# First get the current player instance for this player_id
cur.execute(
    "SELECT id FROM player_instances WHERE player_id = %s AND is_current = true",
    (slip.player_id,)
)
result = cur.fetchone()
if not result:
    raise HTTPException(status_code=404, detail=f"Player {slip.player_id} not found")

player_instance_id = result[0]

cur.execute(
    "INSERT INTO manual_slips (week_id, player_instance_id, amount, note) VALUES (%s, %s, %s, %s) RETURNING id",
    (slip.week_id, player_instance_id, slip.amount, slip.note)
)
```

**GET /slips** - Get manual slips
```python
# OLD:
cur.execute("""
    SELECT ms.id, ms.week_id, ms.player_id, ms.amount, ms.note, ms.created_at,
           p.display_name, a.name as agent_name
    FROM manual_slips ms
    JOIN players p ON p.player_id = ms.player_id
    JOIN agents a ON a.id = p.agent_id
    WHERE ms.week_id = %s
""", (week_id,))

# NEW:
cur.execute("""
    SELECT ms.id, ms.week_id, ms.player_instance_id, ms.amount, ms.note, ms.created_at,
           pi.player_id, pi.display_name, a.name as agent_name
    FROM manual_slips ms
    JOIN player_instances pi ON pi.id = ms.player_instance_id
    JOIN agents a ON a.id = pi.agent_id
    WHERE ms.week_id = %s
""", (week_id,))
```

#### Dashboard Query Changes

**GET /** - Dashboard
```python
# OLD:
cur.execute("""
    SELECT
        w.week_id,
        p.player_id,
        p.display_name,
        a.name as agent,
        COALESCE(wr.week_amount, 0) + COALESCE(slips.total_adjustment, 0) as week_amount,
        COALESCE(s.engaged, false) as engaged,
        COALESCE(s.paid, false) as paid
    FROM weekly_raw wr
    JOIN players p ON p.player_id = wr.player_id
    JOIN agents a ON a.id = p.agent_id
    JOIN weeks w ON w.week_id = wr.week_id
    LEFT JOIN weekly_player_status s ON s.week_id = wr.week_id AND s.player_id = wr.player_id
    LEFT JOIN (
        SELECT week_id, player_id, SUM(amount) as total_adjustment
        FROM manual_slips
        GROUP BY week_id, player_id
    ) slips ON slips.week_id = wr.week_id AND slips.player_id = wr.player_id
    WHERE w.week_id = (SELECT MAX(week_id) FROM weeks)
    ORDER BY agent, p.player_id
""")

# NEW:
cur.execute("""
    SELECT
        w.week_id,
        pi.player_id,
        pi.display_name,
        a.name as agent,
        COALESCE(wr.week_amount, 0) + COALESCE(slips.total_adjustment, 0) as week_amount,
        COALESCE(s.engaged, false) as engaged,
        COALESCE(s.paid, false) as paid
    FROM weekly_raw wr
    JOIN player_instances pi ON pi.id = wr.player_instance_id
    JOIN agents a ON a.id = pi.agent_id
    JOIN weeks w ON w.week_id = wr.week_id
    LEFT JOIN weekly_player_status s ON s.week_id = wr.week_id AND s.player_instance_id = wr.player_instance_id
    LEFT JOIN (
        SELECT week_id, player_instance_id, SUM(amount) as total_adjustment
        FROM manual_slips
        GROUP BY week_id, player_instance_id
    ) slips ON slips.week_id = wr.week_id AND slips.player_instance_id = wr.player_instance_id
    WHERE w.week_id = (SELECT MAX(week_id) FROM weeks)
    ORDER BY agent, pi.player_id
""")
```

#### Excel Upload Changes

**POST /upload/weekly** - Excel upload

The Excel upload logic in `engine/translate.py` needs to be updated to use `get_or_create_player_instance()`:

```python
# After parsing the Excel file and extracting player data:
for _, row in df.iterrows():
    player_id = row['player_id']
    display_name = row.get('display_name', '')
    agent_id = row['agent_id']  # Need to determine this from the data
    week_id = row['week_id']
    week_amount = row['week_amount']
    pending = row['pending']

    # Get or create player instance
    cur.execute(
        "SELECT get_or_create_player_instance(%s, %s, %s, %s)",
        (player_id, display_name, agent_id, week_id)
    )
    player_instance_id = cur.fetchone()[0]

    # Insert weekly data
    cur.execute("""
        INSERT INTO weekly_raw (week_id, player_instance_id, week_amount, pending, scraped_at)
        VALUES (%s, %s, %s, %s, now())
        ON CONFLICT (week_id, player_instance_id)
        DO UPDATE SET week_amount = EXCLUDED.week_amount, pending = EXCLUDED.pending
    """, (week_id, player_instance_id, week_amount, pending))
```

### Step 6: Update Historical Import

Use the new import script:

```bash
# Test with dry run
python3 scripts/import_historical_v2.py --dry-run --limit 10

# Full import
python3 scripts/import_historical_v2.py
```

### Step 7: Update Templates

The HTML templates need minimal changes since they work with the API responses. Main changes:

**dashboard.html:**
- No changes needed (still receives player_id, display_name from API)

**manage.html:**
- Optionally add "Show Historical Players" toggle
- Add visual indicator for `is_current` status

## Testing the Migration

### 1. Test Player Instance Creation

```sql
-- Create a player
INSERT INTO player_instances (player_id, display_name, agent_id, first_seen, is_current)
VALUES ('pyr999', 'Test User 1', 1, '2024-01-01', true);

-- Try to create same player_id with different name (should work)
INSERT INTO player_instances (player_id, display_name, agent_id, first_seen, is_current)
VALUES ('pyr999', 'Test User 2', 1, '2024-06-01', true);

-- View both instances
SELECT * FROM player_instances WHERE player_id = 'pyr999' ORDER BY first_seen;
```

### 2. Test Helper Function

```sql
-- Get or create player instance
SELECT get_or_create_player_instance('pyr888', 'John Doe', 1, '2024-01-15');

-- Call again with same data (should return same instance)
SELECT get_or_create_player_instance('pyr888', 'John Doe', 1, '2024-01-20');

-- Call with different name (should create new instance and mark old as historical)
SELECT get_or_create_player_instance('pyr888', 'Jane Smith', 1, '2024-06-01');

-- View history
SELECT * FROM player_history WHERE player_id = 'pyr888';
```

### 3. Test Data Integrity

```sql
-- Ensure all weekly_raw records have valid player_instance_id
SELECT COUNT(*)
FROM weekly_raw wr
LEFT JOIN player_instances pi ON pi.id = wr.player_instance_id
WHERE pi.id IS NULL;
-- Should be 0

-- Check for orphaned manual slips
SELECT COUNT(*)
FROM manual_slips ms
LEFT JOIN player_instances pi ON pi.id = ms.player_instance_id
WHERE pi.id IS NULL;
-- Should be 0
```

## Rollback Plan

If you need to rollback the migration:

```bash
# Restore from backup
psql $DATABASE_URL < backup_YYYYMMDD_HHMMSS.sql

# Revert code changes
mv app/models_v1_backup.py app/models.py
```

## Benefits of v2 Schema

1. **Historical Accuracy**: Can import 248 weeks of data without losing information
2. **Player Tracking**: Know exactly which person was behind each player_id in each time period
3. **Analytics**: Can calculate accurate per-person metrics across player_id changes
4. **Audit Trail**: Track when player_ids changed hands with `first_seen`/`last_seen`
5. **Data Integrity**: No more overwrites when importing historical data

## Common Issues

### Issue: "player_instance_id cannot be null"
**Solution:** Run the migration script completely. Ensure Step 9 of migration completes.

### Issue: "function get_or_create_player_instance does not exist"
**Solution:** Run the migration script which creates this function.

### Issue: Historical import creates duplicate players
**Solution:** The `get_or_create_player_instance()` function should prevent this. Check that the function is working correctly and that you're using `import_historical_v2.py`.

### Issue: Dashboard shows no players
**Solution:** Make sure queries filter for `is_current = true` when showing current players.

## Questions?

After migrating, you can:
- View all current players: `SELECT * FROM current_players;`
- View full player history: `SELECT * FROM player_history;`
- Check specific player's instances: `SELECT * FROM player_instances WHERE player_id = 'pyr103';`
