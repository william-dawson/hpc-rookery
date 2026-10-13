"""Best-effort local job-id to scheduler registry for cell2026."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import time

_LOG = logging.getLogger(__name__)
_REGISTRY_DIR = Path.home() / ".hpc-agent" / "cell2026-registry"
_JOB_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_SCHEDULERS = frozenset({"slurm", "gridengine"})


def _safe_job_id(job_id: str) -> bool:
    return bool(_JOB_ID_RE.fullmatch(job_id)) and ".." not in job_id


def _entry_path(scheduler: str, job_id: str) -> Path:
    if scheduler not in _SCHEDULERS or not _safe_job_id(job_id):
        raise ValueError("Invalid cell2026 scheduler or job id for local registry")
    return _REGISTRY_DIR / f"{scheduler}-{job_id}.json"


def record(job_id: str, scheduler: str, queue: str | None,
           script_path: str | None) -> None:
    """Atomically record a successful submission; never break submission."""
    temporary: Path | None = None
    try:
        _REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
        target = _entry_path(scheduler, job_id)
        temporary = target.with_suffix(f".{os.getpid()}.tmp")
        payload = {
            "job_id": job_id, "scheduler": scheduler, "queue": queue,
            "script_path": script_path, "recorded_at": time.time(),
        }
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(temporary, target)
    except Exception as exc:  # noqa: BLE001 - registry is deliberately best effort
        _LOG.warning("cell2026 registry record failed for %s: %s", job_id, exc)
        try:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass


def lookup(job_id: str) -> str | None:
    if not _safe_job_id(job_id):
        return None
    hits = []
    for scheduler in ("slurm", "gridengine"):
        try:
            if _entry_path(scheduler, job_id).exists():
                hits.append(scheduler)
        except OSError:
            return None
    if len(hits) > 1:
        _LOG.warning("cell2026 job id %s is registered to both schedulers", job_id)
        return None
    return hits[0] if hits else None


def recent(limit: int = 100) -> list[dict]:
    try:
        paths = list(_REGISTRY_DIR.glob("*.json"))
    except OSError as exc:
        _LOG.warning("cell2026 registry cannot be read: %s", exc)
        return []
    records = []
    for path in paths:
        try:
            record_data = json.loads(path.read_text(encoding="utf-8"))
            if (record_data.get("scheduler") in _SCHEDULERS
                    and _safe_job_id(str(record_data.get("job_id", "")))):
                records.append(record_data)
        except (OSError, json.JSONDecodeError) as exc:
            _LOG.warning("skipping malformed cell2026 registry entry %s: %s", path, exc)
    records.sort(key=lambda item: item.get("recorded_at", 0), reverse=True)
    return records[:limit]
