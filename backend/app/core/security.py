import base64
import hashlib
import hmac
import logging
import os
import time

import jwt

from .config import get_settings

log = logging.getLogger(__name__)

_PBKDF2_ITERATIONS = 120_000

# Password kredensial device (kamera) disimpan reversible — perlu dipakai
# untuk login ke perangkat. Kunci diturunkan dari SECRET_KEY (SHA-256).
_FERNET: "object | None" = None


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt, _PBKDF2_ITERATIONS
    )
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split(":")
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), _PBKDF2_ITERATIONS
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


def create_token(username: str, role: str = "viewer") -> str:
    settings = get_settings()
    payload = {
        "sub": username,
        "role": role,
        "exp": int(time.time()) + settings.access_token_expire_minutes * 60,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_token_full(token: str) -> dict | None:
    try:
        return jwt.decode(
            token, get_settings().secret_key, algorithms=["HS256"]
        )
    except jwt.PyJWTError:
        return None


def decode_token(token: str) -> str | None:
    payload = decode_token_full(token)
    if payload is None:
        return None
    sub = payload.get("sub")
    return str(sub) if sub else None


# --------------------------------------------------- step-up (re-auth) token
def create_step_up_token(username: str, scope: str, minutes: int = 5) -> str:
    """Token sementara penanda user sudah verifikasi password untuk `scope`.

    Terpisah dari token sesi: klaim `stepup` + `scope` mencegah token ini
    dipakai sebagai sesi normal, dan sebaliknya.
    """
    settings = get_settings()
    payload = {
        "sub": username,
        "scope": scope,
        "stepup": True,
        "exp": int(time.time()) + minutes * 60,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_step_up_token(token: str, scope: str) -> dict | None:
    try:
        payload = jwt.decode(
            token, get_settings().secret_key, algorithms=["HS256"]
        )
    except jwt.PyJWTError:
        return None
    if not payload.get("stepup"):
        return None
    if payload.get("scope") != scope:
        return None
    return payload


# ----------------------------------------------- device secret encryption
def _fernet():
    global _FERNET
    if _FERNET is None:
        from cryptography.fernet import Fernet

        key = hashlib.sha256(get_settings().secret_key.encode()).digest()
        _FERNET = Fernet(base64.urlsafe_b64encode(key))
    return _FERNET


def encrypt_secret(plain: str) -> str:
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except Exception:  # noqa: BLE001 — token rusak/kunci berubah
        # Jangan diam: password global kamera yang gagal decrypt membuat
        # semua tile 502 "kredensial gagal" tanpa jejak. Log agar admin tahu
        # harus set ulang (kemungkinan SECRET_KEY berubah).
        log.warning("decrypt_secret gagal (token rusak atau SECRET_KEY berubah)")
        return ""
