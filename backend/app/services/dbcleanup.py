import logging
import os
import threading
import time
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..db.database import SessionLocal
from ..db.models import APEvent, AuditLog, BackupRun, CameraEvent, MetricSample
from . import computer_metrics, logcleanup

log = logging.getLogger(__name__)

# Berapa hari terakhir yang dipertahankan. 0 / negatif = matikan untuk tabel itu.
AUDIT_RETENTION_DAYS = int(os.getenv("CLEANUP_AUDIT_DAYS", "90"))
APEVENT_RETENTION_DAYS = int(os.getenv("CLEANUP_APEVENT_DAYS", "30"))
BACKUP_RETENTION_DAYS = int(os.getenv("CLEANUP_BACKUP_RUNS_DAYS", "14"))
METRIC_RETENTION_DAYS = int(os.getenv("CLEANUP_METRIC_DAYS", "30"))
CAMERA_EVENT_RETENTION_DAYS = int(os.getenv("CLEANUP_CAMERA_EVENT_DAYS", "30"))
CLEANUP_INTERVAL = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "3600"))


def run_cleanup(db: Session) -> dict:
    """Hapus baris lama dari tabel log yang menumpuk.

    Menghapus data lebih tua dari ambang retensi supaya DB tidak membengkak
    seiring waktu (audit log & event AP bisa tumbuh sangat cepat). Hanya baris
    yang sudah tua yang dihapus; baris terbaru tetap dipertahankan. Log runtime
    yang melebihi batas juga dipangkas di akhir siklus.
    """
    now = datetime.utcnow()
    result: dict[str, int] = {}

    # Rekap sampel komputer per jam sebelum sampel mentah lama dihapus.
    result["computer_rollup"] = computer_metrics.rollup_completed_hours(db, now)

    if AUDIT_RETENTION_DAYS > 0:
        cutoff = now - timedelta(days=AUDIT_RETENTION_DAYS)
        n = (
            db.query(AuditLog)
            .filter(AuditLog.timestamp < cutoff)
            .delete(synchronize_session=False)
        )
        result["audit_logs"] = n

    if APEVENT_RETENTION_DAYS > 0:
        cutoff = now - timedelta(days=APEVENT_RETENTION_DAYS)
        n = (
            db.query(APEvent)
            .filter(APEvent.timestamp < cutoff)
            .delete(synchronize_session=False)
        )
        result["ap_events"] = n

    if BACKUP_RETENTION_DAYS > 0:
        # hanya hapus run yang sudah selesai (jangan sentuh yang RUNNING)
        cutoff = now - timedelta(days=BACKUP_RETENTION_DAYS)
        n = (
            db.query(BackupRun)
            .filter(BackupRun.finished_at.isnot(None))
            .filter(BackupRun.finished_at < cutoff)
            .delete(synchronize_session=False)
        )
        result["backup_runs"] = n

    if METRIC_RETENTION_DAYS > 0:
        cutoff = now - timedelta(days=METRIC_RETENTION_DAYS)
        n = (
            db.query(MetricSample)
            .filter(MetricSample.timestamp < cutoff)
            .delete(synchronize_session=False)
        )
        result["metric_samples"] = n

    if CAMERA_EVENT_RETENTION_DAYS > 0:
        cutoff = now - timedelta(days=CAMERA_EVENT_RETENTION_DAYS)
        n = (
            db.query(CameraEvent)
            .filter(CameraEvent.timestamp < cutoff)
            .delete(synchronize_session=False)
        )
        result["camera_events"] = n

    raw_deleted, hourly_deleted = computer_metrics.cleanup_metrics(db, now)
    result["computer_metric_samples"] = raw_deleted
    result["computer_metric_hourly"] = hourly_deleted
    result["computer_speed_samples"] = computer_metrics.cleanup_speed_samples(
        db, now
    )
    result["logs"] = logcleanup.trim_logs()

    db.commit()
    return result


def _cleanup_once() -> dict:
    db = SessionLocal()
    try:
        return run_cleanup(db)
    finally:
        db.close()


def _scheduler_loop() -> None:
    while True:
        try:
            _cleanup_once()
        except Exception:
            log.exception("pembersihan database gagal")
        time.sleep(max(30, CLEANUP_INTERVAL))


def start_scheduler() -> None:
    """Jalankan cleanup berkala di background (sekali di awal, lalu tiap interval)."""
    threading.Thread(
        target=_scheduler_loop, daemon=True, name="db-cleanup"
    ).start()
