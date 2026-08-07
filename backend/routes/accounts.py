"""Account browsing endpoints."""

from typing import Literal

from fastapi import APIRouter, Path, Query

from models.schemas import (
    AccountDetail,
    AccountListResponse,
    ConnectionsResponse,
    ExplainResponse,
    Transaction,
)
from services import account_service, explain_service

router = APIRouter(prefix="/accounts", tags=["accounts"])

# Account ids are `ACC_1234`. Validating the shape at the edge turns a
# malformed id into a clear 422 instead of an empty result set.
ACC_ID = Path(pattern=r"^[A-Za-z0-9_\-]{1,64}$", description="Account id, e.g. ACC_1101")


@router.get("", response_model=AccountListResponse)
async def list_accounts(
    status: Literal["SAFE", "SUSPICIOUS", "FLAGGED"] | None = Query(default=None),
    min_risk: int | None = Query(default=None, ge=0, le=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> AccountListResponse:
    result = await account_service.list_accounts(
        status=status, min_risk=min_risk, page=page, page_size=page_size
    )
    return AccountListResponse(**result)


@router.get("/{acc_id}", response_model=AccountDetail)
async def get_account(acc_id: str = ACC_ID) -> AccountDetail:
    return AccountDetail(**await account_service.get_account(acc_id))


@router.get("/{acc_id}/transactions", response_model=list[Transaction])
async def get_transactions(
    acc_id: str = ACC_ID,
    direction: Literal["in", "out", "both"] = Query(default="both"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Transaction]:
    rows = await account_service.get_transactions(acc_id, direction=direction, limit=limit)
    return [Transaction(**row) for row in rows]


@router.get("/{acc_id}/connections", response_model=ConnectionsResponse)
async def get_connections(acc_id: str = ACC_ID) -> ConnectionsResponse:
    return ConnectionsResponse(**await account_service.get_connections(acc_id))


@router.get("/{acc_id}/explain", response_model=ExplainResponse)
async def explain(acc_id: str = ACC_ID) -> ExplainResponse:
    return ExplainResponse(**await explain_service.explain_account(acc_id))
