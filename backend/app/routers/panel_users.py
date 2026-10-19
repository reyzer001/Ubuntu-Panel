import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_superadmin
from ..core.security import hash_password
from ..db.database import get_db
from ..db.models import (
    AuditLog,
    ManagedComputer,
    User,
    UserComputerAccess,
    UserPageAccess,
)
from ..services.audit import record

router = APIRouter(prefix="/panel-users", tags=["panel-users"])

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,64}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9\s\-]{5,19}$")
VALID_ROLES = ("superadmin", "admin", "viewer")
# halaman yang bisa di-grant per user (non-superadmin)
VALID_PAGES = ("cctv",)


class CreateUserBody(BaseModel):
    username: str
    password: str
    role: str = "viewer"
    full_name: str = ""
    email: str = ""
    phone: str = ""


class RoleBody(BaseModel):
    role: str


class PasswordBody(BaseModel):
    password: str


class ProfileBody(BaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""


class ComputerAccessBody(BaseModel):
    computer_ids: list[int] = []


class PageAccessBody(BaseModel):
    pages: list[str] = []


def _serialize(u: User) -> dict:
    last_seen = u.last_seen_at or u.last_login_at
    online = bool(last_seen and (datetime.utcnow() - last_seen) <= timedelta(minutes=5))
    return {
        "id": u.id,
        "username": u.username,
        "role": u.role or "viewer",
        "full_name": u.full_name or "",
        "email": u.email or "",
        "phone": u.phone or "",
        "created_at": u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "",
        "last_login_at": u.last_login_at.strftime("%Y-%m-%d %H:%M:%S") if u.last_login_at else None,
        "last_seen_at": last_seen.strftime("%Y-%m-%d %H:%M:%S") if last_seen else None,
        "logout_at": u.logout_at.strftime("%Y-%m-%d %H:%M:%S") if u.logout_at else None,
        "online": online,
    }


def _serialize_detail(u: User, allowed_ids: set[int], pages: list[str]) -> dict:
    last_seen = u.last_seen_at or u.last_login_at
    online = bool(last_seen and (datetime.utcnow() - last_seen) <= timedelta(minutes=5))
    return {
        "id": u.id,
        "username": u.username,
        "role": u.role or "viewer",
        "full_name": u.full_name or "",
        "email": u.email or "",
        "phone": u.phone or "",
        "created_at": u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "",
        "last_login_at": u.last_login_at.strftime("%Y-%m-%d %H:%M:%S") if u.last_login_at else None,
        "last_seen_at": last_seen.strftime("%Y-%m-%d %H:%M:%S") if last_seen else None,
        "logout_at": u.logout_at.strftime("%Y-%m-%d %H:%M:%S") if u.logout_at else None,
        "online": online,
        "computer_access": sorted(allowed_ids),
        "page_access": sorted(pages),
    }


def _validate_contact(email: str, phone: str) -> None:
    if email and not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Format email tidak valid")
    if phone and not _PHONE_RE.match(phone):
        raise HTTPException(
            status_code=400,
            detail="Nomor telepon tidak valid (6-20 digit, boleh diawali +)",
        )


def _validate_role(role: str) -> str:
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Role harus salah satu dari: {', '.join(VALID_ROLES)}",
        )
    return role


def _count_superadmins(db: Session, exclude_id: int | None = None) -> int:
    q = db.query(User).filter(User.role == "superadmin")
    if exclude_id is not None:
        q = q.filter(User.id != exclude_id)
    return q.count()


@router.get("")
def list_panel_users(_: str = Depends(get_current_user), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id).all()
    return {"users": [_serialize(u) for u in users]}


@router.get("/active")
def list_active_panel_users(_: str = Depends(get_current_user), db: Session = Depends(get_db)):
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    rows = db.query(User).filter(User.last_seen_at.isnot(None)).order_by(User.last_seen_at.desc()).all()
    users = []
    for user in rows:
        last_seen = user.last_seen_at or user.last_login_at
        if last_seen and last_seen >= cutoff:
            users.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "role": user.role or "viewer",
                    "full_name": user.full_name or "",
                    "last_seen_at": last_seen.strftime("%Y-%m-%d %H:%M:%S") if last_seen else None,
                    "online": True,
                }
            )
    return {"users": users}


@router.get("/{user_id}/detail")
def get_panel_user_detail(
    user_id: int,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    allowed_ids = {
        item.computer_id for item in db.query(UserComputerAccess).filter(UserComputerAccess.user_id == user.id).all()
    }
    pages = [
        p for (p,) in db.query(UserPageAccess.page)
        .filter(UserPageAccess.user_id == user.id)
        .all()
    ]
    return _serialize_detail(user, allowed_ids, pages)


@router.get("/{user_id}/activity")
def get_user_activity(
    user_id: int,
    limit: int = 50,
    offset: int = 0,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Semua log aktivitas seorang user (paginasi).

    `limit` maksimal 200. Dipakai halaman detail untuk menampilkan SEMUA
    aktivitas, bukan cuma 20 terbaru seperti di /detail.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    base = db.query(AuditLog).filter(AuditLog.username == user.username)
    total = base.count()
    logs = (
        base.order_by(AuditLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "logs": [
            {
                "id": log.id,
                "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                if log.timestamp
                else "",
                "action": log.action,
                "target": log.target,
                "result": log.result,
            }
            for log in logs
        ],
    }


@router.get("/{user_id}/computer-access")
def get_user_computer_access(
    user_id: int,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    allowed = db.query(UserComputerAccess.computer_id).filter(UserComputerAccess.user_id == user.id).all()
    return {"computer_ids": sorted({item[0] for item in allowed})}


@router.put("/{user_id}/computer-access", dependencies=[Depends(require_superadmin)])
def set_user_computer_access(
    user_id: int,
    body: ComputerAccessBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")

    ids = list(dict.fromkeys(body.computer_ids))
    if ids:
        computers = db.query(ManagedComputer).filter(ManagedComputer.id.in_(ids)).all()
        found = {c.id for c in computers}
        if len(found) != len(ids):
            missing = [str(i) for i in ids if i not in found]
            raise HTTPException(400, detail=f"Komputer tidak ditemukan: {', '.join(missing)}")

    existing = db.query(UserComputerAccess).filter(UserComputerAccess.user_id == user_id).all()
    for access in existing:
        db.delete(access)
    for computer_id in ids:
        db.add(UserComputerAccess(user_id=user_id, computer_id=computer_id))
    db.commit()
    record(db, user, "PANEL_USER_ACCESS", f"{target.username}:{len(ids)} komputer", "SUCCESS")
    db.commit()
    return {"success": True, "computer_ids": ids}


@router.put("/{user_id}/page-access", dependencies=[Depends(require_superadmin)])
def set_user_page_access(
    user_id: int,
    body: PageAccessBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Grant/revoke izin halaman (mis. CCTV) — hanya superadmin, hanya role admin."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    if (target.role or "") != "admin":
        raise HTTPException(
            status_code=400,
            detail="Izin halaman hanya diberikan ke role admin",
        )

    pages = [p for p in dict.fromkeys(body.pages) if p in VALID_PAGES]
    db.query(UserPageAccess).filter(
        UserPageAccess.user_id == user_id
    ).delete(synchronize_session=False)
    for page in pages:
        db.add(UserPageAccess(user_id=user_id, page=page))
    record(
        db, user, "PANEL_USER_PAGE_ACCESS",
        f"{target.username}:{','.join(pages) if pages else '-'}", "SUCCESS",
    )
    db.commit()
    return {"success": True, "page_access": sorted(pages)}


@router.post("", dependencies=[Depends(require_superadmin)])
def create_panel_user(
    body: CreateUserBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    username = body.username.strip()
    if not _USERNAME_RE.match(username):
        raise HTTPException(
            status_code=400,
            detail="Username 3-64 karakter (huruf, angka, . _ -)",
        )
    _validate_role(body.role)
    full_name = body.full_name.strip()[:128]
    email = body.email.strip().lower()[:128]
    phone = body.phone.strip()[:32]
    _validate_contact(email, phone)
    if len(body.password) < 4:
        raise HTTPException(status_code=400, detail="Password minimal 4 karakter")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username sudah dipakai")
    if email and db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email sudah dipakai")

    u = User(
        username=username,
        password_hash=hash_password(body.password),
        role=body.role,
        full_name=full_name,
        email=email,
        phone=phone,
    )
    db.add(u)
    db.commit()
    record(db, user, "PANEL_USER_CREATE", f"{username}:{body.role}", "SUCCESS")
    db.commit()
    return {"success": True, "user": _serialize(u)}


@router.patch("/{user_id}/role", dependencies=[Depends(require_superadmin)])
def change_role(
    user_id: int,
    body: RoleBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    new_role = _validate_role(body.role)

    if target.role == "superadmin" and new_role != "superadmin":
        if target.username == user:
            raise HTTPException(
                status_code=400, detail="Tidak bisa menurunkan role diri sendiri"
            )
        if _count_superadmins(db, exclude_id=target.id) == 0:
            raise HTTPException(
                status_code=400, detail="Minimal harus tersisa satu superadmin"
            )

    target.role = new_role
    db.commit()
    record(db, user, "PANEL_USER_ROLE", f"{target.username}:{new_role}", "SUCCESS")
    db.commit()
    return {"success": True, "user": _serialize(target)}


@router.patch("/{user_id}", dependencies=[Depends(require_superadmin)])
def update_profile(
    user_id: int,
    body: ProfileBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")

    full_name = body.full_name.strip()[:128]
    email = body.email.strip().lower()[:128]
    phone = body.phone.strip()[:32]
    _validate_contact(email, phone)
    if email and db.query(User).filter(User.email == email, User.id != user_id).first():
        raise HTTPException(status_code=400, detail="Email sudah dipakai")

    target.full_name = full_name
    target.email = email
    target.phone = phone
    db.commit()
    record(db, user, "PANEL_USER_PROFILE", target.username, "SUCCESS")
    db.commit()
    return {"success": True, "user": _serialize(target)}


@router.patch("/{user_id}/password", dependencies=[Depends(require_superadmin)])
def change_password(
    user_id: int,
    body: PasswordBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if len(body.password) < 4:
        raise HTTPException(status_code=400, detail="Password minimal 4 karakter")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")

    target.password_hash = hash_password(body.password)
    db.commit()
    record(db, user, "PANEL_USER_PASSWORD", target.username, "SUCCESS")
    db.commit()
    return {"success": True}


@router.delete("/{user_id}", dependencies=[Depends(require_superadmin)])
def delete_panel_user(
    user_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    if target.username == user:
        raise HTTPException(
            status_code=400, detail="Tidak bisa menghapus akun sendiri"
        )
    if target.role == "superadmin" and _count_superadmins(db) <= 1:
        raise HTTPException(
            status_code=400, detail="Minimal harus tersisa satu superadmin"
        )

    record(db, user, "PANEL_USER_DELETE", target.username, "SUCCESS")
    db.delete(target)
    db.commit()
    return {"success": True}
