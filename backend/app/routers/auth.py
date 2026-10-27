import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import get_current_role, get_current_user
from ..core.security import (
    create_step_up_token,
    create_token,
    decode_step_up_token,
    verify_password,
)
from ..db.database import get_db
from ..db.models import AppSetting, User, UserPageAccess
from ..services.audit import record

def _get_cctv_global_password(_db: Session) -> str:
    try:
        from ..routers import settings
        return settings.get_cctv_global_password(_db)
    except Exception:
        return ""

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)

# scope step-up yang dikenal + batas percobaan gagal (rate limit sederhana)
VALID_STEP_UP_SCOPES = ("cctv", "myzrok")
_STEP_UP_MAX_FAILS = 5
_STEP_UP_WINDOW = 60.0
_step_up_fails: dict[str, list[float]] = {}


class LoginBody(BaseModel):
    username: str
    password: str


class StepUpBody(BaseModel):
    password: str
    scope: str = "cctv"


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        record(db, body.username, "LOGIN", "", "FAILED")
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_token(user.username, user.role or "viewer")
    user.last_login_at = datetime.utcnow()
    user.last_seen_at = datetime.utcnow()
    record(db, user.username, "LOGIN", "", "SUCCESS")
    db.commit()
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"username": user.username, "role": user.role or "viewer"},
    }


def _page_access(db: Session, user: User | None, role: str) -> list[str]:
    if role == "superadmin":
        return list(VALID_STEP_UP_SCOPES)
    if user is None:
        return []
    rows = (
        db.query(UserPageAccess.page)
        .filter(UserPageAccess.user_id == user.id)
        .all()
    )
    return sorted({p for (p,) in rows})


@router.get("/me")
def me(username: str = Depends(get_current_user), role: str = Depends(get_current_role), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if user:
        user.last_seen_at = datetime.utcnow()
        db.commit()
    return {
        "username": username,
        "role": role,
        "page_access": _page_access(db, user, role),
    }


@router.post("/step-up")
def step_up(
    body: StepUpBody,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verifikasi ulang password untuk membuka halaman terproteksi.

    Dipakai sebelum mengakses halaman CCTV: berlaku untuk SEMUA role
    (termasuk superadmin). Token yang dikembalikan berumur pendek.
    """
    scope = (body.scope or "").strip().lower()
    if scope not in VALID_STEP_UP_SCOPES:
        raise HTTPException(status_code=400, detail="Scope tidak dikenal")

    now = time.time()
    fails = [t for t in _step_up_fails.get(username, []) if now - t < _STEP_UP_WINDOW]
    if len(fails) >= _STEP_UP_MAX_FAILS:
        raise HTTPException(
            status_code=429,
            detail="Terlalu banyak percobaan. Coba lagi sebentar lagi.",
        )

    user = db.query(User).filter(User.username == username).first()
    # Coba password global CCTV dulu (all-in-one), fallback ke password user
    ok = False
    if scope == "cctv":
        g = _get_cctv_global_password(db)
        if g:
            try:
                import hmac as _h

                ok = _h.compare_digest(g, body.password)
            except Exception:
                ok = g == body.password
        # Password kredensial global kamera juga berlaku sebagai
        # password global CCTV — satu password sebagai patokan semua CCTV.
        if not ok:
            try:
                from ..routers import settings as _settings

                _, cam_pw = _settings.get_cctv_global_cam_cred(db)
                if cam_pw:
                    import hmac as _h2

                    ok = _h2.compare_digest(cam_pw, body.password)
            except Exception:
                pass
    if not ok and user is not None:
        ok = verify_password(body.password, user.password_hash)
    if not ok:
        fails.append(now)
        _step_up_fails[username] = fails
        record(db, username, f"STEPUP_{scope.upper()}", "", "FAILED")
        db.commit()
        raise HTTPException(status_code=400, detail="Password salah")

    _step_up_fails.pop(username, None)
    token = create_step_up_token(username, scope, minutes=5)
    record(db, username, f"STEPUP_{scope.upper()}", "", "SUCCESS")
    db.commit()
    return {"elevated_token": token, "scope": scope, "expires_in": 300}


class StepUpRefreshBody(BaseModel):
    elevated_token: str
    scope: str = "cctv"


@router.post("/step-up/refresh")
def step_up_refresh(
    body: StepUpRefreshBody,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Perpanjang sesi step-up yang MASIH VALID tanpa password ulang.

    Dipakai heartbeat halaman CCTV agar monitoring tidak terputus tiap
    5 menit (tidak perlu ketik password manual berulang). Token basi
    tetap ditolak 428 → user lewat gerbang password seperti biasa.
    """
    scope = (body.scope or "").strip().lower()
    if scope not in VALID_STEP_UP_SCOPES:
        raise HTTPException(status_code=400, detail="Scope tidak dikenal")
    payload = decode_step_up_token(body.elevated_token or "", scope)
    if payload is None or str(payload.get("sub")) != username:
        raise HTTPException(
            status_code=428,
            detail="Sesi verifikasi tidak valid / kedaluwarsa",
        )
    token = create_step_up_token(username, scope, minutes=5)
    record(db, username, f"STEPUP_{scope.upper()}_REFRESH", "", "SUCCESS")
    db.commit()
    return {"elevated_token": token, "scope": scope, "expires_in": 300}


@router.post("/logout")
def logout(
    username: str = Depends(get_current_user),
    _role: str = Depends(get_current_role),
    db: Session = Depends(get_db),
):
    """Catat waktu user keluar (off) secara eksplisit.

    Frontend memanggil endpoint ini saat user menekan Logout, sehingga
    panel punya catatan "kapan terakhir di-off" di samping last_login.
    """
    user = db.query(User).filter(User.username == username).first()
    if user:
        user.logout_at = datetime.utcnow()
        record(db, username, "LOGOUT", "", "SUCCESS")
    else:
        record(db, username, "LOGOUT", "", "FAILED")
    db.commit()
    return {"ok": True, "logout_at": user.logout_at.isoformat() if user and user.logout_at else None}
