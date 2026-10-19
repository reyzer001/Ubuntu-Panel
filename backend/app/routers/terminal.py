import shlex
import subprocess

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.deps import get_current_user, require_write
from ..services import collectors

router = APIRouter(prefix="/terminal", tags=["terminal"])


class ExecBody(BaseModel):
    command: str


class WebsiteExecBody(BaseModel):
    command: str


@router.post("/exec", dependencies=[Depends(require_write)])
def exec_command(
    body: ExecBody,
    user: str = Depends(get_current_user),
):
    try:
        return collectors.terminal_exec(body.command)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/website/{app_id}", dependencies=[Depends(require_write)])
def exec_website_command(
    app_id: int,
    body: WebsiteExecBody,
    _: str = Depends(get_current_user),
):
    from ..db.database import SessionLocal
    from ..db.models import WebApp, WebService

    db = SessionLocal()
    try:
        app = db.get(WebApp, app_id)
        svc = (
            db.query(WebService)
            .filter(WebService.app_id == app_id)
            .order_by(WebService.id)
            .first()
        )
        if not app or not svc:
            raise HTTPException(status_code=404, detail="Website tidak ditemukan")
        try:
            return collectors.website_terminal_exec(body.command, svc.dir)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    finally:
        db.close()


@router.post("/website/{app_id}/docker", dependencies=[Depends(require_write)])
def exec_website_docker_command(
    app_id: int,
    body: WebsiteExecBody,
    _: str = Depends(get_current_user),
):
    from ..db.database import SessionLocal
    from ..db.models import WebApp

    db = SessionLocal()
    try:
        app = db.get(WebApp, app_id)
        if not app:
            raise HTTPException(status_code=404, detail="Website tidak ditemukan")
        if not app.docker_container:
            raise HTTPException(status_code=400, detail="Website belum dipindahkan ke Docker")
        command = body.command.strip()
        if not command:
            raise HTTPException(status_code=400, detail="Command tidak boleh kosong")
        try:
            args = shlex.split(command)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Command tidak valid") from exc
        allowed = {
            "pwd", "ls", "whoami", "php", "composer", "node", "npm", "python",
            "git", "bash", "sh", "code-server", "cat", "grep",
        }
        if not args or args[0] not in allowed:
            raise HTTPException(status_code=400, detail=f"Command tidak diizinkan: {args[0] if args else ''}")
        if any(token in {";", "&&", "||", "|", ">", ">>", "<"} for token in args):
            raise HTTPException(status_code=400, detail="Shell operator tidak diizinkan")
        proc = subprocess.run(
            ["docker", "exec", app.docker_container, *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (proc.stdout + proc.stderr).strip()
        return {"output": output or f"exit code {proc.returncode}", "returncode": proc.returncode}
    finally:
        db.close()
