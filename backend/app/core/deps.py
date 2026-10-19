from datetime import datetime

from fastapi import Depends, Header, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..db.database import SessionLocal, get_db
from ..db.models import User, UserPageAccess
from .security import (
    decode_step_up_token,
    decode_token,
    decode_token_full,
)

bearer = HTTPBearer(auto_error=False)

ROLES = ("superadmin", "admin", "viewer")
# viewer read-only; admin & superadmin boleh melakukan perubahan
WRITE_ROLES = ("superadmin", "admin")


def get_credentials(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> HTTPAuthorizationCredentials:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return credentials


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    token: str | None = Query(default=None),
) -> str:
    # Header Authorization normal; fallback query `token` dipakai endpoint
    # media yang diakses lewat <img> (tak bisa mengirim header).
    raw = credentials.credentials if credentials is not None else (token or "")
    if not raw:
        raise HTTPException(status_code=401, detail="Not authenticated")
    username = decode_token(raw)
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    try:
        with SessionLocal() as db:
            user = db.query(User).filter(User.username == username).first()
            if user is not None:
                user.last_seen_at = datetime.utcnow()
                db.commit()
    except Exception:
        pass
    return username


def _role_for_token(payload: dict) -> str:
    """Role dari claim JWT; token lama (tanpa claim) dicari ke DB."""
    role = str(payload.get("role") or "")
    if role in ROLES:
        return role
    username = str(payload.get("sub") or "")
    if username:
        try:
            with SessionLocal() as db:
                u = db.query(User).filter(User.username == username).first()
                if u and (u.role or "") in ROLES:
                    return u.role
        except Exception:
            pass  # DB error: keep role from JWT payload
    # fallback: gunakan role dari JWT bila ada, atau viewer
    return role if role in ROLES else "viewer"


def get_current_role(
    credentials: HTTPAuthorizationCredentials = Depends(get_credentials),
) -> str:
    payload = decode_token_full(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return _role_for_token(payload)


def require_roles(*allowed: str):
    """Dependency factory: batasi endpoint ke role tertentu."""

    def checker(role: str = Depends(get_current_role)) -> str:
        if role not in allowed:
            raise HTTPException(
                status_code=403, detail="Insufficient permissions"
            )
        return role

    return checker


require_write = require_roles(*WRITE_ROLES)
require_superadmin = require_roles("superadmin")


def user_has_page_access(db, username: str, page: str) -> bool:
    """Superadmin selalu boleh; role lain hanya bila di-grant lewat UserPageAccess."""
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        return False
    if (user.role or "") == "superadmin":
        return True
    return (
        db.query(UserPageAccess)
        .filter(UserPageAccess.user_id == user.id, UserPageAccess.page == page)
        .first()
        is not None
    )


def require_page_access(page: str):
    """Batasi endpoint ke user yang punya izin `page` (atau superadmin)."""

    def checker(
        username: str = Depends(get_current_user),
        db=Depends(get_db),
    ) -> str:
        if not user_has_page_access(db, username, page):
            raise HTTPException(
                status_code=403,
                detail="Tidak punya akses ke halaman ini",
            )
        return username

    return checker


def require_step_up(scope: str):
    """Wajibkan token verifikasi password (step-up) yang valid untuk `scope`.

    Token dikirim via header ``X-Elevated-Token`` (API) atau query ``et``
    (endpoint media yang diakses lewat <img>).
    """

    def checker(
        username: str = Depends(get_current_user),
        x_elevated_token: str | None = Header(default=None, alias="X-Elevated-Token"),
        et: str | None = Query(default=None),
    ) -> str:
        token = x_elevated_token or et
        if not token:
            raise HTTPException(
                status_code=428, detail="Verifikasi password diperlukan"
            )
        payload = decode_step_up_token(token, scope)
        if payload is None or str(payload.get("sub")) != username:
            raise HTTPException(
                status_code=428,
                detail="Sesi verifikasi tidak valid / kedaluwarsa",
            )
        return username

    return checker
