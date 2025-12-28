# Deployment Fixes V2 - Sign Inversion & UI Cleanup

## Issues Fixed

### 1. Sign Inversion Corrected ✅
**Problem:** Net amounts were inverted - when players lost, agents showed positive net
**Root Cause:** `profit = -week_amt` was inverting the natural sign
**Fix:** Changed to `agent_net = week_amt` to preserve correct signs
**Result:**
- Player loses $100 → agent shows -$100 net (they owe us)
- Player wins $100 → agent shows +$100 net (we owe them)
- Book total now represents total agent winnings (not house profit)

### 2. Split Explanation Simplified ✅
**Problem:** Split explanation was verbose with multiple lines
**Fix:** Reduced to single-line messages:
- "Standard splits this week"
- "Trev didn't have enough players or volume"
- "Gabe had a great week"
- "Gabe had a great week, Trev didn't have enough volume"

### 3. Split Notice Relocated ✅
**Problem:** Split notice was in prominent colored box above transfers
**Fix:** Moved to footer-note format below "This is the simplest way..." message
**Result:** Much less prominent, same styling as other footer notes

## Code Changes

### [engine/compute.py](engine/compute.py:35-56)

**Before:**
```python
profit = -week_amt          # ← Inverted sign
book_total += profit
action = "Pay" if profit < 0 else "Request"
agents[agent]["net"] += profit
```

**After:**
```python
agent_net = week_amt        # ← Correct sign
book_total += agent_net
action = "Pay" if agent_net > 0 else "Request"
agents[agent]["net"] += agent_net
```

### [engine/split_rules.py](engine/split_rules.py:104-141)

**Before:**
```python
explanation.append(f"Low exposure rule: {name} 20%, others 40% each")
explanation.append(f"({name} had {num_players} players and ${net:.2f} total)")
return "\n".join(explanation)
```

**After:**
```python
return f"{low_agent} didn't have enough players or volume"
```

### [app/templates/dashboard.html](app/templates/dashboard.html:76-81)

**Before:**
```html
<div style="padding: 10px; background: rgba(52, 199, 89, 0.08)...">
  <div>Split Calculation</div>
  <div>{{ split_info.explanation }}</div>
</div>
```

**After:**
```html
<div class="footer-note">
  This is the simplest way to equalize everyone's take for the week.
  <br>{{ split_info.explanation }}
</div>
```

## Sign Convention Reference

### Database (week_amount)
- Positive = Player wins (agent owes player)
- Negative = Player loses (player owes agent)

### Agent Net (displayed)
- Positive = Agent's players won overall (we pay agent)
- Negative = Agent's players lost overall (agent pays us)

### Book Total (displayed)
- Sum of all agent nets
- Positive = Overall we owe money
- Negative = Overall we collect money

### Settlement Logic
- Agent net > final_balance → Agent pays (made more than fair share)
- Agent net < final_balance → Agent receives (made less than fair share)

## Example Scenarios

### Scenario 1: Agent Loses
```
Trev's players: -$1,781 total
Display: Net: -$1,781
Meaning: Trev's players lost $1,781 (they owe us)
Settlement: Trev receives money (because others made profit)
```

### Scenario 2: Agent Wins
```
Gabe's players: +$900 total
Display: Net: +$900
Meaning: Gabe's players won $900 (we owe them)
Settlement: Gabe pays (because he made the profit)
```

### Scenario 3: Mixed Week
```
Gabe: +$500
Trev: -$300
Orso: +$100

Book Total: +$300 (we owe $300 overall)
Split: Each gets $100 (even split)

Settlements:
- Gabe pays $400 (made $500, entitled to $100)
- Trev receives $400 (made -$300, entitled to $100)
- Orso receives $0 (made $100, entitled to $100)
```

## UI Examples

### Footer Note (New Format)
```
This is the simplest way to equalize everyone's take for the week.
Standard splits this week
```

or

```
This is the simplest way to equalize everyone's take for the week.
Trev didn't have enough players or volume
```

## Testing

Verify these scenarios:

1. **Agent loses money:**
   - Net shows negative
   - Gets paid by winners in settlement

2. **Agent wins money:**
   - Net shows positive
   - Pays losers in settlement

3. **Split messages:**
   - Even split: "Standard splits this week"
   - Low exposure: "[Name] didn't have enough players or volume"
   - Dominant: "[Name] had a great week"
   - Combined: "[Name] had a great week, [Name] didn't have enough volume"

4. **UI placement:**
   - Split message appears in footer-note
   - Same styling as "This is the simplest way..." message
   - No colored boxes or prominent styling
