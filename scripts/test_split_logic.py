#!/usr/bin/env python3
"""
Test script for all split calculation and Kevin bubble logic.
This script tests the business rules without hitting the database.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.split_rules import calculate_split_percentages, format_split_explanation, calculate_final_balances


def test_even_split():
    """Test default even split (33.33% each)"""
    print("\n=== Test 1: Even Split (Default) ===")
    agents = {
        'Gabe': {'net': 300, 'num_players': 8},
        'Trev': {'net': 300, 'num_players': 7},
        'Orso': {'net': 300, 'num_players': 6}
    }
    book_total = 900

    splits = calculate_split_percentages(agents, book_total)
    explanation = format_split_explanation(agents, splits, book_total)
    final_balances = calculate_final_balances(agents, book_total, splits)

    print(f"Splits: {splits}")
    print(f"Final Balances: {final_balances}")
    print(f"Explanation:\n{explanation}")

    assert splits['Gabe'] == splits['Trev'] == splits['Orso'] == 1/3
    print("✓ PASSED")


def test_low_exposure():
    """Test low exposure rule (< 5 players AND < $500 → 20% split)"""
    print("\n=== Test 2: Low Exposure Rule ===")
    agents = {
        'Gabe': {'net': 600, 'num_players': 8},
        'Trev': {'net': 200, 'num_players': 3},  # Low exposure: 3 players, $200
        'Orso': {'net': 100, 'num_players': 7}
    }
    book_total = 900

    splits = calculate_split_percentages(agents, book_total)
    explanation = format_split_explanation(agents, splits, book_total)
    final_balances = calculate_final_balances(agents, book_total, splits)

    print(f"Splits: {splits}")
    print(f"Final Balances: {final_balances}")
    print(f"Explanation:\n{explanation}")

    assert splits['Trev'] == 0.20, f"Expected Trev 0.20, got {splits['Trev']}"
    assert splits['Gabe'] == 0.40 and splits['Orso'] == 0.40
    print("✓ PASSED")


def test_low_exposure_edge_case():
    """Test that low exposure doesn't apply if player count >= 5"""
    print("\n=== Test 3: Low Exposure Edge Case (5 players = no penalty) ===")
    agents = {
        'Gabe': {'net': 600, 'num_players': 8},
        'Trev': {'net': 200, 'num_players': 5},  # 5 players (threshold), $200
        'Orso': {'net': 100, 'num_players': 7}
    }
    book_total = 900

    splits = calculate_split_percentages(agents, book_total)
    explanation = format_split_explanation(agents, splits, book_total)

    print(f"Splits: {splits}")
    print(f"Explanation:\n{explanation}")

    # Should be even split (5 players meets threshold)
    assert splits['Trev'] == splits['Gabe'] == splits['Orso'] == 1/3
    print("✓ PASSED")


def test_low_exposure_edge_case_2():
    """Test that low exposure doesn't apply if amount >= $500"""
    print("\n=== Test 4: Low Exposure Edge Case ($500+ = no penalty) ===")
    agents = {
        'Gabe': {'net': 300, 'num_players': 8},
        'Trev': {'net': 500, 'num_players': 3},  # 3 players but $500 (threshold)
        'Orso': {'net': 100, 'num_players': 7}
    }
    book_total = 900

    splits = calculate_split_percentages(agents, book_total)
    explanation = format_split_explanation(agents, splits, book_total)

    print(f"Splits: {splits}")
    print(f"Explanation:\n{explanation}")

    # Should be even split ($500 meets threshold)
    assert splits['Trev'] == splits['Gabe'] == splits['Orso'] == 1/3
    print("✓ PASSED")


def test_dominant_winner():
    """Test dominant winner rule (> 75% of winnings when book > $1K → 40% split)"""
    print("\n=== Test 5: Dominant Winner Rule ===")
    agents = {
        'Gabe': {'net': 900, 'num_players': 8},  # 900/1100 = 81.8% > 75%
        'Trev': {'net': 100, 'num_players': 7},
        'Orso': {'net': 100, 'num_players': 6}
    }
    book_total = 1100

    splits = calculate_split_percentages(agents, book_total)
    explanation = format_split_explanation(agents, splits, book_total)
    final_balances = calculate_final_balances(agents, book_total, splits)

    print(f"Splits: {splits}")
    print(f"Final Balances: {final_balances}")
    print(f"Explanation:\n{explanation}")

    assert splits['Gabe'] == 0.40, f"Expected Gabe 0.40, got {splits['Gabe']}"
    assert splits['Trev'] == 0.30 and splits['Orso'] == 0.30
    print("✓ PASSED")


def test_dominant_winner_threshold():
    """Test that dominant winner doesn't apply if book total <= $1K"""
    print("\n=== Test 6: Dominant Winner Threshold ($1K minimum) ===")
    agents = {
        'Gabe': {'net': 800, 'num_players': 8},  # 800/1000 = 80% > 75%, but book = $1K
        'Trev': {'net': 100, 'num_players': 7},
        'Orso': {'net': 100, 'num_players': 6}
    }
    book_total = 1000

    splits = calculate_split_percentages(agents, book_total)
    explanation = format_split_explanation(agents, splits, book_total)

    print(f"Splits: {splits}")
    print(f"Explanation:\n{explanation}")

    # Should be even split (book total not > 1000)
    assert splits['Gabe'] == splits['Trev'] == splits['Orso'] == 1/3
    print("✓ PASSED")


def test_combined_rule():
    """Test combined rule (dominant winner + low exposure → 45%/35%/15% split)"""
    print("\n=== Test 7: Combined Rule (Dominant + Low Exposure) ===")
    agents = {
        'Gabe': {'net': 900, 'num_players': 8},  # Dominant: 900/1100 = 81.8%
        'Trev': {'net': 150, 'num_players': 3},  # Low exposure: 3 players, $150
        'Orso': {'net': 50, 'num_players': 7}    # Middle agent
    }
    book_total = 1100

    splits = calculate_split_percentages(agents, book_total)
    explanation = format_split_explanation(agents, splits, book_total)
    final_balances = calculate_final_balances(agents, book_total, splits)

    print(f"Splits: {splits}")
    print(f"Final Balances: {final_balances}")
    print(f"Explanation:\n{explanation}")

    assert splits['Gabe'] == 0.45, f"Expected Gabe 0.45, got {splits['Gabe']}"
    assert splits['Orso'] == 0.35, f"Expected Orso 0.35, got {splits['Orso']}"
    assert splits['Trev'] == 0.15, f"Expected Trev 0.15, got {splits['Trev']}"
    print("✓ PASSED")


def test_settlement_calculation():
    """Test full settlement calculation including transfers"""
    print("\n=== Test 8: Full Settlement Calculation ===")
    from engine.settlement import compute_transfers

    agents = {
        'Gabe': {'net': 600, 'num_players': 8},
        'Trev': {'net': -200, 'num_players': 7},
        'Orso': {'net': -100, 'num_players': 6}
    }
    book_total = 300  # Total house profit

    splits = calculate_split_percentages(agents, book_total)
    final_balances = calculate_final_balances(agents, book_total, splits)

    # Calculate settlements
    for name, agent in agents.items():
        agent['final_balance'] = final_balances[name]
        agent['split_percentage'] = splits[name]
        agent['settlement'] = agent['net'] - agent['final_balance']

    transfers = compute_transfers(agents)

    print(f"Splits: {splits}")
    print(f"Final Balances: {final_balances}")
    print(f"Settlements: {[(name, a['settlement']) for name, a in agents.items()]}")
    print(f"Transfers: {transfers}")

    # Verify settlement math adds up to zero
    total_settlement = sum(a['settlement'] for a in agents.values())
    assert abs(total_settlement) < 0.01, f"Settlement should sum to 0, got {total_settlement}"
    print("✓ PASSED")


def main():
    """Run all tests"""
    print("=" * 60)
    print("BAW Split Logic Test Suite")
    print("=" * 60)

    tests = [
        test_even_split,
        test_low_exposure,
        test_low_exposure_edge_case,
        test_low_exposure_edge_case_2,
        test_dominant_winner,
        test_dominant_winner_threshold,
        test_combined_rule,
        test_settlement_calculation,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ ERROR: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
