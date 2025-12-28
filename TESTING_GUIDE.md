# Split Rules Testing Guide

## Quick Start

Run the automated test suite:
```bash
python scripts/test_split_logic.py
```

Expected output: `Results: 8 passed, 0 failed`

## Manual Testing Scenarios

### Scenario 1: Test Low Exposure Rule

**Setup:**
1. Create 3 agents (Gabe, Trev, Orso)
2. Assign 8 players to Gabe
3. Assign 3 players to Trev (< 5 threshold)
4. Assign 7 players to Orso
5. Set weekly amounts to create ~$200 total for Trev (< $500 threshold)

**Expected Result:**
- Split: Gabe 40%, Trev 20%, Orso 40%
- UI shows green "Low exposure rule" card
- Trev's split percentage shows 20.0%

---

### Scenario 2: Test Dominant Winner Rule

**Setup:**
1. Create week with book total > $1,000
2. Make one agent account for > 75% of the winnings
3. Ensure no low exposure agents exist (all have 5+ players OR $500+ total)

**Expected Result:**
- Split: Dominant 40%, Others 30% each
- UI shows green "Dominant winner rule" card
- Explanation shows percentage calculation

---

### Scenario 3: Test Combined Rule

**Setup:**
1. Create week with book total > $1,000
2. Make one agent dominant (> 75% of winnings)
3. Make another agent low exposure (< 5 players AND < $500)

**Expected Result:**
- Split: Dominant 45%, Middle 35%, Low 15%
- UI shows green "Combined rule applied" card

---

### Scenario 4: Test Kevin Bubble (Below Threshold)

**Setup:**
1. Ensure Kevin (pyr109) exists as a player
2. Set Kevin's weekly amount to something < $100 (e.g., $75)
3. Check database for existing balance

**Expected Result:**
- Kevin's amount added to running balance
- Kevin's weekly amount set to $0 in calculations
- UI shows orange "Kevin bubble" card
- Database `kevin_balance` table updated

**Verify:**
```sql
SELECT * FROM kevin_balance
WHERE player_instance_id = (
  SELECT id FROM player_instances WHERE player_id = 'pyr109' AND is_current = true
);
```

---

### Scenario 5: Test Kevin Bubble (Exceeds Threshold)

**Setup:**
1. Set Kevin's previous balance to $50 (manually update DB)
2. Set Kevin's weekly amount to $100 (total = $150)

**Expected Result:**
- Full $100 applied to settlement
- Running balance reset to $0
- UI shows orange card explaining threshold exceeded

---

### Scenario 6: Test Even Split (Default)

**Setup:**
1. Create week with no special conditions
2. All agents have 5+ players
3. All agents have reasonable weekly totals

**Expected Result:**
- Split: 33.3% / 33.3% / 33.3%
- UI shows "Even split" card
- All final balances equal

---

## Database Verification Queries

### Check Kevin's Balance
```sql
SELECT
  kb.current_balance,
  kb.updated_at,
  pi.player_id,
  pi.display_name
FROM kevin_balance kb
JOIN player_instances pi ON pi.id = kb.player_instance_id
WHERE pi.player_id = 'pyr109';
```

### Check Current Week Player Counts
```sql
SELECT
  a.name as agent,
  COUNT(*) as num_players,
  SUM(wr.week_amount) as total_amount
FROM weekly_raw wr
JOIN player_instances pi ON pi.id = wr.player_instance_id
JOIN agents a ON a.id = pi.agent_id
WHERE wr.week_id = (SELECT week_id FROM weeks ORDER BY week_id DESC LIMIT 1)
GROUP BY a.name
ORDER BY a.name;
```

### Check Split Calculation (Manual)
```python
# In Python console
from engine.split_rules import calculate_split_percentages

agents = {
    'Gabe': {'net': 600, 'num_players': 8},
    'Trev': {'net': 200, 'num_players': 3},
    'Orso': {'net': 100, 'num_players': 7}
}
book_total = 900

splits = calculate_split_percentages(agents, book_total)
print(splits)
# Expected: {'Gabe': 0.4, 'Trev': 0.2, 'Orso': 0.4}
```

## Common Issues

### Issue: Split rules not applying

**Check:**
1. Is the week actually > $1,000 for dominant winner rule?
2. Does the low exposure agent have < 5 players AND < $500?
3. Are there exactly 3 agents? (Rules only apply with 3 agents)

### Issue: Kevin bubble not working

**Check:**
1. Does Kevin exist as `pyr109` with `is_current = true`?
2. Does `kevin_balance` table have a row for Kevin?
3. Is the database connection being passed to `compute_dashboard()`?

### Issue: Wrong explanation showing

**Check:**
1. Re-run tests: `python scripts/test_split_logic.py`
2. Check that 0.20 is checked before 0.40 in `format_split_explanation()`
3. Verify split values match expected rule

## Testing Checklist

Before deploying:

- [ ] Run automated test suite (all 8 tests pass)
- [ ] Test even split in UI
- [ ] Test low exposure in UI
- [ ] Test dominant winner in UI
- [ ] Test combined rule in UI
- [ ] Test Kevin bubble (below threshold)
- [ ] Test Kevin bubble (exceeds threshold)
- [ ] Verify split percentages show correctly on agent cards
- [ ] Verify explanation cards appear with correct colors
- [ ] Verify settlement transfers calculate correctly
- [ ] Test with real historical data

## Performance Notes

- Split calculation is O(n) where n = number of agents (always 3)
- Kevin bubble logic requires one DB read and one DB write per dashboard load
- All calculations happen in-memory after data fetch
- No impact on page load time (< 1ms for split calculations)

## Edge Cases Handled

✓ Agent with 0 players (treated as even split)
✓ Negative weekly totals (absolute value used for low exposure check)
✓ Exactly 5 players (no penalty - even split)
✓ Exactly $500 total (no penalty - even split)
✓ Exactly $1,000 book total (no dominant winner bonus)
✓ Kevin doesn't exist (bubble logic silently skipped)
✓ Multiple low exposure agents (each gets 20%)
✓ Dominant winner IS the low exposure agent (combined rule not applied)

## Debugging Tips

1. **Enable verbose logging:**
   ```python
   # In engine/split_rules.py, add print statements
   print(f"Low exposure agents: {low_exposure_agents}")
   print(f"Dominant winner: {dominant_winner}")
   print(f"Final splits: {splits}")
   ```

2. **Check intermediate values:**
   ```python
   # In dashboard endpoint
   print(f"Book total: {book_total}")
   print(f"Agents: {[(name, a['net'], a['num_players']) for name, a in agents.items()]}")
   print(f"Split info: {split_info}")
   ```

3. **Verify database state:**
   ```bash
   # Check kevin_balance table
   psql $DATABASE_URL -c "SELECT * FROM kevin_balance;"

   # Check player counts
   psql $DATABASE_URL -c "SELECT a.name, COUNT(*) FROM player_instances pi JOIN agents a ON a.id = pi.agent_id WHERE pi.is_current = true GROUP BY a.name;"
   ```

## Next Steps After Testing

Once all tests pass:

1. Review SPLIT_RULES_SUMMARY.md for full documentation
2. Test with real historical data
3. Verify UI displays correctly in all browsers
4. Document any agent name changes needed
5. Consider adding admin panel to view/modify Kevin's balance manually
