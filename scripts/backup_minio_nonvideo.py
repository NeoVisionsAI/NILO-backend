#!/usr/bin/env python3
"""Backup MinIO objects for monitoring sessions, excluding large video chunks.

Object keys follow ``patients/<id>/<category>/...``. Objects under category
``video`` are skipped. By default only objects whose last-modified date (UTC)
matches ``--date`` are copied.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Allow running from repo root: python scripts/backup_minio_nonvideo.py
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.core.config import settings  # noqa: E402
from app.storage.minio_client import get_minio  # noqa: E402


def _category_from_key(object_key: str) -> str | None:
    parts = object_key.split("/")
    if len(parts) >= 3 and parts[0] == "patients":
        return parts[2]
    return None


def backup_minio_for_day(
    target_dir: Path,
    *,
    day: date,
    exclude_category: str = "video",
) -> tuple[int, int]:
    client = get_minio()
    bucket = settings.MINIO_BUCKET
    copied = 0
    skipped = 0

    for obj in client.list_objects(bucket, recursive=True):
        category = _category_from_key(obj.object_name)
        if category == exclude_category:
            skipped += 1
            continue
        modified = obj.last_modified
        if modified.tzinfo is None:
            modified = modified.replace(tzinfo=timezone.utc)
        if modified.date() != day:
            continue
        dest = target_dir / bucket / obj.object_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        client.fget_object(bucket, obj.object_name, str(dest))
        copied += 1

    return copied, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup non-video MinIO objects for one UTC day")
    parser.add_argument(
        "--date",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        help="UTC date YYYY-MM-DD (default: today UTC)",
    )
    parser.add_argument(
        "--dest",
        default=None,
        help="Destination directory (default: BACKUP_DIR/<date>/minio)",
    )
    args = parser.parse_args()
    day = date.fromisoformat(args.date)
    base = Path(args.dest or Path(settings.BACKUP_DIR) / args.date / "minio")
    base.mkdir(parents=True, exist_ok=True)
    copied, skipped_video = backup_minio_for_day(
        base,
        day=day,
        exclude_category=settings.BACKUP_MINIO_EXCLUDE_CATEGORY,
    )
    print(f"minio backup day={args.date} copied={copied} skipped_video_keys={skipped_video} dest={base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
