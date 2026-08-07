"""Builds the node/edge payload Cytoscape consumes.

The Cypher returns one row per relationship carrying both endpoints; this
module de-duplicates those rows into a node list and an edge list. Node ids are
the business identifiers (`ACC_1101`, `DEV_8899`, `192.168.1.100`, ...), which
the seed script guarantees to be unique across labels.
"""

from __future__ import annotations

from database import run_query
from queries import cypher

MAX_LIMIT = 400


def _node_from(prefix: str, row: dict) -> dict | None:
    node_id = row.get(f"{prefix}_id")
    if node_id is None:
        return None
    return {
        "id": str(node_id),
        "label": str(row.get(f"{prefix}_label_text") or node_id),
        "kind": row.get(f"{prefix}_label") or "Unknown",
        "status": row.get(f"{prefix}_status"),
        "risk_score": row.get(f"{prefix}_risk"),
    }


def _assemble(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}

    for index, row in enumerate(rows):
        source = _node_from("source", row)
        target = _node_from("target", row)
        if not source or not target:
            continue

        nodes.setdefault(source["id"], source)
        nodes.setdefault(target["id"], target)

        rel_type = row.get("rel_type") or "RELATED"
        edge_id = f"{source['id']}|{rel_type}|{target['id']}|{index}"
        edges[edge_id] = {
            "id": edge_id,
            "source": source["id"],
            "target": target["id"],
            "type": rel_type,
            "amount": row.get("amount"),
            "timestamp": row.get("timestamp"),
        }

    return list(nodes.values()), list(edges.values())


async def get_graph(*, focus: str | None = None, depth: int = 2, limit: int = 250) -> dict:
    limit = max(10, min(limit, MAX_LIMIT))

    if focus:
        query = cypher.GRAPH_FOCUS_1 if depth <= 1 else cypher.GRAPH_FOCUS_2
        rows = await run_query(query, {"acc_id": focus, "limit": limit})
    else:
        rows = await run_query(cypher.GRAPH_ALL, {"limit": limit})

    nodes, edges = _assemble(rows)

    # Without a focus, surface accounts that have no relationships at all --
    # otherwise they silently vanish from the overview.
    if not focus:
        isolated = await run_query(cypher.GRAPH_ISOLATED_ACCOUNTS, {"limit": 50})
        for row in isolated:
            node_id = str(row["id"])
            nodes.append(
                {
                    "id": node_id,
                    "label": row.get("label_text") or node_id,
                    "kind": "Account",
                    "status": row.get("status"),
                    "risk_score": row.get("risk_score"),
                }
            )

    return {
        "nodes": nodes,
        "edges": edges,
        "truncated": len(rows) >= limit,
        "focus": focus,
    }


async def search(term: str, limit: int = 20) -> list[dict]:
    params = {"q": term.strip().lower(), "limit": limit}
    try:
        return await run_query(cypher.SEARCH, params)
    except Exception:  # noqa: BLE001 -- CALL {} subquery may be unsupported
        return await run_query(cypher.SEARCH_SIMPLE, params)


async def get_stats(active_ring_count: int) -> dict:
    rows = await run_query(cypher.STATS, {})
    entity_rows = await run_query(cypher.STATS_ENTITY_COUNTS, {})

    base = rows[0] if rows else {}
    entities = entity_rows[0] if entity_rows else {}

    return {
        "total_accounts": base.get("total_accounts", 0) or 0,
        "total_transactions": base.get("total_transactions", 0) or 0,
        "active_fraud_rings": active_ring_count,
        "high_risk_accounts": base.get("high_risk_accounts", 0) or 0,
        "flagged_accounts": base.get("flagged_accounts", 0) or 0,
        "suspicious_accounts": base.get("suspicious_accounts", 0) or 0,
        "total_transferred": float(base.get("total_transferred") or 0),
        "total_balance": float(base.get("total_balance") or 0),
        "customers": entities.get("customers", 0) or 0,
        "devices": entities.get("devices", 0) or 0,
        "ip_addresses": entities.get("ip_addresses", 0) or 0,
        "credit_cards": entities.get("credit_cards", 0) or 0,
    }
