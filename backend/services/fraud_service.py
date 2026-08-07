"""Fraud detection.

Each detector runs one bounded Cypher query, folds the raw rows into a result
shape the UI can render, and attaches a plain-English `summary` sentence. The
Cypher source is returned alongside the results so the UI can show analysts
exactly what was asked of the database.
"""

from __future__ import annotations

from database import run_query
from queries import cypher
from services.formatting import describe_days, join_names, money, plural


# --------------------------------------------------------------------------
# Q1 -- circular money-laundering rings
# --------------------------------------------------------------------------
def _ring_key(chain: list[str]) -> tuple[str, ...]:
    """A cycle is found once per member and once per rotation. Canonicalise it
    so ACC_A->B->C->A and ACC_B->C->A->B collapse to a single ring."""
    members = chain[:-1] if len(chain) > 1 and chain[0] == chain[-1] else chain
    return tuple(sorted(set(members)))


def _shape_ring(row: dict) -> dict:
    chain = [c for c in (row.get("account_chain") or []) if c]
    amounts = [float(a) for a in (row.get("amounts") or []) if a is not None]
    total = sum(amounts)
    members = chain[:-1] if len(chain) > 1 and chain[0] == chain[-1] else chain

    return {
        "account_chain": chain,
        "hops": row.get("hops") or len(amounts),
        "total_cycled_amount": total,
        "amounts": amounts,
        "timestamps": [t for t in (row.get("timestamps") or []) if t],
        "txn_ids": [t for t in (row.get("txn_ids") or []) if t],
        "summary": (
            f"{plural(len(members), 'account')} moved {money(total)} in a closed loop "
            f"that returns to where it started ({' → '.join(chain)})."
        ),
    }


async def detect_rings(*, acc_id: str | None = None, limit: int = 25, seed_limit: int = 30) -> dict:
    if acc_id:
        rows = await run_query(cypher.DETECT_RING_FOR_ACCOUNT, {"acc_id": acc_id, "limit": limit})
        used = cypher.DETECT_RING_FOR_ACCOUNT
        params = {"acc_id": acc_id, "limit": limit}
    else:
        rows = await run_query(cypher.DETECT_RINGS_SCAN, {"seed_limit": seed_limit, "limit": limit})
        used = cypher.DETECT_RINGS_SCAN
        params = {"seed_limit": seed_limit, "limit": limit}

    unique: dict[tuple[str, ...], dict] = {}
    for row in rows:
        chain = row.get("account_chain") or []
        if not chain:
            continue
        unique.setdefault(_ring_key(chain), _shape_ring(row))

    results = sorted(unique.values(), key=lambda r: r["total_cycled_amount"], reverse=True)

    if results:
        biggest = results[0]
        headline = (
            f"Found {plural(len(results), 'circular money flow')}. "
            f"The largest cycles {money(biggest['total_cycled_amount'])} through "
            f"{plural(len(set(biggest['account_chain'])), 'account')}."
        )
    elif acc_id:
        headline = f"{acc_id} is not part of any circular money flow of 3 to 5 hops."
    else:
        headline = "No circular money flows were found among the flagged and suspicious accounts."

    return {
        "detector": "rings",
        "title": "Circular money laundering",
        "headline": headline,
        "count": len(results),
        "results": results,
        "parameters": params,
        "cypher": used.strip(),
    }


# --------------------------------------------------------------------------
# Q2 -- shared infrastructure
# --------------------------------------------------------------------------
async def detect_shared_infrastructure(*, limit: int = 200) -> dict:
    rows = await run_query(cypher.DETECT_SHARED_INFRASTRUCTURE, {"limit": limit})

    # Rows are account *pairs*. Roll them up into one cluster per (IP, device)
    # so the analyst sees "6 accounts share this phone", not 15 pair rows.
    clusters: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["ip_address"], row["device_id"])
        cluster = clusters.setdefault(
            key,
            {
                "ip_address": row["ip_address"],
                "device_id": row["device_id"],
                "is_vpn": row.get("is_vpn"),
                "ip_country": row.get("ip_country"),
                "device_type": row.get("device_type"),
                "accounts": {},
                "pair_count": 0,
            },
        )
        cluster["pair_count"] += 1
        for side in ("a", "b"):
            cluster["accounts"][row[f"account_{side}"]] = {
                "acc_id": row[f"account_{side}"],
                "owner_name": row.get(f"owner_{side}"),
                "status": row.get(f"status_{side}"),
            }

    results = []
    for cluster in clusters.values():
        accounts = sorted(cluster["accounts"].values(), key=lambda a: a["acc_id"])
        owners = sorted({a["owner_name"] for a in accounts if a["owner_name"]})
        vpn_note = " The IP is a known VPN exit node." if cluster["is_vpn"] else ""
        cluster["accounts"] = accounts
        cluster["summary"] = (
            f"{plural(len(accounts), 'account')} registered to "
            f"{plural(len(owners), 'different name')} all sign in from the same device "
            f"({cluster['device_id']}) and the same IP address "
            f"({cluster['ip_address']}).{vpn_note}"
        )
        results.append(cluster)

    results.sort(key=lambda c: len(c["accounts"]), reverse=True)

    if results:
        largest = results[0]
        headline = (
            f"Found {plural(len(results), 'cluster')} of accounts sharing hardware. "
            f"The largest links {plural(len(largest['accounts']), 'account')} to a single device."
        )
    else:
        headline = "No accounts share both a device and an IP address."

    return {
        "detector": "shared-infrastructure",
        "title": "Shared infrastructure",
        "headline": headline,
        "count": len(results),
        "results": results,
        "parameters": {"limit": limit},
        "cypher": cypher.DETECT_SHARED_INFRASTRUCTURE.strip(),
    }


# --------------------------------------------------------------------------
# Q5 -- mule funnels
# --------------------------------------------------------------------------
async def detect_mules(*, min_senders: int = 8, payout_ratio: float = 0.85, limit: int = 25) -> dict:
    rows = await run_query(
        cypher.DETECT_MULES,
        {"min_senders": min_senders, "payout_ratio": payout_ratio, "limit": limit},
    )

    results = []
    for row in rows:
        inbound_total = float(row.get("inbound_total") or 0)
        outbound_total = float(row.get("outbound_total") or 0)
        senders = row.get("senders") or []
        window = row.get("window_days")
        results.append(
            {
                "mule_account": row["mule_account"],
                "mule_owner": row.get("mule_owner"),
                "inbound_count": row.get("inbound_count") or 0,
                "inbound_total": inbound_total,
                "window_days": float(window) if window is not None else None,
                "senders": senders,
                "destination": row["destination"],
                "destination_owner": row.get("destination_owner"),
                "destination_country": row.get("destination_country"),
                "outbound_total": outbound_total,
                "payout_ratio": (outbound_total / inbound_total) if inbound_total else 0.0,
                "summary": (
                    f"{plural(row.get('inbound_count') or 0, 'account')} "
                    f"({join_names(senders)}) sent {money(inbound_total)} into "
                    f"{row['mule_account']} over {describe_days(window)}. "
                    f"{row['mule_account']} then forwarded {money(outbound_total)} on to "
                    f"{row['destination']}"
                    + (
                        f" in {row['destination_country']}."
                        if row.get("destination_country")
                        else "."
                    )
                ),
            }
        )

    headline = (
        f"Found {plural(len(results), 'funnel pattern')} where many accounts feed one "
        "account that immediately pays out elsewhere."
        if results
        else f"No account received money from {min_senders} or more distinct senders "
        "and then forwarded most of it onward."
    )

    return {
        "detector": "mules",
        "title": "Mule account funnels",
        "headline": headline,
        "count": len(results),
        "results": results,
        "parameters": {"min_senders": min_senders, "payout_ratio": payout_ratio, "limit": limit},
        "cypher": cypher.DETECT_MULES.strip(),
    }


# --------------------------------------------------------------------------
# Q4 -- money-flow path tracing
# --------------------------------------------------------------------------
async def trace_path(source: str, destination: str, *, limit: int = 5) -> dict:
    rows = await run_query(
        cypher.TRACE_PATH, {"source": source, "destination": destination, "limit": limit}
    )

    results = []
    for row in rows:
        chain = row.get("chain") or []
        amounts = [float(a) for a in (row.get("amounts") or []) if a is not None]
        results.append(
            {
                "chain": chain,
                "owners": row.get("owners") or [],
                "statuses": row.get("statuses") or [],
                "amounts": amounts,
                "timestamps": [t for t in (row.get("timestamps") or []) if t],
                "txn_ids": [t for t in (row.get("txn_ids") or []) if t],
                "hops": row.get("hops") or len(amounts),
                "total_amount": sum(amounts),
                "summary": (
                    f"Money reaches {destination} from {source} in "
                    f"{plural(row.get('hops') or len(amounts), 'step')}: "
                    f"{' → '.join(chain)}."
                ),
            }
        )

    if results:
        shortest = results[0]
        headline = (
            f"Money can move from {source} to {destination} in as few as "
            f"{plural(shortest['hops'], 'step')}."
        )
    else:
        headline = (
            f"No money trail of six steps or fewer leads from {source} to {destination}."
        )

    return {
        "detector": "trace-path",
        "title": "Money flow trace",
        "headline": headline,
        "count": len(results),
        "results": results,
        "parameters": {"source": source, "destination": destination, "limit": limit},
        "cypher": cypher.TRACE_PATH.strip(),
    }


async def count_active_rings(*, seed_limit: int = 30, limit: int = 25) -> int:
    """Ring count for the dashboard tile. Failures degrade to 0 rather than
    taking the whole stats panel down with them."""
    try:
        result = await detect_rings(limit=limit, seed_limit=seed_limit)
        return result["count"]
    except Exception:  # noqa: BLE001
        return 0
