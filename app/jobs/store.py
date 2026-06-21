import json
import os
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


_lock = threading.Lock()
_jobs: dict[str, dict] = {}
_DB = os.environ.get("JOBS_DB_PATH", "data/jobs.json")


def _load_from_disk() -> dict:
    if os.path.exists(_DB):
        with open(_DB, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_to_disk() -> None:
    os.makedirs(os.path.dirname(_DB) or ".", exist_ok=True)
    with open(_DB, "w", encoding="utf-8") as f:
        json.dump(_jobs, f, indent=2, ensure_ascii=False)


def init() -> None:
    global _jobs
    with _lock:
        _jobs = _load_from_disk()


def create_job(job_type: str, params: dict) -> dict:
    job_id = uuid.uuid4().hex[:10]
    job = {
        "id": job_id,
        "type": job_type,
        "status": JobStatus.QUEUED,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "started_at": None,
        "completed_at": None,
        "params": params,
        "result": None,
        "error": None,
    }
    with _lock:
        _jobs[job_id] = job
        _save_to_disk()
    return job


def get_job(job_id: str) -> dict | None:
    with _lock:
        return dict(_jobs[job_id]) if job_id in _jobs else None


def list_jobs() -> list[dict]:
    with _lock:
        return list(_jobs.values())


def update_job(job_id: str, **kwargs) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)
            _save_to_disk()


def delete_job(job_id: str) -> bool:
    with _lock:
        if job_id not in _jobs:
            return False
        del _jobs[job_id]
        _save_to_disk()
        return True


def cleanup_old_jobs(max_age_hours: int = 2) -> int:
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    to_delete = []
    with _lock:
        for jid, job in _jobs.items():
            if job["status"] in (JobStatus.COMPLETED, JobStatus.FAILED):
                created = datetime.fromisoformat(job["created_at"])
                if created < cutoff:
                    to_delete.append(jid)
        for jid in to_delete:
            del _jobs[jid]
        if to_delete:
            _save_to_disk()
    return len(to_delete)
