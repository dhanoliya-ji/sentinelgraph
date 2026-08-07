"""Graph payload, dashboard statistics and search."""

from fastapi import APIRouter, Query

from models.schemas import GraphResponse, SearchResponse, StatsResponse
from services import fraud_service, graph_service

router = APIRouter(tags=["graph"])


@router.get("/stats", response_model=StatsResponse)
async def stats() -> StatsResponse:
    ring_count = await fraud_service.count_active_rings()
    return StatsResponse(**await graph_service.get_stats(ring_count))


@router.get("/graph", response_model=GraphResponse)
async def graph(
    focus: str | None = Query(
        default=None,
        pattern=r"^[A-Za-z0-9_\-]{1,64}$",
        description="Centre the view on this account and show its neighbourhood.",
    ),
    depth: int = Query(default=2, ge=1, le=2, description="Hops from the focus account."),
    limit: int = Query(default=250, ge=10, le=400),
) -> GraphResponse:
    return GraphResponse(**await graph_service.get_graph(focus=focus, depth=depth, limit=limit))


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=1, max_length=64, description="Account id, owner name, device id or IP"),
    limit: int = Query(default=20, ge=1, le=50),
) -> SearchResponse:
    results = await graph_service.search(q, limit=limit)
    return SearchResponse(query=q, results=results)
