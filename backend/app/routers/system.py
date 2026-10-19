from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.deps import get_current_user
from ..db.database import get_db
from ..db.models import APEvent, AuditLog, BackupRun
from ..services import collectors, dbcleanup

router = APIRouter(tags=["system"])


@router.get("/system/metrics")
def metrics(_: str = Depends(get_current_user)):
    return collectors.get_metrics()


@router.get("/system/info")
def info(_: str = Depends(get_current_user)):
    return collectors.get_system_info()


@router.get("/storage/filesystems")
def filesystems(_: str = Depends(get_current_user)):
    return {"filesystems": collectors.list_filesystems()}


@router.get("/network/interfaces")
def interfaces(_: str = Depends(get_current_user)):
    return {"interfaces": collectors.list_interfaces()}


@router.get("/network/ports")
def ports(_: str = Depends(get_current_user)):
    return collectors.list_ports()


@router.get("/system/cleanup/status")
def cleanup_status(
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Info auto-cleanup DB: ambang retensi + ukuran tabel log yang menumpuk."""
    return {
        "retention_days": {
            "audit_logs": dbcleanup.AUDIT_RETENTION_DAYS,
            "ap_events": dbcleanup.APEVENT_RETENTION_DAYS,
            "backup_runs": dbcleanup.BACKUP_RETENTION_DAYS,
        },
        "interval_seconds": dbcleanup.CLEANUP_INTERVAL,
        "rows": {
            "audit_logs": db.query(AuditLog).count(),
            "ap_events": db.query(APEvent).count(),
            "backup_runs": db.query(BackupRun).count(),
        },
    }


@router.post("/system/cleanup")
def run_cleanup(
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Jalankan pembersihan DB manual sekarang; balas berapa baris dihapus."""
    deleted = dbcleanup.run_cleanup(db)
    return {"deleted": deleted, "retention_days": dbcleanup.AUDIT_RETENTION_DAYS}
