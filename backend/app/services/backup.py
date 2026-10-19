"""Backup engine: job execution, retention, restore, dan scheduler cron.

Semua eksekusi memakai subprocess list-args / modul Python (tarfile) —
tanpa shell, sesuai kebijakan keamanan panel.
"""

import gzip
import os
import re
import subprocess
import tarfile
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse

from ..core.config import get_settings
from ..db.database import SessionLocal
from ..db.models import BackupJob, BackupRun

JOB_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
# path absolut tanpa "..", tanpa spasi agar aman dipakai lintas tool
PATH_RE = re.compile(r"^/(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+$")
DB_NAME_RE = re.compile(r"^[A-Za-z0-9_$]{1,64}$")


def _path_ok(path: str) -> bool:
    """Regex charset + tolak segmen '.'/'..' dan double-slash."""
    if not PATH_RE.match(path):
        return False
    segs = path.split("/")[1:]
    return all(s not in (".", "..") for s in segs)

JOB_TYPES = {"panel", "directory", "config", "mysql", "postgres"}

_running_jobs: set[int] = set()
_lock = threading.Lock()
_last_fired: dict[int, datetime] = {}


# ------------------------------------------------------------- validasi
def validate_job(
    name: str,
    type_: str,
    source: str,
    destination: str,
    schedule: str,
    retention_days: int,
) -> None:
    if not JOB_NAME_RE.match(name):
        raise ValueError("Nama job hanya boleh huruf, angka, titik, strip, underscore (maks 64)")
    if type_ not in JOB_TYPES:
        raise ValueError(f"Tipe job harus salah satu dari: {', '.join(sorted(JOB_TYPES))}")
    if type_ == "panel":
        if source:
            raise ValueError("Job tipe panel tidak memakai source")
    elif type_ in ("mysql", "postgres"):
        if not DB_NAME_RE.match(source):
            raise ValueError("Nama database tidak valid")
    else:
        if not _path_ok(source):
            raise ValueError("Source harus path absolut yang valid (tanpa '..' dan spasi)")
        if not Path(source).exists():
            raise ValueError(f"Source tidak ada: {source}")
    if not _path_ok(destination):
        raise ValueError("Destination harus path absolut yang valid (tanpa '..' dan spasi)")
    if schedule:
        if not _cron_valid(schedule):
            raise ValueError("Schedule harus ekspresi cron 5 field, contoh: 0 3 * * *")
    if not (1 <= int(retention_days) <= 3650):
        raise ValueError("Retensi harus 1–3650 hari")


# ------------------------------------------------------------- cron
def _parse_field(field: str, lo: int, hi: int) -> set[int] | None:
    vals: set[int] = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, _, raw_step = part.partition("/")
            if not raw_step.isdigit() or int(raw_step) == 0:
                return None
            step = int(raw_step)
        if part == "*":
            vals.update(range(lo, hi + 1, step))
        elif "-" in part:
            a, _, b = part.partition("-")
            if not (a.isdigit() and b.isdigit()):
                return None
            ai, bi = int(a), int(b)
            if ai < lo or bi > hi or ai > bi:
                return None
            vals.update(range(ai, bi + 1, step))
        else:
            if not part.isdigit():
                return None
            v = int(part)
            if v < lo or v > hi:
                return None
            if step > 1:
                vals.update(range(v, hi + 1, step))
            else:
                vals.add(v)
    return vals or None


def _cron_fields(expr: str):
    """Return (minute, hour, dom, month, dow, dom_all, dow_all).
    *_all = True bila field aslinya '*' (tidak dibatasi)."""
    parts = expr.split()
    if len(parts) != 5:
        return None
    minute = _parse_field(parts[0], 0, 59)
    hour = _parse_field(parts[1], 0, 23)
    dom = _parse_field(parts[2], 1, 31)
    month = _parse_field(parts[3], 1, 12)
    dow_raw = _parse_field(parts[4], 0, 7)
    if None in (minute, hour, dom, month, dow_raw):
        return None
    # cron: 0 dan 7 sama-sama Minggu; Python Monday=0 → cron_dow=(weekday+1)%7
    dow = {0 if d == 7 else d for d in dow_raw}
    dom_all = parts[2] == "*"
    dow_all = parts[4] == "*"
    return minute, hour, dom, month, dow, dom_all, dow_all


def _cron_valid(expr: str) -> bool:
    return _cron_fields(expr) is not None


def cron_matches(expr: str, dt: datetime) -> bool:
    fields = _cron_fields(expr)
    if fields is None:
        return False
    minute, hour, dom, month, dow, dom_all, dow_all = fields
    cron_dow = (dt.weekday() + 1) % 7
    dom_ok = dt.day in dom
    dow_ok = cron_dow in dow
    # semantik cron standar:
    # - salah satu field '*' → keduanya harus cocok (yang '*' otomatis cocok)
    # - keduanya dibatasi → cukup salah satu cocok
    if dom_all and dow_all:
        day_ok = True
    elif dom_all:
        day_ok = dow_ok
    elif dow_all:
        day_ok = dom_ok
    else:
        day_ok = dom_ok or dow_ok
    return (
        dt.minute in minute
        and dt.hour in hour
        and dt.month in month
        and day_ok
    )


def next_run(expr: str, from_dt: datetime) -> datetime | None:
    """Waktu eksekusi berikutnya (analitik per hari, bukan per menit)."""
    fields = _cron_fields(expr)
    if fields is None:
        return None
    minutes, hours, dom, month, dow, dom_all, dow_all = fields

    base = from_dt.replace(second=0, microsecond=0)
    for offset in range(0, 366 * 4):
        day = (base + timedelta(days=offset)).date()
        if day.month not in month:
            continue
        cron_dow = (day.weekday() + 1) % 7
        dom_ok = day.day in dom
        dow_ok = cron_dow in dow
        if dom_all and dow_all:
            day_ok = True
        elif dom_all:
            day_ok = dow_ok
        elif dow_all:
            day_ok = dom_ok
        else:
            day_ok = dom_ok or dow_ok
        if not day_ok:
            continue
        start_hour = base.hour if offset == 0 else 0
        for h in sorted(hours):
            if h < start_hour:
                continue
            start_min = base.minute + 1 if (offset == 0 and h == base.hour) else 0
            for m in sorted(minutes):
                if m < start_min:
                    continue
                return datetime(day.year, day.month, day.day, h, m)
    return None


# ------------------------------------------------------------- eksekusi
_PANEL_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


def _dump_postgres(url: str, out: Path) -> Path:
    """pg_dump database dari URL postgresql(+psycopg2)://... ke file SQL."""
    u = urlparse(url)
    cmd = ["pg_dump", "-h", u.hostname or "127.0.0.1"]
    if u.port:
        cmd += ["-p", str(u.port)]
    if u.username:
        cmd += ["-U", unquote(u.username)]
    dbname = u.path.lstrip("/")
    if dbname:
        cmd += ["-d", dbname]
    env = {**os.environ, "PGPASSWORD": unquote(u.password or "")}
    try:
        with out.open("wb") as fh:
            proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE, timeout=1800, env=env)
    except FileNotFoundError:
        raise RuntimeError("perintah 'pg_dump' tidak ditemukan di server")
    except subprocess.TimeoutExpired:
        raise RuntimeError("pg_dump timeout setelah 1800s")
    if proc.returncode != 0:
        msg = proc.stderr.decode(errors="replace").strip()[:2000]
        raise RuntimeError(msg or "pg_dump gagal")
    return out


def _dump_mysql(url: str, out: Path) -> Path:
    """mysqldump database dari URL mysql://... ke file SQL."""
    u = urlparse(url)
    cmd = ["mysqldump", "--single-transaction"]
    if u.hostname:
        cmd += ["-h", u.hostname]
    if u.port:
        cmd += ["-P", str(u.port)]
    if u.username:
        cmd += ["-u", unquote(u.username)]
    dbname = u.path.lstrip("/")
    if dbname:
        cmd.append(dbname)
    env = {**os.environ}
    if u.password:
        env["MYSQL_PWD"] = unquote(u.password)
    try:
        with out.open("wb") as fh:
            proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE, timeout=1800, env=env)
    except FileNotFoundError:
        raise RuntimeError("perintah 'mysqldump' tidak ditemukan di server")
    except subprocess.TimeoutExpired:
        raise RuntimeError("mysqldump timeout setelah 1800s")
    if proc.returncode != 0:
        msg = proc.stderr.decode(errors="replace").strip()[:2000]
        raise RuntimeError(msg or "mysqldump gagal")
    return out


def _panel_archive(archive: Path) -> None:
    """Arsip panel: dump database (sesuai DATABASE_URL) + file .env.

    Mendukung SQLite (tar file DB), PostgreSQL (pg_dump) dan MySQL
    (mysqldump). Hasilnya .tar.gz sehingga restore tetap non-destruktif.
    """
    url = get_settings().database_url
    with tempfile.TemporaryDirectory(prefix="panel-backup-") as tmp:
        tmp_dir = Path(tmp)
        items: list[Path] = []
        if url.startswith("sqlite:///"):
            db_path = Path(url.replace("sqlite:///", "", 1)).resolve()
            if not db_path.exists():
                raise RuntimeError("File database panel tidak ditemukan")
            items.append(db_path)
        elif url.startswith(("postgresql", "postgres")):
            items.append(_dump_postgres(url, tmp_dir / "panel-db.sql"))
        elif url.startswith("mysql"):
            items.append(_dump_mysql(url, tmp_dir / "panel-db.sql"))
        else:
            raise RuntimeError(
                f"Database tidak didukung untuk backup panel: {url.split('://', 1)[0]}"
            )
        if _PANEL_ENV_PATH.exists():
            items.append(_PANEL_ENV_PATH)
        _make_tar(archive, items)


def _make_tar(archive: Path, items: list[Path]) -> None:
    with tarfile.open(archive, "w:gz") as tf:
        for item in items:
            tf.add(item, arcname=item.name)


def _dump_to_gz(cmd: list[str], archive: Path, timeout: int) -> tuple[bool, str]:
    try:
        with gzip.open(archive, "wb") as fh:
            proc = subprocess.run(
                cmd, stdout=fh, stderr=subprocess.PIPE, timeout=timeout
            )
    except FileNotFoundError:
        return False, f"perintah '{cmd[0]}' tidak ditemukan di server"
    except subprocess.TimeoutExpired:
        return False, f"{cmd[0]} timeout setelah {timeout}s"
    if proc.returncode != 0:
        return False, proc.stderr.decode(errors="replace").strip()[:2000]
    return True, ""


def _execute(job: BackupJob) -> tuple[str, int, str]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest_dir = Path(job.destination)
    dest_dir.mkdir(parents=True, exist_ok=True)

    if job.type == "panel":
        archive = dest_dir / f"{job.name}-{stamp}.tar.gz"
        _panel_archive(archive)

    elif job.type in ("directory", "config"):
        src = Path(job.source)
        archive = dest_dir / f"{job.name}-{stamp}.tar.gz"
        _make_tar(archive, [src])

    elif job.type == "mysql":
        archive = dest_dir / f"{job.name}-{stamp}.sql.gz"
        ok, msg = _dump_to_gz(["mysqldump", "--single-transaction", job.source], archive, 1800)
        if not ok:
            archive.unlink(missing_ok=True)
            raise RuntimeError(msg)

    else:  # postgres
        archive = dest_dir / f"{job.name}-{stamp}.sql.gz"
        ok, msg = _dump_to_gz(["pg_dump", job.source], archive, 1800)
        if not ok:
            archive.unlink(missing_ok=True)
            raise RuntimeError(msg)

    size = archive.stat().st_size
    removed = apply_retention(dest_dir, job.name, job.retention_days)
    msg_ret = f", {removed} file lama dihapus retensi" if removed else ""
    return str(archive), size, f"OK{msg_ret}"


def apply_retention(dest_dir: Path, prefix: str, days: int) -> int:
    cutoff = time.time() - days * 86400
    removed = 0
    for f in dest_dir.glob(f"{prefix}-*"):
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
            removed += 1
    return removed


def trigger(job_id: int) -> int | None:
    """Jalankan job di thread terpisah. Return id run, atau None jika
    job sedang berjalan / tidak ditemukan."""
    with _lock:
        if job_id in _running_jobs:
            return None
        _running_jobs.add(job_id)

    def _worker() -> None:
        db = SessionLocal()
        try:
            job = db.get(BackupJob, job_id)
            if job is None:
                return
            run = BackupRun(
                job_id=job.id,
                job_name=job.name,
                status="RUNNING",
                started_at=datetime.utcnow(),
            )
            db.add(run)
            db.commit()
            try:
                path, size, message = _execute(job)
                run.status = "SUCCESS"
                run.file_path = path
                run.size_bytes = size
                run.message = message[:2000]
                # rapikan riwayat: run job ini yang lebih tua dari retensi
                # (file arsipnya sudah dihapus apply_retention)
                cutoff = datetime.utcnow() - timedelta(days=job.retention_days)
                db.query(BackupRun).filter(
                    BackupRun.job_id == job.id,
                    BackupRun.started_at < cutoff,
                ).delete(synchronize_session=False)
            except Exception as exc:  # noqa: BLE001 — catat apa pun ke riwayat
                run.status = "FAILED"
                run.message = str(exc)[:2000]
            run.finished_at = datetime.utcnow()
            db.commit()
        finally:
            with _lock:
                _running_jobs.discard(job_id)
            db.close()

    threading.Thread(target=_worker, daemon=True, name=f"backup-{job_id}").start()
    return job_id


# ------------------------------------------------------------- restore
def restore_archive(run: BackupRun) -> tuple[str, str]:
    """Ekstrak arsip ke folder restored-<ts> di dalam destination.
    TIDAK pernah menimpa data live."""
    archive = Path(run.file_path)
    dest_dir = archive.parent / f"restored-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tf:
        tf.extractall(dest_dir, filter="data")  # noqa: S202 — filter data blokir path traversal
    return str(dest_dir), "Arsip diekstrak (data live tidak ditimpa)"


def restore_sql(run: BackupRun, job_type: str, source_db: str) -> tuple[str, str]:
    """Impor dump SQL kembali ke database. Menimpa isi database tujuan."""
    archive = Path(run.file_path)
    cmd = ["mysql", source_db] if job_type == "mysql" else ["psql", "-d", source_db]
    try:
        with gzip.open(archive, "rb") as fh:
            proc = subprocess.run(cmd, stdin=fh, stderr=subprocess.PIPE, timeout=3600)
    except FileNotFoundError:
        raise RuntimeError(f"perintah '{cmd[0]}' tidak ditemukan di server")
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="replace").strip()[:2000])
    return source_db, "Dump berhasil diimpor ke database"


# ------------------------------------------------------------- scheduler
def _scheduler_loop() -> None:
    while True:
        now = datetime.now()
        nxt = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        time.sleep(max(0.0, (nxt - now).total_seconds()))
        fire_minute = nxt
        db = SessionLocal()
        try:
            jobs = db.query(BackupJob).filter(BackupJob.enabled.is_(True)).all()
            for job in jobs:
                if not job.schedule:
                    continue
                if not cron_matches(job.schedule, fire_minute):
                    continue
                if _last_fired.get(job.id) == fire_minute:
                    continue
                _last_fired[job.id] = fire_minute
                trigger(job.id)
        except Exception:  # noqa: BLE001 — scheduler tidak boleh mati
            import logging
            logging.getLogger(__name__).warning("backup scheduler error", exc_info=True)
        finally:
            db.close()


def start_scheduler() -> None:
    threading.Thread(
        target=_scheduler_loop, daemon=True, name="backup-scheduler"
    ).start()
