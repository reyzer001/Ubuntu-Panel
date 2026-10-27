"""Notifikasi Telegram untuk event panel (saat ini alert CCTV).

Konfigurasi disimpan di ``AppSetting`` supaya tidak perlu migrasi schema:
- ``telegram_enabled``      : "1" / "0"
- ``telegram_bot_token_enc``: bot token terenkripsi (Fernet)
- ``telegram_chat_id``      : id chat/grup tujuan

Pengiriman dilakukan di daemon thread agar monitor ping CCTV tidak pernah
tertahan oleh timeout jaringan Telegram.
"""

import logging
import threading
from datetime import datetime

import requests
from sqlalchemy.orm import Session

from ..core.security import decrypt_secret, encrypt_secret
from ..db.models import AppSetting

log = logging.getLogger(__name__)

TELEGRAM_ENABLED_KEY = "telegram_enabled"
TELEGRAM_BOT_TOKEN_KEY = "telegram_bot_token_enc"
TELEGRAM_CHAT_ID_KEY = "telegram_chat_id"

_API_TIMEOUT = 8


def _row(db: Session, key: str) -> AppSetting | None:
    return db.query(AppSetting).filter(AppSetting.key == key).first()


def _raw(db: Session, key: str) -> str:
    row = _row(db, key)
    return (row.value_enc or "") if row is not None else ""


def _set(db: Session, key: str, value: str) -> None:
    row = _row(db, key)
    if row is None:
        db.add(AppSetting(key=key, value_enc=value))
    else:
        row.value_enc = value
        row.updated_at = datetime.utcnow()


def get_config(db: Session) -> dict:
    """Ambil konfigurasi Telegram (token didekripsi untuk pemakaian internal)."""
    enabled = _raw(db, TELEGRAM_ENABLED_KEY) == "1"
    chat_id = _raw(db, TELEGRAM_CHAT_ID_KEY).strip()
    token_enc = _raw(db, TELEGRAM_BOT_TOKEN_KEY)
    token = ""
    corrupt = False
    if token_enc:
        try:
            token = decrypt_secret(token_enc)
            corrupt = not bool(token)
        except Exception:  # noqa: BLE001
            corrupt = True
    return {
        "enabled": enabled,
        "bot_token": token,
        "chat_id": chat_id,
        "token_set": bool(token_enc),
        "corrupt": corrupt,
        "ready": bool(enabled and token and chat_id),
    }


def public_config(db: Session) -> dict:
    """Konfigurasi aman untuk dikirim ke frontend (tanpa token)."""
    cfg = get_config(db)
    return {
        "enabled": bool(cfg["enabled"]),
        "chat_id": cfg["chat_id"],
        "token_set": cfg["token_set"],
        "corrupt": cfg["corrupt"],
        "ready": bool(cfg["ready"]),
    }


def save_config(
    db: Session,
    *,
    enabled: bool,
    bot_token: str = "",
    chat_id: str = "",
    actor: str = "",
) -> dict:
    """Simpan konfigurasi. Token kosong berarti pertahankan token lama."""
    chat_id = (chat_id or "").strip()
    token = (bot_token or "").strip()

    if enabled:
        existing_token = get_config(db)["bot_token"]
        if not token and not existing_token:
            raise ValueError("Bot token wajib diisi untuk mengaktifkan Telegram")
        if not chat_id:
            raise ValueError("Chat ID wajib diisi untuk mengaktifkan Telegram")

    if token:
        enc = encrypt_secret(token)
        if not enc or decrypt_secret(enc) != token:
            raise ValueError("Gagal menyimpan bot token (enkripsi tidak valid)")
        _set(db, TELEGRAM_BOT_TOKEN_KEY, enc)
    _set(db, TELEGRAM_CHAT_ID_KEY, chat_id)
    _set(db, TELEGRAM_ENABLED_KEY, "1" if enabled else "0")

    if actor:
        from . import audit

        audit.record(
            db,
            actor,
            "TELEGRAM_CONFIG_SET",
            f"enabled={bool(enabled)} chat_id={chat_id}",
        )
    db.commit()
    return public_config(db)


def clear_config(db: Session, *, actor: str = "") -> None:
    for key in (
        TELEGRAM_ENABLED_KEY,
        TELEGRAM_BOT_TOKEN_KEY,
        TELEGRAM_CHAT_ID_KEY,
    ):
        row = _row(db, key)
        if row is not None:
            db.delete(row)
    if actor:
        from . import audit

        audit.record(db, actor, "TELEGRAM_CONFIG_CLEAR", "")
    db.commit()


def send_message(
    bot_token: str, chat_id: str, text: str, timeout: int = _API_TIMEOUT
) -> tuple[bool, str]:
    """Kirim pesan teks. Return (ok, error_message)."""
    if not bot_token or not chat_id or not (text or "").strip():
        return False, "Konfigurasi Telegram belum lengkap"
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    resp = None
    try:
        resp = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": text[:4096],
                "disable_web_page_preview": "true",
            },
            timeout=timeout,
        )
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        if resp.status_code < 400 and payload.get("ok"):
            return True, ""
        detail = (
            payload.get("description")
            or f"HTTP {resp.status_code}"
        )
        return False, str(detail)
    except requests.RequestException as exc:
        return False, f"Koneksi Telegram gagal: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Gagal mengirim Telegram: {exc}"
    finally:
        if resp is not None:
            try:
                resp.close()
            except Exception:  # noqa: BLE001
                pass


def send_message_async(bot_token: str, chat_id: str, text: str) -> None:
    def _worker() -> None:
        ok, err = send_message(bot_token, chat_id, text)
        if not ok:
            log.warning("telegram send failed: %s", err)

    threading.Thread(
        target=_worker, daemon=True, name="telegram-send"
    ).start()


def notify_cctv_changes(
    db: Session,
    offline: list[dict] | None = None,
    recovered: list[dict] | None = None,
) -> None:
    """Kirim ringkasan perubahan status kamera ke Telegram (jika aktif)."""
    offline = offline or []
    recovered = recovered or []
    if not offline and not recovered:
        return
    cfg = get_config(db)
    if not cfg["ready"]:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if offline:
        lines = [
            f"[CCTV OFFLINE] {len(offline)} kamera tidak terhubung",
        ]
        for cam in offline:
            name = cam.get("name") or "-"
            ip = cam.get("ip") or "-"
            vendor = cam.get("vendor") or "-"
            lines.append(f"- {name} ({ip}) - {vendor}")
        lines.append(f"Waktu: {now}")
        send_message_async(cfg["bot_token"], cfg["chat_id"], "\n".join(lines))

    if recovered:
        lines = [
            f"[CCTV ONLINE] {len(recovered)} kamera kembali terhubung",
        ]
        for cam in recovered:
            name = cam.get("name") or "-"
            ip = cam.get("ip") or "-"
            lines.append(f"- {name} ({ip})")
        lines.append(f"Waktu: {now}")
        send_message_async(cfg["bot_token"], cfg["chat_id"], "\n".join(lines))
