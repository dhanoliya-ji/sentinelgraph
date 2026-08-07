"""Explainability.

The point of a graph model is that a verdict can be traced back to the exact
subgraph that produced it. `explain_account` turns the risk factors and the
detector hits for one account into a list of reasons, each carrying the node
ids responsible. The frontend renders each reason as a sentence and, on click,
highlights those nodes in the Cytoscape view -- so an analyst can see *why*,
not just *what*.
"""

from __future__ import annotations

from services import fraud_service, risk_service
from services.account_service import get_account
from services.formatting import money, plural


async def explain_account(acc_id: str) -> dict:
    account = await get_account(acc_id)

    # Recompute without persisting: explaining an account should never mutate it.
    risk = await risk_service.compute_risk(acc_id, persist=False)

    reasons: list[dict] = []

    for factor in risk["factors"]:
        if factor["code"] == "base":
            continue
        reasons.append(
            {
                "code": factor["code"],
                "title": factor["label"],
                "text": factor["detail"],
                "points": factor["points"],
                "highlight": [acc_id],
            }
        )

    # Ring membership -- attach the actual cycle so it can be highlighted.
    try:
        rings = await fraud_service.detect_rings(acc_id=acc_id, limit=3)
        for ring in rings["results"]:
            reasons.append(
                {
                    "code": "ring_detail",
                    "title": "Circular money flow",
                    "text": ring["summary"],
                    "points": None,
                    "highlight": list(dict.fromkeys(ring["account_chain"])),
                }
            )
    except Exception:  # noqa: BLE001 -- an explanation is best-effort, never fatal
        pass

    # Mule funnel membership -- either as the mule or as the payout destination.
    try:
        mules = await fraud_service.detect_mules(min_senders=8, payout_ratio=0.85, limit=10)
        for mule in mules["results"]:
            if acc_id in (mule["mule_account"], mule["destination"]):
                role = "collection point" if acc_id == mule["mule_account"] else "payout destination"
                reasons.append(
                    {
                        "code": "mule_detail",
                        "title": f"Part of a funnel pattern (as the {role})",
                        "text": mule["summary"],
                        "points": None,
                        "highlight": [mule["mule_account"], mule["destination"], *mule["senders"]],
                    }
                )
    except Exception:  # noqa: BLE001
        pass

    balance = account.get("balance")
    sent, received = account.get("sent_total") or 0, account.get("received_total") or 0
    if not reasons:
        headline = (
            f"{acc_id} looks clean. It holds {money(balance)}, has sent {money(sent)} and "
            f"received {money(received)}, and nothing in its network of connections "
            "matches a known fraud pattern."
        )
    else:
        headline = (
            f"{acc_id} scores {risk['risk_score']}/100 and is currently "
            f"{risk['status'].lower()}. {plural(len(reasons), 'piece')} of evidence "
            "from the graph support that."
        )

    return {
        "acc_id": acc_id,
        "owner_name": account.get("owner_name"),
        "risk_score": risk["risk_score"],
        "status": risk["status"],
        "headline": headline,
        "reasons": reasons,
    }
