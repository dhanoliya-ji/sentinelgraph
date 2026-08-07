"""CognoDB connection management.

One `AsyncDriver` is created at application startup and closed at shutdown --
never per request. On the free c0 instance (0.5 vCPU / 256 MB RAM / 200
connections) a per-request driver would exhaust the server's connection budget
almost immediately.

This module is the ONLY place `session.run()` is called. Every caller goes
through `run_query` / `run_write`, which:

  * accept Cypher as a named constant plus a parameter dict -- no string
    interpolation of user input into Cypher, ever;
  * enforce a client-side timeout (`asyncio.wait_for`) rather than a
    server-side transaction timeout, because transaction-metadata support
    varies across openCypher implementations;
  * retry once on a transient `ServiceUnavailable`, then surface a clean,
    typed error;
  * translate driver exceptions into `DatabaseUnavailable` / `QueryFailed` so
    that no stack trace, URI or credential can leak into an HTTP response.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import (
    AuthError,
    ClientError,
    CypherSyntaxError,
    Neo4jError,
    ServiceUnavailable,
    SessionExpired,
    TransientError,
)

from config import settings

logger = logging.getLogger("sentinelgraph.db")

# Transient failures worth one automatic retry.
_RETRYABLE = (ServiceUnavailable, SessionExpired, TransientError)

_driver: AsyncDriver | None = None


# --------------------------------------------------------------------------
# Typed errors -- the API layer maps these to HTTP status codes.
# --------------------------------------------------------------------------
class DatabaseUnavailable(RuntimeError):
    """The database could not be reached or authentication failed."""

    def __init__(self, message: str, *, reason: str = "unreachable") -> None:
        super().__init__(message)
        self.reason = reason


class QueryFailed(RuntimeError):
    """The database was reached but the query could not be executed."""

    def __init__(self, message: str, *, reason: str = "query_failed") -> None:
        super().__init__(message)
        self.reason = reason


# --------------------------------------------------------------------------
# Driver lifecycle
# --------------------------------------------------------------------------
async def init_driver() -> None:
    """Create the shared driver. Called once from the FastAPI lifespan hook.

    Startup deliberately does NOT abort when the database is unreachable: the
    API still boots and serves `/health`, so the UI can show an honest
    "database offline" banner instead of the whole deployment failing.
    """
    global _driver

    if _driver is not None:
        return

    missing = settings.missing_required
    if missing:
        logger.error(
            "Missing required environment variables: %s. "
            "Copy backend/.env.example to backend/.env and fill them in.",
            ", ".join(missing),
        )
        return

    try:
        _driver = AsyncGraphDatabase.driver(
            settings.cognodb_uri,
            auth=(settings.cognodb_user, settings.cognodb_password),
            max_connection_pool_size=settings.max_connection_pool_size,
            connection_acquisition_timeout=30,
            connection_timeout=15,
            max_transaction_retry_time=10,
        )
        logger.info("CognoDB driver created (pool=%d)", settings.max_connection_pool_size)
    except Exception as exc:  # noqa: BLE001 -- startup must never hard-crash
        _driver = None
        logger.error("Failed to create CognoDB driver: %s", type(exc).__name__)


async def close_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None
        logger.info("CognoDB driver closed")


def get_driver() -> AsyncDriver:
    if _driver is None:
        missing = settings.missing_required
        if missing:
            raise DatabaseUnavailable(
                "Database is not configured. Missing environment variables: "
                + ", ".join(missing),
                reason="not_configured",
            )
        raise DatabaseUnavailable(
            "Database connection is not initialised.", reason="not_initialised"
        )
    return _driver


# --------------------------------------------------------------------------
# Query execution -- the single choke point
# --------------------------------------------------------------------------
async def _execute(query: str, params: dict[str, Any], *, write: bool) -> list[dict[str, Any]]:
    driver = get_driver()

    async def _work() -> list[dict[str, Any]]:
        async with driver.session() as session:
            runner = session.execute_write if write else session.execute_read

            async def _tx(tx):
                # Parameters are passed to the driver separately from the query
                # text. Cypher is never built by string concatenation.
                result = await tx.run(query, params)
                return [record.data() async for record in result]

            return await runner(_tx)

    last_error: Exception | None = None

    for attempt in (1, 2):
        try:
            return await asyncio.wait_for(_work(), timeout=settings.query_timeout_seconds)

        except asyncio.TimeoutError as exc:
            raise QueryFailed(
                f"Query timed out after {settings.query_timeout_seconds:g}s. "
                "Try narrowing the search (fewer hops or a smaller limit).",
                reason="timeout",
            ) from exc

        except AuthError as exc:
            raise DatabaseUnavailable(
                "Database rejected the credentials. Check COGNODB_USER and "
                "COGNODB_PASSWORD in your environment.",
                reason="invalid_credentials",
            ) from exc

        except _RETRYABLE as exc:
            last_error = exc
            if attempt == 1:
                logger.warning("Transient database error, retrying once: %s", type(exc).__name__)
                await asyncio.sleep(0.5)
                continue
            raise DatabaseUnavailable(
                "Database is currently unreachable. Please try again in a moment.",
                reason="unreachable",
            ) from exc

        except CypherSyntaxError as exc:
            logger.error("Cypher syntax error: %s", exc)
            raise QueryFailed(
                "A query could not be parsed by the database. This usually means an "
                "openCypher feature used here is not supported by this instance.",
                reason="unsupported_cypher",
            ) from exc

        except ClientError as exc:
            logger.error("Client error from database: %s", exc)
            raise QueryFailed(
                "The database rejected the query. Check that the schema has been "
                "seeded (run seed/seed_database.py).",
                reason="client_error",
            ) from exc

        except Neo4jError as exc:
            logger.error("Database error: %s", exc)
            raise QueryFailed("The query could not be completed.", reason="query_failed") from exc

        except OSError as exc:
            # DNS failure, refused connection, TLS handshake failure, ...
            last_error = exc
            if attempt == 1:
                await asyncio.sleep(0.5)
                continue
            raise DatabaseUnavailable(
                "Could not open a network connection to the database.",
                reason="unreachable",
            ) from exc

    raise DatabaseUnavailable("Database is currently unreachable.", reason="unreachable") from last_error


async def run_query(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Run a read query. `params` are always sent as driver parameters."""
    return await _execute(query, params or {}, write=False)


async def run_write(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Run a write query. `params` are always sent as driver parameters."""
    return await _execute(query, params or {}, write=True)


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------
async def health_check() -> dict[str, Any]:
    """Never raises. Always returns a renderable status object."""
    started = time.perf_counter()
    try:
        await run_query("RETURN 1 AS ok")
    except DatabaseUnavailable as exc:
        return {"database": "unreachable", "reason": exc.reason, "message": str(exc), "latency_ms": None}
    except QueryFailed as exc:
        return {"database": "degraded", "reason": exc.reason, "message": str(exc), "latency_ms": None}

    return {
        "database": "connected",
        "reason": None,
        "message": "Connected to CognoDB.",
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }
