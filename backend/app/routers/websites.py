"""API website lokal: daftar, folder browser, run/stop multi-service."""

import os
import re
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_write
from ..db.database import get_db
from ..db.models import WebApp, WebService
from ..services import audit, collectors, deploy
from ..services import websites as runner
from ..services import compose_runner
from ..services import reconcile as reconcile_service
import logging
log = logging.getLogger(__name__)

router = APIRouter(tags=["websites"])

_CHUNK = 8 * 1024 * 1024
_MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "5120")) * 1024 * 1024


def _project_dir(db: Session, app: WebApp) -> str:
    """Folder proyek docker-compose untuk sebuah WebApp.

   /compose butuh cwd yang pasti; tanpa service tidak ada yang bisa
    dijalankan, jadi error-nya harus masuk ke user sebagai 400 — bukan
    jadi ValueError liar yang culminate di 500 tanpa pesan.
    """
    svc = db.query(WebService).filter(WebService.app_id == app.id).first()
    if not svc or not svc.dir.strip():
        raise HTTPException(
            400,
            "Website ini belum punya folder service, jadi docker compose "
            "tidak tahu harus dijalankan di mana.",
        )
    return str(svc.dir)


def _compose_guard(app: WebApp) -> None:
    """Pastikan app memang docker-compose dan punya compose_file."""
    if app.runtime != "docker-compose":
        raise HTTPException(400, "Website ini bukan docker-compose runtime")
    if not app.compose_file:
        raise HTTPException(400, "compose_file belum diisi")


def _slugify(name: str) -> str:
    """Convert website name to a Docker-safe container name."""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "site"


def _container_name(app_id: int, name: str) -> str:
    return f"site-{_slugify(name)}"


def _checked_php_version(version: str) -> str:
    """Validasi versi PHP yang diplih user; timbulkan 400 bila tak didukung."""
    v = collectors.normalize_php_version(version)
    return v  # '' artinya auto-detect


def _php_version_err(version: str) -> str | None:
    """Pesan error bila versi PHP dikenali tapi tak didukung, else None."""
    v = (version or "").strip()
    if v and v not in collectors.SUPPORTED_PHP_VERSIONS:
        return (
            f"Versi PHP '{v}' tidak didukung. Pilih dari dropdown: "
            + ", ".join(collectors.SUPPORTED_PHP_VERSIONS)
        )
    return None


def _svc_dict(s: WebService) -> dict:
    return {
        "id": s.id,
        "label": s.label,
        "dir": s.dir,
        "command": s.command,
        "port": s.port,
        "resolved_port": s.resolved_port,
        "pid": s.pid,
        "status": s.status,
        "tunnel_url": s.tunnel_url,
        "tunnel_pid": s.tunnel_pid,
        "tunnel_auto": s.tunnel_auto,
    }


def _app_dict(db: Session, app: WebApp) -> dict:
    services = (
        db.query(WebService)
        .filter(WebService.app_id == app.id)
        .order_by(WebService.id)
        .all()
    )
    svcs = [_svc_dict(s) for s in services]
    online = sum(1 for s in svcs if s["status"] == "ONLINE")
    result = {
        "id": app.id,
        "name": app.name,
        "runtime": app.runtime,
        "php_version": app.php_version,
        "docker_image": app.docker_image,
        "dockerfile": app.dockerfile,
        "docker_container": app.docker_container,
        "docker_status": app.docker_status,
        "compose_file": app.compose_file,
        "compose_project": app.compose_project,
        "created_at": app.created_at.isoformat() + "Z",
        "services": svcs,
        "online": online,
        "total": len(svcs),
    }
    if app.runtime == "docker-compose" and app.compose_file:
        svc = services[0] if services else None
        project_dir = str(svc.dir) if svc and svc.dir else ""
        cstatus = compose_runner.compose_status(
            project_dir, app.compose_file, app.compose_project
        )
        # error compose ditampilkan, bukan ditelan jadi "OFFLINE" tanpa alasan
        result["compose_status"] = cstatus
        result["compose_error"] = cstatus.get("error", "")
        # Untuk compose, online/total dihitung dari container compose — bukan
        # dari WebService. Sebelumnya hanya `online` yang ditimpa sehingga
        # total tetap jumlah baris service (biasanya 1) dan UI menampilkan
        # "2/1 online" dengan badge kuning padahal semua container sehat.
        if cstatus["total"] > 0:
            result["online"] = cstatus["online"]
            result["total"] = cstatus["total"]
    return result


# ---------------------------------------------------------------- browse
@router.get("/websites/browse")
def browse(path: str = "", _: str = Depends(get_current_user)):
    return runner.browse_dirs(path)


# ------------------------------------------------------------------ list
@router.get("/websites")
def list_apps(
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    apps = db.query(WebApp).order_by(WebApp.id.desc()).all()
    # sinkronkan status sekali agar list selalu segar saat dibuka
    runner.sync_all_status()
    db.expire_all()
    return {
        "apps": [_app_dict(db, a) for a in apps],
        "host_hint": "localhost",
    }


# ------------------------------------------------------------- create+run
class ServiceIn(BaseModel):
    dir: str = Field(min_length=1, max_length=1024)
    command: str = Field(min_length=1, max_length=1024)
    port: int = Field(default=0, ge=0, le=65535)
    label: str = Field(default="", max_length=64)


class AppCreate(BaseModel):
    name: str = Field(default="", max_length=128)
    start: bool = True
    runtime: str = Field(default="native", pattern="^(native|docker|docker-compose)$")
    php_version: str = Field(default="", max_length=16)
    dockerfile: str = Field(default="Dockerfile", max_length=1024)
    services: list[ServiceIn] = Field(min_length=1, max_length=8)
    compose_file: str = Field(default="", max_length=1024)


class RuntimeIn(BaseModel):
    runtime: str = Field(default="native", pattern="^(native|docker|docker-compose)$")
    php_version: str = Field(default="", max_length=16)
    dockerfile: str = Field(default="Dockerfile", max_length=1024)


@router.post("/websites", dependencies=[Depends(require_write)])
def create_app(
    body: AppCreate,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not body.start:
        raise HTTPException(400, "Gunakan /start untuk menjalankan")
    for i, s in enumerate(body.services):
        d = Path(s.dir.strip()).expanduser()
        if not d.is_dir():
            raise HTTPException(400, f"Folder tidak ada: {s.dir} (baris {i + 1})")
        if not s.command.strip():
            raise HTTPException(400, f"Command kosong (baris {i + 1})")
        if shutil.which(s.command.strip().split()[0]) is None and "/" not in s.command.strip().split()[0]:
            raise HTTPException(
                400,
                f"'{s.command.strip().split()[0]}' tidak ditemukan di PATH (baris {i + 1})",
            )
    # cegah bagian ganda (folder+command+port sama) — biang "masih ada"
    # duplicates seperti kasus e-tiket- yang punya 3 part identik.
    seen: set[tuple] = set()
    for i, s in enumerate(body.services):
        key = (str(Path(s.dir.strip()).expanduser()), s.command.strip(), s.port)
        if key in seen:
            raise HTTPException(
                400,
                f"Bagian duplikat (baris {i + 1}): folder, command, dan port sama dengan baris lain",
            )
        seen.add(key)

    name = body.name.strip()
    if not name:
        first_dir = Path(body.services[0].dir.strip()).name or "website"
        name = first_dir + (" (+)" if len(body.services) > 1 else "")

    app = WebApp(
        name=name,
        runtime=body.runtime,
        php_version=body.php_version.strip(),
        dockerfile=body.dockerfile.strip() or "Dockerfile",
        compose_file=body.compose_file.strip() or "",
    )
    db.add(app)
    db.flush()
    log.info("create_app: runtime=%s compose_file=%r", body.runtime, body.compose_file)

    used: set[int] = set()
    results: list[dict] = []
    for s in body.services:
        d = str(Path(s.dir.strip()).expanduser())
        label = s.label.strip() or d.rstrip("/").split("/")[-1] or f"service-{s.port}"
        svc = WebService(
            app_id=app.id, label=label[:64], dir=d,
            command=s.command.strip(), port=s.port,
        )
        db.add(svc)
        db.flush()
        err = None
        if body.start and body.runtime == "native":
            err = runner.start_service(db, svc, used)
        elif body.start and body.runtime == "docker":
            err = "Docker image belum dibuild"
        elif body.start and body.runtime == "docker-compose":
            # compose app — jangan start_service native; user bisa compose-up lewat tombol
            err = None
        results.append({"label": svc.label, "error": err})

    audit.record(db, username, "WEB_APP_RUN", target=name)
    db.commit()
    return {"ok": True, "id": app.id, "results": results}


# ------------------------------------------------------------ lifecycle
def _get_app_or_404(db: Session, app_id: int) -> WebApp:
    app = db.get(WebApp, app_id)
    if not app:
        raise HTTPException(404, "Website tidak ditemukan")
    return app


@router.post("/websites/{app_id}/start", dependencies=[Depends(require_write)])
def start_app(
    app_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    app = _get_app_or_404(db, app_id)
    services = db.query(WebService).filter(WebService.app_id == app_id).all()
    used: set[int] = set()
    results = []
    for svc in services:
        if app.runtime == "docker-compose":
            try:
                err = compose_runner.compose_up(
                    svc.dir, app.compose_file, app.compose_project
                )
            except compose_runner.ComposeError as exc:
                err = str(exc)
        elif app.runtime == "docker":
            if not app.docker_image or not app.docker_container:
                err = "Docker image belum dibuild"
            else:
                err = runner.start_docker_service(
                    db, svc, app.docker_image, app.docker_container
                )
        else:
            err = runner.start_service(db, svc, used)
        results.append({"label": svc.label, "error": err})
    audit.record(db, username, "WEB_APP_START", target=app.name)
    db.commit()
    return {"ok": True, "results": results}


@router.get("/websites/{app_id}/runtime")
def get_runtime(app_id: int, _: str = Depends(get_current_user), db: Session = Depends(get_db)):
    return _app_dict(db, _get_app_or_404(db, app_id))


@router.put("/websites/{app_id}/runtime", dependencies=[Depends(require_write)])
def update_runtime(
    app_id: int,
    body: RuntimeIn,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    app = _get_app_or_404(db, app_id)
    app.runtime = body.runtime
    app.php_version = body.php_version.strip()
    app.dockerfile = body.dockerfile.strip() or "Dockerfile"
    audit.record(db, username, "WEB_RUNTIME_UPDATE", target=app.name)
    db.commit()
    return _app_dict(db, app)


@router.post("/websites/{app_id}/build", dependencies=[Depends(require_write)])
def build_app(
    app_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    app = _get_app_or_404(db, app_id)
    svc = (
        db.query(WebService)
        .filter(WebService.app_id == app_id)
        .order_by(WebService.id)
        .first()
    )
    if not svc:
        raise HTTPException(400, "Website belum memiliki service")
    tag = f"ubuntu-panel-site-{app.id}:latest"
    container = _container_name(app.id, app.name)
    try:
        if not Path(svc.dir, "Dockerfile").is_file():
            from ..services.collectors import ensure_website_dockerfile
            app.dockerfile = ensure_website_dockerfile(svc.dir, app.php_version)
        result = runner.build_docker_image(svc.dir, app.dockerfile or "Dockerfile", tag)
        app.runtime = "docker"
        app.docker_image = tag
        app.docker_container = container
        app.docker_status = "BUILT"

        run_error = runner.start_docker_service(db, svc, tag, container)
        if not run_error:
            try:
                sync_res = collectors.sync_folder_to_container(svc.dir, app.docker_container, svc.label)
                result["output"] += (
                    f" — synced {sync_res.get('files_synced', 0)} files to /app/{svc.label or ''}"
                )
            except Exception as exc:
                result["output"] += f" — sync warning: {exc}"
            result["output"] += " — container started"
        else:
            result["output"] += f" (warning: {run_error})"

        audit.record(db, username, "WEB_DOCKER_BUILD", target=app.name, result="SUCCESS")
        db.commit()
        return result
    except Exception as exc:
        app.docker_status = "BUILD_FAILED"
        audit.record(db, username, "WEB_DOCKER_BUILD", target=app.name, result="FAILED")
        db.commit()
        message = str(exc).strip() or "Docker build gagal"
        raise HTTPException(400, message[:1000])


@router.post("/websites/{app_id}/docker-delete", dependencies=[Depends(require_write)])
def delete_website_docker(
    app_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    app = _get_app_or_404(db, app_id)
    if not app.docker_container and not app.docker_image:
        raise HTTPException(400, "Tidak ada docker resource untuk website ini")
    from ..services.collectors import remove_container
    output_parts = []
    if app.docker_container:
        result = remove_container(app.docker_container, remove_image=False)
        output_parts.append(result.get("output", ""))
    if app.docker_image:
        try:
            from ..services.collectors import docker_client
            client = docker_client()
            client.images.remove(app.docker_image, force=True)
            output_parts.append(f"Image '{app.docker_image}' removed")
        except Exception as exc:
            output_parts.append(f"Image removal: {exc}")
    app.docker_image = ""
    app.docker_container = ""
    app.docker_status = ""
    app.runtime = "native"
    audit.record(db, username, "WEB_DOCKER_DELETE", target=app.name, result="SUCCESS")
    db.commit()
    return {"ok": True, "output": " | ".join(output_parts) or "Cleaned up"}


# ------------------------------------------------------------- website detail
@router.get("/websites/{app_id}/detail")
def website_detail(
    app_id: int,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return full website info including Docker container status if linked."""
    app = _get_app_or_404(db, app_id)
    services = (
        db.query(WebService)
        .filter(WebService.app_id == app_id)
        .order_by(WebService.id)
        .all()
    )
    svcs = []
    for s in services:
        svc_info = _svc_dict(s)
        # cek apakah folder masih ada
        svc_info["dir_exists"] = Path(s.dir).is_dir()
        # hitung ukuran folder
        try:
            folder_size = sum(
                f.stat().st_size for f in Path(s.dir).rglob("*") if f.is_file()
            )
            svc_info["dir_size"] = folder_size
        except Exception:
            svc_info["dir_size"] = 0
        svcs.append(svc_info)

    result = {
        "id": app.id,
        "name": app.name,
        "runtime": app.runtime,
        "php_version": app.php_version,
        "docker_image": app.docker_image,
        "dockerfile": app.dockerfile,
        "docker_container": app.docker_container,
        "docker_status": app.docker_status,
        "compose_file": app.compose_file,
        "compose_project": app.compose_project,
        "created_at": app.created_at.isoformat() + "Z",
        "services": svcs,
        "online": sum(1 for s in svcs if s["status"] == "ONLINE"),
        "total": len(svcs),
    }

    # tambahan status compose bila runtime docker-compose
    if app.runtime == "docker-compose" and app.compose_file:
        svc = services[0] if services else None
        project_dir = str(svc.dir) if svc and svc.dir else ""
        cstatus = compose_runner.compose_status(
            project_dir, app.compose_file, app.compose_project
        )
        result["compose_status"] = cstatus
        result["compose_error"] = cstatus.get("error", "")
        # Sama seperti di _app_dict: untuk compose, online/total berasal dari
        # container compose supaya badge di UI tidak salah warna.
        if cstatus["total"] > 0:
            result["online"] = cstatus["online"]
            result["total"] = cstatus["total"]

    # tambah info docker container jika terhubung
    if app.docker_container:
        try:
            from ..services.collectors import container_detail as get_container_detail
            detail = get_container_detail(app.docker_container)
            result["container_detail"] = detail
        except Exception:
            result["container_detail"] = None

    return result


# ------------------------------------------------------- update via upload
@router.post("/websites/{app_id}/upload", dependencies=[Depends(require_write)])
async def deploy_upload(
    app_id: int,
    file: UploadFile = File(...),
    service_id: int = Form(0),
    restart: str = Form("0"),
    sync_docker: str = Form("1"),
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update folder website dari zip — tanpa mematikan service.

    Zip di-unzip & isinya diganti langsung di lokasi folder service,
    sehingga folder di server tetap di inode yang sama (dev-server yang
    auto-reload langsung melihat versi baru). File konfigurasi server
    (.env, node_modules, vendor, .next, venv) dipertahankan.
    """
    app = _get_app_or_404(db, app_id)
    services = (
        db.query(WebService)
        .filter(WebService.app_id == app_id)
        .order_by(WebService.id)
        .all()
    )
    if not services:
        raise HTTPException(400, "Website belum memiliki service folder")
    svc = services[0]
    if service_id:
        picked = next((s for s in services if s.id == service_id), None)
        if picked is None:
            raise HTTPException(404, "Service tidak ditemukan")
        svc = picked

    dest = deploy.uploads_dir() / f"{uuid.uuid4().hex}.zip"
    written = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(_CHUNK)
                if not chunk:
                    break
                written += len(chunk)
                if written > _MAX_UPLOAD_BYTES:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        413,
                        f"Ukuran zip melebihi batas {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except OSError as e:
        raise HTTPException(500, f"Gagal menyimpan zip: {e}")
    finally:
        await file.close()

    if written == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "File zip kosong")

    jid = deploy.start_deploy(
        app,
        svc,
        str(dest),
        restart=restart in ("1", "true", "on"),
        sync_docker=sync_docker in ("1", "true", "on"),
        username=username,
    )
    db.commit()
    return {"ok": True, "job_id": jid}


@router.get("/websites/deploys/{job_id}")
def deploy_status(
    job_id: str,
    _: str = Depends(get_current_user),
):
    job = deploy.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Deploy job tidak ditemukan")
    return job


# ------------------------------------------------------------- sync to docker
@router.post("/websites/{app_id}/sync", dependencies=[Depends(require_write)])
def sync_to_docker(
    app_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sync source folder files into running Docker container."""
    app = _get_app_or_404(db, app_id)
    if not app.docker_container:
        raise HTTPException(400, "Website ini tidak memiliki Docker container")
    services = db.query(WebService).filter(WebService.app_id == app_id).all()
    if not services:
        raise HTTPException(400, "Tidak ada service folder untuk disinkronkan")

    results = []
    for svc in services:
        if not Path(svc.dir).is_dir():
            results.append({"label": svc.label, "error": f"Folder tidak ada: {svc.dir}"})
            continue
        try:
            from ..services.collectors import sync_folder_to_container
            res = sync_folder_to_container(svc.dir, app.docker_container, svc.label)
            results.append({"label": svc.label, "error": None, **res})
        except Exception as exc:
            results.append({"label": svc.label, "error": str(exc)})

    audit.record(db, username, "WEB_DOCKER_SYNC", target=app.name)
    db.commit()
    return {"ok": True, "results": results}


# ------------------------------------------------------------- docker logs
@router.get("/websites/{app_id}/docker-logs")
def docker_logs(
    app_id: int,
    lines: int = 200,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get Docker container logs for a website."""
    app = _get_app_or_404(db, app_id)
    if not app.docker_container:
        raise HTTPException(400, "Website ini tidak memiliki Docker container")
    lines = max(1, min(lines, 1000))
    try:
        from ..services.collectors import docker_client
        client = docker_client()
        container = client.containers.get(app.docker_container)
        logs = container.logs(tail=lines, timestamps=False).decode("utf-8", errors="replace")
        return {"lines": logs.splitlines()}
    except Exception as exc:
        raise HTTPException(500, f"Gagal membaca logs: {exc}")


# --------------------------------------------------------- project dependencies
@router.get("/websites/{app_id}/dependencies")
def project_dependencies(
    app_id: int,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Scan project folders and detect dependency version requirements."""
    app = _get_app_or_404(db, app_id)
    services = (
        db.query(WebService)
        .filter(WebService.app_id == app_id)
        .order_by(WebService.id)
        .all()
    )
    if not services:
        raise HTTPException(400, "Tidak ada service folder")

    results = []
    for svc in services:
        if not Path(svc.dir).is_dir():
            results.append({
                "label": svc.label,
                "dir": svc.dir,
                "error": f"Folder tidak ada: {svc.dir}",
            })
            continue
        try:
            from ..services.collectors import detect_project_dependencies
            deps = detect_project_dependencies(svc.dir)
            deps["label"] = svc.label
            deps["dir"] = svc.dir
            results.append(deps)
        except Exception as exc:
            results.append({
                "label": svc.label,
                "dir": svc.dir,
                "error": str(exc),
            })

    return {"dependencies": results}


@router.post("/websites/{app_id}/local", dependencies=[Depends(require_write)])
def run_local_app(
    app_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    app = _get_app_or_404(db, app_id)
    services = db.query(WebService).filter(WebService.app_id == app_id).all()
    if not services:
        raise HTTPException(400, "Website belum memiliki service")
    if app.runtime == "docker-compose":
        try:
            error = compose_runner.compose_up(
                services[0].dir, app.compose_file, app.compose_project
            )
        except compose_runner.ComposeError as exc:
            raise HTTPException(400, str(exc))
        port = 0
        if not error:
            cs = compose_runner.compose_status(
                services[0].dir, app.compose_file, app.compose_project
            )
            if cs.get("error"):
                raise HTTPException(500, cs["error"])
            for s in cs.get("services", []):
                for p in s.get("ports", []):
                    m = re.search(r"0\.0\.0\.0:(\d+)->(\d+)/", p)
                    if m:
                        port = int(m.group(2))
                        break
                if port:
                    break
        elif error != "sudah berjalan":
            raise HTTPException(409, error)
        audit.record(db, username, "WEB_APP_LOCAL", target=app.name)
        db.commit()
        return {"ok": True, "port": port}
    elif app.runtime == "docker":
        if not app.docker_image or not app.docker_container:
            raise HTTPException(400, "Build Docker terlebih dahulu")
        error = runner.start_docker_service(
            db, services[0], app.docker_image, app.docker_container
        )
        port = services[0].resolved_port
    else:
        error = runner.start_service(db, services[0], set())
        port = services[0].resolved_port
    if error and error != "sudah berjalan":
        raise HTTPException(409, error)
    audit.record(db, username, "WEB_APP_LOCAL", target=app.name)
    db.commit()
    return {"ok": True, "port": port}


@router.post("/websites/{app_id}/stop", dependencies=[Depends(require_write)])
def stop_app(
    app_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    app = _get_app_or_404(db, app_id)
    services = db.query(WebService).filter(WebService.app_id == app_id).all()
    for svc in services:
        if app.runtime == "docker-compose":
            if app.compose_file:
                try:
                    compose_runner.compose_down(
                        svc.dir, app.compose_file, app.compose_project
                    )
                except compose_runner.ComposeError:
                    log.warning("compose down dilewati untuk %s: folder/compose tak valid", svc.label)
        elif app.runtime == "docker" and app.docker_container:
            runner.stop_docker_service(db, svc, app.docker_container)
        else:
            runner.stop_service(db, svc)
    audit.record(db, username, "WEB_APP_STOP", target=app.name)
    db.commit()
    return {"ok": True}


@router.delete("/websites/{app_id}", dependencies=[Depends(require_write)])
def delete_app(
    app_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    app = _get_app_or_404(db, app_id)
    services = db.query(WebService).filter(WebService.app_id == app_id).all()
    for svc in services:
        if app.runtime == "docker" and app.docker_container:
            runner.stop_docker_service(db, svc, app.docker_container)
        else:
            runner.stop_service(db, svc)
    # hapus service milik app ini eksplisit — jangan andalkan FK cascade saja
    # (SQLite lama tanpa PRAGMA foreign_keys=ON tidak menjalankannya).
    db.query(WebService).filter(WebService.app_id == app_id).delete(
        synchronize_session=False
    )
    audit.record(db, username, "WEB_APP_DELETE", target=app.name)
    db.delete(app)
    db.commit()
    return {"ok": True}


@router.post("/websites/services/{service_id}/start", dependencies=[Depends(require_write)])
def start_one(
    service_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = db.get(WebService, service_id)
    if not svc:
        raise HTTPException(404, "Service tidak ditemukan")
    err = runner.start_service(db, svc, set())
    if err:
        raise HTTPException(409, err)
    audit.record(db, username, "WEB_SERVICE_START", target=f"{svc.label}:{svc.resolved_port}")
    db.commit()
    return {"ok": True}


@router.post("/websites/services/{service_id}/stop", dependencies=[Depends(require_write)])
def stop_one(
    service_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = db.get(WebService, service_id)
    if not svc:
        raise HTTPException(404, "Service tidak ditemukan")
    runner.stop_service(db, svc)
    audit.record(db, username, "WEB_SERVICE_STOP", target=svc.label)
    db.commit()
    return {"ok": True}


@router.get("/websites/services/{service_id}/logs")
def service_logs(
    service_id: int,
    lines: int = 200,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lines = max(1, min(lines, 1000))
    svc = db.get(WebService, service_id)
    if not svc:
        raise HTTPException(404, "Service tidak ditemukan")
    rows = runner.tail_log(svc.log_path, lines)
    return {"lines": rows}


# ----------------------------------------------------------- cloudflare tunnel
@router.post("/websites/services/{service_id}/expose", dependencies=[Depends(require_write)])
def expose_service(
    service_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Expose service ke internet lewat Cloudflare Quick Tunnel."""
    svc = db.get(WebService, service_id)
    if not svc:
        raise HTTPException(404, "Service tidak ditemukan")
    # runtime docker-compose belum punya resolved_port; resolve dari container
    if svc.resolved_port <= 0:
        app = db.get(WebApp, svc.app_id)
        if app and app.runtime == "docker-compose" and app.compose_file:
            cs = compose_runner.compose_status(
                svc.dir, app.compose_file, app.compose_project
            )
            if cs.get("error"):
                raise HTTPException(409, cs["error"])
            for s in cs.get("services", []):
                for p in s.get("ports", []):
                    # "0.0.0.0:HOST->KONTENER/tcp" — cloudflared dijalankan di host
                    # dan menembak localhost:HOST, jadi yang dipakai adalah port
                    # host (grup 1), bukan port kontener (grup 2).
                    m = re.search(r"0\.0\.0\.0:(\d+)->(\d+)/", p)
                    if m:
                        svc.resolved_port = int(m.group(1))
                        break
                if svc.resolved_port:
                    break
        db.commit()
    if svc.resolved_port <= 0:
        raise HTTPException(
            409,
            "Port service belum bisa ditentukan. Pastikan container compose "
            "mem publishes port (ports: - \"0.0.0.0:NAMA_PORT:NAMA_PORT\").",
        )
    err = runner.expose_service(db, svc)
    if err:
        raise HTTPException(409, err)
    audit.record(db, username, "WEB_SERVICE_EXPOSE", target=f"{svc.label}:{svc.resolved_port}")
    db.commit()
    # return langsung; URL akan muncul setelah beberapa detik
    return {"ok": True, "tunnel_pid": svc.tunnel_pid, "tunnel_url": svc.tunnel_url}


@router.get("/websites/services/{service_id}/check")
def check_service_status(
    service_id: int,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Status lengkap satu service: proses, port, log, dan tunnel (liveness)."""
    svc = db.get(WebService, service_id)
    if not svc:
        raise HTTPException(404, "Service tidak ditemukan")
    db.commit()
    return runner.check_service_status(db, svc)


class TunnelAutoIn(BaseModel):
    enabled: bool


@router.put("/websites/services/{service_id}/tunnel-auto", dependencies=[Depends(require_write)])
def set_tunnel_auto(
    service_id: int,
    body: TunnelAutoIn,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aktif/nonaktifkan auto re-expose (URL baru saat tunnel mati/server restart)."""
    svc = db.get(WebService, service_id)
    if not svc:
        raise HTTPException(404, "Service tidak ditemukan")
    svc.tunnel_auto = body.enabled
    audit.record(
        db, username, "WEB_SERVICE_EXPOSE",
        target=f"{svc.label}:tunnel_auto={'on' if body.enabled else 'off'}",
    )
    db.commit()
    return {"ok": True, "tunnel_auto": svc.tunnel_auto}


@router.post("/websites/services/{service_id}/unexpose", dependencies=[Depends(require_write)])
def unexpose_service(
    service_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Hentikan Cloudflare Tunnel untuk service (termasuk proses yatim)."""
    svc = db.get(WebService, service_id)
    if not svc:
        raise HTTPException(404, "Service tidak ditemukan")
    killed = runner.unexpose_service(db, svc)
    audit.record(db, username, "WEB_SERVICE_UNEXPOSE", target=svc.label)
    db.commit()
    return {"ok": True, "killed": killed}


# ---------------------------------------------------------- docker-compose
@router.post("/websites/{app_id}/compose-up", dependencies=[Depends(require_write)])
def compose_up_route(
    app_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Jalankan website via docker compose up -d --build."""
    app = _get_app_or_404(db, app_id)
    _compose_guard(app)
    project_dir = _project_dir(db, app)
    try:
        err = compose_runner.compose_up(
            project_dir, app.compose_file, app.compose_project
        )
    except compose_runner.ComposeError as exc:
        raise HTTPException(400, str(exc))
    if err:
        raise HTTPException(500, err)
    audit.record(db, username, "WEB_APP_RUN", target=app.name)
    db.commit()
    return {"ok": True}


@router.post("/websites/{app_id}/compose-down", dependencies=[Depends(require_write)])
def compose_down_route(
    app_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Hentikan website via docker compose down."""
    app = _get_app_or_404(db, app_id)
    _compose_guard(app)
    project_dir = _project_dir(db, app)
    try:
        err = compose_runner.compose_down(
            project_dir, app.compose_file, app.compose_project
        )
    except compose_runner.ComposeError as exc:
        raise HTTPException(400, str(exc))
    if err:
        raise HTTPException(500, err)
    audit.record(db, username, "WEB_APP_STOP", target=app.name)
    db.commit()
    return {"ok": True}


@router.get("/websites/{app_id}/compose-status")
def compose_status_route(
    app_id: int,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Status container docker compose."""
    app = _get_app_or_404(db, app_id)
    _compose_guard(app)
    project_dir = _project_dir(db, app)
    return compose_runner.compose_status(
        project_dir, app.compose_file, app.compose_project
    )


@router.get("/websites/{app_id}/compose-logs")
def compose_logs_route(
    app_id: int,
    service: str = "",
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Logs docker compose."""
    app = _get_app_or_404(db, app_id)
    _compose_guard(app)
    project_dir = _project_dir(db, app)
    try:
        lines = compose_runner.compose_logs(
            project_dir, app.compose_file, service or None, project=app.compose_project
        )
    except compose_runner.ComposeError as exc:
        raise HTTPException(400, str(exc))
    return {"lines": lines}


# ------------------------------------------------------------- reconcile
def _registered_targets(db: Session) -> list[dict]:
    """Daftar lokasi yang sudah dikelola panel (folder + project compose).

    Hanya runtime docker-compose yang relevan: native/docker tidak punya
    folder project compose, jadi tidak bisa dibandingkan dengan hasil scan.
    """
    rows = (
        db.query(WebApp)
        .filter(WebApp.runtime == "docker-compose")
        .order_by(WebApp.id)
        .all()
    )
    out: list[dict] = []
    for app in rows:
        svc = (
            db.query(WebService)
            .filter(WebService.app_id == app.id)
            .order_by(WebService.id)
            .first()
        )
        out.append(
            {
                "app_id": app.id,
                "name": app.name,
                "project_dir": str(svc.dir).rstrip("/") if svc and svc.dir else "",
                "compose_project": app.compose_project or "",
            }
        )
    return out


@router.get("/websites/reconcile")
def reconcile_route(
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Project compose yang jalan tapi belum terdaftar di panel.

    Read-only: tidak mengubah DB maupun container. Adoption lewat
    POST /websites/adopt supaya user tetap memegang kendali.
    """
    registered = _registered_targets(db)
    try:
        running = reconcile_service.detect_running_projects()
    except Exception as exc:  # noqa: BLE001 — deteksi tidak boleh menggagalkan list
        log.warning("[reconcile] deteksi gagal: %s", exc)
        running = []

    unmanaged = reconcile_service.find_unmanaged(running, registered)
    return {
        "unmanaged": unmanaged,
        "registered_count": len(registered),
        "running_count": len(running),
    }


class AdoptIn(BaseModel):
    project_dir: str = Field(min_length=1, max_length=1024)
    compose_file: str = Field(min_length=1, max_length=1024)
    compose_project: str = Field(min_length=1, max_length=128)
    name: str = Field(default="", max_length=128)


@router.post("/websites/adopt", dependencies=[Depends(require_write)])
def adopt_route(
    body: AdoptIn,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Daftarkan project compose yang sudah berjalan ke dalam panel.

    Non-destruktif: TIDAK menjalankan compose up/down dan tidak menyentuh
    container yang sedang hidup. Hanya membuat baris WebApp + WebService
    memakai nilai project yang sedang aktif, supaya `docker compose -p ...`
    di panel menunjuk project yang sama (induk dari konflik container name).
    """
    try:
        project_dir = Path(body.project_dir).expanduser().resolve()
    except OSError as exc:
        raise HTTPException(400, f"Folder tidak bisa dibaca: {exc}")
    # validasi whitelist path —.compose_runner akan menolak, tapi lebih baik
    # gagal cepat di sini dengan pesan jelas.
    try:
        compose_runner._resolve_dir(str(project_dir))
    except compose_runner.ComposeError as exc:
        raise HTTPException(400, str(exc))
    if not project_dir.is_dir():
        raise HTTPException(400, f"Folder tidak ada: {body.project_dir}")

    compose_file = body.compose_file.strip()
    if not (project_dir / compose_file).is_file():
        raise HTTPException(
            400, f"Compose file '{compose_file}' tidak ditemukan di {project_dir}"
        )

    project = body.compose_project.strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", project):
        raise HTTPException(
            400,
            "Nama project compose tidak valid — hanya huruf kecil, angka, "
            "'-' dan '_'",
        )

    # tolak adopsi ganda: folder atau project sudah dipakai website lain
    for app in db.query(WebApp).filter(WebApp.runtime == "docker-compose").all():
        svc = (
            db.query(WebService)
            .filter(WebService.app_id == app.id)
            .order_by(WebService.id)
            .first()
        )
        same_dir = bool(svc and svc.dir and str(Path(svc.dir).expanduser().resolve()).rstrip("/") == str(project_dir).rstrip("/"))
        same_project = bool(app.compose_project) and app.compose_project == project
        if same_dir or same_project:
            raise HTTPException(
                409,
                f'Sudah terdaftar sebagai website "{app.name}" — tidak perlu diadopsi lagi.',
            )

    name = body.name.strip() or project_dir.name or project
    app = WebApp(
        name=name[:128],
        runtime="docker-compose",
        compose_file=compose_file,
        compose_project=project,
    )
    db.add(app)
    db.flush()
    db.add(
        WebService(
            app_id=app.id,
            label=project_dir.name[:64] or project,
            dir=str(project_dir),
            # command tidak dipakai runtime compose; diisi agar UI/DB konsisten
            command="docker compose up -d",
            port=0,
        )
    )
    audit.record(db, username, "WEB_APP_ADOPT", target=name)
    db.commit()

    # pastikan status terisisegera setelah adopt
    status = compose_runner.compose_status(str(project_dir), compose_file, project)
    return {"ok": True, "id": app.id, "name": name, "compose_status": status}
