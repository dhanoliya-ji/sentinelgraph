"""Pydantic response models.

Kept deliberately thin -- these exist to document the API surface and to keep
the frontend contract explicit, not to re-model the graph. Detection results
use `RiskFactor` / narrative fields so the UI can render a plain-language
explanation without knowing any Cypher.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AccountStatus = Literal["SAFE", "SUSPICIOUS", "FLAGGED"]


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------
class ErrorBody(BaseModel):
    code: str = Field(examples=["database_unreachable"])
    message: str
    detail: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


# --------------------------------------------------------------------------
# Health & stats
# --------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    database: Literal["connected", "degraded", "unreachable"]
    reason: str | None = None
    message: str
    latency_ms: float | None = None
    version: str


class StatsResponse(BaseModel):
    total_accounts: int
    total_transactions: int
    active_fraud_rings: int
    high_risk_accounts: int
    flagged_accounts: int
    suspicious_accounts: int
    total_transferred: float
    total_balance: float
    customers: int
    devices: int
    ip_addresses: int
    credit_cards: int


# --------------------------------------------------------------------------
# Accounts
# --------------------------------------------------------------------------
class AccountSummary(BaseModel):
    acc_id: str
    owner_name: str | None = None
    balance: float | None = None
    risk_score: int | None = None
    status: AccountStatus | None = None
    country: str | None = None
    created_at: str | None = None
    customer_id: str | None = None
    customer_name: str | None = None


class AccountListResponse(BaseModel):
    items: list[AccountSummary]
    total: int
    page: int
    page_size: int


class AccountDetail(AccountSummary):
    customer_country: str | None = None
    customer_risk_rating: str | None = None
    sent_count: int = 0
    sent_total: float = 0.0
    received_count: int = 0
    received_total: float = 0.0


class Transaction(BaseModel):
    txn_id: str | None = None
    amount: float | None = None
    currency: str | None = None
    timestamp: str | None = None
    direction: Literal["in", "out"]
    counterparty_id: str | None = None
    counterparty_name: str | None = None
    counterparty_status: AccountStatus | None = None


class ConnectionsResponse(BaseModel):
    devices: list[dict[str, Any]] = []
    ips: list[dict[str, Any]] = []
    cards: list[dict[str, Any]] = []
    customers: list[dict[str, Any]] = []


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------
class SearchHit(BaseModel):
    kind: Literal["Account", "Device", "IPAddress", "Customer"]
    id: str
    label: str | None = None
    status: str | None = None
    risk_score: int | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchHit]


# --------------------------------------------------------------------------
# Graph
# --------------------------------------------------------------------------
class GraphNode(BaseModel):
    id: str
    label: str
    kind: str
    status: str | None = None
    risk_score: int | None = None


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    amount: float | None = None
    timestamp: str | None = None


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool = False
    focus: str | None = None


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------
class RingResult(BaseModel):
    account_chain: list[str]
    hops: int
    total_cycled_amount: float
    amounts: list[float] = []
    timestamps: list[str] = []
    txn_ids: list[str] = []
    summary: str


class SharedInfraCluster(BaseModel):
    ip_address: str
    device_id: str
    is_vpn: bool | None = None
    ip_country: str | None = None
    device_type: str | None = None
    accounts: list[dict[str, Any]]
    pair_count: int
    summary: str


class MuleResult(BaseModel):
    mule_account: str
    mule_owner: str | None = None
    inbound_count: int
    inbound_total: float
    window_days: float | None = None
    senders: list[str] = []
    destination: str
    destination_owner: str | None = None
    destination_country: str | None = None
    outbound_total: float
    payout_ratio: float
    summary: str


class TracedPath(BaseModel):
    chain: list[str]
    owners: list[str | None] = []
    statuses: list[str | None] = []
    amounts: list[float] = []
    timestamps: list[str] = []
    txn_ids: list[str] = []
    hops: int
    total_amount: float
    summary: str


class DetectionResponse(BaseModel):
    """Uniform envelope so the UI renders every detection panel the same way."""

    detector: str
    title: str
    headline: str
    count: int
    results: list[dict[str, Any]]
    parameters: dict[str, Any] = {}
    cypher: str | None = None


class RiskFactor(BaseModel):
    code: str
    label: str
    points: int
    detail: str


class RiskScoreResponse(BaseModel):
    acc_id: str
    risk_score: int
    status: AccountStatus
    previous_score: int | None = None
    previous_status: str | None = None
    factors: list[RiskFactor]
    persisted: bool
    summary: str


class ExplainResponse(BaseModel):
    acc_id: str
    owner_name: str | None = None
    risk_score: int
    status: str
    headline: str
    reasons: list[dict[str, Any]]


class TracePathRequest(BaseModel):
    source: str = Field(min_length=1, max_length=64)
    destination: str = Field(min_length=1, max_length=64)


class RiskScoreRequest(BaseModel):
    acc_id: str = Field(min_length=1, max_length=64)
    persist: bool = True
