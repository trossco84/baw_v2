"""
Kevin (pyr109) specific logic: $100 bubble handling.

Kevin's weekly amounts accumulate in a running balance until the absolute value
exceeds $100, at which point the full amount is applied to the weekly settlement.
"""

import psycopg2


def get_kevin_instance_id(cur) -> int | None:
    """Get Kevin's current player_instance_id."""
    cur.execute("""
        SELECT id FROM player_instances
        WHERE player_id = 'pyr109' AND is_current = true
        LIMIT 1
    """)
    result = cur.fetchone()
    return result[0] if result else None


def get_kevin_balance(cur, kevin_instance_id: int) -> float:
    """Get Kevin's current running balance."""
    cur.execute("""
        SELECT current_balance FROM kevin_balance
        WHERE player_instance_id = %s
    """, (kevin_instance_id,))
    result = cur.fetchone()
    return float(result[0]) if result else 0.0


def update_kevin_balance(cur, kevin_instance_id: int, new_balance: float):
    """Update Kevin's running balance in the database."""
    cur.execute("""
        INSERT INTO kevin_balance (player_instance_id, current_balance, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (player_instance_id)
        DO UPDATE SET current_balance = EXCLUDED.current_balance, updated_at = NOW()
    """, (kevin_instance_id, new_balance))


def apply_kevin_bubble_logic(cur, player_rows: list) -> tuple[list, str]:
    """
    Apply $100 bubble logic to Kevin's weekly amount.

    Args:
        cur: database cursor
        player_rows: list of player dicts with week_amount, player_id, etc.

    Returns:
        tuple: (modified_player_rows, explanation_message)

    Logic:
    - If Kevin's weekly amount has |amount| < $100:
        - Add to running balance
        - Set his weekly amount to 0 (won't appear in settlement)
    - If Kevin's weekly amount has |amount| >= $100:
        - Apply full amount to settlement
        - Reset running balance to 0
    """

    kevin_instance_id = get_kevin_instance_id(cur)
    if not kevin_instance_id:
        return player_rows, ""

    # Find Kevin in player_rows
    kevin_row = None
    kevin_index = None
    for i, row in enumerate(player_rows):
        if row.get('player_id') == 'pyr109':
            kevin_row = row
            kevin_index = i
            break

    if not kevin_row:
        return player_rows, ""

    # Get current balance and weekly amount
    current_balance = get_kevin_balance(cur, kevin_instance_id)
    weekly_amount = float(kevin_row.get('week_amount', 0))

    # Calculate what the total would be
    potential_balance = current_balance + weekly_amount

    explanation = []

    # Apply bubble logic based on total (not just weekly amount)
    if abs(potential_balance) < 100:
        # Total is still under threshold - add to running balance, zero out weekly
        update_kevin_balance(cur, kevin_instance_id, potential_balance)

        explanation.append(f"Kevin bubble: ${weekly_amount:.2f} added to balance (now ${potential_balance:.2f})")
        explanation.append(f"Kevin's amount set to $0 for this week (bubble active)")

        # Modify Kevin's row to have 0 amount
        modified_rows = player_rows.copy()
        modified_rows[kevin_index] = {**kevin_row, 'week_amount': 0}

        return modified_rows, "\n".join(explanation)

    else:
        # Total exceeds threshold - apply the FULL BALANCE (not just weekly amount)
        total_amount = potential_balance
        update_kevin_balance(cur, kevin_instance_id, 0.0)

        if current_balance != 0:
            explanation.append(f"Kevin bubble: ${weekly_amount:.2f} this week, ${current_balance:.2f} accumulated")
            explanation.append(f"Total ${total_amount:.2f} exceeds $100 threshold - applying full amount")
        else:
            explanation.append(f"Kevin bubble: ${weekly_amount:.2f} exceeds $100 threshold")

        # Modify Kevin's row to show the TOTAL amount (accumulated + this week)
        modified_rows = player_rows.copy()
        modified_rows[kevin_index] = {**kevin_row, 'week_amount': total_amount}

        return modified_rows, "\n".join(explanation)


def get_kevin_balance_status(conn) -> dict:
    """
    Get Kevin's current balance status for display.

    Args:
        conn: database connection

    Returns:
        dict: {balance: float, threshold: float, is_active: bool}
    """
    cur = conn.cursor()
    kevin_instance_id = get_kevin_instance_id(cur)

    if not kevin_instance_id:
        return {"balance": 0.0, "threshold": 100.0, "is_active": False}

    balance = get_kevin_balance(cur, kevin_instance_id)

    return {
        "balance": balance,
        "threshold": 100.0,
        "is_active": abs(balance) > 0
    }
