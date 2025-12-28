from engine.settlement import compute_transfers

def compute_dashboard(rows):
    agents = {}
    book_total = 0.0

    for r in rows:
        agent = r["agent"]
        week_amt = float(r["week_amount"] or 0.0)

        # House profit
        profit = -week_amt
        book_total += profit

        action = "Pay" if profit < 0 else "Request"
        abs_amt = abs(profit)

        agents.setdefault(agent, {"players": [], "net": 0.0, "num_players": 0})
        agents[agent]["net"] += profit
        agents[agent]["num_players"] += 1

        agents[agent]["players"].append({
            **r,
            "profit": profit,
            "action": action,
            "abs_amount": abs_amt,
        })

    agent_count = max(len(agents), 1)
    final_balance = book_total / agent_count

    # IMPORTANT: payer/receiver definition 
    # If net > final_balance => you pay (you made more than your share)
    # If net < final_balance => you receive
    for a in agents.values():
        a["final_balance"] = final_balance
        a["settlement"] = a["net"] - final_balance  # >0 pays, <0 receives

        # Sort players: Pay then Request, then Name A-Z
        action_order = {"Pay": 0, "Request": 1}
        a["players"].sort(key=lambda p: (action_order[p["action"]], (p.get("display_name") or "").lower()))

    transfers = compute_transfers(agents)
    return agents, book_total, final_balance, transfers
