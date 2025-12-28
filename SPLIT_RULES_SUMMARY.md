# Split Rules Implementation Summary

## Overview

This document summarizes the advanced split calculation rules implemented in the BAW v2 system. These rules determine how weekly profits are distributed among the three core agents (Gabe, Trev, Orso).

## Default Behavior

**Even Split: 33.33% / 33.33% / 33.33%**

- By default, all agents receive an equal share of the weekly book total
- This applies when no special conditions are met
- All weekly totals and player results are calculated normally and shown in full in the UI

## Special Split Rules

### 1. Kevin Bubble Rule ($100 Threshold)

**Player:** Kevin (pyr109)

**Logic:**
- Kevin's weekly amounts accumulate in a running balance
- If `|weekly_amount| < $100`: Add to running balance, set weekly amount to $0
- If `|weekly_amount| >= $100`: Apply full amount to settlement, reset balance to $0

**Database:**
- Table: `kevin_balance`
- Tracks `player_instance_id`, `current_balance`, `updated_at`

**UI Display:**
- Orange warning card shows Kevin's bubble status when active
- Shows running balance and explains whether bubble is active or threshold exceeded

---

### 2. Low Exposure Rule

**Condition:** Agent has `< 5 active players` AND `|weekly_total| < $500`

**Split Adjustment:**
- Qualifying agent: **20%**
- Other two agents: **40%** each

**Example:**
- Trev: 3 players, $200 total → 20%
- Gabe: 8 players → 40%
- Orso: 7 players → 40%

**Purpose:** Prevents low-volume, low-risk weeks from disproportionately affecting settlements

**Important:** Both conditions must be true. If agent has 5+ players OR $500+ total, standard split applies.

---

### 3. Dominant Winner Rule

**Condition:** Agent accounts for `> 75% of winnings` AND `book_total > $1,000`

**Split Adjustment:**
- Dominant agent: **40%**
- Other two agents: **30%** each

**Example:**
- Gabe: $900 of $1,100 total (81.8%) → 40%
- Trev: $100 → 30%
- Orso: $100 → 30%

**Purpose:** Rewards exceptional performance while maintaining team structure

**Important:** Both conditions must be true. If book total ≤ $1,000, standard split applies.

---

### 4. Combined Edge Case Rule

**Condition:** BOTH dominant winner AND low exposure agent exist

**Split Adjustment:**
- Dominant winner: **45%**
- Middle agent: **35%**
- Low exposure agent: **15%**

**Example:**
- Gabe: $900 (dominant) → 45%
- Orso: $50 (middle) → 35%
- Trev: $150, 3 players (low exposure) → 15%

**Purpose:** Handles the rare case where one agent dominates AND another has minimal exposure

---

## What Does NOT Change

These split rules ONLY affect settlement calculations. The following remain unchanged:

✓ Player-level results (shown in full)
✓ Agent-level weekly totals (shown in full)
✓ Historical stats, trends, or averages
✓ Locking rules for completed weeks
✓ Individual player win/loss amounts

## UI Changes

### Dashboard Display

1. **Split Calculation Card** (Green)
   - Shows which rule was applied
   - Displays percentage breakdown
   - Explains the reasoning

2. **Kevin Bubble Status Card** (Orange)
   - Only appears when Kevin has activity
   - Shows current running balance
   - Explains whether bubble is active

3. **Agent Summary Cards**
   - Added "Split" metric showing agent's percentage (20%, 33.3%, 40%, or 45%)
   - Shows split percentage in blue color
   - Final balance now reflects split-adjusted amount

4. **Settlement Transfers**
   - Unchanged - still shows simplest way to equalize everyone's take
   - But amounts now reflect split-adjusted final balances

## Technical Implementation

### New Files Created

1. **`engine/split_rules.py`**
   - `calculate_split_percentages()` - Determines split for each agent
   - `calculate_final_balances()` - Calculates dollar amounts based on splits
   - `format_split_explanation()` - Generates human-readable explanations

2. **`engine/kevin_logic.py`**
   - `apply_kevin_bubble_logic()` - Handles Kevin's $100 bubble
   - `get_kevin_balance()` - Retrieves current balance
   - `update_kevin_balance()` - Updates balance in DB

3. **`scripts/add_kevin_balance_table.sql`**
   - Database migration to create `kevin_balance` table

4. **`scripts/test_split_logic.py`**
   - Comprehensive test suite with 8 test cases
   - Tests all rules and edge cases
   - Can be run independently: `python scripts/test_split_logic.py`

### Modified Files

1. **`engine/compute.py`**
   - Updated `compute_dashboard()` to accept database connection
   - Integrates Kevin bubble logic
   - Calls split_rules to calculate percentages
   - Returns `split_info` dict for template

2. **`app/main.py`**
   - Dashboard endpoint now passes connection to `compute_dashboard()`
   - Passes `split_info` to template

3. **`app/templates/dashboard.html`**
   - Added split calculation explanation card
   - Added Kevin bubble status card
   - Added split percentage to agent summary cards

## Testing

All split rules have been tested with the following scenarios:

✓ Even split (default)
✓ Low exposure (< 5 players, < $500)
✓ Low exposure edge cases (exactly 5 players, exactly $500)
✓ Dominant winner (> 75%, book > $1K)
✓ Dominant winner threshold (book = $1K)
✓ Combined rule (dominant + low exposure)
✓ Full settlement calculation with transfers

**Run tests:** `python scripts/test_split_logic.py`

## Migration Steps (Already Completed)

1. ✅ Created `kevin_balance` table
2. ✅ Implemented split calculation logic
3. ✅ Updated compute engine
4. ✅ Updated UI templates
5. ✅ Tested all scenarios

## Notes for Future Development

### Ignored Legacy Features

Per user request, the following from the original script are NOT implemented:

- ❌ Freeplays (legacy construct)
- ❌ Kickbacks (legacy construct)
- ❌ Christian/Mark sub-agent logic
- ❌ Cole/Kaufman logic
- ❌ Dro (4th agent) - system focuses on 3 core agents only

### Agent Names

The system currently uses placeholder agent names in `engine/compute.py`:
```python
CORE_AGENTS = {"Gabe", "Trev", "Orso"}
```

This constant is defined but not actively used (filtering happens naturally since only 3 agents exist). If a 4th agent is added in the future, the split rules will only apply when exactly 3 agents are present.

## Example Calculations

### Example 1: Even Split
```
Book Total: $900
Gabe: $300 (8 players)
Trev: $300 (7 players)
Orso: $300 (6 players)

Splits: 33.3% / 33.3% / 33.3%
Final Balances: $300 / $300 / $300
```

### Example 2: Low Exposure
```
Book Total: $900
Gabe: $600 (8 players)
Trev: $200 (3 players) ← Low exposure
Orso: $100 (7 players)

Splits: 40% / 20% / 40%
Final Balances: $360 / $180 / $360
```

### Example 3: Dominant Winner
```
Book Total: $1,100
Gabe: $900 (8 players) ← Dominant (81.8%)
Trev: $100 (7 players)
Orso: $100 (6 players)

Splits: 40% / 30% / 30%
Final Balances: $440 / $330 / $330
```

### Example 4: Combined Rule
```
Book Total: $1,100
Gabe: $900 (8 players) ← Dominant
Trev: $150 (3 players) ← Low exposure
Orso: $50 (7 players) ← Middle

Splits: 45% / 15% / 35%
Final Balances: $495 / $165 / $385
```

### Example 5: Kevin Bubble (Active)
```
Kevin's Previous Balance: $75
Kevin's This Week: -$50 (owes $50)

Total: $75 + (-$50) = $25
Action: Add to balance (< $100 threshold)
Kevin's Weekly Amount: $0 (hidden from settlement)
New Balance: $25
```

### Example 6: Kevin Bubble (Triggered)
```
Kevin's Previous Balance: $75
Kevin's This Week: $150 (wins $150)

Total: $75 + $150 = $225
Action: Exceeds threshold, apply full amount
Kevin's Weekly Amount: $150 (shown in settlement)
New Balance: $0
```

## Support

For questions or issues with split calculations:
1. Check the test suite: `python scripts/test_split_logic.py`
2. Review this document
3. Check the UI explanation cards (green and orange)
4. Verify agent player counts and weekly totals meet thresholds
