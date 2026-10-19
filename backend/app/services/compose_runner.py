"""Runner docker-compose untuk Websites panel.

Menjalankan CloudBox (atau project lain yang pakai docker-compose)
melalui `docker compose` — satu unit, bukan docker run per service.
Status dilacak via `docker compose ps --json`.
"""

import json
import logging
import os
import re
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

# folder yang diizinkan menjalankan compose (whitelist path traversal)
_ALLOWED_ROOT = Path("/home/eta/Website").resolve()

_COMPOSE_FILES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")


class ComposeError(ValueError):
    """Kesalahan yang bisa ditampilkan ke user (bukan 500).

    Turunan ValueError supaya pemanggil lama yang menangkap ValueError
    tetap bekerja.
    """


def _resolve_dir(project_dir: str) -> Path:
    """Validasi & kembalikan path absolut yang diizinkan."""
    if not project_dir or not project_dir.strip():
        raise ComposeError(
            "Website ini belum punya folder service, jadi docker compose "
            "tidak tahu harus dijalankan di mana."
        )
    p = Path(project_dir).expanduser().resolve()
    if not str(p).startswith(str(_ALLOWED_ROOT)):
        raise ComposeError(f"Folder tidak diizinkan: {project_dir}")
    return p


def _find_compose(project_dir: Path, compose_file: str = "") -> Path:
    """Cari file compose yang valid. Preferensi: arg > folder > error."""
    if compose_file:
        cand = (project_dir / compose_file).resolve()
        if cand.is_file():
            return cand
        raise ComposeError(
            f"Compose file '{compose_file}' tidak ditemukan di {project_dir}"
        )
    for name in _COMPOSE_FILES:
        cand = project_dir / name
        if cand.is_file():
            return cand
    raise ComposeError(
        f"Tidak ada docker-compose.yml/compose.yml di {project_dir}"
    )


def _project_args(project: str = "") -> list[str]:
    """`-p <nama>` supaya nama container stabil & tidak bentrok antar app."""
    return ["-p", project.strip()] if project and project.strip() else []


# ----------------------------------------------------------------- public API

def compose_up(
    project_dir: str, compose_file: str = "", project: str = ""
) -> str | None:
    """Jalankan compose up -d --build. Return error string or None."""
    d = _resolve_dir(project_dir)
    cf = _find_compose(d, compose_file)
    # override agar selalu pakai file yang ditemukan
    result = subprocess.run(
        ["docker", "compose", "-f", str(cf), *_project_args(project), "up", "-d", "--build"],
        cwd=str(d),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip()
        log.error("[compose] up gagal: %s", msg)
        return msg or "compose up gagal"
    return None


def compose_down(
    project_dir: str, compose_file: str = "", project: str = ""
) -> str | None:
    """Hentikan compose. Return error string or None."""
    d = _resolve_dir(project_dir)
    cf = _find_compose(d, compose_file)
    result = subprocess.run(
        ["docker", "compose", "-f", str(cf), *_project_args(project), "down"],
        cwd=str(d),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip()
        log.error("[compose] down gagal: %s", msg)
        return msg or "compose down gagal"
    return None


def compose_status(
    project_dir: str, compose_file: str = "", project: str = ""
) -> dict:
    """Kembalikan status service dari `docker compose ps --json`.

    Format:
      {
        "online": 1,
        "total": 1,
        "error": "",            # isi kalau compose tidak bisa dibaca
        "services": [
          {"name": "cloudbox", "status": "running", "ports": ["0.0.0.0:3001->3001/tcp"], "health": "healthy"}
        ]
      }

    Tidak pernah melempar exception: `error` diisi string supaya UI bisa
    menampilkan penyebab, bukan diam-diam menampilkan OFFLINE.
    """
    empty = {"online": 0, "total": 0, "error": "", "services": []}
    try:
        d = _resolve_dir(project_dir)
        cf = _find_compose(d, compose_file)
    except ComposeError as exc:
        return {**empty, "error": str(exc)}

    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(cf), *_project_args(project),
             "ps", "--all", "--format", "json"],
            cwd=str(d),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {**empty, "error": "docker compose ps timeout (30s)"}
    except OSError as exc:
        return {**empty, "error": f"gagal menjalankan docker: {exc}"}

    if result.returncode != 0:
        msg = (result.stderr or result.stdout or "").strip()
        return {**empty, "error": msg[:500] or "docker compose ps gagal"}

    services: list[dict] = []
    stdout = result.stdout.strip()
    if not stdout:
        return {**empty, "error": ""}
    # ps --format json bisa menghasilkan multi-line JSON (satu objek per baris)
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        status_raw = obj.get("Status", "").lower()
        state = obj.get("State", "").lower()
        is_online = state == "running" or status_raw.startswith("up") or status_raw.startswith("restarting")
        services.append(
            {
                "name": obj.get("Service", obj.get("Name", "")),
                "status": "ONLINE" if is_online else "OFFLINE",
                "ports": obj.get("Ports", "").split("\n") if obj.get("Ports") else [],
                "health": obj.get("Health", obj.get("State", "")),
            }
        )
    online = sum(1 for s in services if s["status"] == "ONLINE")
    return {"online": online, "total": len(services), "error": "", "services": services}


def compose_logs(
    project_dir: str,
    compose_file: str = "",
    service: str = "",
    lines: int = 200,
    project: str = "",
) -> list[str]:
    """Baca compose logs (tail). Return list of lines."""
    d = _resolve_dir(project_dir)
    cf = _find_compose(d, compose_file)
    cmd = [
        "docker", "compose", "-f", str(cf), *_project_args(project),
        "logs", "--tail", str(lines),
    ]
    if service:
        cmd.append(service)
    result = subprocess.run(
        cmd,
        cwd=str(d),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        log.warning("[compose] logs gagal: %s", result.stderr)
        return []
    return result.stdout.splitlines()
