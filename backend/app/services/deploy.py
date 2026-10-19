"""Deploy website via zip upload — update folder tanpa mematikan service.

Alur kerja:
1. Zip project diekstrak ke staging secara aman (anti zip-slip, batas
   ukuran, symlink diabaikan).
2. Isi staging disalin OVER folder live in-place, sehingga folder di server
   tetap di inode yang sama — dev-server yang auto-reload langsung melihat
   versi baru dan website tidak pernah mati (file hanya "diganti").
3. File milik server (`.env`, node_modules, vendor, .next, venv, .git,
   __pycache__) dipertahankan: tidak ditimpa/hapus dari zip. `.env*` hanya
   ditimpa bila zip memang memuatnya.
4. Folder lama dibackup dulu sebagai jaring pengaman; bila terjadi error,
   isi backup dipulihkan otomatis (rollback).
5. Opsional: restart service atau sync ke Docker container — default off.
"""

import logging
import os
import re
import shutil
import stat as statmod
import threading
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from ..db.database import SessionLocal
from ..db.models import WebApp, WebService
from ..services import audit

log = logging.getLogger(__name__)

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_MAX_LINES = 400
_MAX_JOBS = 20
_CHUNK = 8 * 1024 * 1024
_MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "5120")) * 1024 * 1024

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_DEPLOY_DIR = _BACKEND_DIR / "data" / "deploys"

# entri yang SELALU milik server — tidak pernah ditimpa/dihapus oleh zip.
# Ini terutama direktori build/dependency; cadangan disimpan terpisah.
_ALWAYS_SERVER = {
    "node_modules",
    "vendor",
    ".next",
    ".venv",
    "venv",
    "__pycache__",
    ".git",
}


class DeployError(Exception):
    pass


# ------------------------------------------------------------- job store
def _safe_job(job: dict) -> dict:
    return {
        **{k: v for k, v in job.items() if k != "log"},
        "log": list(job.get("log", [])),
    }


def _set(jid: str, **kw: object) -> None:
    with _jobs_lock:
        job = _jobs.get(jid)
        if job:
            job.update(kw)


def _log(jid: str, line: str) -> None:
    with _jobs_lock:
        job = _jobs.get(jid)
        if job is None:
            return
        buf = job["log"]
        if len(buf) >= _MAX_LINES:
            buf.pop(0)
        buf.append(line)


def get_job(job_id: str) -> dict | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        return _safe_job(job) if job else None


def uploads_dir() -> Path:
    d = _DEPLOY_DIR / "tmp" / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ------------------------------------------------------------ zip extract
def _extract_zip(zip_path: Path, dest: Path) -> Path:
    """Ekstrak zip dengan aman; return akar proyek (folder tunggal bila ada)."""
    dest.mkdir(parents=True, exist_ok=True)
    total = 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if not name or name.startswith("__MACOSX/"):
                continue
            parts = Path(name).parts
            if name.startswith("/") or ".." in parts:
                raise DeployError(f"Zip berisi path tidak aman: {name}")
            total += info.file_size
            if total > _MAX_UPLOAD_BYTES:
                raise DeployError("Ukuran isi zip melebihi batas upload")
            mode = (info.external_attr >> 16) & 0o777
            is_symlink = statmod.S_IFMT(info.external_attr >> 16) == statmod.S_IFLNK
            target = dest / name
            if is_symlink:
                continue  # abaikan symlink di dalam zip
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out, _CHUNK)
            if mode:
                try:
                    target.chmod(mode)
                except OSError:
                    pass

    # bersihkan sampah macOS
    macox = dest / "__MACOSX"
    if macox.exists():
        shutil.rmtree(macox, ignore_errors=True)
    for f in dest.rglob(".DS_Store"):
        try:
            f.unlink()
        except OSError:
            pass

    entries = [e for e in dest.iterdir() if e.is_dir() and not e.name.startswith(".")]
    if len(entries) == 1:
        return entries[0]
    return dest


# ------------------------------------------------------------ file update
def _rel_list(src: Path) -> set[str]:
    rels: set[str] = set()
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in _ALWAYS_SERVER]
        for name in files:
            rels.add(os.path.relpath(os.path.join(root, name), src))
    return rels


def _copy_tree(src: Path, dst: Path) -> dict:
    counts = {"updated": 0, "skipped": 0}
    for root, dirs, files in os.walk(src):
        rel_root = os.path.relpath(root, src)
        dirs[:] = [d for d in dirs if d not in _ALWAYS_SERVER]
        dst_root = dst if rel_root == "." else dst / rel_root
        dst_root.mkdir(parents=True, exist_ok=True)
        for name in files:
            if name in _ALWAYS_SERVER or name == ".DS_Store":
                counts["skipped"] += 1
                continue
            s = Path(root) / name
            d = dst_root / name
            try:
                if d.is_symlink() or d.exists():
                    d.unlink()
                shutil.copy2(s, d, follow_symlinks=False)
                counts["updated"] += 1
            except OSError as exc:
                raise DeployError(f"gagal menyalin {s}: {exc}")
    return counts


def _remove_stale(src_rels: set[str], dst: Path) -> int:
    """Hapus file lama yang tidak ada di versi baru (kecuali milik server)."""
    removed = 0
    for root, dirs, files in os.walk(dst):
        dirs[:] = [d for d in dirs if d not in _ALWAYS_SERVER]
        for name in files:
            if name in _ALWAYS_SERVER or name.startswith(".env") or name == ".DS_Store":
                continue
            rel = os.path.relpath(os.path.join(root, name), dst)
            if rel not in src_rels:
                try:
                    os.unlink(os.path.join(root, name))
                    removed += 1
                except OSError:
                    pass
    return removed


def _ignore_heavy(_dir: str, names: list[str]) -> set[str]:
    return {n for n in names if n in _ALWAYS_SERVER}


def _make_backup(app_id: int, svc_dir: Path, label: str) -> Path:
    base = _DEPLOY_DIR / f"app_{app_id}" / "backups"
    base.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("_") or "svc"
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    bk = base / f"{safe}_{ts}"
    shutil.copytree(
        svc_dir, bk, symlinks=True, ignore=_ignore_heavy, ignore_dangling_symlinks=True
    )
    return bk


def _restore_backup(bk: Path, svc_dir: Path) -> None:
    if not bk.is_dir():
        return
    _copy_tree(bk, svc_dir)
    src_rels = _rel_list(bk)
    _remove_stale(src_rels, svc_dir)


def _prune_backups(app_id: int, keep: int = 3) -> None:
    base = _DEPLOY_DIR / f"app_{app_id}" / "backups"
    if not base.is_dir():
        return
    backups = sorted(
        (p for p in base.iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
    )
    for old in backups[:-keep]:
        shutil.rmtree(old, ignore_errors=True)


# ------------------------------------------------------------ worker
def _record_audit(app_id: int, username: str, result: str, detail: str = "") -> None:
    try:
        db = SessionLocal()
        try:
            app = db.get(WebApp, app_id)
            audit.record(
                db, username, "WEB_DEPLOY",
                target=app.name if app else f"app-{app_id}",
                result=result,
                detail=detail[:500] if detail else "",
            )
            db.commit()
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        log.warning("gagal mencatat audit deploy", exc_info=True)


def _worker(
    jid: str,
    app_id: int,
    svc_id: int,
    zip_path: str,
    restart: bool,
    sync_docker: bool,
    username: str,
) -> None:
    from ..services import websites as runner

    db = None
    svc_dir: Path | None = None
    backup: Path | None = None
    touched = False
    try:
        db = SessionLocal()
        svc = db.get(WebService, svc_id)
        if svc is None or svc.app_id != app_id:
            raise DeployError("Service tidak ditemukan")
        app = db.get(WebApp, app_id)
        if app is None:
            raise DeployError("Website tidak ditemukan")

        svc_dir = Path(svc.dir).expanduser()
        label = svc.label or svc_dir.name or f"svc-{svc.id}"
        _log(jid, f"Target: {label} → {svc_dir}")
        _log(jid, "Website tetap online selama update (file diganti di lokasi).")

        _set(jid, stage="extract", progress=8)
        staging = _DEPLOY_DIR / "tmp" / jid / "staging"
        new_root = _extract_zip(Path(zip_path), staging)
        if not new_root.is_dir():
            raise DeployError("Isi zip bukan sebuah folder proyek")
        _log(jid, f"Zip diekstrak: {staging}")

        if not svc_dir.is_dir():
            svc_dir.mkdir(parents=True, exist_ok=True)

        _set(jid, stage="backup", progress=35)
        was_running = bool(svc.pid and runner.pid_alive(svc.pid))
        backup = _make_backup(app_id, svc_dir, label)
        _log(jid, f"Backup folder lama: {backup}")
        touched = True

        _set(jid, stage="update", progress=60)
        src_rels = _rel_list(new_root)
        counts = _copy_tree(new_root, svc_dir)
        removed = _remove_stale(src_rels, svc_dir)
        _log(
            jid,
            f"File: {counts['updated']} disalin, {removed} dihapus, "
            f"{counts['skipped']} dilewati (milik server) — "
            "versi baru aktif.",
        )
        _prune_backups(app_id)
        touched = False  # sudah sukses; backup tak perlu dikembalikan otomatis

        if app.runtime == "docker" and sync_docker and app.docker_container:
            _set(jid, stage="docker-sync", progress=88)
            try:
                from .collectors import sync_folder_to_container

                res = sync_folder_to_container(str(svc_dir), app.docker_container, label)
                _log(jid, res.get("output", "Docker disinkronkan."))
            except Exception as exc:  # noqa: BLE001
                _log(jid, f"[deploy] peringatan docker sync: {exc}")
        elif restart and was_running:
            _set(jid, stage="restart", progress=92)
            runner.stop_service(db, svc)
            err = runner.start_service(db, svc, set())
            if err:
                raise DeployError(f"Restart gagal: {err}")
            _log(jid, "Service di-restart — versi baru aktif.")
        elif was_running:
            _log(jid, "Service dibiarkan berjalan; reload otomatis membaca file baru.")

        audit.record(db, username, "WEB_DEPLOY", target=app.name, result="SUCCESS")
        db.commit()
        _set(
            jid, status="done", stage="done", progress=100,
            finished_at=datetime.utcnow().isoformat(),
        )
    except DeployError as exc:
        if touched and backup and backup.is_dir() and svc_dir:
            _log(jid, f"[deploy] error: {exc}")
            _log(jid, f"[deploy] rollback ke backup: {backup}")
            try:
                _restore_backup(backup, svc_dir)
                _log(jid, "Rollback selesai.")
            except Exception:  # noqa: BLE001
                _log(jid, "[deploy] GAGAL rollback — hubungi admin.")
        _record_audit(app_id, username, "FAILED", str(exc))
        _set(jid, status="failed", stage="failed", error=str(exc),
             finished_at=datetime.utcnow().isoformat())
        log.warning("deploy %s gagal: %s", jid, exc)
    except Exception as exc:  # noqa: BLE001
        _record_audit(app_id, username, "FAILED", f"{type(exc).__name__}: {exc}")
        _set(jid, status="failed", stage="failed",
             error=f"{type(exc).__name__}: {exc}",
             finished_at=datetime.utcnow().isoformat())
        log.exception("deploy %s error", jid)
    finally:
        if db is not None:
            db.close()
        try:
            staging = _DEPLOY_DIR / "tmp" / jid
            shutil.rmtree(staging, ignore_errors=True)
            Path(zip_path).unlink(missing_ok=True)
        except OSError:
            pass


def start_deploy(
    app: WebApp,
    svc: WebService,
    zip_path: str,
    restart: bool,
    sync_docker: bool,
    username: str,
) -> str:
    _DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
    jid = uuid.uuid4().hex[:12]
    job = {
        "id": jid,
        "app_id": app.id,
        "service_id": svc.id,
        "service_label": svc.label,
        "dir": svc.dir,
        "status": "running",
        "stage": "start",
        "progress": 0,
        "log": [],
        "error": None,
        "started_at": datetime.utcnow().isoformat(),
        "finished_at": None,
    }
    with _jobs_lock:
        done = [k for k, v in _jobs.items() if v["status"] != "running"]
        for k in sorted(done, key=lambda k: _jobs[k]["started_at"])[:-_MAX_JOBS]:
            _jobs.pop(k, None)
        _jobs[jid] = job

    threading.Thread(
        target=_worker,
        args=(jid, app.id, svc.id, zip_path, restart, sync_docker, username),
        daemon=True,
        name=f"deploy-{jid}",
    ).start()
    return jid