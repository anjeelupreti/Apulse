"""Liveness, readiness and build-version endpoints for probes and support tooling."""

import time
from collections.abc import Callable

import redis
from django.conf import settings
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

# ATOMIC_REQUESTS wraps every request in a transaction. Probes must not: a liveness check
# that needs the database turns a brief database blip into a container restart loop.


def _check_database() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")


def _check_migrations() -> None:
    executor = MigrationExecutor(connection)
    pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
    if pending:
        raise RuntimeError(f"{len(pending)} unapplied migrations")


def _check_redis() -> None:
    client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
    try:
        client.ping()
    finally:
        client.close()


READINESS_CHECKS: dict[str, Callable[[], None]] = {
    "database": _check_database,
    "migrations": _check_migrations,
    "redis": _check_redis,
}


@transaction.non_atomic_requests
@never_cache
@require_GET
def healthz(_request: HttpRequest) -> JsonResponse:
    """Process is alive. Never touches dependencies."""
    return JsonResponse({"status": "ok"})


@transaction.non_atomic_requests
@never_cache
@require_GET
def readyz(_request: HttpRequest) -> JsonResponse:
    """Process can serve traffic: database reachable, migrations applied, Redis reachable."""
    results: dict[str, dict[str, object]] = {}
    healthy = True
    for name, check in READINESS_CHECKS.items():
        started = time.perf_counter()
        result: dict[str, object] = {"ok": True}
        try:
            check()
        except Exception as exc:
            healthy = False
            # Only the exception type: readiness output must not leak hosts or credentials.
            result = {"ok": False, "error": type(exc).__name__}
        result["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
        results[name] = result
    return JsonResponse(
        {"status": "ok" if healthy else "fail", "checks": results},
        status=200 if healthy else 503,
    )


@transaction.non_atomic_requests
@never_cache
@require_GET
def version(_request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        {
            "version": settings.APP_VERSION,
            "git_sha": settings.GIT_SHA,
            "build_time": settings.BUILD_TIME,
            "environment": settings.ENVIRONMENT,
        }
    )
