# Schema v2 Overview - Player Instance Tracking

## The Problem

Your current database schema has a fundamental issue: **player IDs get reused over time**.

For example:
- In 2021, `pyr103` might be "John Smith" under agent Trev
- In 2024, `pyr103` might be "Sarah Johnson" under agent Gabe

With the v1 schema, when you import historical data:
1. The `players` table has `player_id` as a unique key
2. When importing 2021 data, it creates `pyr103 → John Smith`
3. When importing 2024 data, it **overwrites** to `pyr103 → Sarah Johnson`
4. All historical data now shows "Sarah Johnson" for weeks that should show "John Smith"
5. You can't calculate per-person analytics because the data is mixed

## The Solution

**Schema v2** introduces **player instances** - a way to track each unique combination of `(player_id, display_name, agent)` over time.

### Key Concept: Player Instances

Instead of one `players` table, we now have:

**player_instances** table:
```sql
id  | player_id | display_name   | agent_id | first_seen  | last_seen   | is_current
----|-----------|----------------|----------|-------------|-------------|------------
1   | pyr103    | John Smith     | 1        | 2021-01-01  | 2023-12-31  | false
2   | pyr103    | Sarah Johnson  | 2        | 2024-01-01  | 2024-12-15  | true
```

Now:
- Each row is a unique **instance** of a player
- Same `player_id` can exist multiple times
- `first_seen` / `last_seen` track when this person used that ID
- `is_current` = true for the currently active player with that ID
- Historical data is preserved perfectly

### How It Works

When importing or creating player data, the system uses a smart function: `get_or_create_player_instance(player_id, display_name, agent_id, week_id)`

**Scenario 1: New player**
```sql
SELECT get_or_create_player_instance('pyr150', 'Mike Jones', 1, '2024-01-01');
-- Creates new instance, returns instance_id
```

**Scenario 2: Existing player (same ID, same name, same agent)**
```sql
SELECT get_or_create_player_instance('pyr150', 'Mike Jones', 1, '2024-01-15');
-- Returns existing instance_id, updates last_seen to 2024-01-15
```

**Scenario 3: Player ID reused (same ID, different name or agent)**
```sql
SELECT get_or_create_player_instance('pyr150', 'New Person', 2, '2024-06-01');
-- Marks old instance as is_current=false with last_seen=2024-05-31
-- Creates new instance with is_current=true, first_seen=2024-06-01
-- Returns new instance_id
```

This logic happens **automatically** - you don't need to manage it manually.

## What Changes in Your Code

### Database Schema

**Before (v1):**
```sql
players (id, player_id, display_name, agent_id)
weekly_raw (week_id, player_id, ...)
```

**After (v2):**
```sql
player_instances (id, player_id, display_name, agent_id, first_seen, last_seen, is_current)
weekly_raw (week_id, player_instance_id, ...)
```

All tables that referenced `player_id` now reference `player_instance_id`.

### API Endpoints

**Player List** - Now only shows current players:
```python
# Filter for is_current = true
SELECT * FROM player_instances WHERE is_current = true
```

**Player Create** - Automatically handles reuse:
```python
# Just insert, the function handles everything
SELECT get_or_create_player_instance(...)
```

**Manual Slips** - Need to look up instance:
```python
# Convert player_id to player_instance_id
player_instance_id = get_current_instance_id(player_id)
INSERT INTO manual_slips (player_instance_id, ...)
```

### Historical Import

The new import script (`import_historical_v2.py`) uses `get_or_create_player_instance()` for every row:

```python
for row in csv_data:
    instance_id = get_or_create_player_instance(
        player_id=row['Player'],
        display_name=row['Name'],
        agent_id=agent_id,
        week_id=week_id
    )
    # Insert weekly_raw with instance_id
```

This means:
- Import 2021 data → creates instance #1 for pyr103
- Import 2024 data → creates instance #2 for pyr103
- Both instances coexist peacefully
- No data is overwritten

## Migration Process

1. **Backup** your database
2. **Run** `migrate_to_v2.sql` - converts existing data
3. **Update** models: use `models_v2.py`
4. **Update** API endpoints: use player_instance_id
5. **Test** with a small import
6. **Import** all historical data with `import_historical_v2.py`

## Benefits You Get

### 1. Accurate Historical Data
Import all 248 weeks without losing any information. Every player name is preserved exactly as it appeared in that week.

### 2. True Per-Person Analytics
```sql
-- See all activity for the person who was pyr103 from 2021-2023
SELECT SUM(week_amount)
FROM weekly_raw wr
WHERE player_instance_id = 1;  -- The John Smith instance

-- See all activity for the current pyr103
SELECT SUM(week_amount)
FROM weekly_raw wr
WHERE player_instance_id = 2;  -- The Sarah Johnson instance
```

### 3. Player History Tracking
```sql
-- Who has used pyr103 over time?
SELECT * FROM player_history WHERE player_id = 'pyr103';
```

Output:
```
player_id | display_name   | first_seen  | last_seen   | status
----------|----------------|-------------|-------------|----------
pyr103    | Sarah Johnson  | 2024-01-01  | NULL        | Active
pyr103    | John Smith     | 2021-01-01  | 2023-12-31  | Historical
```

### 4. No More Overwrites
Re-running imports is safe. The system is idempotent - running the same import twice won't create duplicates or overwrite data.

### 5. Audit Trail
You can always see:
- When a player_id started being used by someone (`first_seen`)
- When they stopped using it (`last_seen`)
- Who currently has it (`is_current = true`)

## Examples

### Example 1: Player ID Reused

**Timeline:**
- 2021-2023: pyr103 = John Smith (agent Trev)
- 2024: pyr103 = Sarah Johnson (agent Gabe)

**v1 schema (bad):**
```sql
players: [pyr103, Sarah Johnson, Gabe]
-- John Smith data is lost!
```

**v2 schema (good):**
```sql
player_instances:
  [1, pyr103, John Smith, Trev, 2021-01-01, 2023-12-31, false]
  [2, pyr103, Sarah Johnson, Gabe, 2024-01-01, NULL, true]
-- Both preserved!
```

### Example 2: Importing Historical Week

**Week: 2022-06-15, Player: pyr103, Name: John Smith**

```python
# Automatic instance matching
instance_id = get_or_create_player_instance(
    'pyr103', 'John Smith', trev_agent_id, '2022-06-15'
)
# Returns instance #1 (John Smith)

# Insert weekly data
INSERT INTO weekly_raw (week_id, player_instance_id, ...)
VALUES ('2022-06-15', 1, ...)
```

### Example 3: Current Dashboard

When showing current week, only show active players:

```sql
SELECT pi.player_id, pi.display_name, wr.week_amount
FROM weekly_raw wr
JOIN player_instances pi ON pi.id = wr.player_instance_id
WHERE wr.week_id = '2024-12-15'
  AND pi.is_current = true  -- Only current players
```

## Visual Comparison

### v1 Schema Problem:

```
Week 2021-01-01: pyr103 → ??? (overwritten, lost)
Week 2022-06-15: pyr103 → ??? (overwritten, lost)
Week 2024-12-15: pyr103 → Sarah Johnson
```

All weeks show Sarah Johnson because that's what's in the `players` table.

### v2 Schema Solution:

```
Week 2021-01-01: pyr103 (instance 1) → John Smith ✓
Week 2022-06-15: pyr103 (instance 1) → John Smith ✓
Week 2024-12-15: pyr103 (instance 2) → Sarah Johnson ✓
```

Each week correctly links to the right person via `player_instance_id`.

## Files Created

1. **scripts/init_db_v2.sql** - Clean v2 schema for new deployments
2. **scripts/migrate_to_v2.sql** - Migration script from v1 to v2
3. **scripts/import_historical_v2.py** - Historical import using player instances
4. **app/models_v2.py** - Pydantic models for v2 schema
5. **SCHEMA_V2_MIGRATION_GUIDE.md** - Detailed migration instructions
6. **SCHEMA_V2_OVERVIEW.md** - This document

## Next Steps

1. Review this overview to understand the concept
2. Read SCHEMA_V2_MIGRATION_GUIDE.md for detailed migration steps
3. Backup your database
4. Run the migration
5. Update your code
6. Import historical data
7. Enjoy accurate player tracking!

## Questions to Consider

- **Do I need to update the UI?** Minimal changes. The API still returns `player_id` and `display_name`, just from the player_instances table instead.

- **What about performance?** The migration adds indexes. Queries may actually be faster. The `current_players` view makes common queries easy.

- **Can I rollback?** Yes, restore from backup. Keep your backup until you've verified everything works.

- **Will this break existing code?** The API can maintain backwards compatibility by continuing to accept `player_id` and translating to `player_instance_id` internally.

- **What if I don't migrate?** You'll continue to have data integrity issues when importing historical data, and won't be able to accurately track player history or calculate per-person analytics.
