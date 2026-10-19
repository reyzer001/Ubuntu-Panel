"""Runner website lokal: spawn dev-server per folder + command.

Fitur:
1. Deteksi port default dari framework (next, vite, django, laravel, ...)
   bila user tidak mengisi port; bila terpakai, cari port bebas di atasnya.
2. Spawn proses dengan session sendiri (kill process tree aman),
   output ditulis ke log file per service.
3. ONLINE berarti proses hidup DAN port merespon koneksi.
4. Monitor loop berkala memperbarui status; proses mati -> OFFLINE.
"""

import json
import logging
import os
import re
import shutil
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import psutil
from sqlalchemy.orm import Session

from ..db.models import WebService

log = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_LOG_DIR = _BACKEND_DIR / "data" / "weblogs"

# interval monitor status (detik)
_MONITOR_INTERVAL = int(os.environ.get("WEB_MONITOR_INTERVAL", "4"))

# berapa lama menunggu port siap setelah spawn (detik)
_LISTEN_TIMEOUT = 25

# urutan penting: keyword spesifik dicek sebelum generik
_FRAMEWORK_PORTS: tuple[tuple[tuple[str, ...], int], ...] = (
    (("vite",), 5173),
    (("ng serve", "angular"), 4200),
    (("nuxt",), 3000),
    (("next",), 3000),
    (("manage.py", "django"), 8000),
    (("artisan", "laravel"), 8000),
    (("flask",), 5000),
    (("uvicorn", "fastapi"), 8000),
    (("gunicorn",), 8000),
    (("rails",), 3000),
    (("go run",), 8080),
    (("cargo run",), 8080),
    (("npm", "pnpm", "yarn", "bun", "node", "deno"), 3000),
    (("python",), 8000),
    (("php",), 8000),
)


def framework_default_port(command: str) -> int:
    low = command.lower()
    for keywords, port in _FRAMEWORK_PORTS:
        if any(k in low for k in keywords):
            return port
    return 3000


def extract_port(command: str) -> int:
    """Ambil port eksplisit di dalam command user (0 bila tak ada)."""
    # --port=8000 / --port 8000
    m = re.search(r"(?:^|\s)--port(?:=|\s+)(\d{2,5})(?=\s|$)", command)
    if m:
        return _valid_port(int(m.group(1)))
    # -p 8000
    m = re.search(r"(?:^|\s)-p\s+(\d{2,5})(?=\s|$)", command)
    if m:
        return _valid_port(int(m.group(1)))
    # host:port, mis. 0.0.0.0:8000 / localhost:3000
    m = re.search(r"(?:^|\s)[\w.\-]+:(\d{2,5})(?=\s|$)", command)
    if m:
        return _valid_port(int(m.group(1)))
    # angka posisi akhir, mis. "python -m http.server 8123"
    m = re.search(r"(?:^|\s)(\d{4,5})(?=\s*$)", command)
    if m:
        return _valid_port(int(m.group(1)))
    return 0


def _valid_port(n: int) -> int:
    return n if 80 <= n <= 65535 else 0


# ---------------------------------------------------------------- bind-all
def _already_bound_anywhere(command: str) -> bool:
    """True bila command sudah menyebut host bind sendiri."""
    return bool(
        re.search(r"--host(?:=|\s)|--hostname(?:=|\s)|\b0\.0\.0\.0\b", command.lower())
    )


def bind_all_command(command: str, port: int, project_dir: str | None = None) -> str:
    """Sisipkan opsi bind 0.0.0.0 agar website bisa diakses dari IP lain.

    Tanpa ini dev-server umumnya hanya listen di 127.0.0.1 — panel menampilkan
    ONLINE (port merespon di localhost) tapi dibuka via IP LAN/Tailscale
    koneksi ditolak.
    """
    if _already_bound_anywhere(command):
        return command

    low = command.lower()

    if "artisan serve" in low:  # Laravel
        return f"{command} --host=0.0.0.0"

    if "manage.py" in low and "runserver" in low:  # Django
        # ganti argumen port bila ada, kalau tidak tambahkan addrport lengkap
        if re.search(r"\s\d{4,5}\s*$", command):
            return re.sub(r"\d{4,5}\s*$", f"0.0.0.0:{port}", command)
        return f"{command} 0.0.0.0:{port}"

    if "uvicorn" in low:
        return f"{command} --host 0.0.0.0"

    if re.search(r"(?:^|\s|-m\s+)flask(?:\s|$)", low):
        return f"{command} --host=0.0.0.0"

    if "-m http.server" in low:
        return f"{command} --bind 0.0.0.0"

    m = re.search(r"(?:^|\s)next\s+(?:dev|start)(?:\s|$)", low)
    if m:  # dipanggil langsung (bukan lewat npm run)
        return f"{command} -H 0.0.0.0"

    if re.search(r"(?:^|\s)(?:vite|nuxt(?:\s+(?:dev|build))?|ng\s+serve)(?:\s|$)", low):
        return f"{command} --host 0.0.0.0"

    # wrapper package manager: deteksi framework dari package.json proyek,
    # flag dilewatkan lewat ` -- ` (didukung npm/pnpm/yarn/bun modern)
    pm = re.match(r"\s*(?:npx\s+)?(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(\S+)", low)
    if pm and project_dir:
        try:
            pkg = json.loads(
                (Path(project_dir) / "package.json").read_text()[:200_000]
            )
        except Exception:  # noqa: BLE001 — package.json tak ada/rusak: lewati saja
            pkg = {}
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        if "next" in deps:
            return f"{command} -- -H 0.0.0.0"
        if "vite" in deps or "@angular/cli" in deps or "nuxt" in deps:
            return f"{command} -- --host 0.0.0.0"
    return command


def _port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def _port_listening(port: int, host: str = "127.0.0.1") -> bool:
    if port <= 0:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def resolve_port(
    command: str, requested: int, used: set[int] | None = None
) -> int:
    """Port final untuk sebuah service.

    Prioritas: port dari form user > port tertulis di command >
    default framework (geser ke atas bila terpakai).
    """
    used = used or set()
    effective = requested if requested > 0 else extract_port(command)
    if effective > 0:
        if effective in used or not _port_free(effective):
            raise ValueError(f"Port {effective} sudah dipakai proses lain")
        return effective
    base = framework_default_port(command)
    candidate = base
    while candidate in used or not _port_free(candidate):
        candidate += 1
        if candidate > 65535:
            raise ValueError("Tidak ada port bebas tersedia")
    return candidate


def pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def service_status(svc: WebService) -> str:
    """ONLINE bila proses hidup dan port merespon."""
    if svc.pid and pid_alive(svc.pid):
        if svc.resolved_port > 0:
            return "ONLINE" if _port_listening(svc.resolved_port) else "OFFLINE"
        return "ONLINE"
    return "OFFLINE"


def _log_file(svc_id: int) -> Path:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    return _LOG_DIR / f"svc_{svc_id}.log"


def start_service(db: Session, svc: WebService, used: set[int]) -> str | None:
    """Spawn proses untuk satu service. Return pesan error atau None."""
    if svc.pid and pid_alive(svc.pid):
        return "sudah berjalan"
    if not Path(svc.dir).is_dir():
        return f"folder tidak ditemukan: {svc.dir}"
    try:
        port = resolve_port(svc.command, svc.port, used)
    except ValueError as e:
        return str(e)
    used.add(port)

    log_path = _log_file(svc.id)
    # banyak framework hormati PORT/HOST; sisanya diberi flag bind-all eksplisit
    env = {**os.environ, "PORT": str(port), "HOST": "0.0.0.0"}
    run_command = bind_all_command(svc.command, port, svc.dir)
    try:
        log_fh = open(log_path, "ab")
        proc = subprocess.Popen(
            run_command,
            shell=True,
            cwd=svc.dir,
            env=env,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # pgid = pid -> kill tree aman
        )
    except OSError as e:
        return f"gagal spawn: {e}"
    finally:
        try:
            log_fh.close()
        except Exception:  # noqa: BLE001
            pass

    svc.pid = proc.pid
    svc.resolved_port = port
    svc.log_path = str(log_path)
    svc.status = "OFFLINE"  # monitor akan mengangkat ke ONLINE
    db.commit()

    # penanda ONLINE cepat: tunggu port siap di background thread
    threading.Thread(
        target=_wait_online, args=(svc.id, port, proc.pid),
        daemon=True, name=f"web-wait-{svc.id}",
    ).start()
    return None


def _wait_online(svc_id: int, port: int, pid: int) -> None:
    deadline = time.monotonic() + _LISTEN_TIMEOUT
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return  # mati sebelum sempat listen — biarkan monitor menandai
        if _port_listening(port):
            _set_status_if_changed(svc_id)
            return
        time.sleep(0.7)


def stop_service(db: Session, svc: WebService) -> None:
    if svc.pid and pid_alive(svc.pid):
        try:
            os.killpg(os.getpgid(svc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        # beri waktu graceful lalu paksa
        for _ in range(10):
            time.sleep(0.3)
            if not pid_alive(svc.pid):
                break
        else:
            try:
                os.killpg(os.getpgid(svc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    # service berhenti → tunnel yang mengarah ke port mati ikut dibersihkan,
    # supaya tidak ada tunnel yatim (auto-online nanti bikin URL baru).
    if svc.tunnel_pid is not None or svc.tunnel_url is not None:
        unexpose_service(db, svc)
    svc.pid = None
    svc.status = "OFFLINE"
    db.commit()


def build_docker_image(project_dir: str, dockerfile: str, tag: str) -> dict:
    from .collectors import build_website_image
    return build_website_image(project_dir, dockerfile, tag)


def start_docker_service(db: Session, svc: WebService, image: str, container: str) -> str | None:
    from .collectors import run_website_image
    try:
        port = resolve_port(svc.command, svc.port, set())
        result = run_website_image(image, container, port)
    except (ValueError, RuntimeError, OSError) as exc:
        return str(exc)
    svc.resolved_port = port
    svc.pid = result.get("pid") or None
    svc.status = "OFFLINE"
    db.commit()
    return None


def stop_docker_service(db: Session, svc: WebService, container: str) -> None:
    from .collectors import container_action
    try:
        container_action(container, "stop")
    except Exception:
        pass
    svc.pid = None
    svc.status = "OFFLINE"
    db.commit()


# ------------------------------------------------------------- monitor
def sync_all_status() -> dict:
    """Perbarui kolom status semua service sekali (transaksi pendek)."""
    from ..db.database import SessionLocal

    changed = {"online": 0, "offline": 0}
    db = SessionLocal()
    try:
        for svc in db.query(WebService).all():
            new = service_status(svc)
            if svc.pid and not pid_alive(svc.pid):
                svc.pid = None  # proses benar-benar mati
            if new != svc.status:
                svc.status = new
                changed["online" if new == "ONLINE" else "offline"] += 1
        db.commit()
        return changed
    finally:
        db.close()


def _set_status_if_changed(svc_id: int) -> None:
    from ..db.database import SessionLocal

    db = SessionLocal()
    try:
        svc = db.get(WebService, svc_id)
        if svc is None:
            return
        new = service_status(svc)
        if new != svc.status:
            svc.status = new
            db.commit()
    finally:
        db.close()


def tail_log(path: str, lines: int = 200) -> list[str]:
    p = Path(path)
    if not path or not p.is_file():
        return []
    try:
        data = p.read_bytes()[-64_000:]
        rows = data.decode("utf-8", errors="replace").splitlines()
        return rows[-lines:]
    except OSError:
        return []


# ------------------------------------------------------------- browse
def browse_dirs(path: str = "") -> dict:
    target = Path(path).expanduser().resolve() if path else Path.home()
    if not target.is_dir():
        target = Path.home()
    dirs = sorted(
        (d.name for d in target.iterdir()
         if d.is_dir() and not d.name.startswith(".")),
        key=str.lower,
    )
    parent = str(target.parent) if target.parent != target else None
    return {"path": str(target), "parent": parent, "dirs": dirs}


def which_missing(command: str) -> str:
    """Nama executable pertama yang tidak ada di PATH ('' bila lengkap)."""
    parts = command.split()
    if not parts:
        return ""
    exe = shutil.which(parts[0])
    if exe is None and "/" not in parts[0]:
        return parts[0]
    return ""


# ----------------------------------------------------------- cloudflare tunnel
_TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

# cooldown detik antara percobaan auto re-expose tiap service (cegah loop spawn
# saat cloudflared langsung mati, mis. port belum siap)
_EXPOSE_COOLDOWN = 30
_last_expose_at: dict[int, float] = {}


def _tunnel_log_path(svc_id: int) -> Path:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    return _LOG_DIR / f"tunnel_{svc_id}.log"


def find_tunnel_process(port: int) -> int | None:
    """PID proses cloudflared yang mengarah ke localhost:<port>.

    Cari diseluruh proses (bukan hanya yang tercatat di DB) sehingga tunnel
    yatim / pid yang pernah hilang tetap terdeteksi; dasar untuk expose
    idempoten, unexpose yang tuntas, dan check status.
    """
    if port <= 0:
        return None
    needle = f"localhost:{port}"
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = str(proc.info["name"] or "").lower()
            cmd = " ".join(proc.info["cmdline"] or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        if "cloudflared" not in name and "cloudflared" not in cmd:
            continue
        if "tunnel" in cmd and needle in cmd:
            return proc.info["pid"]
    return None


def _recover_tunnel_url(svc_id: int) -> str | None:
    """Ambil URL terakhir dari log tunnel (recovery saat DB kehilangan URL)."""
    try:
        data = _tunnel_log_path(svc_id).read_bytes()[-64_000:]
        text = data.decode("utf-8", errors="replace")
        matches = _TUNNEL_URL_RE.findall(text)
        return matches[-1] if matches else None
    except OSError:
        return None


def _tunnel_running_pid(svc: WebService) -> int | None:
    """Pid tunnel yang benar-benar hidup: pid tercatat atau orphan untuk port."""
    if svc.tunnel_pid and pid_alive(svc.tunnel_pid):
        return svc.tunnel_pid
    return find_tunnel_process(svc.resolved_port or 0)


def expose_service(db: Session, svc: WebService) -> str | None:
    """Start cloudflared quick tunnel mengarah ke resolved_port service.

    Idempoten: kalau tunnel untuk port ini sudah hidup (tercatat ATAU yatim),
    adopsi dan kembalikan sukses — tidak spawn duplikat. Return error atau None.
    """
    if svc.resolved_port <= 0:
        return "service belum jalan (tidak ada port)"
    # runtime docker-compose tidak punya svc.pid (container, bukan proses native);
    # cukup pastikan port sudah merespon.
    if not pid_alive(svc.pid):
        if not (svc.resolved_port > 0 and _port_listening(svc.resolved_port)):
            return "service belum jalan"

    existing = _tunnel_running_pid(svc)
    if existing:
        svc.tunnel_pid = existing
        if not svc.tunnel_url:
            svc.tunnel_url = _recover_tunnel_url(svc.id)
        db.commit()
        return None

    log_path = _tunnel_log_path(svc.id)
    try:
        log_fh = open(log_path, "wb")  # truncate agar URL lama tidak terbaca
        proc = subprocess.Popen(
            [
                "cloudflared", "tunnel",
                "--url", f"http://localhost:{svc.resolved_port}",
            ],
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as e:
        return f"gagal jalankan cloudflared: {e}"
    finally:
        try:
            log_fh.close()
        except Exception:  # noqa: BLE001
            pass

    svc.tunnel_pid = proc.pid
    svc.tunnel_url = None  # akan diisi setelah URL terdeteksi
    db.commit()

    # background thread: tunggu URL muncul di log
    threading.Thread(
        target=_wait_tunnel_url,
        args=(svc.id, proc.pid, str(log_path)),
        daemon=True, name=f"tunnel-url-{svc.id}",
    ).start()
    return None


def _wait_tunnel_url(svc_id: int, pid: int, log_path: str) -> None:
    """Tunggu cloudflared mengeluarkan URL di log (max 20 detik)."""
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return  # proses mati sebelum URL muncul
        try:
            data = Path(log_path).read_bytes()[-32_000:]
            text = data.decode("utf-8", errors="replace")
            matches = _TUNNEL_URL_RE.findall(text)
            if matches:
                _save_tunnel_url(svc_id, matches[-1])  # ambil URL terbaru
                return
        except OSError:
            pass
        time.sleep(0.8)


def _save_tunnel_url(svc_id: int, url: str) -> None:
    from ..db.database import SessionLocal

    db = SessionLocal()
    try:
        svc = db.get(WebService, svc_id)
        if svc:
            svc.tunnel_url = url
            db.commit()
    finally:
        db.close()


def unexpose_service(db: Session, svc: WebService) -> list[int]:
    """Stop cloudflared tunnel untuk service ini (trecatat + yatim).

    Return daftar PID yang berhasil dihentikan supaya frontend bisa tahu
    tombolnya benar-benar mematikan tunnel.
    """
    killed: list[int] = []
    targets: list[int] = []

    if svc.tunnel_pid and pid_alive(svc.tunnel_pid):
        targets.append(svc.tunnel_pid)
    orphan = find_tunnel_process(svc.resolved_port or 0)
    if orphan and orphan not in targets:
        targets.append(orphan)

    for pid in targets:
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        for _ in range(8):
            time.sleep(0.25)
            if not pid_alive(pid):
                break
        else:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                try:
                    os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        if not pid_alive(pid):
            killed.append(pid)

    svc.tunnel_pid = None
    svc.tunnel_url = None
    db.commit()
    return killed


def _probe_url(url: str) -> dict:
    """Probe singkat ke URL tunnel — cek apakah benar-benar bisa diakses."""
    try:
        req = urllib.request.Request(
            url, method="GET",
            headers={"User-Agent": "ubuntu-panel/check"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            resp.read(2048)
            return {"reachable": True, "status_code": resp.status, "error": None}
    except urllib.error.HTTPError as e:
        # HTTP error masih berarti reachable (server merespons)
        return {"reachable": True, "status_code": e.code, "error": None}
    except Exception as e:  # noqa: BLE001
        return {"reachable": False, "status_code": None, "error": str(e)[:200]}


def check_service_status(db: Session, svc: WebService) -> dict:
    """Laporan status lengkap service + tunnel-nya (untuk tombol "Cek").."""
    pid_up = pid_alive(svc.pid)
    port = svc.resolved_port or 0
    listening = _port_listening(port) if port > 0 else False
    status = "ONLINE" if pid_up and (port <= 0 or listening) else "OFFLINE"

    running_pid = _tunnel_running_pid(svc)
    url = svc.tunnel_url
    if not url and running_pid:
        url = _recover_tunnel_url(svc.id)
    probe = _probe_url(url) if url else None

    return {
        "service": {
            "pid": svc.pid,
            "pid_alive": pid_up,
            "status": status,
            "resolved_port": port,
            "port_listening": listening,
            "log_tail": tail_log(svc.log_path, 100),
        },
        "tunnel": {
            "running": running_pid is not None,
            "running_pid": running_pid,
            "url": url,
            "reachable": probe["reachable"] if probe else None,
            "status_code": probe["status_code"] if probe else None,
            "error": probe["error"] if probe else None,
            "log_tail": tail_log(_tunnel_log_path(svc.id), 60),
        },
    }


def sync_tunnel_status() -> None:
    """Pastikan tunnel_pid yang mati dibersihkan dari DB."""
    from ..db.database import SessionLocal

    db = SessionLocal()
    try:
        for svc in db.query(WebService).filter(
            WebService.tunnel_pid.isnot(None)
        ).all():
            if not pid_alive(svc.tunnel_pid):
                svc.tunnel_pid = None
                svc.tunnel_url = None
        db.commit()
    finally:
        db.close()


def _ensure_auto_tunnels() -> dict:
    """Auto re-expose service bertanda tunnel_auto.

    Saat tunnel mati (dimatikan manual, crash, atau server restart), tunnel
    baru langsung dibuat dengan URL baru — sesuai sifat trycloudflare yang
    memberi URL acak berbeda tiap spawn.
    """
    from ..db.database import SessionLocal

    respawned: list[int] = []
    now = time.monotonic()
    db = SessionLocal()
    try:
        for svc in db.query(WebService).filter(
            WebService.tunnel_auto.is_(True)
        ).all():
            if not pid_alive(svc.pid):
                if not (svc.resolved_port > 0 and _port_listening(svc.resolved_port)):
                    continue  # service tidak jalan — jangan dibangunkan
            if _tunnel_running_pid(svc):
                continue
            if now - _last_expose_at.get(svc.id, 0) < _EXPOSE_COOLDOWN:
                continue
            _last_expose_at[svc.id] = now
            err = expose_service(db, svc)
            if err:
                log.warning("auto re-expose %s gagal: %s", svc.id, err)
            else:
                respawned.append(svc.id)
                log.info("auto re-expose service %s (URL baru)", svc.id)
    finally:
        db.close()
    return {"respawned": respawned}


# ------------------------------------------------------------- monitor
def _monitor_loop() -> None:
    while True:
        time.sleep(_MONITOR_INTERVAL)
        try:
            sync_all_status()
            sync_tunnel_status()
            _ensure_auto_tunnels()
        except Exception:  # noqa: BLE001 — monitor tidak boleh mati
            log.warning("web status sync failed", exc_info=True)


def start_monitor() -> None:
    threading.Thread(
        target=_monitor_loop, daemon=True, name="web-monitor"
    ).start()
