"""Deteksi docker-compose project yang berjalan tapi belum dikelola panel.

Tujuan: kasus "website jalan tapi tidak terlihat / salah di management
website" terdeteksi otomatis, tanpa harus daftar manual satu per satu.

Prinsip penting:
- **Read-only.** Modul ini tidak pernah menulis DB, tidak pernah start/stop/
  remove container. Ia hanya melaporkan.
- **Non-destruktif.** Adoption keputusan user (POST /websites/adopt),
  bukan efek samping dari scan.
- **Konservatif.** Kalau project tidak bisa diidentifikasi dengan yakin
  (mis. container tanpa label compose, atau project dir di luar whitelist),
  ia tidak dilaporkan daripada Reported salah.

Sumber kebenaran urutan (dari paling andal):
1. `docker ps` -> container dengan label `com.docker.compose.project`.
   Dari sana `project.working_dir` memberi folder proyek secara presisi.
2. Nama project compose sebagai identitas tambahan.

`com.docker.compose.project.working_dir` dipakai realpath supaya pencocokan
tahan terhadap symlink / path relatif.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

# Folder yang boleh diadopsi panel (sama dengan compose_runner).
_ALLOWED_ROOT = Path("/home/eta/Website").resolve()

_COMPOSE_FILES = (
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)

_LABEL_PROJECT = "com.docker.compose.project"
_LABEL_WORKDIR = "com.docker.compose.project.working_dir"
_LABEL_CONFIG = "com.docker.compose.project.config_files"
_LABEL_RUNNING = "com.docker.compose.service"


def _is_allowed_dir(raw: str) -> Path | None:
    """Kembalikan path absolut kalau ada di dalam whitelist, else None."""
    if not raw or not raw.strip():
        return None
    p = Path(raw.strip()).expanduser()
    try:
        resolved = p.resolve()
    except OSError:
        return None
    if resolved == _ALLOWED_ROOT or not str(resolved).startswith(str(_ALLOWED_ROOT)):
        return None
    return resolved


def _detect_compose_file(project_dir: Path, config_files: str) -> str:
    """Pilih nama file compose yang benar-benar ada di folder.

    Prefer label `config_files` (yang diisi compose sendiri) karena itu yang
    benar-benar dipakai saat `up`. Fallback: cari kandidat umum.
    """
    if config_files:
        # bisa berisi beberapa path dipisah ',' (multi-file compose)
        for raw in config_files.split(","):
            cand = Path(raw.strip())
            if not cand.name:
                continue
            if (project_dir / cand.name).is_file():
                return cand.name
            if cand.is_file():
                try:
                    return str(cand.resolve().relative_to(project_dir))
                except ValueError:
                    return cand.name
    for name in _COMPOSE_FILES:
        if (project_dir / name).is_file():
            return name
    return ""


def _label_from_raw(raw: str, key: str) -> str:
    """Ambil satu nilai dari string Labels ala `docker ps --format json`.

    Formatnya: "k1=v1,k2=v2,..." — nilai bisa mengandung '=' (mis. sha256),
    jadi split harus dilakukan pada '=' pertama saja per pasang.
    """
    if not raw:
        return ""
    for pair in raw.split(","):
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        if k.strip() == key:
            return v.strip()
    return ""


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return s or "app"


def _running_ports(inspected: list[dict]) -> list[str]:
    """Kumpulkan port publish dari hasil `docker inspect`."""
    ports: list[str] = []
    for c in inspected:
        for key, value in (c.get("Ports") or {}).items():
            # value: None | [{'HostIp':'', 'HostPort':'3001'}]
            if not value:
                continue
            for entry in value:
                host_port = str(entry.get("HostPort", "")).strip()
                if host_port:
                    ports.append(f"{host_port}->{key}")
    return sorted(set(ports))


def _ports_from_ps_line(lines: list[str]) -> list[str]:
    """Cadangan: ambil port dari kolom `Ports` di `docker ps` output."""
    ports: set[str] = set()
    for line in lines:
        raw = line.get("Ports", "") or ""
        for part in raw.split(","):
            part = part.strip()
            # hanya port yang benar-benar dipublish ke host (ada "->")
            if "->" in part and re.match(r"[\d.:]+:\d+->", part):
                ports.add(part)
    return sorted(ports)


def _docker(args: list[str], timeout: int = 20) -> tuple[int, str, str]:
    try:
        res = subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 1, "", "timeout"
    except OSError as exc:
        return 1, "", str(exc)
    return res.returncode, res.stdout, res.stderr


def detect_running_projects() -> list[dict]:
    """Daftar project compose yang sedang running di host.

    Kembalikan list dict:
      {
        "kind": "docker-compose",
        "project": "cloudbox",
        "project_dir": "/home/eta/Website/cloudbox",
        "compose_file": "docker-compose.yml",
        "running_services": ["cloudbox", "cloudbox-db"],
        "ports": ["3001->3001/tcp"],
        "container_count": 2,
        "name_suggest": "cloudbox"
      }
    """
    code, stdout, stderr = _docker(
        ["ps", "--filter", f"label={_LABEL_PROJECT}", "--format", "{{json .}}"]
    )
    if code != 0:
        log.warning("[reconcile] docker ps gagal: %s", (stderr or "").strip()[:200])
        return []

    # Kumpulkan container per project.
    by_project: dict[str, dict] = {}
    obj_lines: dict[str, list[dict]] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        # `docker ps --format '{{json .}}'` mengembalikan Labels sebagai string
        # "k=v,k=v", bukan objek -> harus diparse.
        project = _label_from_raw(obj.get("Labels", ""), _LABEL_PROJECT)
        if not project:
            continue
        by_project.setdefault(project, {"containers": []})["containers"].append(
            obj.get("ID", "")
        )
        obj_lines.setdefault(project, []).append(obj)

    projects: list[dict] = []
    for project, info in by_project.items():
        if not project:
            continue
        details: list[dict] = []
        for cid in info["containers"]:
            code_i, out_i, _ = _docker(["inspect", cid], timeout=15)
            if code_i != 0:
                continue
            try:
                arr = json.loads(out_i)
            except json.JSONDecodeError:
                continue
            if arr:
                details.append(arr[0])

        if not details:
            continue

        # Hanya container yang benar-benar running.
        running = [
            d
            for d in details
            if (d.get("State") or {}).get("Status") == "running"
        ]
        if not running:
            continue

        labels = {}
        for d in running:
            labels.update(d.get("Config", {}).get("Labels") or {})

        raw_dir = labels.get(_LABEL_WORKDIR, "")
        project_dir = _is_allowed_dir(raw_dir)
        if project_dir is None or not project_dir.is_dir():
            # project di luar whitelist / folder hilang -> tidak dilaporkan
            continue

        compose_file = _detect_compose_file(
            project_dir, labels.get(_LABEL_CONFIG, "")
        )
        if not compose_file:
            # tidak ada file compose yang bisa dibaca -> tidak bisa dikelola
            continue

        services = sorted(
            {
                (d.get("Config", {}).get("Labels") or {}).get(_LABEL_RUNNING, "")
                for d in running
            }
            - {""}
        )

        # Port publish juga bisa diambil langsung dari `docker ps` (label di
        # situ sudah berupa string), dipakai sebagai cadangan bila inspect
        # tidak punya.
        published = _running_ports(running)
        if not published:
            published = _ports_from_ps_line(obj_lines.get(project, []))

        projects.append(
            {
                "kind": "docker-compose",
                "project": project,
                "project_dir": str(project_dir),
                "compose_file": compose_file,
                "running_services": services,
                "ports": published,
                "container_count": len(running),
                "name_suggest": _slug(project_dir.name),
            }
        )

    projects.sort(key=lambda p: p["project_dir"])
    return projects


def find_unmanaged(
    projects: list[dict],
    registered: list[dict],
) -> list[dict]:
    """Filter project running yang belum terdaftar di panel.

    `registered` = [{'project_dir': ..., 'compose_project': ...}, ...]
    """
    known_dirs = {str(r.get("project_dir", "")).rstrip("/") for r in registered if r.get("project_dir")}
    known_projects = {str(r.get("compose_project", "")).strip() for r in registered if r.get("compose_project")}

    unmanaged: list[dict] = []
    for p in projects:
        d = str(p["project_dir"]).rstrip("/")
        if d in known_dirs:
            continue
        # project name yang sama persis juga dianggap sudah dikelola, supaya
        # tidak muncul dua entri untuk satu project yang cuma beda nama folder.
        if p["project"] in known_projects:
            continue
        unmanaged.append(p)
    return unmanaged