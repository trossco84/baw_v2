# Player Instance Fix - 2025-12-28

## Problem

The database had 203 player instances for only 102 unique player IDs, with many incorrect instances marked as `is_current=true`. This caused:

1. **Wrong players showing in dashboard** - e.g., showing "Luc" and "Jalen" who haven't played in years
2. **Incorrect financial calculations** - book totals and agent balances were wrong
3. **Data corruption** - `weekly_raw` entries pointing to old/wrong player instances

### Root Cause

The `get_or_create_player_instance()` SQL function was too complex and created duplicate instances when player IDs were reused. It failed to properly handle the case where a player_id gets reassigned to a completely different person (different name/agent).

## Solution

### 1. Fixed Player Instances (via `scripts/fix_player_instances.py`)

- Marked ALL 203 existing instances as `is_current=false`
- Loaded `sample_data/players_and_agents.csv` as source of truth (102 players)
- Reactivated or created one instance per player_id matching the CSV
- Result: Exactly 102 player instances, all correct, all marked `is_current=true`

### 2. Cleaned Latest Week Data (via `scripts/delete_latest_week.py`)

- Deleted week 2025-12-15 which had 42 entries pointing to old instances
- Removed from tables: `weekly_player_status`, `manual_slips`, `weekly_raw`, `weeks`
- Preserved all historical data (player_instances kept for history)

### 3. Updated Database Function (via `scripts/update_player_instance_function.sql`)

Simplified `get_or_create_player_instance()` to use `(player_id, display_name, agent_id)` as the unique composite key:

- If exact match exists → use it
- If no match → mark old instances as `is_current=false`, create new instance
- No more complex logic that created duplicates

## Verification

After fix:
```bash
python scripts/investigate_db.py
```

Shows:
- ✅ 102 player instances (matches CSV)
- ✅ All marked as `is_current=true`
- ✅ All match source of truth CSV
- ✅ No mismatches

## Next Steps

1. **Re-upload latest week** - Upload `Weekly Figures _ December 21, 2025 8_07 PM.xlsx`
2. **Verify dashboard** - Check that correct players appear
3. **Test future uploads** - Ensure no duplicate instances are created

## Prevention

Going forward:
- **Source of truth**: `sample_data/players_and_agents.csv` defines all valid players
- **Composite key**: Player identity is `(player_id, display_name, agent_id)`
- **Upload logic**: Looks up `is_current=true` instances only
- **Function updated**: Simplified logic prevents duplicates

## Files Modified

1. `scripts/fix_player_instances.py` - One-time fix script
2. `scripts/delete_latest_week.py` - Week deletion utility
3. `scripts/investigate_db.py` - Investigation tool
4. `scripts/update_player_instance_function.sql` - Database function update

## Database State

**Before:**
- 203 player instances (101 duplicates)
- Many wrong instances marked as current
- Latest week had 25/42 entries pointing to wrong instances

**After:**
- 102 player instances (no duplicates)
- All instances match CSV source of truth
- Latest week deleted, ready for clean re-upload
- Function updated to prevent future duplicates
