"""Sharing printer berbasis ID komputer.

PC yang punya printer (USB/lokal) melaporkan printernya lewat heartbeat.
Klien "mencari" printer dengan memasukkan ID komputer pemilik; panel
mengembalikan **IP terkini** pemilik + path share sehingga tetap bekerja
walau IP berubah karena DHCP.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import get_current_role, get_current_user, require_write
from ..db.database import get_db
from ..db.models import ManagedComputer, SharedPrinter
from ..services.audit import record
from .computers import _assert_can_manage, _is_online

router = APIRouter(prefix="/printers", tags=["printers"])


def _serialize(p: SharedPrinter, owner: ManagedComputer) -> dict:
    online = _is_online(owner)
    share_path = (
        rf"\\{owner.ip}\{p.share_name}" if (p.share_name and owner.ip) else ""
    )
    return {
        "id": p.id,
        "computer_id": p.computer_id,
        "owner_name": owner.name or owner.hostname or str(owner.id),
        "owner_ip": owner.ip,
        "owner_mac": owner.mac,
        "owner_online": online,
        "owner_status": "online" if online else ("offline" if owner.last_seen else "waiting"),
        "name": p.name,
        "share_name": p.share_name,
        "share_path": share_path,
        "platform": p.platform,
        "driver": p.driver,
        "port": p.port,
        "is_shared": p.is_shared,
        "online": p.online,
        "updated_at": (
            p.updated_at.strftime("%Y-%m-%d %H:%M:%S") if p.updated_at else ""
        ),
    }


def _connect_command(owner: ManagedComputer, p: SharedPrinter) -> dict:
    """Perintah siap-tempel untuk menghubungkan printer di PC klien."""
    path = rf"\\{owner.ip}\{p.share_name}" if (p.share_name and owner.ip) else ""
    platform = (p.platform or "").lower()
    if platform.startswith("win") or (owner.os_info or "").lower().startswith("windows"):
        ps = (
            "# Sekali saja (jalankan sebagai Administrator): buka blokir guest SMB\n"
            "Set-SmbClientConfiguration -EnableInsecureGuestLogons $true -Force\n\n"
            "# Hubungkan printer pemilik (bisa dijalankan sebagai user biasa)\n"
            f'Add-Printer -ConnectionName "{path}"'
        )
        cmd = (
            f'net use "{path}" "" /user:guest /persistent:no & '
            f'rundll32 printui.dll,PrintUIEntry /in /n "{path}"'
        )
        return {"powershell": ps, "cmd": cmd, "share_path": path}
    # Linux/CUPS
    queue = p.share_name or p.name
    return {
        "shell": (
            f'lpadmin -p "{queue}" -E -v "ipp://{owner.ip}/printers/{queue}" '
            f'-m everywhere && lpoptions -d "{queue}"'
        ),
        "share_path": path,
    }


@router.get("")
def list_printers(
    computer_id: int | None = None,
    only_shared: bool = True,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(SharedPrinter, ManagedComputer).join(
        ManagedComputer, SharedPrinter.computer_id == ManagedComputer.id
    )
    if computer_id is not None:
        q = q.filter(SharedPrinter.computer_id == computer_id)
    if only_shared:
        q = q.filter(SharedPrinter.is_shared.is_(True))
    rows = q.order_by(SharedPrinter.computer_id, SharedPrinter.name).all()
    printers = [_serialize(p, c) for p, c in rows]
    return {
        "printers": printers,
        "total": len(printers),
        "shared": sum(1 for x in printers if x["is_shared"]),
    }


class ResolveBody(BaseModel):
    owner_id: int | None = None
    owner: str = ""       # nama / hostname / MAC (opsional)
    printer: str = ""     # nama printer / share name (opsional)
    include_unshared: bool = False


@router.post("/resolve")
def resolve(
    body: ResolveBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cari printer pemilik dari ID komputer (atau nama/hostname/MAC).

    Mengembalikan IP terkini pemilik + perintah connect, sehingga klien tetap
    bisa print walau pemilik berpindah IP (DHCP).
    """
    owner: ManagedComputer | None = None
    if body.owner_id is not None:
        owner = (
            db.query(ManagedComputer)
            .filter(ManagedComputer.id == body.owner_id)
            .first()
        )
    elif body.owner.strip():
        key = body.owner.strip()
        owner = (
            db.query(ManagedComputer)
            .filter(
                (ManagedComputer.name.ilike(key))
                | (ManagedComputer.hostname.ilike(key))
                | (ManagedComputer.mac.ilike(key))
            )
            .first()
        )
    if owner is None:
        raise HTTPException(404, "Komputer pemilik printer tidak ditemukan")

    q = db.query(SharedPrinter).filter(SharedPrinter.computer_id == owner.id)
    if not body.include_unshared:
        q = q.filter(SharedPrinter.is_shared.is_(True))
    if body.printer.strip():
        key = body.printer.strip()
        q = q.filter(
            (SharedPrinter.name.ilike(f"%{key}%"))
            | (SharedPrinter.share_name.ilike(f"%{key}%"))
        )
    rows = q.order_by(SharedPrinter.name).all()

    printers = []
    for p in rows:
        item = _serialize(p, owner)
        item["connect"] = _connect_command(owner, p) if p.is_shared else None
        printers.append(item)

    record(
        db, user,
        "PRINTER_RESOLVE",
        f"{body.owner_id if body.owner_id is not None else body.owner} · {owner.ip}",
    )
    db.commit()

    return {
        "owner": {
            "id": owner.id,
            "name": owner.name or owner.hostname or str(owner.id),
            "ip": owner.ip,
            "hostname": owner.hostname,
            "online": _is_online(owner),
            "status": "online" if _is_online(owner) else ("offline" if owner.last_seen else "waiting"),
        },
        "printers": printers,
        "total": len(printers),
    }


@router.post("/{printer_id}/share", dependencies=[Depends(require_write)])
def share_printer(
    printer_id: int,
    user: str = Depends(get_current_user),
    role: str = Depends(get_current_role),
    db: Session = Depends(get_db),
):
    """Minta agent pemilik mengaktifkan sharing printer (butuh admin di PC pemilik)."""
    p = db.query(SharedPrinter).filter(SharedPrinter.id == printer_id).first()
    if not p:
        raise HTTPException(404, "Printer tidak ditemukan")
    owner = (
        db.query(ManagedComputer)
        .filter(ManagedComputer.id == p.computer_id)
        .first()
    )
    if not owner:
        raise HTTPException(404, "Komputer pemilik tidak ditemukan")
    _assert_can_manage(db, user, role, owner)
    owner.pending_cmd = f"share-printer:{p.name}"
    owner.cmd_issued_at = datetime.utcnow()
    record(db, user, "PRINTER_SHARE", f"{owner.name or owner.id}: {p.name}", "PENDING")
    db.commit()
    return {
        "success": True,
        "detail": (
            f"Permintaan share '{p.name}' dikirim ke {owner.name or owner.id} "
            "— diproses agent pada heartbeat berikutnya"
        ),
    }


@router.post("/{printer_id}/unshare", dependencies=[Depends(require_write)])
def unshare_printer(
    printer_id: int,
    user: str = Depends(get_current_user),
    role: str = Depends(get_current_role),
    db: Session = Depends(get_db),
):
    p = db.query(SharedPrinter).filter(SharedPrinter.id == printer_id).first()
    if not p:
        raise HTTPException(404, "Printer tidak ditemukan")
    owner = (
        db.query(ManagedComputer)
        .filter(ManagedComputer.id == p.computer_id)
        .first()
    )
    if not owner:
        raise HTTPException(404, "Komputer pemilik tidak ditemukan")
    _assert_can_manage(db, user, role, owner)
    owner.pending_cmd = f"unshare-printer:{p.name}"
    owner.cmd_issued_at = datetime.utcnow()
    record(db, user, "PRINTER_UNSHARE", f"{owner.name or owner.id}: {p.name}", "PENDING")
    db.commit()
    return {"success": True, "detail": f"Permintaan unshare '{p.name}' dikirim ke {owner.name or owner.id}"}
