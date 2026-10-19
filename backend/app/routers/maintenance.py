from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_superadmin
from ..db.database import get_db
from ..services import maintenance
from ..services.audit import record

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


class CleanupBody(BaseModel):
    journal_days: int | None = None
    apt_clean: bool = False
    sudo_password: str = ""


class TaskBody(BaseModel):
    kind: str  # apt_update | apt_upgrade | apt_autoremove
    sudo_password: str = ""


class RebootBody(BaseModel):
    confirm: bool = False
    sudo_password: str = ""


def _check_sudo(password: str) -> None:
    """Wajibkan & validasi password sudo sebelum aksi root.

    Kebijakan: password selalu diminta (kecuali backend berjalan sebagai
    root). Password tidak pernah dicatat ke audit log / output.
    """
    if maintenance.is_root():
        return
    if not password:
        raise HTTPException(status_code=403, detail="Password sudo wajib diisi")
    ok, err = maintenance.verify_sudo(password)
    if not ok:
        raise HTTPException(status_code=403, detail=f"Password sudo salah: {err}")


@router.get("/status")
def get_status(_: str = Depends(get_current_user)):
    return maintenance.status()


@router.post("/cleanup", dependencies=[Depends(require_superadmin)])
def cleanup(
    body: CleanupBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not body.journal_days and not body.apt_clean:
        raise HTTPException(status_code=400, detail="Tidak ada aksi cleanup yang dipilih")
    if body.journal_days is not None and not (1 <= body.journal_days <= 3650):
        raise HTTPException(status_code=400, detail="journal_days harus 1–3650")
    _check_sudo(body.sudo_password)
    results = maintenance.cleanup(
        body.journal_days, body.apt_clean, body.sudo_password
    )
    ok = all(r["success"] for r in results) if results else False
    record(db, user, "MAINTENANCE_CLEANUP", ",".join(r["action"] for r in results),
           "SUCCESS" if ok else "PARTIAL/FAILED")
    db.commit()
    return {"results": results}


@router.post("/tasks", dependencies=[Depends(require_superadmin)])
def start_task(
    body: TaskBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.kind not in maintenance.TASK_KINDS:
        raise HTTPException(status_code=400, detail=f"Jenis task tidak dikenal: {body.kind}")
    _check_sudo(body.sudo_password)
    task_id = maintenance.start_task(body.kind, body.sudo_password)
    if task_id is None:
        raise HTTPException(status_code=400, detail=f"Jenis task tidak dikenal: {body.kind}")
    record(db, user, "MAINTENANCE_TASK", body.kind)
    db.commit()
    return {"task_id": task_id, "kind": body.kind}


@router.get("/tasks/{task_id}")
def task_status(
    task_id: str,
    _: str = Depends(get_current_user),
):
    task = maintenance.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan")
    return task


@router.post("/reboot", dependencies=[Depends(require_superadmin)])
def reboot_server(
    body: RebootBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm=true wajib untuk reboot")
    _check_sudo(body.sudo_password)
    record(db, user, "MAINTENANCE_REBOOT", "systemctl reboot")
    db.commit()
    maintenance.reboot(password=body.sudo_password)
    return {"ok": True, "message": "Server akan reboot dalam 1-2 detik"}
