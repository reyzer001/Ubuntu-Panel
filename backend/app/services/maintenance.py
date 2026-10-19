"""Maintenance: cleanup (journal/apt), update & upgrade sistem, reboot.

Operasi panjang (apt) dijalankan sebagai background task yang bisa
di-poll lewat endpoint /maintenance/tasks/{id}. Karena backend umumnya
bukan root, perintah dibungkus sudo: `sudo -n` (non-interaktif) bila
passwordless sudo tersedia, atau `sudo -S` dengan password yang dikirim
user lewat web (via stdin, tidak pernah masuk argv/ps).

Password sudo TIDAK disimpan: hanya dipakai sesaat untuk memvalidasi dan
menjalankan perintah.
"""

import getpass
import os
import re
import shutil
import signal
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path

_tasks: dict[str, dict] = {}
_lock = threading.Lock()
_MAX_LINES = 400

TASK_KINDS = {
    "apt_update": (["apt-get", "update"], 600),
    "apt_upgrade": (
        ["apt-get", "upgrade", "-y", "-o", "Dpkg::Options::=--force-confold"],
        7200,
    ),
    "apt_autoremove": (["apt-get", "autoremove", "-y"], 1800),
}

_ERROR_RE = re.compile(
    r"^E:|^Err:|^ERROR|dpkg: error|error processing|\bfailed\b|"
    r"could not|unable to|no space left|sudo:.*(password|incorrect)",
    re.IGNORECASE,
)
_WARN_RE = re.compile(r"^W:|^warning|warning:", re.IGNORECASE)


def _is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def is_root() -> bool:
    return _is_root()


def os_username() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return "?"


def _sudo_prefix(password: str | None = None) -> list[str]:
    """Argv prefix pengganti root.

    - root: tanpa sudo.
    - ada password: `sudo -S -k -p ''` (password dibaca dari stdin).
    - tanpa password: `sudo -n` (passwordless; gagal bersih bila belum diatur).
    """
    if _is_root():
        return []
    if password:
        return ["sudo", "-S", "-k", "-p", ""]
    return ["sudo", "-n"]


def sudo_nopasswd() -> bool:
    """True bila perintah maintenance diizinkan NOPASSWD di sudoers.

    Dicek lewat `sudo -n -l` (tidak memicu prompt). `sudo -n true` tidak
    dipakai karena sudoers bisa mengizinkan perintah spesifik (apt-get,
    systemctl, ...) tanpa mengizinkan `true`.
    """
    if _is_root():
        return True
    try:
        proc = subprocess.run(
            ["sudo", "-n", "-l"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:  # noqa: BLE001
        return False
    if proc.returncode != 0 or "NOPASSWD:" not in (proc.stdout or ""):
        return False
    nopasswd = proc.stdout.split("NOPASSWD:", 1)[1]
    return "apt-get" in nopasswd and "systemctl" in nopasswd


def verify_sudo(password: str) -> tuple[bool, str]:
    """Validasi password sudo lebih dulu agar task panjang tidak sia-sia.

    Password dikirim via stdin (`sudo -S`) — tidak pernah muncul di argv.
    """
    if _is_root() or not password:
        return True, ""
    try:
        proc = subprocess.run(
            ["sudo", "-S", "-k", "-p", "", "-v"],
            input=password + "\n",
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:200]
    if proc.returncode == 0:
        return True, ""
    err = (proc.stderr or "").strip().replace("\n", " ")
    return False, err[:200] or "password sudo ditolak"


def _extract_issues(lines: list[str]) -> dict:
    """Pisahkan baris output menjadi daftar error & warning."""
    errors: list[str] = []
    warnings: list[str] = []
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        if _ERROR_RE.search(s):
            errors.append(s)
        elif _WARN_RE.search(s):
            warnings.append(s)
    return {"errors": errors[:200], "warnings": warnings[:200]}


def _run(
    cmd: list[str],
    timeout: int = 60,
    priv: bool = False,
    password: str | None = None,
) -> subprocess.CompletedProcess:
    """priv=True hanya untuk perintah yang benar-benar butuh root
    (apt-get, vacuum). Perintah read-only berjalan sebagai user biasa."""
    argv = (_sudo_prefix(password) + cmd) if priv else cmd
    data = password + "\n" if (priv and password and not _is_root()) else None
    return subprocess.run(
        argv,
        input=data,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ------------------------------------------------------------- task API
def start_task(kind: str, password: str | None = None) -> str | None:
    if kind not in TASK_KINDS:
        return None
    cmd, timeout = TASK_KINDS[kind]
    task_id = uuid.uuid4().hex[:12]
    task = {
        "id": task_id,
        "kind": kind,
        "status": "running",
        "started_at": datetime.utcnow().isoformat(),
        "finished_at": None,
        "returncode": None,
        "output": [],
        "errors": [],
        "warnings": [],
    }
    with _lock:
        # batasi riwayat task in-memory agar tidak bocor memori
        done = [k for k, v in _tasks.items() if v["status"] != "running"]
        for k in sorted(done, key=lambda k: _tasks[k]["started_at"])[:-9]:
            _tasks.pop(k, None)
        _tasks[task_id] = task

    def _finalize(rc: int, extra: str | None = None) -> None:
        with _lock:
            buf = _tasks.get(task_id)
            if buf is None:
                return
            if extra:
                buf["output"].append(extra)
            issues = _extract_issues(buf["output"])
            buf["errors"] = issues["errors"]
            buf["warnings"] = issues["warnings"]
            buf["returncode"] = rc
            buf["status"] = "done" if rc == 0 else "failed"
            buf["finished_at"] = datetime.utcnow().isoformat()

    def _worker() -> None:
        needs_pw = bool(password) and not _is_root()
        env = {
            **os.environ,
            "DEBIAN_FRONTEND": "noninteractive",
            "DEBIAN_PRIORITY": "critical",
        }
        try:
            proc = subprocess.Popen(
                _sudo_prefix(password) + cmd,
                stdin=subprocess.PIPE if needs_pw else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                start_new_session=True,
                env=env,
            )
            if needs_pw and proc.stdin is not None:
                try:
                    proc.stdin.write(password + "\n")
                    proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
                finally:
                    try:
                        proc.stdin.close()
                    except OSError:
                        pass
            assert proc.stdout is not None
            for line in proc.stdout:
                with _lock:
                    buf = _tasks.get(task_id)
                    if buf is not None and len(buf["output"]) < _MAX_LINES:
                        buf["output"].append(line.rstrip("\n"))
            try:
                rc = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    try:
                        proc.kill()
                    except (ProcessLookupError, OSError):
                        pass
                _finalize(-1, f"[panel] timeout setelah {timeout}s")
                return
            _finalize(rc)
            if rc != 0:
                msg = (
                    "[panel] gagal — kemungkinan password sudo salah"
                    if needs_pw
                    else "[panel] gagal — butuh sudo tanpa password?"
                )
                with _lock:
                    buf = _tasks.get(task_id)
                    if buf is not None and not buf["errors"]:
                        buf["errors"] = [msg]
        except FileNotFoundError as exc:
            _finalize(-1, str(exc))

    threading.Thread(target=_worker, daemon=True, name=f"maint-{task_id}").start()
    return task_id


def get_task(task_id: str) -> dict | None:
    with _lock:
        task = _tasks.get(task_id)
        return dict(task) if task else None


# ------------------------------------------------------------- aksi cepat
def cleanup(
    journal_days: int | None,
    apt_clean: bool,
    password: str | None = None,
) -> list[dict]:
    results: list[dict] = []
    if journal_days:
        try:
            proc = _run(
                ["journalctl", f"--vacuum-time={int(journal_days)}d"],
                timeout=120,
                priv=True,
                password=password,
            )
            results.append({
                "action": f"journal_vacuum_{journal_days}d",
                "success": proc.returncode == 0,
                "output": (proc.stdout or proc.stderr).strip()[:2000],
            })
        except subprocess.TimeoutExpired:
            results.append({"action": f"journal_vacuum_{journal_days}d", "success": False, "output": "timeout"})
        except Exception as exc:  # noqa: BLE001
            results.append({"action": f"journal_vacuum_{journal_days}d", "success": False, "output": str(exc)[:500]})
    if apt_clean:
        try:
            proc = _run(
                ["apt-get", "clean"], timeout=300, priv=True, password=password
            )
            results.append({
                "action": "apt_clean",
                "success": proc.returncode == 0,
                "output": (proc.stdout or proc.stderr).strip()[:2000]
                or ("OK" if proc.returncode == 0 else "gagal — periksa password sudo"),
            })
        except Exception as exc:  # noqa: BLE001
            results.append({"action": "apt_clean", "success": False, "output": str(exc)[:500]})
    return results


def reboot(delay_seconds: float = 1.5, password: str | None = None) -> None:
    def _worker() -> None:
        import time

        time.sleep(delay_seconds)
        data = password + "\n" if (password and not _is_root()) else None
        try:
            subprocess.run(
                _sudo_prefix(password) + ["systemctl", "reboot"],
                input=data,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_worker, daemon=True, name="maintenance-reboot").start()


# ------------------------------------------------------------- status
_JOURNAL_RE = re.compile(r"take up ([\d.]+)\s*([KMGT])")


def status() -> dict:
    du = shutil.disk_usage("/")
    journal_raw = ""
    journal_bytes = None
    try:
        proc = _run(["journalctl", "--disk-usage"], timeout=15)
        journal_raw = (proc.stdout or "").strip()
        m = _JOURNAL_RE.search(journal_raw)
        if m:
            mult = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}[m.group(2)]
            journal_bytes = int(float(m.group(1)) * mult)
    except Exception:  # noqa: BLE001
        pass

    apt_cache_bytes = 0
    cache_dir = Path("/var/cache/apt/archives")
    try:
        for f in cache_dir.glob("*.deb"):
            apt_cache_bytes += f.stat().st_size
    except Exception:  # noqa: BLE001
        pass

    upgradable = None
    try:
        proc = _run(["apt", "list", "--upgradable"], timeout=60)
        if proc.returncode == 0:
            lines = [l for l in proc.stdout.splitlines() if l and not l.startswith("Listing")]
            upgradable = len(lines)
    except Exception:  # noqa: BLE001
        pass

    return {
        "root_disk": {
            "total": du.total,
            "used": du.used,
            "percent": round(du.used / du.total * 100, 1),
        },
        "journal_usage": journal_raw,
        "journal_bytes": journal_bytes,
        "apt_cache_bytes": apt_cache_bytes,
        "upgradable": upgradable,
        "is_root": _is_root(),
        "os_user": os_username(),
        "sudo_nopasswd": sudo_nopasswd(),
    }
