"""Account read operations."""

from __future__ import annotations

from database import run_query
from queries import cypher


class AccountNotFound(LookupError):
    def __init__(self, acc_id: str) -> None:
        super().__init__(f"No account found with id '{acc_id}'.")
        self.acc_id = acc_id


async def list_accounts(
    *,
    status: str | None = None,
    min_risk: int | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict:
    skip = (page - 1) * page_size
    params = {"status": status, "min_risk": min_risk, "skip": skip, "limit": page_size}

    rows = await run_query(cypher.ACCOUNT_LIST, params)
    total_rows = await run_query(cypher.ACCOUNT_COUNT, {"status": status, "min_risk": min_risk})
    total = total_rows[0]["total"] if total_rows else 0

    return {"items": rows, "total": total, "page": page, "page_size": page_size}


async def get_account(acc_id: str) -> dict:
    rows = await run_query(cypher.ACCOUNT_DETAIL, {"acc_id": acc_id})
    if not rows:
        raise AccountNotFound(acc_id)
    return rows[0]


async def assert_account_exists(acc_id: str) -> None:
    rows = await run_query(cypher.ACCOUNT_EXISTS, {"acc_id": acc_id})
    if not rows:
        raise AccountNotFound(acc_id)


async def get_transactions(acc_id: str, *, direction: str = "both", limit: int = 100) -> list[dict]:
    await assert_account_exists(acc_id)

    # The combined query uses a CALL {} subquery. Older openCypher engines may
    # not support it, so fall back to two simple queries merged in Python.
    try:
        return await run_query(
            cypher.ACCOUNT_TRANSACTIONS,
            {"acc_id": acc_id, "direction": direction, "limit": limit},
        )
    except Exception:  # noqa: BLE001 -- portability fallback, re-raised below if it also fails
        rows: list[dict] = []
        if direction in ("out", "both"):
            rows += await run_query(cypher.ACCOUNT_TRANSACTIONS_OUT, {"acc_id": acc_id, "limit": limit})
        if direction in ("in", "both"):
            rows += await run_query(cypher.ACCOUNT_TRANSACTIONS_IN, {"acc_id": acc_id, "limit": limit})
        rows.sort(key=lambda r: r.get("ts") or 0, reverse=True)
        return rows[:limit]


async def get_connections(acc_id: str) -> dict:
    await assert_account_exists(acc_id)
    rows = await run_query(cypher.ACCOUNT_CONNECTIONS, {"acc_id": acc_id})
    if not rows:
        return {"devices": [], "ips": [], "cards": [], "customers": []}

    row = rows[0]

    def clean(items: list[dict] | None) -> list[dict]:
        # OPTIONAL MATCH yields a single {id: null} entry when nothing matched.
        return [item for item in (items or []) if item and item.get("id") is not None]

    return {
        "devices": clean(row.get("devices")),
        "ips": clean(row.get("ips")),
        "cards": clean(row.get("cards")),
        "customers": clean(row.get("customers")),
    }
