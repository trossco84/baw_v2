# Schema v2 Quick Start

## TL;DR

Player IDs get reused over time. The v2 schema fixes this by tracking each unique combination of `(player_id, display_name, agent)` as a separate "player instance". This preserves all historical data when importing.

## Quick Migration (15 minutes)

### 1. Backup (2 min)
```bash
pg_dump $DATABASE_URL > backup.sql
```

### 2. Migrate Database (5 min)
```bash
psql $DATABASE_URL -f scripts/migrate_to_v2.sql
```

### 3. Update Code (3 min)
```bash
mv app/models.py app/models_v1_backup.py
mv app/models_v2.py app/models.py
```

### 4. Update API Endpoints (5 min)

In [app/main.py](app/main.py), update database queries:

**Key Changes:**
- `players` → `player_instances`
- `player_id` → `player_instance_id` in JOIN conditions
- Add `WHERE is_current = true` when querying current players
- Use `get_or_create_player_instance()` when creating players

See [SCHEMA_V2_MIGRATION_GUIDE.md](SCHEMA_V2_MIGRATION_GUIDE.md) for detailed code examples.

### 5. Test (Optional)
```bash
# Test historical import
python3 scripts/import_historical_v2.py --dry-run --limit 5
```

## Files You Need

| File | Purpose |
|------|---------|
| [scripts/migrate_to_v2.sql](scripts/migrate_to_v2.sql) | Converts your existing database to v2 schema |
| [scripts/import_historical_v2.py](scripts/import_historical_v2.py) | Import historical CSVs with player instance tracking |
| [app/models_v2.py](app/models_v2.py) | Updated Pydantic models |
| [SCHEMA_V2_OVERVIEW.md](SCHEMA_V2_OVERVIEW.md) | Detailed explanation of the problem and solution |
| [SCHEMA_V2_MIGRATION_GUIDE.md](SCHEMA_V2_MIGRATION_GUIDE.md) | Step-by-step migration instructions |

## What Changes

### Database
```sql
-- Before
players: (id, player_id, display_name, agent_id)
weekly_raw: (week_id, player_id, ...)

-- After
player_instances: (id, player_id, display_name, agent_id, first_seen, last_seen, is_current)
weekly_raw: (week_id, player_instance_id, ...)
```

### Queries
```sql
-- Before: Get all players
SELECT * FROM players;

-- After: Get current players only
SELECT * FROM player_instances WHERE is_current = true;
-- Or use the view
SELECT * FROM current_players;
```

### Creating Players
```sql
-- Before
INSERT INTO players (player_id, display_name, agent_id)
VALUES ('pyr103', 'John', 1);

-- After (use helper function)
SELECT get_or_create_player_instance('pyr103', 'John', 1, '2024-01-01');
```

## Verification

After migration, run these checks:

```sql
-- 1. All players migrated?
SELECT COUNT(*) FROM players;  -- Old count
SELECT COUNT(*) FROM player_instances;  -- Should match or be higher

-- 2. All weekly_raw records mapped?
SELECT COUNT(*) FROM weekly_raw WHERE player_instance_id IS NULL;  -- Should be 0

-- 3. View player history
SELECT * FROM player_history ORDER BY player_id, first_seen;
```

## Common Tasks After Migration

### View Current Players
```sql
SELECT * FROM current_players;
```

### View Player History (All Instances)
```sql
SELECT * FROM player_history WHERE player_id = 'pyr103';
```

### Import Historical Data
```bash
# Dry run first
python3 scripts/import_historical_v2.py --dry-run --limit 10

# Full import
python3 scripts/import_historical_v2.py
```

### Check for Player ID Reuse
```sql
-- Find player_ids that have been reused
SELECT player_id, COUNT(*) as instances
FROM player_instances
GROUP BY player_id
HAVING COUNT(*) > 1;
```

### Get Instance for Current Player
```sql
SELECT id FROM player_instances
WHERE player_id = 'pyr103' AND is_current = true;
```

## Rollback

If something goes wrong:

```bash
# Restore from backup
psql $DATABASE_URL < backup.sql

# Revert code
mv app/models_v1_backup.py app/models.py
```

## Need More Detail?

- **Why do this?** → Read [SCHEMA_V2_OVERVIEW.md](SCHEMA_V2_OVERVIEW.md)
- **Step-by-step migration** → Read [SCHEMA_V2_MIGRATION_GUIDE.md](SCHEMA_V2_MIGRATION_GUIDE.md)
- **API changes** → See detailed examples in [SCHEMA_V2_MIGRATION_GUIDE.md](SCHEMA_V2_MIGRATION_GUIDE.md#step-5-update-api-endpoints)

## Support

The migration script includes verification steps and will warn you if anything goes wrong. If you see warnings about unmapped records, check the migration log output.
