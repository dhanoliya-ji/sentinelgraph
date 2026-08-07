"""Fraud detection endpoints.

Detectors are GET: they are read-only, idempotent and cacheable, and being able
to link straight to a result (`/detect/rings?acc_id=ACC_1101`) is useful. POST
is reserved for the two calls that either mutate state (`/detect/risk-score`
persists the new score) or genuinely want a body (`/trace-path`).
"""

from fastapi import APIRouter, Query

from models.schemas import DetectionResponse, RiskScoreRequest, RiskScoreResponse, TracePathRequest
from services import fraud_service, risk_service

router = APIRouter(tags=["detection"])


@router.get("/detect/rings", response_model=DetectionResponse)
async def detect_rings(
    acc_id: str | None = Query(
        default=None,
        pattern=r"^[A-Za-z0-9_\-]{1,64}$",
        description="Restrict the search to cycles through this account. Omit to scan.",
    ),
    limit: int = Query(default=25, ge=1, le=100),
    seed_limit: int = Query(default=30, ge=1, le=100, description="Accounts used as scan seeds."),
) -> DetectionResponse:
    return DetectionResponse(
        **await fraud_service.detect_rings(acc_id=acc_id, limit=limit, seed_limit=seed_limit)
    )


@router.get("/detect/shared-infrastructure", response_model=DetectionResponse)
async def detect_shared_infrastructure(
    limit: int = Query(default=200, ge=1, le=500),
) -> DetectionResponse:
    return DetectionResponse(**await fraud_service.detect_shared_infrastructure(limit=limit))


@router.get("/detect/mules", response_model=DetectionResponse)
async def detect_mules(
    min_senders: int = Query(default=8, ge=2, le=50),
    payout_ratio: float = Query(default=0.85, ge=0.1, le=1.0),
    limit: int = Query(default=25, ge=1, le=100),
) -> DetectionResponse:
    return DetectionResponse(
        **await fraud_service.detect_mules(
            min_senders=min_senders, payout_ratio=payout_ratio, limit=limit
        )
    )


@router.post("/trace-path", response_model=DetectionResponse)
async def trace_path(payload: TracePathRequest) -> DetectionResponse:
    return DetectionResponse(
        **await fraud_service.trace_path(payload.source, payload.destination)
    )


@router.post("/detect/risk-score", response_model=RiskScoreResponse)
async def risk_score(payload: RiskScoreRequest) -> RiskScoreResponse:
    return RiskScoreResponse(
        **await risk_service.compute_risk(payload.acc_id, persist=payload.persist)
    )
