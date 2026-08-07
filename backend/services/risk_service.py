"""Risk scoring.

The score is deliberately a transparent, additive rule set rather than a black
box: an analyst has to be able to read the reason a customer was frozen. Each
factor is one bounded Cypher query, and each contributes a `RiskFactor` with
its own points and human-readable detail. The final score is the sum, clamped
to 0-100.

    base                                                              +5
    member of a TRANSFERRED cycle of 3-5 hops                        +35
    shares BOTH a device and an IP with >= 2 other accounts          +25
    shares BOTH a device and an IP with exactly 1 other account      +15
    >= 8 distinct inbound senders inside a 7-day window              +20
    each FLAGGED account within 2 hops (capped at 30)            +10 each
    logged in from a VPN exit node                                   +10

Note the shared-infrastructure factor deliberately requires the device *and*
the IP to match. With 50 accounts signing in from 15 devices, a shared device
alone is ordinary; a shared full fingerprint is not.

    >= 70 -> FLAGGED      40-69 -> SUSPICIOUS      < 40 -> SAFE

Changing a weight here changes it everywhere: the seed script, the API and the
README all read from these constants.
"""

from __future__ import annotations

from database import run_query, run_write
from queries import cypher
from services.account_service import assert_account_exists
from services.formatting import join_names, money, plural

BASE_SCORE = 5
POINTS_IN_CYCLE = 35
POINTS_SHARED_BOTH = 25
POINTS_SHARED_ONE = 15
POINTS_FAN_IN = 20
POINTS_PER_FLAGGED_NEIGHBOUR = 10
MAX_FLAGGED_NEIGHBOUR_POINTS = 30
POINTS_VPN = 10

SHARED_PEER_THRESHOLD = 2
FAN_IN_SENDER_THRESHOLD = 8
FAN_IN_WINDOW_DAYS = 7

FLAGGED_AT = 70
SUSPICIOUS_AT = 40


def status_for(score: int) -> str:
    if score >= FLAGGED_AT:
        return "FLAGGED"
    if score >= SUSPICIOUS_AT:
        return "SUSPICIOUS"
    return "SAFE"


async def _factor_cycle(acc_id: str) -> dict | None:
    rows = await run_query(cypher.RISK_IN_CYCLE, {"acc_id": acc_id})
    if not rows:
        return None
    chain = rows[0].get("chain") or []
    return {
        "code": "in_cycle",
        "label": "Member of a circular money flow",
        "points": POINTS_IN_CYCLE,
        "detail": (
            f"Money leaves this account and returns to it after "
            f"{plural(rows[0].get('hops') or len(chain), 'hop')}: {' → '.join(chain)}."
        ),
    }


async def _factor_shared_infra(acc_id: str) -> dict | None:
    rows = await run_query(cypher.RISK_SHARED_INFRA, {"acc_id": acc_id})
    if not rows:
        return None

    row = rows[0]
    peers = row.get("both_peers") or 0
    if peers < 1:
        return None

    devices = [d for d in (row.get("shared_devices") or []) if d]
    ips = [i for i in (row.get("shared_ips") or []) if i]
    peer_accounts = [p for p in (row.get("peer_accounts") or []) if p]

    strong = peers >= SHARED_PEER_THRESHOLD
    return {
        "code": "shared_infra_both" if strong else "shared_infra_pair",
        "label": (
            "Shares a device and an IP address with several accounts"
            if strong
            else "Shares a device and an IP address with another account"
        ),
        "points": POINTS_SHARED_BOTH if strong else POINTS_SHARED_ONE,
        "detail": (
            f"This account signs in from {join_names(devices)} and {join_names(ips)} -- "
            f"the same device *and* the same address used by "
            f"{plural(peers, 'other account')} ({join_names(peer_accounts)})."
        ),
    }


async def _factor_fan_in(acc_id: str) -> dict | None:
    rows = await run_query(cypher.RISK_FAN_IN, {"acc_id": acc_id})
    if not rows:
        return None

    row = rows[0]
    sender_count = row.get("sender_count") or 0
    if sender_count < FAN_IN_SENDER_THRESHOLD:
        return None

    first_ts, last_ts = row.get("first_ts"), row.get("last_ts")
    window_days = ((last_ts - first_ts) / 86400.0) if (first_ts and last_ts) else None
    if window_days is not None and window_days > FAN_IN_WINDOW_DAYS:
        return None

    return {
        "code": "fan_in",
        "label": "Unusual number of incoming senders in a short window",
        "points": POINTS_FAN_IN,
        "detail": (
            f"{plural(sender_count, 'distinct account')} sent "
            f"{money(row.get('inbound_total'))} into this account"
            + (f" within {window_days:.1f} days." if window_days is not None else ".")
        ),
    }


async def _factor_flagged_nearby(acc_id: str) -> dict | None:
    rows = await run_query(cypher.RISK_FLAGGED_NEARBY, {"acc_id": acc_id})
    if not rows:
        return None

    count = rows[0].get("flagged_count") or 0
    if count == 0:
        return None

    points = min(count * POINTS_PER_FLAGGED_NEIGHBOUR, MAX_FLAGGED_NEIGHBOUR_POINTS)
    examples = [e for e in (rows[0].get("examples") or []) if e]
    return {
        "code": "flagged_nearby",
        "label": "Close to accounts that are already flagged",
        "points": points,
        "detail": (
            f"{plural(count, 'flagged account')} sit within two hops of this one "
            f"(for example {join_names(examples)}). Hops may cross a shared device or IP, "
            "not only a transfer."
        ),
    }


async def _factor_vpn(acc_id: str) -> dict | None:
    rows = await run_query(cypher.RISK_VPN_LOGIN, {"acc_id": acc_id})
    if not rows:
        return None
    ips = [i for i in (rows[0].get("vpn_ips") or []) if i]
    if not ips:
        return None
    return {
        "code": "vpn_login",
        "label": "Signs in through a VPN",
        "points": POINTS_VPN,
        "detail": f"Logins recorded from VPN exit node(s) {join_names(ips)}.",
    }


async def compute_risk(acc_id: str, *, persist: bool = True) -> dict:
    await assert_account_exists(acc_id)

    before = await run_query(cypher.ACCOUNT_DETAIL, {"acc_id": acc_id})
    previous = before[0] if before else {}

    factors: list[dict] = [
        {
            "code": "base",
            "label": "Baseline",
            "points": BASE_SCORE,
            "detail": "Every account starts from a small non-zero baseline.",
        }
    ]

    for producer in (
        _factor_cycle,
        _factor_shared_infra,
        _factor_fan_in,
        _factor_flagged_nearby,
        _factor_vpn,
    ):
        factor = await producer(acc_id)
        if factor:
            factors.append(factor)

    score = max(0, min(100, sum(f["points"] for f in factors)))
    status = status_for(score)

    persisted = False
    if persist:
        await run_write(
            cypher.RISK_PERSIST, {"acc_id": acc_id, "risk_score": score, "status": status}
        )
        persisted = True

    contributing = [f for f in factors if f["code"] != "base"]
    if contributing:
        summary = (
            f"{acc_id} scores {score}/100 ({status.lower()}), driven by "
            f"{plural(len(contributing), 'risk signal')}: "
            + join_names([f["label"].lower() for f in contributing])
            + "."
        )
    else:
        summary = (
            f"{acc_id} scores {score}/100 (safe). No risk signals were found in the graph "
            "around this account."
        )

    return {
        "acc_id": acc_id,
        "risk_score": score,
        "status": status,
        "previous_score": previous.get("risk_score"),
        "previous_status": previous.get("status"),
        "factors": factors,
        "persisted": persisted,
        "summary": summary,
    }
