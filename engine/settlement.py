def compute_transfers(agents: dict, cents_tolerance: float = 0.01):
    """
    agents: dict like { "Gabe": {"settlement": +123.45}, "Trev": {"settlement": -123.45} }
    settlement definition:
      > 0 => agent owes money (payer)
      < 0 => agent is owed money (receiver)
    Returns list of transfers: [{"from": "Gabe", "to": "Trev", "amount": 123.45}, ...]
    """
    payers = []
    receivers = []

    for name, a in agents.items():
        s = float(a.get("settlement", 0.0))
        if s > cents_tolerance:
            payers.append([name, s])          # owes
        elif s < -cents_tolerance:
            receivers.append([name, -s])      # is owed (store positive amount owed)

    # Sort largest first so we settle quickly/cleanly
    payers.sort(key=lambda x: x[1], reverse=True)
    receivers.sort(key=lambda x: x[1], reverse=True)

    transfers = []
    i = j = 0

    while i < len(payers) and j < len(receivers):
        payer_name, payer_amt = payers[i]
        recv_name, recv_amt = receivers[j]

        amt = min(payer_amt, recv_amt)
        amt = round(amt, 2)

        if amt >= cents_tolerance:
            transfers.append({"from": payer_name, "to": recv_name, "amount": amt})

        payer_amt = round(payer_amt - amt, 2)
        recv_amt = round(recv_amt - amt, 2)

        payers[i][1] = payer_amt
        receivers[j][1] = recv_amt

        if payer_amt <= cents_tolerance:
            i += 1
        if recv_amt <= cents_tolerance:
            j += 1

    return transfers
