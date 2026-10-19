from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_superadmin, require_write
from ..db.database import get_db
from ..db.models import BackupJob, BackupRun
from ..services import backup as engine
from ..services.audit import record

router = APIRouter(prefix="/backup", tags=["backup"])


class JobBody(BaseModel):
    name: str
    type: str
    source: str = ""
    destination: str
    schedule: str = ""
    retention_days: int = 7
    enabled: bool = True


class RestoreBody(BaseModel):
    confirm: bool = False


def _serialize_job(job: BackupJob, db: Session) -> dict:
    last = (
        db.query(BackupRun)
        .filter(BackupRun.job_id == job.id)
        .order_by(BackupRun.started_at.desc())
        .first()
    )
    return {
        "id": job.id,
        "name": job.name,
        "type": job.type,
        "source": job.source,
        "destination": job.destination,
        "schedule": job.schedule,
        "retention_days": job.retention_days,
        "enabled": job.enabled,
        "last_run": _serialize_run(last) if last else None,
        "next_run": (
            engine.next_run(job.schedule, datetime.now()).isoformat()
            if job.enabled and job.schedule and engine._cron_valid(job.schedule)
            else None
        ),
    }


def _serialize_run(run: BackupRun) -> dict:
    return {
        "id": run.id,
        "job_id": run.job_id,
        "job_name": run.job_name,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "status": run.status,
        "size_bytes": run.size_bytes,
        "file_path": run.file_path,
        "message": run.message,
    }


@router.get("/jobs")
def list_jobs(_: str = Depends(get_current_user), db: Session = Depends(get_db)):
    jobs = db.query(BackupJob).order_by(BackupJob.name).all()
    return {"jobs": [_serialize_job(j, db) for j in jobs]}


@router.post("/jobs", dependencies=[Depends(require_write)])
def create_job(
    body: JobBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        engine.validate_job(
            body.name, body.type, body.source, body.destination,
            body.schedule.strip(), body.retention_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if db.query(BackupJob).filter(BackupJob.name == body.name).first():
        raise HTTPException(status_code=400, detail=f"Job '{body.name}' sudah ada")
    job = BackupJob(
        name=body.name,
        type=body.type,
        source=body.source,
        destination=body.destination.rstrip("/") if body.destination != "/" else body.destination,
        schedule=body.schedule.strip(),
        retention_days=body.retention_days,
        enabled=body.enabled,
    )
    db.add(job)
    record(db, user, "BACKUP_JOB_CREATE", f"{body.name} ({body.type})")
    db.commit()
    return _serialize_job(job, db)


@router.put("/jobs/{job_id}", dependencies=[Depends(require_write)])
def update_job(
    job_id: int,
    body: JobBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.get(BackupJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    try:
        engine.validate_job(
            body.name, body.type, body.source, body.destination,
            body.schedule.strip(), body.retention_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    dup = (
        db.query(BackupJob)
        .filter(BackupJob.name == body.name, BackupJob.id != job_id)
        .first()
    )
    if dup:
        raise HTTPException(status_code=400, detail=f"Job '{body.name}' sudah ada")
    job.name = body.name
    job.type = body.type
    job.source = body.source
    job.destination = body.destination.rstrip("/") if body.destination != "/" else body.destination
    job.schedule = body.schedule.strip()
    job.retention_days = body.retention_days
    job.enabled = body.enabled
    record(db, user, "BACKUP_JOB_UPDATE", body.name)
    db.commit()
    return _serialize_job(job, db)


@router.delete("/jobs/{job_id}", dependencies=[Depends(require_write)])
def delete_job(
    job_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.get(BackupJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    db.query(BackupRun).filter(BackupRun.job_id == job_id).delete()
    db.delete(job)
    record(db, user, "BACKUP_JOB_DELETE", job.name)
    db.commit()
    return {"ok": True}


@router.post("/jobs/{job_id}/run", dependencies=[Depends(require_write)])
def run_job(
    job_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.get(BackupJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    run_id = engine.trigger(job_id)
    if run_id is None:
        raise HTTPException(status_code=409, detail="Job sedang berjalan")
    record(db, user, "BACKUP_RUN", job.name)
    db.commit()
    return {"started": True, "job_id": job_id}


@router.get("/runs")
def list_runs(
    limit: int = 50,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 200))
    runs = (
        db.query(BackupRun)
        .order_by(BackupRun.started_at.desc())
        .limit(limit)
        .all()
    )
    return {"runs": [_serialize_run(r) for r in runs]}


@router.post("/runs/{run_id}/restore", dependencies=[Depends(require_write)])
def restore_run(
    run_id: int,
    body: RestoreBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = db.get(BackupRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Riwayat tidak ditemukan")
    if run.status != "SUCCESS" or not run.file_path:
        raise HTTPException(status_code=400, detail="Backup ini tidak berhasil / tidak punya file")
    archive = Path(run.file_path)
    if not archive.exists():
        raise HTTPException(status_code=400, detail="File backup sudah tidak ada (mungkin terhapus retensi)")

    job = db.get(BackupJob, run.job_id) if run.job_id else None
    job_type = job.type if job else ("mysql" if archive.suffix == ".gz" and archive.name.endswith(".sql.gz") else "directory")

    try:
        if job_type in ("mysql", "postgres"):
            if not body.confirm:
                raise HTTPException(
                    status_code=400,
                    detail="Restore database akan MENIMPA isi database tujuan. Kirim confirm=true untuk lanjut.",
                )
            target, message = engine.restore_sql(run, job_type, job.source if job else "")
        else:
            target, message = engine.restore_archive(run)
    except RuntimeError as exc:
        record(db, user, "BACKUP_RESTORE", run.job_name, "FAILED")
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc))

    record(db, user, "BACKUP_RESTORE", f"{run.job_name} → {target}")
    db.commit()
    return {"restored_to": target, "message": message}


@router.get("/runs/{run_id}/download", dependencies=[Depends(require_superadmin)])
def download_run(
    run_id: int,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = db.get(BackupRun, run_id)
    if run is None or not run.file_path:
        raise HTTPException(status_code=404, detail="File tidak ditemukan")
    path = Path(run.file_path)
    if not path.exists():
        raise HTTPException(status_code=400, detail="File backup sudah tidak ada")
    return FileResponse(path, filename=path.name, media_type="application/gzip")
