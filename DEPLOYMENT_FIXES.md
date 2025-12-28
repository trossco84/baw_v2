# Deployment Fixes - Post-Launch

## Issues Fixed

### 1. Dro Filtered from Dashboard ✅
**Problem:** Dro (4th agent) was appearing in calculations and UI
**Fix:** Added SQL filter `and a.name != 'Dro'` to exclude from all queries
**Result:** Only Gabe, Trev, and Orso appear in dashboard and settlements

### 2. Dashboard Now Shows Current Week Only ✅
**Problem:** Dashboard was aggregating ALL weeks instead of just the most recent
**Fix:** Added `where w.week_id = %s` to limit to current week
**Result:** Dashboard only shows data for the most recent week

### 3. Split Calculation Moved to Settlement Panel ✅
**Problem:** Split calculation was a large card at top of page
**Fix:** Moved to small notice inside Settlement Transfers card
**Result:** Cleaner layout, split info contextually placed with settlements

### 4. Kevin Bubble Moved to Bottom ✅
**Problem:** Kevin bubble status was prominent card at top
**Fix:** Moved to bottom of page after all other content
**Result:** De-emphasized but still visible when active

### 5. Emojis Removed from UI ✅
**Problem:** UI used emojis (📊, 💰) in cards
**Fix:** Removed all emoji decorations
**Result:** Clean, professional appearance

## Files Modified

### [app/main.py](app/main.py:34-60)
```python
# Changed query to:
# 1. Filter to current week only: where w.week_id = %s
# 2. Exclude Dro: and a.name != 'Dro'
```

### [app/templates/dashboard.html](app/templates/dashboard.html)
**Line 7:** Added week display in subtitle
**Lines 56-61:** Split calculation embedded in Settlement Transfers card (small)
**Lines 372-378:** Kevin bubble moved to bottom of page
**Removed:** All emoji characters from UI

## Testing Checklist

- [ ] Dashboard shows only current week data
- [ ] Dro does not appear in agent cards
- [ ] Dro does not appear in calculations or settlements
- [ ] Split calculation appears in settlement panel (not as large card)
- [ ] Kevin bubble appears at bottom (if active)
- [ ] No emojis visible anywhere in UI
- [ ] Settlement transfers calculate correctly for 3 agents

## SQL Query Changes

**Before:**
```sql
select ... from weekly_raw wr
join ...
order by agent, pi.player_id
```

**After:**
```sql
select ... from weekly_raw wr
join ...
where w.week_id = %s          -- ← Current week only
  and a.name != 'Dro'         -- ← Exclude Dro
order by a.name, pi.player_id
```

## UI Layout Changes

**Before:**
```
[Title]
[🔵 Large Split Calculation Card]
[🟠 Large Kevin Bubble Card]
[Agent Summary Cards]
[Settlement Transfers]
...
```

**After:**
```
[Title - Week of YYYY-MM-DD]
[Agent Summary Cards]
[Settlement Transfers]
  ├─ Split Calculation (small notice)
  └─ Transfer table
[Manual Betslips]
[Player Details]
[Kevin Bubble Status] (small, if active)
```

## Behavior Notes

1. **Week Display:** Subtitle now shows "Week of [date]" for clarity
2. **Dro's Data:** Still in database, just filtered from view
3. **Split Rules:** Still apply correctly to 3 agents only
4. **Kevin Bubble:** Only appears if Kevin has activity this week

## Future Enhancements

- Consider adding week selector dropdown to view historical weeks
- Add "View All Agents" toggle to optionally show Dro
- Create separate analytics dashboard for historical trends
