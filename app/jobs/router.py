from fastapi import APIRouter, HTTPException

from app.jobs.store import get_job, list_jobs, delete_job, cleanup_old_jobs, JobStatus

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("")
def get_all_jobs():
    return list_jobs()


@router.get("/{job_id}")
def get_job_detail(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/status")
def get_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    resp: dict = {"job_id": job_id, "status": job["status"]}
    if job["status"] == JobStatus.COMPLETED:
        result = job.get("result") or {}
        resp["result"] = result
        resp["download_url"] = result.get("download_url")
    elif job["status"] == JobStatus.FAILED:
        resp["error"] = job.get("error")
    return resp


@router.delete("/{job_id}")
def remove_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] == JobStatus.PROCESSING:
        raise HTTPException(status_code=409, detail="Cannot delete a running job")
    delete_job(job_id)
    return {"deleted": job_id}


@router.post("/cleanup")
def run_cleanup(max_age_hours: int = 2):
    removed = cleanup_old_jobs(max_age_hours=max_age_hours)
    return {"removed": removed}
