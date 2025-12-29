from engine.settlement import compute_transfers
from engine.split_rules import (
    calculate_split_percentages,
    calculate_final_balances,
    format_split_explanation
)


def compute_dashboard(rows, conn=None):
    """
    Compute dashboard data with advanced split rules.

    Args:
        rows: list of player dicts with week_amount, player_id, agent, etc.
        conn: optional database connection for Kevin bubble logic

    Returns:
        tuple: (agents, book_total, final_balance, transfers, split_info)
    """

    # Apply Kevin bubble logic if we have a database connection
    kevin_explanation = ""
    if conn:
        from engine.kevin_logic import apply_kevin_bubble_logic
        cur = conn.cursor()
        rows, kevin_explanation = apply_kevin_bubble_logic(cur, rows)
        cur.close()

    agents = {}
    book_total = 0.0

    # Filter out Dro (4th agent) - only process the 3 core agents
    CORE_AGENTS = {"Gabe", "Trev", "Orso"}  # Update these names to match your actual agent names

    for r in rows:
        agent = r["agent"]
        week_amt = float(r["week_amount"] or 0.0)

        # Agent perspective (opposite of player):
        # DB: positive week_amt = player won (bad for agent)
        # DB: negative week_amt = player lost (good for agent)
        # So we negate to get agent's perspective:
        # agent_net positive = agent revenue (player lost, owes us)
        # agent_net negative = agent owes player (player won)
        agent_net = -week_amt
        book_total += agent_net

        # Action from agent's perspective:
        # Positive agent_net = agent revenue (player lost) → Request payment from player
        # Negative agent_net = agent loss (player won) → Pay the player
        action = "Request" if agent_net > 0 else "Pay"
        abs_amt = abs(agent_net)

        agents.setdefault(agent, {"players": [], "net": 0.0, "num_players": 0})
        agents[agent]["net"] += agent_net
        agents[agent]["num_players"] += 1

        agents[agent]["players"].append({
            **r,
            "profit": agent_net,
            "action": action,
            "abs_amount": abs_amt,
        })

    # Calculate split percentages based on business rules
    splits = calculate_split_percentages(agents, book_total)
    final_balances = calculate_final_balances(agents, book_total, splits)

    # Generate split explanation
    split_explanation = format_split_explanation(agents, splits, book_total)

    # IMPORTANT: payer/receiver definition
    # If net > final_balance => you pay (you made more than your share)
    # If net < final_balance => you receive
    for agent_name, a in agents.items():
        a["final_balance"] = final_balances.get(agent_name, 0.0)
        a["split_percentage"] = splits.get(agent_name, 0.0)
        a["settlement"] = a["net"] - a["final_balance"]  # >0 pays, <0 receives

        # Sort players: Pay then Request, then Name A-Z
        action_order = {"Pay": 0, "Request": 1}
        a["players"].sort(key=lambda p: (action_order[p["action"]], (p.get("display_name") or "").lower()))

    transfers = compute_transfers(agents)

    # Create split_info dict for template
    split_info = {
        "explanation": split_explanation,
        "kevin_bubble": kevin_explanation,
        "splits": splits,
    }

    # Note: final_balance is now agent-specific, but we'll keep a "default" for backwards compat
    # Use the average final balance as the default
    avg_final_balance = sum(final_balances.values()) / max(len(final_balances), 1) if final_balances else 0

    return agents, book_total, avg_final_balance, transfers, split_info
