"""Dependency and disk checks for /health."""

import asyncio
import logging
import shutil
import time
from pathlib import Path

from app.core.config import settings
from app.db.mongodb import get_client
from app.schemas.health import ComponentHealth, DiskHealth, HealthReport
from app.storage.minio_client import ensure_bucket, get_minio

logger = logging.getLogger(__name__)


def _disk_level(used_percent: float) -> str:
    if used_percent >= settings.DISK_CRITICAL_USED_PERCENT:
        return "critical"
    if used_percent >= settings.DISK_WARN_USED_PERCENT:
        return "warn"
    return "ok"


def check_disk_paths() -> list[DiskHealth]:
    results: list[DiskHealth] = []
    for raw in settings.disk_check_paths_list():
        path = raw.strip()
        if not path:
            continue
        try:
            usage = shutil.disk_usage(path)
        except OSError as exc:
            results.append(
                DiskHealth(
                    ok=False,
                    path=path,
                    total_bytes=0,
                    used_bytes=0,
                    free_bytes=0,
                    used_percent=100.0,
                    level="critical",
                )
            )
            logger.debug("disk_usage failed for %s: %s", path, exc)
            continue
        used_pct = (usage.used / usage.total * 100.0) if usage.total else 100.0
        level = _disk_level(used_pct)
        results.append(
            DiskHealth(
                ok=level != "critical",
                path=path,
                total_bytes=usage.total,
                used_bytes=usage.used,
                free_bytes=usage.free,
                used_percent=round(used_pct, 2),
                level=level,
            )
        )
    return results


async def check_mongodb() -> ComponentHealth:
    start = time.perf_counter()
    try:
        client = get_client()
        await client.admin.command("ping")
        ms = (time.perf_counter() - start) * 1000
        return ComponentHealth(ok=True, detail="ping ok", latency_ms=round(ms, 2))
    except RuntimeError:
        return ComponentHealth(ok=False, detail="client not initialized")
    except Exception as exc:  # noqa: BLE001
        return ComponentHealth(ok=False, detail=str(exc))


async def check_minio() -> ComponentHealth:
    start = time.perf_counter()

    def _probe() -> None:
        client = get_minio()
        bucket = settings.MINIO_BUCKET
        if not client.bucket_exists(bucket):
            ensure_bucket(bucket)
        it = client.list_objects(bucket, recursive=True)
        next(it, None)

    try:
        await asyncio.to_thread(_probe)
        ms = (time.perf_counter() - start) * 1000
        return ComponentHealth(ok=True, detail="bucket reachable", latency_ms=round(ms, 2))
    except Exception as exc:  # noqa: BLE001
        return ComponentHealth(ok=False, detail=str(exc))


async def build_health_report() -> HealthReport:
    mongo = await check_mongodb()
    minio = await check_minio()
    disk = await asyncio.to_thread(check_disk_paths)

    disk_status = "ok"
    for d in disk:
        if d.level == "critical":
            disk_status = "critical"
            break
        if d.level == "warn":
            disk_status = "warn"

    ready = mongo.ok and minio.ok

    if not ready or disk_status == "critical":
        status = "critical"
    elif disk_status == "warn":
        status = "degraded"
    else:
        status = "ok"

    return HealthReport(
        status=status,
        service=settings.PROJECT_NAME,
        environment=settings.ENVIRONMENT,
        ready=ready,
        mongodb=mongo,
        minio=minio,
        disk=disk,
        disk_status=disk_status,
    )
