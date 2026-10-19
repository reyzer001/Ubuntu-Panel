from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_page_access, require_superadmin
from ..core.security import decrypt_secret, encrypt_secret
from ..db.database import get_db
from ..db.models import AppSetting
from ..services import audit

router = APIRouter(prefix="/settings", tags=["settings"])

CCTV_PW_KEY = "cctv_stepup_password"

CCTV_CAM_USERNAME = "cctv_cam_username"
CCTV_CAM_PASSWORD = "cctv_cam_password_enc"



class CctvPasswordBody(BaseModel):
    password: str


class CctvCamCredBody(BaseModel):
    username: str
    password: str


@router.get("/cctv-password", dependencies=[Depends(require_superadmin)])
def get_cctv_password_set(_: str = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(AppSetting).filter(AppSetting.key == CCTV_PW_KEY).first()
    return {"set": row is not None and bool(row.value_enc)}


@router.put("/cctv-password", dependencies=[Depends(require_superadmin)])
def set_cctv_password(
    body: CctvPasswordBody,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pw = (body.password or "").strip()
    if not pw:
        raise HTTPException(400, "Password tidak boleh kosong")
    row = db.query(AppSetting).filter(AppSetting.key == CCTV_PW_KEY).first()
    enc = encrypt_secret(pw)
    if row is None:
        db.add(AppSetting(key=CCTV_PW_KEY, value_enc=enc))
    else:
        row.value_enc = enc
        from datetime import datetime

        row.updated_at = datetime.utcnow()
    audit.record(db, username, "CCTV_PASSWORD_SET", "")
    db.commit()
    return {"ok": True}


@router.delete("/cctv-password", dependencies=[Depends(require_superadmin)])
def clear_cctv_password(
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.query(AppSetting).filter(AppSetting.key == CCTV_PW_KEY).first()
    if row is not None:
        db.delete(row)
        audit.record(db, username, "CCTV_PASSWORD_CLEAR", "")
        db.commit()
    return {"ok": True}


def get_cctv_global_password(db: Session) -> str:
    row = db.query(AppSetting).filter(AppSetting.key == CCTV_PW_KEY).first()
    if row is None or not row.value_enc:
        return ""
    return decrypt_secret(row.value_enc)


@router.get("/cctv-camera-cred", dependencies=[Depends(require_superadmin)])
def get_cctv_camera_cred_set(_: str = Depends(get_current_user), db: Session = Depends(get_db)):
    un = db.query(AppSetting).filter(AppSetting.key == CCTV_CAM_USERNAME).first()
    pw = db.query(AppSetting).filter(AppSetting.key == CCTV_CAM_PASSWORD).first()
    set_flag = bool(un and un.value_enc and pw and pw.value_enc)
    # corrupt = baris password ada tapi tidak bisa di-decrypt (mis. SECRET_KEY
    # berubah) → password global diam-diam tidak berlaku; admin harus set ulang.
    corrupt = False
    if pw and pw.value_enc:
        try:
            corrupt = not bool(decrypt_secret(pw.value_enc))
        except Exception:
            corrupt = True
    return {"set": set_flag, "username": un.value_enc if un and un.value_enc else "", "corrupt": corrupt}


@router.put("/cctv-camera-cred", dependencies=[Depends(require_superadmin)])
def set_cctv_camera_cred(
    body: CctvCamCredBody,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    un = (body.username or "").strip()
    pw = (body.password or "").strip()
    if not un:
        raise HTTPException(400, "Username tidak boleh kosong")
    if not pw:
        raise HTTPException(400, "Password tidak boleh kosong")
    row_un = db.query(AppSetting).filter(AppSetting.key == CCTV_CAM_USERNAME).first()
    row_pw = db.query(AppSetting).filter(AppSetting.key == CCTV_CAM_PASSWORD).first()
    if row_un is None:
        db.add(AppSetting(key=CCTV_CAM_USERNAME, value_enc=un))
    else:
        row_un.value_enc = un
    enc_pw = encrypt_secret(pw)
    # Round-trip check: pastikan hasil enkripsi bisa di-decrypt kembali.
    # Kalau gagal (mis. masalah kunci), jangan simpan nilai yang akan
    # membuat semua tile 502 "kredensial gagal" tanpa jejak.
    if not enc_pw or decrypt_secret(enc_pw) != pw:
        raise HTTPException(500, "Gagal menyimpan kredensial (enkripsi tidak valid)")
    if row_pw is None:
        db.add(AppSetting(key=CCTV_CAM_PASSWORD, value_enc=enc_pw))
    else:
        row_pw.value_enc = enc_pw
    from datetime import datetime

    for r in [row_un, row_pw]:
        if r is not None:
            r.updated_at = datetime.utcnow()
    audit.record(db, username, "CCTV_CAM_CRED_SET", "")
    db.commit()
    # Password global baru harus langsung berlaku: naikkan versi (reset
    # negative cache + cache resolve) agar semua kamera dicoba ulang.
    # Import di sini (bukan top-level) untuk menghindari circular import
    # karena cammon mengimpor modul ini.
    try:
        from ..services import cammon as _cammon

        _cammon.bump_global_cred_version()
    except Exception:
        pass
    return {"ok": True}


@router.delete("/cctv-camera-cred", dependencies=[Depends(require_superadmin)])
def clear_cctv_camera_cred(
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    for k in (CCTV_CAM_USERNAME, CCTV_CAM_PASSWORD):
        row = db.query(AppSetting).filter(AppSetting.key == k).first()
        if row is not None:
            db.delete(row)
    audit.record(db, username, "CCTV_CAM_CRED_CLEAR", "")
    db.commit()
    try:
        from ..services import cammon as _cammon

        _cammon.bump_global_cred_version()
    except Exception:
        pass
    return {"ok": True}


CCTV_MODE_KEY = "cctv_default_mode"


class CctvModeBody(BaseModel):
    mode: str


@router.get("/cctv-default-mode", dependencies=[Depends(require_page_access("cctv"))])
def get_cctv_default_mode(_: str = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(AppSetting).filter(AppSetting.key == CCTV_MODE_KEY).first()
    mode = row.value_enc if row and row.value_enc in ("live", "snapshot") else "live"
    return {"mode": mode}


@router.put("/cctv-default-mode", dependencies=[Depends(require_superadmin)])
def set_cctv_default_mode(
    body: CctvModeBody,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mode = (body.mode or "").strip().lower()
    if mode not in ("live", "snapshot"):
        raise HTTPException(400, "Mode tidak dikenal")
    row = db.query(AppSetting).filter(AppSetting.key == CCTV_MODE_KEY).first()
    if row is None:
        db.add(AppSetting(key=CCTV_MODE_KEY, value_enc=mode))
    else:
        row.value_enc = mode
    audit.record(db, username, "CCTV_MODE_SET", mode)
    db.commit()
    return {"ok": True, "mode": mode}


def get_cctv_global_cam_cred(db: Session) -> tuple[str | None, str | None]:
    un = db.query(AppSetting).filter(AppSetting.key == CCTV_CAM_USERNAME).first()
    pw = db.query(AppSetting).filter(AppSetting.key == CCTV_CAM_PASSWORD).first()
    username = (un.value_enc or "").strip() if un and un.value_enc else None
    password = decrypt_secret(pw.value_enc) if pw and pw.value_enc else None
    if not username or not password:
        return None, None
    return username, password
