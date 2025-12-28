"""
Weekly split adjustment rules for agent settlement calculations.

Default: Even 33.33% / 33.33% / 33.33% split
Special rules can adjust splits based on volume, player count, and dominance.
"""

def calculate_split_percentages(agents: dict, book_total: float) -> dict:
    """
    Calculate split percentages for each agent based on business rules.

    Args:
        agents: dict mapping agent_name -> {net, num_players, ...}
        book_total: total house profit for the week

    Returns:
        dict mapping agent_name -> split_percentage (as decimal, e.g., 0.33)

    Rules applied in order:
    1. Low exposure rule: < 5 players AND |net| < $500 → 20% split (others get 40% each)
    2. Dominant winner rule: > 75% of winnings when week > $1K → 40% split (others get 30% each)
    3. Combined rule: Both dominant winner AND low exposure exist → 45%/35%/15% split
    """

    agent_names = list(agents.keys())
    num_agents = len(agent_names)

    if num_agents == 0:
        return {}

    # Default: even split
    splits = {name: 1.0 / num_agents for name in agent_names}

    # Only apply special rules if we have exactly 3 agents (Gabe, Trev, Orso)
    # Ignore Dro or any 4th agent
    if num_agents != 3:
        return splits

    # Identify low exposure agents (< 5 players AND |net| < $500)
    low_exposure_agents = []
    for name, data in agents.items():
        num_players = data.get("num_players", 0)
        net = abs(float(data.get("net", 0)))

        if num_players < 5 and net < 500:
            low_exposure_agents.append(name)

    # Identify dominant winner (> 75% of winnings when week > $1K)
    dominant_winner = None
    if book_total > 1000:
        for name, data in agents.items():
            net = float(data.get("net", 0))
            # Dominant winner has > 75% of the positive winnings
            if net > 0 and net > (book_total * 0.75):
                dominant_winner = name
                break

    # Apply split rules based on conditions

    # RULE 4: Combined edge case (dominant winner + low exposure)
    if dominant_winner and len(low_exposure_agents) > 0 and dominant_winner not in low_exposure_agents:
        # dominant_winner gets 45%, middle agent gets 35%, low_exposure agent gets 15%
        # Find the "middle" agent (not winner, not low exposure)
        middle_agent = None
        for name in agent_names:
            if name != dominant_winner and name not in low_exposure_agents:
                middle_agent = name
                break

        if middle_agent and len(low_exposure_agents) == 1:
            low_agent = low_exposure_agents[0]
            splits[dominant_winner] = 0.45
            splits[middle_agent] = 0.35
            splits[low_agent] = 0.15
            return splits

    # RULE 3: Dominant winner (> 75% of winnings when week > $1K)
    if dominant_winner and len(low_exposure_agents) == 0:
        # Winner gets 40%, others get 30% each
        for name in agent_names:
            if name == dominant_winner:
                splits[name] = 0.40
            else:
                splits[name] = 0.30
        return splits

    # RULE 2: Low exposure (< 5 players AND < $500 total)
    if len(low_exposure_agents) > 0:
        # Low exposure agent(s) get 20%, others split the remaining 80%
        num_normal_agents = num_agents - len(low_exposure_agents)
        normal_split = 0.80 / max(num_normal_agents, 1)

        for name in agent_names:
            if name in low_exposure_agents:
                splits[name] = 0.20
            else:
                splits[name] = normal_split
        return splits

    # RULE 1: Default even split (already set)
    return splits


def format_split_explanation(agents: dict, splits: dict, book_total: float) -> str:
    """
    Generate simple one-line explanation of the split calculation.

    Args:
        agents: dict mapping agent_name -> {net, num_players, ...}
        splits: dict mapping agent_name -> split_percentage
        book_total: total house profit for the week

    Returns:
        str: single-line explanation
    """

    # Check which rule was applied
    split_values = sorted(set(splits.values()), reverse=True)

    if len(split_values) == 1:
        # Even split
        return "Standard splits this week"

    elif 0.45 in split_values:
        # Combined rule (45/35/15)
        winner = [n for n, s in splits.items() if s == 0.45][0]
        low = [n for n, s in splits.items() if s == 0.15][0]
        return f"{winner} had a great week, {low} didn't have enough volume"

    elif 0.20 in split_values:
        # Low exposure rule (40/40/20)
        low_agents = [n for n, s in splits.items() if s == 0.20]
        low_agent = low_agents[0]
        return f"{low_agent} didn't have enough players or volume"

    elif 0.40 in split_values and 0.30 in split_values:
        # Dominant winner rule (40/30/30)
        winner = [n for n, s in splits.items() if s == 0.40][0]
        return f"{winner} had a great week"

    return "Standard splits this week"


def calculate_final_balances(agents: dict, book_total: float, splits: dict) -> dict:
    """
    Calculate final balance for each agent based on split percentages.

    Args:
        agents: dict mapping agent_name -> {net, num_players, ...}
        book_total: total house profit for the week
        splits: dict mapping agent_name -> split_percentage

    Returns:
        dict mapping agent_name -> final_balance
    """

    final_balances = {}
    for name, split_pct in splits.items():
        final_balances[name] = book_total * split_pct

    return final_balances
