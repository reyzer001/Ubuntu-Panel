"""Kontrol akses publik panel lewat zrok2 (toggle khusus superadmin).

Proses zrok2 dijalankan di foreground (mode lokal) dan dipegang oleh backend.
URL publik memakai reserved name zrok v2, sehingga tetap sama setiap kali
toggle diaktifkan.
"""

import logging
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path

import psutil

log = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _BACKEND_DIR / "data"
_PID_FILE = _DATA_DIR / "myzrok.pid"
_LOG_FILE = _DATA_DIR / "myzrok.log"

_ZROK_BIN = os.environ.get("ZROK_BIN", "zrok2")
_ZROK_NAME = os.environ.get("ZROK_SHARE_NAME", "ubuntu-panel")
_ZROK_NAMESPACE = os.environ.get("ZROK_SHARE_NAMESPACE", "public")
_FRONTEND_PORT = int(os.environ.get("FRONTEND_PORT", "3000"))
_TARGET = f"http://127.0.0.1:{_FRONTEND_PORT}"
_SHARE_URL = os.environ.get(
    "ZROK_SHARE_URL", f"https://{_ZROK_NAME}.shares.zrok.io"
).rstrip("/")

_START_TIMEOUT = 20.0
_DOMAIN_RE = re.compile(r"[a-z0-9.-]+\.shares\.zrok\.io", re.IGNORECASE)

_lock = threading.Lock()


def _pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def _matches_share(pid: int) -> bool:
    """True bila PID benar-benar proses share zrok2 milik panel ini."""
    try:
        proc = psutil.Process(pid)
        cmd = " ".join(proc.cmdline())
    except psutil.Error:
        return False
    low = cmd.lower()
    return (
        "zrok2" in low
        and "share" in low
        and "public" in low
        and (_ZROK_NAME.lower() in low or _TARGET.lower() in low)
    )


def _read_pid() -> int | None:
    try:
        raw = _PID_FILE.read_text().strip()
        return int(raw) if raw else None
    except (OSError, ValueError):
        return None


def _write_pid(pid: int) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(str(pid))


def _remove_pid() -> None:
    try:
        _PID_FILE.unlink()
    except OSError:
        pass


def _find_process() -> int | None:
    """Cari proses share zrok2 yang hidup (tercatat atau orphan)."""
    recorded = _read_pid()
    if recorded and _pid_alive(recorded) and _matches_share(recorded):
        return recorded

    for proc in psutil.process_iter(["pid"]):
        try:
            pid = proc.info["pid"]
            if pid == os.getpid():
                continue
            if _matches_share(pid):
                _write_pid(pid)
                return pid
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return None


def _read_log(max_bytes: int = 64_000) -> str:
    try:
        data = _LOG_FILE.read_bytes()[-max_bytes:]
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _tail(lines: int = 20) -> list[str]:
    text = _read_log()
    if not text:
        return []
    return text.splitlines()[-lines:]


def _error_detail(limit: int = 400) -> str:
    """Pesan error ringkas dari log JSON zrok2."""
    for line in reversed(_tail(40)):
        m = re.search(r'"msg":"(.*?)"', line)
        if m:
            return m.group(1).replace("\\n", " ")[:limit]
    tail = _tail(3)
    return (" | ".join(tail) if tail else "proses zrok2 keluar")[:limit]


def _discover_url() -> str:
    """Ambil URL share dari log bila reserved URL berbeda dari konfigurasi."""
    m = _DOMAIN_RE.search(_read_log())
    if m:
        return f"https://{m.group(0).lower()}"
    return _SHARE_URL


def _status_unlocked() -> dict:
    pid = _find_process()
    running = pid is not None
    url = _discover_url() if running else _SHARE_URL
    return {
        "running": running,
        "pid": pid,
        "url": url,
        "login_url": f"{url.rstrip('/')}/login",
        "target": _TARGET,
        "name": f"{_ZROK_NAMESPACE}:{_ZROK_NAME}",
        "log_tail": _tail(40),
    }


def status() -> dict:
    with _lock:
        return _status_unlocked()


def _terminate(pid: int) -> None:
    if not _pid_alive(pid):
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    for _ in range(12):
        time.sleep(0.25)
        if not _pid_alive(pid):
            return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def start() -> dict:
    """Aktifkan share publik. Idempotent bila sudah berjalan."""
    with _lock:
        existing = _find_process()
        if existing:
            return _status_unlocked()

        binary = shutil.which(_ZROK_BIN)
        if not binary:
            raise RuntimeError(
                f"{_ZROK_BIN} tidak ditemukan di PATH. Pastikan zrok2 terpasang."
            )

        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        log_fh = None
        try:
            log_fh = open(_LOG_FILE, "wb")
            proc = subprocess.Popen(
                [
                    binary,
                    "share",
                    "public",
                    _TARGET,
                    "-n",
                    f"{_ZROK_NAMESPACE}:{_ZROK_NAME}",
                    "--headless",
                ],
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise RuntimeError(f"gagal menjalankan {_ZROK_BIN}: {exc}") from exc
        finally:
            if log_fh is not None:
                try:
                    log_fh.close()
                except Exception:  # noqa: BLE001
                    pass

        _write_pid(proc.pid)
        deadline = time.monotonic() + _START_TIMEOUT
        ready = False
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                _remove_pid()
                raise RuntimeError(f"zrok2 gagal dimulai: {_error_detail()}")
            log_text = _read_log()
            if ".shares.zrok.io" in log_text or "access your zrok share" in log_text:
                ready = True
                break
            time.sleep(0.4)

        if not ready:
            _terminate(proc.pid)
            _remove_pid()
            raise RuntimeError(
                "zrok2 tidak siap dalam batas waktu. Cek log myzrok di server."
            )

        log.info("myzrok share aktif: %s -> %s", _TARGET, _discover_url())
        return _status_unlocked()


def stop() -> dict:
    """Matikan share publik (termasuk proses orphan)."""
    with _lock:
        pid = _find_process()
        if pid:
            _terminate(pid)
            if _pid_alive(pid):
                raise RuntimeError(f"gagal menghentikan proses zrok2 (PID {pid})")
            log.info("myzrok share dihentikan (PID %d)", pid)
        _remove_pid()
        return _status_unlocked()
