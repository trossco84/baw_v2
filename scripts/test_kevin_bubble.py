#!/usr/bin/env python3
"""
Test Kevin bubble logic with database.
This script tests the $100 threshold logic for Kevin (pyr109).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
from dotenv import load_dotenv
from engine.kevin_logic import (
    get_kevin_instance_id,
    get_kevin_balance,
    update_kevin_balance,
    apply_kevin_bubble_logic
)

load_dotenv()


def setup_test_environment(conn):
    """Ensure Kevin exists and has a balance entry"""
    cur = conn.cursor()

    # Check if Kevin exists
    kevin_id = get_kevin_instance_id(cur)
    if not kevin_id:
        print("⚠️  Kevin (pyr109) not found in current players")
        print("Creating test Kevin player...")

        # Get or create an agent
        cur.execute("SELECT id FROM agents LIMIT 1")
        agent_result = cur.fetchone()
        if not agent_result:
            cur.execute("INSERT INTO agents (name) VALUES ('Test Agent') RETURNING id")
            agent_id = cur.fetchone()[0]
        else:
            agent_id = agent_result[0]

        # Create Kevin player instance
        cur.execute("""
            SELECT get_or_create_player_instance('pyr109', 'Kevin', %s, CURRENT_DATE)
        """, (agent_id,))
        kevin_id = cur.fetchone()[0]
        conn.commit()
        print(f"✓ Created Kevin with instance_id: {kevin_id}")

    # Ensure balance entry exists
    cur.execute("""
        INSERT INTO kevin_balance (player_instance_id, current_balance)
        VALUES (%s, 0.00)
        ON CONFLICT (player_instance_id) DO NOTHING
    """, (kevin_id,))
    conn.commit()

    return kevin_id


def test_bubble_below_threshold():
    """Test Kevin bubble when amount is below $100 threshold"""
    print("\n=== Test 1: Below Threshold ($75) ===")

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    kevin_id = setup_test_environment(conn)

    # Reset balance to $0
    update_kevin_balance(cur, kevin_id, 0.00)
    conn.commit()

    # Create test player row with Kevin having $75
    player_rows = [
        {'player_id': 'pyr109', 'week_amount': 75.0, 'display_name': 'Kevin'},
        {'player_id': 'pyr101', 'week_amount': 100.0, 'display_name': 'Other Player'}
    ]

    # Apply bubble logic
    modified_rows, explanation = apply_kevin_bubble_logic(cur, player_rows)
    conn.commit()

    # Get new balance
    new_balance = get_kevin_balance(cur, kevin_id)

    print(f"Original amount: $75.00")
    print(f"Modified amount: ${modified_rows[0]['week_amount']:.2f}")
    print(f"New balance: ${new_balance:.2f}")
    print(f"Explanation: {explanation}")

    assert modified_rows[0]['week_amount'] == 0, "Kevin's amount should be $0"
    assert new_balance == 75.0, f"Balance should be $75, got ${new_balance}"
    print("✓ PASSED")

    conn.close()


def test_bubble_exceeds_threshold():
    """Test Kevin bubble when accumulated total exceeds $100 threshold"""
    print("\n=== Test 2: Accumulated Total Exceeds Threshold ===")

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    kevin_id = setup_test_environment(conn)

    # Set balance to $50
    update_kevin_balance(cur, kevin_id, 50.00)
    conn.commit()

    # Create test player row with Kevin having $150 this week
    # Total would be $50 (prev) + $150 (this week) = $200
    player_rows = [
        {'player_id': 'pyr109', 'week_amount': 150.0, 'display_name': 'Kevin'}
    ]

    # Apply bubble logic
    modified_rows, explanation = apply_kevin_bubble_logic(cur, player_rows)
    conn.commit()

    # Get new balance
    new_balance = get_kevin_balance(cur, kevin_id)

    print(f"Previous balance: $50.00")
    print(f"This week amount: $150.00")
    print(f"Total: $200.00")
    print(f"Modified amount (applied): ${modified_rows[0]['week_amount']:.2f}")
    print(f"New balance: ${new_balance:.2f}")
    print(f"Explanation: {explanation}")

    # Should apply the TOTAL ($200), not just this week's amount
    assert modified_rows[0]['week_amount'] == 200.0, f"Kevin's amount should be $200 (total), got ${modified_rows[0]['week_amount']}"
    assert new_balance == 0.0, f"Balance should be $0, got ${new_balance}"
    print("✓ PASSED")

    conn.close()


def test_bubble_accumulation():
    """Test Kevin bubble accumulates over multiple weeks"""
    print("\n=== Test 3: Accumulation Over Multiple Weeks ===")

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    kevin_id = setup_test_environment(conn)

    # Reset balance
    update_kevin_balance(cur, kevin_id, 0.00)
    conn.commit()

    # Week 1: $30
    rows1 = [{'player_id': 'pyr109', 'week_amount': 30.0, 'display_name': 'Kevin'}]
    _, expl1 = apply_kevin_bubble_logic(cur, rows1)
    conn.commit()
    balance1 = get_kevin_balance(cur, kevin_id)
    print(f"Week 1: $30 → Balance: ${balance1:.2f}")

    # Week 2: $40
    rows2 = [{'player_id': 'pyr109', 'week_amount': 40.0, 'display_name': 'Kevin'}]
    _, expl2 = apply_kevin_bubble_logic(cur, rows2)
    conn.commit()
    balance2 = get_kevin_balance(cur, kevin_id)
    print(f"Week 2: $40 → Balance: ${balance2:.2f}")

    # Week 3: $50 (total = $70 + $50 = $120, exceeds threshold)
    rows3 = [{'player_id': 'pyr109', 'week_amount': 50.0, 'display_name': 'Kevin'}]
    modified3, expl3 = apply_kevin_bubble_logic(cur, rows3)
    conn.commit()
    balance3 = get_kevin_balance(cur, kevin_id)
    print(f"Week 3: $50 → Total would be $120")
    print(f"Amount applied: ${modified3[0]['week_amount']:.2f}")
    print(f"Final balance: ${balance3:.2f}")

    assert balance1 == 30.0, "Week 1 balance should be $30"
    assert balance2 == 70.0, "Week 2 balance should be $70"
    assert modified3[0]['week_amount'] == 120.0, f"Week 3 should apply full $120 total, got ${modified3[0]['week_amount']}"
    assert balance3 == 0.0, "Week 3 balance should be reset to $0"
    print("✓ PASSED")

    conn.close()


def test_bubble_negative_amounts():
    """Test Kevin bubble with negative amounts (losses)"""
    print("\n=== Test 4: Negative Amounts (Losses) ===")

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    kevin_id = setup_test_environment(conn)

    # Set balance to $50
    update_kevin_balance(cur, kevin_id, 50.00)
    conn.commit()

    # Kevin loses $30
    rows = [{'player_id': 'pyr109', 'week_amount': -30.0, 'display_name': 'Kevin'}]
    modified, explanation = apply_kevin_bubble_logic(cur, rows)
    conn.commit()

    new_balance = get_kevin_balance(cur, kevin_id)

    print(f"Previous balance: $50.00")
    print(f"Weekly loss: -$30.00")
    print(f"Modified amount: ${modified[0]['week_amount']:.2f}")
    print(f"New balance: ${new_balance:.2f}")
    print(f"Explanation: {explanation}")

    # Loss of $30 brings balance to $20 (< $100), should be hidden
    assert modified[0]['week_amount'] == 0.0, "Kevin's loss should be hidden (< $100)"
    assert new_balance == 20.0, f"Balance should be $20, got ${new_balance}"
    print("✓ PASSED")

    conn.close()


def test_bubble_large_loss():
    """Test Kevin bubble with large loss that exceeds threshold"""
    print("\n=== Test 5: Large Loss Exceeds Threshold ===")

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    kevin_id = setup_test_environment(conn)

    # Set balance to $50
    update_kevin_balance(cur, kevin_id, 50.00)
    conn.commit()

    # Kevin loses $150 (absolute value > $100)
    rows = [{'player_id': 'pyr109', 'week_amount': -150.0, 'display_name': 'Kevin'}]
    modified, explanation = apply_kevin_bubble_logic(cur, rows)
    conn.commit()

    new_balance = get_kevin_balance(cur, kevin_id)

    print(f"Previous balance: $50.00")
    print(f"Weekly loss: -$150.00")
    print(f"Modified amount: ${modified[0]['week_amount']:.2f}")
    print(f"New balance: ${new_balance:.2f}")
    print(f"Explanation: {explanation}")

    # Total loss of -$100 (-$150 + $50 prev) exceeds threshold, should apply full amount
    expected_total = 50.0 + (-150.0)  # = -$100
    assert modified[0]['week_amount'] == expected_total, f"Kevin's total should be ${expected_total}, got ${modified[0]['week_amount']}"
    assert new_balance == 0.0, f"Balance should be reset to $0, got ${new_balance}"
    print("✓ PASSED")

    conn.close()


def main():
    """Run all Kevin bubble tests"""
    print("=" * 60)
    print("Kevin Bubble Logic Test Suite")
    print("=" * 60)

    try:
        test_bubble_below_threshold()
        test_bubble_exceeds_threshold()
        test_bubble_accumulation()
        test_bubble_negative_amounts()
        test_bubble_large_loss()

        print("\n" + "=" * 60)
        print("✓ All Kevin bubble tests passed!")
        print("=" * 60)
        return 0

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
