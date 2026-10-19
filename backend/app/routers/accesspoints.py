"""API monitoring Akses Point: inventory, subnet target, scan, events."""

import ipaddress

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_write
from ..db.database import get_db
from ..db.models import APEvent, APGroup, APScanTarget, AccessPoint
from ..services import apmon, audit

router = APIRouter(tags=["access-points"])


def _ap_dict(ap: AccessPoint, group_name: str = "") -> dict:
    return {
        "id": ap.id,
        "mac": ap.mac,
        "ip": ap.ip,
        "vendor": ap.vendor,
        "model": ap.model,
        "ssid": ap.ssid,
        "group_id": ap.group_id,
        "group_name": group_name,
        "pinned": ap.pinned,
        "notes": ap.notes,
        "is_ap": ap.is_ap,
        "segment": ap.segment,
        "status": ap.status,
        "first_seen": ap.first_seen.isoformat() + "Z",
        "last_seen": ap.last_seen.isoformat() + "Z",
    }


def _group_names(db: Session) -> dict[int, str]:
    return {g.id: g.name for g in db.query(APGroup).all()}


# ------------------------------------------------------------- inventory
@router.get("/access-points")
def list_access_points(
    status: str = "",
    q: str = "",
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(AccessPoint)
    if status.upper() in ("ONLINE", "OFFLINE"):
        query = query.filter(AccessPoint.status == status.upper())
    if q:
        like = f"%{q}%"
        query = query.filter(
            AccessPoint.mac.ilike(like)
            | AccessPoint.ip.ilike(like)
            | AccessPoint.vendor.ilike(like)
            | AccessPoint.model.ilike(like)
            | AccessPoint.ssid.ilike(like)
        )
    aps = query.order_by(AccessPoint.is_ap.desc(), AccessPoint.status.asc(),
                         AccessPoint.ip.asc()).all()
    names = _group_names(db)
    return {
        "aps": [_ap_dict(a, names.get(a.group_id, "")) for a in aps],
        "summary": apmon.status_summary(db),
    }


class APEdit(BaseModel):
    ssid: str = ""
    model: str = ""
    group_id: int | None = None
    notes: str = ""
    is_ap: bool = False
    pinned: bool = False


@router.put("/access-points/{ap_id}", dependencies=[Depends(require_write)])
def edit_access_point(
    ap_id: int,
    body: APEdit,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ap = db.get(AccessPoint, ap_id)
    if not ap:
        raise HTTPException(404, "Perangkat tidak ditemukan")
    if body.group_id is not None and not db.get(APGroup, body.group_id):
        raise HTTPException(400, "Grup tidak ditemukan")
    ap.ssid = body.ssid.strip()
    ap.model = body.model.strip()
    ap.group_id = body.group_id
    ap.notes = body.notes.strip()
    ap.is_ap = body.is_ap
    ap.pinned = body.pinned
    audit.record(db, username, "AP_EDIT", target=f"{ap.mac} ({ap.ip})")
    db.commit()
    return {"ok": True}


@router.post("/access-points/{ap_id}/pin", dependencies=[Depends(require_write)])
def pin_access_point(
    ap_id: int,
    pinned: bool = True,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ap = db.get(AccessPoint, ap_id)
    if not ap:
        raise HTTPException(404, "Perangkat tidak ditemukan")
    ap.pinned = pinned
    audit.record(db, username, "AP_PIN" if pinned else "AP_UNPIN",
                 target=f"{ap.mac} ({ap.ip})")
    db.commit()
    return {"ok": True, "pinned": ap.pinned}


@router.delete("/access-points/events", dependencies=[Depends(require_write)])
def clear_events(
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Hapus semua kejadian KECUALI milik perangkat yang di-pin."""
    pinned_macs = {
        m for (m,) in db.query(AccessPoint.mac)
        .filter(AccessPoint.pinned.is_(True)).all()
    }
    q = db.query(APEvent)
    if pinned_macs:
        q = q.filter(~APEvent.mac.in_(pinned_macs))
    deleted = q.delete(synchronize_session=False)
    audit.record(
        db, username, "AP_EVENTS_CLEAR",
        target=f"{deleted} events cleared (pinned kept)",
    )
    db.commit()
    return {"ok": True, "deleted": deleted}


@router.delete("/access-points/cleanup-stale", dependencies=[Depends(require_write)])
def cleanup_stale_devices(
    days: int = 3,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Hapus perangkat offline yang unpinned, tanpa grup/catatan, yang sudah lama tidak aktif."""
    deleted = apmon.prune_stale_devices(db, days=days)
    audit.record(
        db, username, "AP_CLEANUP_STALE",
        target=f"{deleted} stale devices removed",
    )
    return {"ok": True, "deleted": deleted}


@router.delete("/access-points/{ap_id}", dependencies=[Depends(require_write)])
def delete_access_point(
    ap_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ap = db.get(AccessPoint, ap_id)
    if not ap:
        raise HTTPException(404, "Perangkat tidak ditemukan")
    audit.record(db, username, "AP_DELETE", target=f"{ap.mac} ({ap.ip})")
    db.delete(ap)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------- groups
@router.get("/access-points/groups")
def list_groups(_: str = Depends(get_current_user), db: Session = Depends(get_db)):
    groups = db.query(APGroup).order_by(APGroup.name).all()
    counts: dict[int, int] = {}
    for (gid, n) in db.query(AccessPoint.group_id, AccessPoint.id).all():
        if gid is not None:
            counts[gid] = counts.get(gid, 0) + 1
    return {
        "groups": [
            {"id": g.id, "name": g.name, "count": counts.get(g.id, 0)}
            for g in groups
        ]
    }


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


@router.post("/access-points/groups", dependencies=[Depends(require_write)])
def add_group(
    body: GroupCreate,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Nama grup kosong")
    if db.query(APGroup).filter_by(name=name).first():
        raise HTTPException(409, f"Grup '{name}' sudah ada")
    g = APGroup(name=name)
    db.add(g)
    audit.record(db, username, "AP_GROUP_ADD", target=name)
    db.commit()
    return {"ok": True, "id": g.id}


@router.put("/access-points/groups/{group_id}", dependencies=[Depends(require_write)])
def rename_group(
    group_id: int,
    body: GroupCreate,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    g = db.get(APGroup, group_id)
    if not g:
        raise HTTPException(404, "Grup tidak ditemukan")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Nama grup kosong")
    dup = db.query(APGroup).filter_by(name=name).first()
    if dup and dup.id != group_id:
        raise HTTPException(409, f"Grup '{name}' sudah ada")
    old = g.name
    g.name = name
    audit.record(db, username, "AP_GROUP_RENAME", target=f"{old} → {name}")
    db.commit()
    return {"ok": True}


@router.delete("/access-points/groups/{group_id}", dependencies=[Depends(require_write)])
def delete_group(
    group_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    g = db.get(APGroup, group_id)
    if not g:
        raise HTTPException(404, "Grup tidak ditemukan")
    # perangkat tidak ikut terhapus — hanya lepas dari grup
    db.query(AccessPoint).filter(AccessPoint.group_id == group_id).update(
        {AccessPoint.group_id: None}
    )
    audit.record(db, username, "AP_GROUP_DELETE", target=g.name)
    db.delete(g)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- events
@router.get("/access-points/events")
def list_events(
    limit: int = 100,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 500))
    rows = (
        db.query(APEvent)
        .order_by(APEvent.timestamp.desc(), APEvent.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "events": [
            {
                "id": e.id,
                "mac": e.mac,
                "ip": e.ip,
                "event": e.event,
                "timestamp": e.timestamp.isoformat() + "Z",
            }
            for e in rows
        ]
    }


# ---------------------------------------------------------------- targets
class TargetCreate(BaseModel):
    cidr: str = Field(min_length=7, max_length=64)
    label: str = Field(default="", max_length=128)


@router.get("/access-points/targets")
def list_targets(_: str = Depends(get_current_user), db: Session = Depends(get_db)):
    return {
        "targets": [
            {"id": t.id, "cidr": t.cidr, "label": t.label}
            for t in db.query(APScanTarget).order_by(APScanTarget.cidr).all()
        ]
    }


@router.get("/access-points/suggest-targets")
def suggest_targets(_: str = Depends(get_current_user)):
    """Subnet /24 lokal dari interface server — bantu isi target scan."""
    import re as _re
    import subprocess

    out = subprocess.run(
        ["ip", "-4", "-o", "addr", "show"],
        capture_output=True, text=True, timeout=10,
    ).stdout
    seen: set[str] = set()
    for line in out.splitlines():
        m = _re.search(r"inet (\d{1,3}(?:\.\d{1,3}){3}/\d+)\s", line)
        if not m:
            continue
        try:
            net = ipaddress.ip_network(m.group(1), strict=False)
        except ValueError:
            continue
        if (
            not net.is_loopback
            and 8 <= net.num_addresses <= 256
            and not net.is_link_local
        ):
            cidr = f"{net.network_address}/{net.prefixlen}"
            iface = line.split()[1]
            seen.add(f"{cidr}|{iface}")
    return {
        "suggestions": [
            {"cidr": s.split("|")[0], "iface": s.split("|")[1]}
            for s in sorted(seen)
        ]
    }


@router.post("/access-points/targets", dependencies=[Depends(require_write)])
def add_target(
    body: TargetCreate,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        net = ipaddress.ip_network(body.cidr.strip(), strict=False)
    except ValueError:
        raise HTTPException(400, f"CIDR tidak valid: {body.cidr}")
    if net.num_addresses > apmon._MAX_HOSTS:
        raise HTTPException(
            400, f"Subnet terlalu besar; maksimal {apmon._MAX_HOSTS} host"
        )
    cidr = str(net)
    if db.query(APScanTarget).filter_by(cidr=cidr).first():
        raise HTTPException(409, f"Subnet {cidr} sudah terdaftar")
    t = APScanTarget(cidr=cidr, label=body.label.strip())
    db.add(t)
    audit.record(db, username, "AP_TARGET_ADD", target=cidr)
    db.commit()
    return {"ok": True, "cidr": cidr}


@router.delete("/access-points/targets/{target_id}", dependencies=[Depends(require_write)])
def delete_target(
    target_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = db.get(APScanTarget, target_id)
    if not t:
        raise HTTPException(404, "Target tidak ditemukan")
    audit.record(db, username, "AP_TARGET_DELETE", target=t.cidr)
    db.delete(t)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ scan
@router.post("/access-points/scan-now", dependencies=[Depends(require_write)])
def trigger_scan(
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    started = apmon.scan_now()
    audit.record(
        db, username, "AP_SCAN_NOW",
        result="SUCCESS" if started else "SKIPPED",
    )
    db.commit()
    if not started:
        raise HTTPException(409, "Scan sedang berjalan")
    return {"started": True}
