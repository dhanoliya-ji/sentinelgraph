"""SentinelGraph API.

Layering, outermost first:

    routes/    HTTP concerns only -- validation, status codes, response models
    services/  business logic, plain-language summaries, risk scoring
    queries/   every Cypher statement, as named constants
    database/  the single driver and the single place a query is executed

Nothing below a layer imports from above it, and the only module that talks to
the Bolt driver is `database.connection`.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import DatabaseUnavailable, QueryFailed, close_driver, init_driver
from routes import accounts, detection, graph, health
from services.account_service import AccountNotFound

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
logger = logging.getLogger("sentinelgraph")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting SentinelGraph API | config=%s", settings.safe_summary())
    if not settings.is_configured:
        logger.warning(
            "Starting WITHOUT database credentials (%s missing). The API will serve /health "
            "and return a clear error on data endpoints.",
            ", ".join(settings.missing_required),
        )
    await init_driver()
    try:
        yield
    finally:
        await close_driver()


app = FastAPI(
    title="SentinelGraph API",
    description=(
        "Graph-based financial fraud detection over CognoDB. "
        "Every query is parameterised and every traversal is bounded."
    ),
    version=health.VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# Error handling
#
# Every failure leaves the API in the same envelope:
#     {"error": {"code": ..., "message": ..., "detail": ...}}
# Messages are written for a human reader. Stack traces, the connection URI and
# credentials are logged server-side and never serialised into a response.
# --------------------------------------------------------------------------
def _error(status: int, code: str, message: str, detail: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "detail": detail}},
    )


@app.exception_handler(DatabaseUnavailable)
async def _handle_db_unavailable(_: Request, exc: DatabaseUnavailable) -> JSONResponse:
    logger.error("Database unavailable (%s)", exc.reason)
    return _error(
        503,
        f"database_{exc.reason}",
        str(exc),
        "The API is running but cannot reach CognoDB. Check the instance is awake and "
        "that COGNODB_URI / COGNODB_PASSWORD are set correctly.",
    )


@app.exception_handler(QueryFailed)
async def _handle_query_failed(_: Request, exc: QueryFailed) -> JSONResponse:
    logger.error("Query failed (%s)", exc.reason)
    status = 504 if exc.reason == "timeout" else 500
    return _error(status, exc.reason, str(exc))


@app.exception_handler(AccountNotFound)
async def _handle_not_found(_: Request, exc: AccountNotFound) -> JSONResponse:
    return _error(
        404,
        "account_not_found",
        str(exc),
        "Check the account id, or use the search box to find it.",
    )


@app.exception_handler(RequestValidationError)
async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(part) for part in first.get("loc", [])[1:]) or "input"
    return _error(
        422,
        "invalid_request",
        f"'{field}' is not valid: {first.get('msg', 'check the value and try again')}.",
    )


@app.exception_handler(Exception)
async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", type(exc).__name__)
    return _error(
        500,
        "internal_error",
        "Something went wrong while handling that request.",
        "The details have been logged on the server.",
    )


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
app.include_router(health.router)
app.include_router(graph.router)
app.include_router(detection.router)
app.include_router(accounts.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)
