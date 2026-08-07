"""Liveness and database reachability.

This endpoint never raises and never returns 5xx for a *server* problem -- when
the database is down it answers 200 with `database: "unreachable"` so the
frontend can render an honest offline banner and keep working, and Render's
health check does not restart-loop a container whose only problem is that
CognoDB is asleep.
"""

from fastapi import APIRouter

from config import settings
from database import health_check
from models.schemas import HealthResponse

router = APIRouter(tags=["system"])

VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    if not settings.is_configured:
        missing = ", ".join(settings.missing_required)
        return HealthResponse(
            status="down",
            database="unreachable",
            reason="not_configured",
            message=f"Server is running but not configured. Missing: {missing}.",
            latency_ms=None,
            version=VERSION,
        )

    result = await health_check()
    database = result["database"]
    status = {"connected": "ok", "degraded": "degraded"}.get(database, "down")

    return HealthResponse(
        status=status,
        database=database,
        reason=result["reason"],
        message=result["message"],
        latency_ms=result["latency_ms"],
        version=VERSION,
    )


@router.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "name": "SentinelGraph API",
        "version": VERSION,
        "docs": "/docs",
        "health": "/health",
    }
