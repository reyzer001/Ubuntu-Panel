"""Manajemen kamera CCTV: login otomatis + proxy snapshot/stream.

Prinsip:
1. Panel login SENDIRI ke kamera memakai daftar kredensial berurutan,
   lalu mem-proxy JPEG/stream ke browser — browser tidak pernah login
   ataupun menerima kredensial kamera.
2. Urutan percobaan: mulai dari kredensial terakhir yang berhasil
   (``Camera.active_credential_id``), lalu sisanya sesuai ``order_index``.
   Berhenti di percobaan pertama yang sukses.
3. Status ONLINE/OFFLINE dari port kamera (tanpa kredensial) agar tidak
   memicu lockout kamera karena salah password berulang.
"""

import logging
import os
import shutil
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import quote

import requests
import urllib3
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from ..core.security import decrypt_secret
from ..db.database import SessionLocal
from ..db.models import Camera, CameraCredential, CameraEvent
from . import telegram

try:
    from ..routers.settings import get_cctv_global_cam_cred as _get_cctv_global_cam_cred
except Exception:  # noqa: BLE001
    def _get_cctv_global_cam_cred(_db) -> tuple[str | None, str | None]:
        return None, None

log = logging.getLogger(__name__)

# kamera sering pakai sertifikat self-signed
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_PING_INTERVAL = int(os.environ.get("CAM_PING_INTERVAL", "60"))
_OFFLINE_AFTER = 3
_miss: dict[int, int] = {}
# Kamera yang sudah pernah dinotifikasikan OFFLINE ke Telegram (cegah spam).
_alerted_offline: set[int] = set()

# cooldown agar satu kamera tidak dihantam berulang saat resolve kredensial
_RESOLVE_COOLDOWN = 30.0
_last_resolve: dict[int, float] = {}
_resolve_lock = threading.Lock()
# cache kredensial berhasil per kamera: camera_id -> (waktu, username, password)
_cred_cache: dict[int, tuple[float, str, str]] = {}
# lockout anti-bruteforce kamera (mis. Dahua RmLock): camera_id -> timestamp buka
_locked_until: dict[int, float] = {}
# Negative cache kredensial global per kamera: camera_id -> (versi_global, gagal_at).
# Kalau password global sudah terbukti salah untuk kamera X, jangan diprobe
# ulang selama _GLOBAL_FAIL_TTL (langsung coba kredensial manual) — mencegah
# lockout anti-bruteforce kamera akibat hantaman global yang salah berulang.
# Versi di-bump setiap kredensial global diubah (lihat bump_global_cred_version),
# sehingga password global baru selalu dicoba lagi ke semua kamera.
_GLOBAL_FAIL_TTL = 60.0
_global_fail: dict[int, tuple[int, float]] = {}
_global_cred_version: int = 0


def bump_global_cred_version() -> int:
    """Naikkan versi kredensial global + bersihkan cache terkait.

    Dipanggil setiap PUT/DELETE /settings/cctv-camera-cred agar password
    baru langsung berlaku (tidak menunggu cooldown) dan negative cache usang.
    """
    global _global_cred_version
    with _resolve_lock:
        _global_cred_version += 1
        _global_fail.clear()
        _cred_cache.clear()
        _failure_cooldown.clear()
        _last_resolve.clear()
        _locked_until.clear()
    return _global_cred_version


def reset_camera_cred_state(camera_id: int) -> None:
    """Bersihkan cache kredensial/cooldown satu kamera.

    Dipanggil setelah kredensial manual diubah agar password baru langsung
    dipakai (tidak menunggu cooldown) dan tile yang gagal segera retry.
    Lockout anti-bruteforce kamera TIDAK dibersihkan demi keamanan.
    """
    with _resolve_lock:
        _cred_cache.pop(camera_id, None)
        _last_resolve.pop(camera_id, None)
        _failure_cooldown.pop(camera_id, None)
        _global_fail.pop(camera_id, None)
    _snapshot_cache.pop(camera_id, None)


# cache snapshot dalam memori (key: camera_id, value: (data, content_type, timestamp))
# Default TTL 2.5 detik untuk cache grid view responsif & ramah CPU
_SNAPSHOT_TTL = float(os.environ.get("CAM_SNAPSHOT_TTL", "2.5"))
_snapshot_cache: dict[int, tuple[bytes, str, float]] = {}
# failure cooldown: camera_id -> timestamp berakhirnya cooldown (30 detak)
# mencegah probe FFmpeg berulang saat kamera offline/gagal
_failure_cooldown: dict[int, float] = {}

# Semaphore batas slot livestream (MJPEG/ffmpeg) bersamaan.
# 24 slot disesuaikan untuk batas 20 tile per halaman + 4 buffer pergantian halaman cepat
# agar CPU i7-4790 (4C/8T) dan RAM tidak over-subscribed.
_STREAM_SLOTS = int(os.environ.get("CAM_STREAM_SLOTS", "24"))
_STREAM_SLOT_TIMEOUT = 10.0
_stream_semaphore = threading.BoundedSemaphore(_STREAM_SLOTS)

# Optimasi FFmpeg untuk grid view ringan (hemat CPU ~65% per stream)
_FFMPEG_SCALE = os.environ.get("CAM_FFMPEG_SCALE", "480:-2")
_FFMPEG_FPS = os.environ.get("CAM_FFMPEG_FPS", "3")
_FFMPEG_Q = os.environ.get("CAM_FFMPEG_Q", "8")


def acquire_stream_slot(timeout: float = _STREAM_SLOT_TIMEOUT) -> bool:
    """Coba ambil 1 slot livestream. Kembalikan False bila penuh."""
    try:
        return _stream_semaphore.acquire(timeout=timeout)
    except Exception:  # noqa: BLE001
        return False


def release_stream_slot() -> None:
    try:
        _stream_semaphore.release()
    except ValueError:  # tidak pernah acquire / sudah di-release
        pass


# ------------------------------------------------------------- URL helpers
def default_snapshot_path(vendor: str, channel: int) -> str:
    v = (vendor or "").lower()
    if "tiandy" in v:
        return "/live/ch0"
    if "hikvision" in v or "ezviz" in v:
        return f"/ISAPI/Streaming/channels/{channel}01/picture"
    if "dahua" in v:
        return f"/cgi-bin/snapshot.cgi?channel={channel}"
    if "reolink" in v:
        return f"/cgi-bin/api.cgi?cmd=Snap&channel={channel}&rs=snap"
    if "axis" in v:
        return f"/axis-cgi/jpg/image.cgi?camera={channel}"
    if "uniview" in v or "unv" in v:
        return f"/cgi-bin/snapshot.cgi?chn={channel}"
    if "amcrest" in v:
        return f"/cgi-bin/snapshot.cgi?channel={channel}"
    return "/snapshot.jpg"


def default_stream_path(vendor: str, channel: int) -> str:
    v = (vendor or "").lower()
    # Gunakan sub-stream (D1/360p) sebagai default untuk efisiensi resource
    # saat grid view — hemat bandwidth ~85% dan CPU ~70% dibanding main stream
    if "tiandy" in v:
        return "/live/ch0"
    if "hikvision" in v or "ezviz" in v:
        # Sub-stream channel 02 untuk menghindari lockout RmLock dan hemat bandwidth
        return f"/Streaming/Channels/{channel}02"
    if "dahua" in v or "amcrest" in v:
        # Sub-stream subtype=1 untuk D1 resolution
        return f"/cam/realmonitor?channel={channel}&subtype=1"
    if "reolink" in v:
        # Sub-stream versi Reolink
        return f"/h264Preview_{channel:02d}_sub"
    if "axis" in v:
        # Axis sub-stream jika tersedia
        return f"/axis-media/media.amp?camera={channel}"
    if "uniview" in v or "unv" in v:
        # Uniview sub-stream layer 1
        return f"/unicast/c{channel}/s1/live"
    return f"/live/ch{channel - 1}"


def rtsp_candidates(vendor: str, channel: int) -> list[str]:
    """Daftar path RTSP kandidat untuk auto-discovery atau fallback."""
    v = (vendor or "").lower()
    cands: list[str] = []
    if "tiandy" in v:
        cands.extend(["/live/ch0", "/video1", "/1/1", "/Streaming/Channels/101"])
    elif "hikvision" in v or "ezviz" in v:
        cands.extend([
            f"/Streaming/Channels/{channel}01",
            f"/Streaming/Channels/{channel}02",
            f"/Streaming/channels/{channel}01",
        ])
    elif "dahua" in v or "amcrest" in v:
        cands.extend([
            f"/cam/realmonitor?channel={channel}&subtype=0",
            f"/cam/realmonitor?channel={channel}&subtype=1",
        ])
    elif "uniview" in v or "unv" in v:
        cands.extend([
            f"/unicast/c{channel}/s0/live",
            f"/media/video{channel}",
        ])
    # Urutan kandidat populer di CCTV jaringan
    cands.extend([
        "/live/ch0",
        f"/cam/realmonitor?channel={channel}&subtype=0",
        f"/Streaming/Channels/{channel}01",
        f"/h264Preview_{channel:02d}_main",
        f"/stream{channel}",
        "/onvif1",
        "/live",
        "/ch0",
        "/video1",
        "/1/1",
        "",
    ])
    # Hapus duplikasi tapi jaga urutan
    return list(dict.fromkeys(cands))


def _base(camera) -> str:
    return f"{camera.scheme}://{camera.ip}:{camera.port}"


def web_url(camera) -> str:
    return f"{_base(camera)}/"


def snapshot_url(camera, username: str = "", password: str = "") -> str:
    path = camera.snapshot_path or default_snapshot_path(camera.vendor, camera.channel)
    return f"{_base(camera)}{path}"


def _is_rtsp(camera) -> bool:
    return camera.protocol == "rtsp" or (camera.stream_path or "").lower().startswith("rtsp")


def rtsp_url(camera, username: str, password: str) -> str:
    path = camera.stream_path or default_stream_path(camera.vendor, camera.channel)
    auth = ""
    if username:
        auth = f"{quote(username, safe='')}:{quote(password, safe='')}@"
    return f"rtsp://{auth}{camera.ip}:{camera.rtsp_port}{path}"


def http_stream_url(camera) -> str:
    path = camera.stream_path or default_stream_path(camera.vendor, camera.channel)
    return f"{_base(camera)}{path}"


def stream_target(camera) -> dict:
    """Snapshot nilai camera jadi dict biasa — aman dipakai setelah sesi DB tutup."""
    return {
        "protocol": camera.protocol,
        "scheme": camera.scheme,
        "ip": camera.ip,
        "port": camera.port,
        "rtsp_port": camera.rtsp_port,
        "vendor": camera.vendor,
        "channel": camera.channel,
        "snapshot_path": camera.snapshot_path,
        "stream_path": camera.stream_path,
    }


def _auths(username: str, password: str):
    return (HTTPDigestAuth(username, password), HTTPBasicAuth(username, password))


# ------------------------------------------------------------- credential
def _http(url: str, username: str, password: str, timeout=4, stream=False, camera_id: int | None = None):
    """GET dengan Digest auth; hanya coba Basic auth jika server meminta Basic.
    Mencegah Dahua lockout akibat salah auth berulang."""
    try:
        # Coba Digest auth terlebih dahulu
        resp = requests.get(
            url, auth=HTTPDigestAuth(username, password), timeout=timeout, stream=stream, verify=False
        )
        if resp.status_code < 400:
            return resp
        # Deteksi Dahua account lockout (RmLock)
        if resp.status_code == 403 and camera_id is not None:
            try:
                txt = resp.text
                if "RmLock" in txt:
                    import re
                    m = re.search(r'"RmLock"\s*:\s*(\d+)', txt)
                    if m:
                        sec = int(m.group(1))
                        _locked_until[camera_id] = time.time() + sec
                        log.warning("Kamera %s terkunci Dahua anti-bruteforce: %s detik", camera_id, sec)
            except Exception:
                pass

        # Cek apakah server secara eksplisit meminta Basic auth
        auth_hdr = resp.headers.get("WWW-Authenticate", "")
        resp.close()

        # Hanya kirim BasicAuth jika server memintanya (misal bukan Digest)
        if "basic" in auth_hdr.lower() and "digest" not in auth_hdr.lower():
            try:
                resp_b = requests.get(
                    url, auth=HTTPBasicAuth(username, password), timeout=timeout, stream=stream, verify=False
                )
                if resp_b.status_code < 400:
                    return resp_b
                resp_b.close()
            except requests.RequestException:
                pass
    except requests.RequestException:
        pass
    return None


def _is_image_like(ct: str | None) -> bool:
    if not ct:
        return False
    c = ct.lower()
    return "image" in c or "jpeg" in c or "jpg" in c or "png" in c or "multipart" in c


def _snapshot_cache_get(camera_id: int) -> tuple[bytes, str] | None:
    """Ambil snapshot dari cache in-memory jika masih valid (TTL default 8 detik)."""
    now = time.time()
    cached = _snapshot_cache.get(camera_id)
    if cached and (now - cached[2]) < _SNAPSHOT_TTL:
        return cached[0], cached[1]
    return None


def _snapshot_cache_set(camera_id: int, data: bytes, content_type: str) -> None:
    """Simpan snapshot ke cache in-memory dengan timestamp."""
    now = time.time()
    # Hapus entry lama jika kamera sudah ada di cache
    _snapshot_cache[camera_id] = (data, content_type, now)
    # Batas maksimum entry cache (mencegah memori melimpah)
    if len(_snapshot_cache) > 200:
        # Hapus entry terlama
        oldest_key = min(_snapshot_cache, key=lambda k: _snapshot_cache[k][2])
        del _snapshot_cache[oldest_key]


def _failure_cooldown_check(camera_id: int) -> bool:
    """Cek dan set failure cooldown untuk kamera. Return True jika masih dalam cooldown."""
    now = time.time()
    cooldown_end = _failure_cooldown.get(camera_id, 0)
    if cooldown_end and now < cooldown_end:
        remaining = int(cooldown_end - now)
        return True  # Masih dalam cooldown, lewati probe
    # Bukan dalam cooldown, reset
    if cooldown_end and now >= cooldown_end:
        _failure_cooldown.pop(camera_id, None)
    return False


def _failure_cooldown_set(camera_id: int, duration: int = 30) -> None:
    """Set failure cooldown untuk kamera."""
    _failure_cooldown[camera_id] = time.time() + duration


def _credential_works(camera, username: str, password: str, db) -> bool:
    """Uji kredensial dengan snapshot (murah); fallback ke RTSP ffmpeg.

    `db` dibutuhkan untuk menyimpan snapshot_path / stream_path yang terbukti benar agar
    tidak perlu probe ulang secara permanen.
    """
    # 0) Cek status lockout Dahua (anti-bruteforce)
    lock_until = _locked_until.get(camera.id, 0)
    if lock_until and time.time() < lock_until:
        remaining = int(lock_until - time.time())
        log.warning("Kamera %s sedang terkunci Dahua (sisa %s dtk), lewati probe.", camera.id, remaining)
        return False

    v_lower = (camera.vendor or "").lower()
    is_tiandy = "tiandy" in v_lower

    # 1) Coba HTTP snapshot jika bukan kamera RTSP murni / Tiandy
    if camera.protocol != "rtsp" and not is_tiandy:
        try:
            candidates_snap = []
            if camera.snapshot_path:
                candidates_snap.append(camera.snapshot_path)
            else:
                candidates_snap.append(default_snapshot_path(camera.vendor, camera.channel))
                # Tambahkan kandidat umum hanya jika snapshot_path belum diset
                candidates_snap.extend([
                    f"/cgi-bin/snapshot.cgi?channel={camera.channel}",
                    f"/ISAPI/Streaming/channels/{camera.channel}01/picture",
                    "/snapshot.jpg",
                ])
            seen = set()
            for sp in candidates_snap:
                if sp in seen:
                    continue
                seen.add(sp)
                url = f"{_base(camera)}{sp}"
                resp = _http(url, username, password, timeout=3, camera_id=camera.id)
                if resp is not None:
                    try:
                        ct = resp.headers.get("Content-Type", "")
                        if resp.status_code < 400 and (_is_image_like(ct) or (resp.content and resp.content[:2] == b"\xff\xd8")):
                            data = resp.content
                            ct_resp = ct
                            # Simpan path snapshot ke database agar tidak perlu probe ulang
                            if not camera.snapshot_path:
                                camera.snapshot_path = sp
                                try:
                                    db.commit()
                                except Exception:  # noqa: BLE001
                                    db.rollback()
                            # Simpan ke cache
                            _snapshot_cache_set(camera.id, data, ct_resp or "image/jpeg")
                            return True
                    finally:
                        resp.close()
                else:
                    # Jika kamera terkunci saat probe, berhenti seketika
                    if _locked_until.get(camera.id, 0) > time.time():
                        return False
        except Exception:
            pass

    # 2) Fallback RTSP via FFmpeg (untuk kamera tanpa HTTP snapshot, mis. Tiandy)
    if shutil.which("ffmpeg"):
        auth = f"{quote(username, safe='')}:{quote(password, safe='')}@" if username else ""
        rtsp_paths = []
        if camera.stream_path:
            rtsp_paths.append(camera.stream_path)
        rtsp_paths.extend(rtsp_candidates(camera.vendor, camera.channel))
        seen_rtsp = set()
        for p in rtsp_paths:
            if p in seen_rtsp:
                continue
            seen_rtsp.add(p)
            url = f"rtsp://{auth}{camera.ip}:{camera.rtsp_port}{p}"
            try:
                proc = subprocess.run(
                    ["ffmpeg", "-loglevel", "error", "-rtsp_transport", "tcp",
                     "-timeout", "2000000", "-i", url, "-t", "1", "-f", "null", "-"],
                    capture_output=True, timeout=3,
                )
                if proc.returncode == 0:
                    # Berhasil terkoneksi via RTSP - simpan ke DB secara permanen!
                    camera.stream_path = p
                    if camera.protocol != "rtsp":
                        camera.protocol = "rtsp"
                    try:
                        db.commit()
                    except Exception:  # noqa: BLE001
                        db.rollback()
                    return True
            except Exception:
                pass

    return False


def _ordered_credentials(db, camera) -> list[CameraCredential]:
    creds = (
        db.query(CameraCredential)
        .filter(CameraCredential.camera_id == camera.id)
        .order_by(CameraCredential.order_index)
        .all()
    )
    if camera.active_credential_id:
        active = [c for c in creds if c.id == camera.active_credential_id]
        rest = [c for c in creds if c.id != camera.active_credential_id]
        return active + rest
    return creds


def resolve_credential(db, camera, force: bool = False) -> tuple[str, str] | None:
    """Coba kredensial berurutan; simpan yang berhasil & kembalikan (user, pass).

    Prioritas: (1) kredensial global kamera (jika diset) — dicoba dulu,
    (2) daftar kredensial per-kamera sesuai urutan.
    Kredensial yang berhasil di-cache selama _RESOLVE_COOLDOWN supaya tidak
    melakukan probe jaringan ulang ke kamera pada setiap request stream.
    """
    # 0) Lewati probe jika kamera OFFLINE atau baru saja gagal (menghemat timeout socket & CPU)
    if not force:
        if camera.status == "OFFLINE":
            return None
        if _failure_cooldown_check(camera.id):
            return None

    # Cache hit: kredensial berhasil ditemukan dalam cooldown → pakai saja.
    # force=True (tombol Tes) wajib memprobe ulang, jadi cache dilewati.
    now = time.time()
    with _resolve_lock:
        cached = _cred_cache.get(camera.id)
        if not force and cached and (now - cached[0]) < _RESOLVE_COOLDOWN:
            return cached[1], cached[2]

    # Cek lockout kamera (mis. Dahua anti-bruteforce)
    lock_until = _locked_until.get(camera.id, 0)
    if lock_until and now < lock_until:
        return None

    # 1) Coba global credential dulu (satu password untuk semua CCTV).
    # Negative cache: bila global versi ini sudah terbukti salah untuk kamera
    # ini, lewati probe global dan langsung coba kredensial manual — hemat
    # request + hindari lockout anti-bruteforce kamera.
    try:
        g_un, g_pw = _get_cctv_global_cam_cred(db)
        if g_un and g_pw:
            with _resolve_lock:
                neg = _global_fail.get(camera.id)
                skip_global = (
                    neg is not None
                    and neg[0] == _global_cred_version
                    and (now - neg[1]) < _GLOBAL_FAIL_TTL
                )
            if not skip_global:
                # Kandidat password global (utamakan huruf kecil pada Dahua agar tidak RmLock)
                v_lower = (camera.vendor or "").lower()
                pw_cands = []
                if "dahua" in v_lower:
                    if g_pw.lower() not in pw_cands:
                        pw_cands.append(g_pw.lower())
                    if g_pw not in pw_cands:
                        pw_cands.append(g_pw)
                else:
                    pw_cands.append(g_pw)
                    if g_pw.lower() != g_pw and g_pw.lower() not in pw_cands:
                        pw_cands.append(g_pw.lower())
                if g_pw.capitalize() != g_pw and g_pw.capitalize() not in pw_cands:
                    pw_cands.append(g_pw.capitalize())

                matched_pw = None
                for cand in pw_cands:
                    if _credential_works(camera, g_un, cand, db):
                        matched_pw = cand
                        break

                if matched_pw:
                    camera.active_credential_id = None
                    db.commit()
                    with _resolve_lock:
                        _last_resolve[camera.id] = time.time()
                        _cred_cache[camera.id] = (time.time(), g_un, matched_pw)
                        _global_fail.pop(camera.id, None)
                    return g_un, matched_pw
                with _resolve_lock:
                    _global_fail[camera.id] = (_global_cred_version, time.time())
    except Exception:  # noqa: BLE001
        pass

    # 2) Coba kredensial per-kamera
    creds = _ordered_credentials(db, camera)
    if not creds:
        with _resolve_lock:
            _last_resolve[camera.id] = time.time()
        return None

    for cred in creds:
        try:
            password = decrypt_secret(cred.password_enc)
        except Exception:  # noqa: BLE001
            continue
        if _credential_works(camera, cred.username, password, db):
            camera.active_credential_id = cred.id
            cred.last_ok_at = datetime.utcnow()
            db.commit()
            with _resolve_lock:
                _last_resolve[camera.id] = time.time()
                _cred_cache[camera.id] = (time.time(), cred.username, password)
            return cred.username, password
    with _resolve_lock:
        _last_resolve[camera.id] = time.time()
        _failure_cooldown_set(camera.id, 20)
    return None


# ------------------------------------------------------------- snapshot
def _is_jpeg(data: bytes) -> bool:
    return len(data) >= 2 and data[0] == 0xFF and data[1] == 0xD8


def fetch_snapshot(camera, username: str, password: str) -> tuple[bytes, str] | None:
    # 1) Coba HTTP snapshot jika bukan protokol murni rtsp
    if camera.protocol != "rtsp":
        candidates = []
        if camera.snapshot_path:
            candidates.append(camera.snapshot_path)
        candidates.append(default_snapshot_path(camera.vendor, camera.channel))
        for v in (camera.vendor or "").lower(), "":
            candidates.append(default_snapshot_path(v, camera.channel))
        seen = set()
        for sp in candidates:
            if sp in seen:
                continue
            seen.add(sp)
            try:
                url = f"{_base(camera)}{sp}"
                resp = _http(url, username, password, timeout=4, camera_id=camera.id)
                if resp is not None:
                    try:
                        ct = resp.headers.get("Content-Type", "image/jpeg")
                        if resp.content and len(resp.content) > 50:
                            if _is_jpeg(resp.content) or _is_image_like(ct) or "multipart" in (ct or "").lower():
                                return resp.content, ct
                    finally:
                        resp.close()
            except Exception:
                pass

    # 2) Fallback RTSP: ambil 1 frame JPEG langsung dari RTSP menggunakan FFmpeg
    if shutil.which("ffmpeg"):
        auth = f"{quote(username, safe='')}:{quote(password, safe='')}@" if username else ""
        paths = []
        if camera.stream_path:
            paths.append(camera.stream_path)
        else:
            paths.extend(rtsp_candidates(camera.vendor, camera.channel))
        for sp in list(dict.fromkeys(paths)):
            url = f"rtsp://{auth}{camera.ip}:{camera.rtsp_port}{sp}"
            try:
                proc = subprocess.run(
                    [
                        "ffmpeg",
                        "-loglevel", "error",
                        "-rtsp_transport", "tcp",
                        "-timeout", "2000000",
                        "-i", url,
                        "-vf", f"scale={_FFMPEG_SCALE}",
                        "-q:v", "7",
                        "-vframes", "1",
                        "-threads", "1",
                        "-f", "image2",
                        "pipe:1",
                    ],
                    capture_output=True,
                    timeout=4,
                )
                if proc.returncode == 0 and len(proc.stdout) > 50 and _is_jpeg(proc.stdout):
                    if not camera.stream_path:
                        camera.stream_path = sp
                    return proc.stdout, "image/jpeg"
            except Exception:
                pass

    return None


# ------------------------------------------------------------- stream
# Boundary standar untuk multipart MJPEG — harus cocok dengan header
# Content-Type di StreamingResponse ("multipart/x-mixed-replace; boundary=frame").
MJPEG_BOUNDARY = b"frame"


def mjpeg_stream(target: dict, username: str, password: str):
    """Generator byte MJPEG (multipart) untuk <img>.

    - Kamera RTSP (Tiandy, Dahua RTSP, dll) → ffmpeg transcode ke MJPEG.
    - Kamera HTTP MJPEG → teruskan byte apa adanya.
    - Fallback: jika RTSP gagal/tidak aktif, gunakan snapshot berulang.
    """
    try:
        is_rtsp = (
            target["protocol"] == "rtsp"
            or (target["stream_path"] or "").lower().startswith("rtsp")
            or "realmonitor" in (target["stream_path"] or "").lower()
            or "/live/" in (target["stream_path"] or "").lower()
            or "streaming/channels" in (target["stream_path"] or "").lower()
        )
        has_yielded = False
        if is_rtsp:
            for chunk in _ffmpeg_mjpeg(target, username, password):
                has_yielded = True
                yield chunk
            if has_yielded:
                return
            # Jika RTSP gagal, langsung fallback ke snapshot streaming (jangan request RTSP via HTTP!)
            yield from _snapshot_stream(target, username, password)
            return

        for chunk in _http_mjpeg(target, username, password):
            has_yielded = True
            yield chunk
        if has_yielded:
            return

        # Fallback snapshot streaming jika stream utama tidak menghasilkan frame
        yield from _snapshot_stream(target, username, password)
    finally:
        release_stream_slot()


def _snapshot_stream(target: dict, username: str, password: str):
    """Streaming menggunakan snapshot berulang jika RTSP / stream tidak tersedia."""
    sp = target["snapshot_path"] or default_snapshot_path(target["vendor"], target["channel"])
    url = f"{target['scheme']}://{target['ip']}:{target['port']}{sp}"
    while True:
        resp = _http(url, username, password, timeout=3)
        if resp is None:
            break
        try:
            data = resp.content
            if data and (len(data) > 50 and data[:2] == b"\xff\xd8"):
                yield (
                    b"--" + MJPEG_BOUNDARY + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(data)).encode() + b"\r\n"
                    b"\r\n" + data + b"\r\n"
                )
        finally:
            resp.close()
        time.sleep(0.5)


def _ffmpeg_mjpeg(target: dict, username: str, password: str):
    """Transcode RTSP → MJPEG via ffmpeg, yield per-frame dengan boundary.

    Dioptimisasi untuk grid view CCTV:
    - Downscale resolusi max 640px untuk menghemat bandwidth
    - Frame rate 5 FPS (cukup mulus untuk multi-tile)
    - Kualitas JPEG -q:v 5 (70% ukuran tanpa penurunan visual nyata)
    - Threads 1 untuk menghindari over-subscription pada host 8 vCPU
    """
    if not shutil.which("ffmpeg"):
        return
    path = target["stream_path"] or default_stream_path(target["vendor"], target["channel"])
    auth = f"{quote(username, safe='')}:{quote(password, safe='')}@" if username else ""
    url = f"rtsp://{auth}{target['ip']}:{target['rtsp_port']}{path}"

    proc = subprocess.Popen(
        [
            "ffmpeg",
            "-loglevel", "error",
            "-rtsp_transport", "tcp",
            "-timeout", "15000000",
            "-fflags", "+genpts",
            "-avoid_negative_ts", "make_zero",
            "-i", url,
            "-an",
            "-vf", f"scale={_FFMPEG_SCALE}",
            "-vcodec", "mjpeg",
            "-q:v", str(_FFMPEG_Q),
            "-r", str(_FFMPEG_FPS),
            "-threads", "1",
            "-f", "image2pipe",
            "pipe:1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        buf = b""
        while True:
            chunk = proc.stdout.read(65536)
            if not chunk:
                break
            buf += chunk
            # Cari JPEG frames: SOI (0xFFD8) dan EOI (0xFFD9)
            while True:
                soi = buf.find(b"\xff\xd8")
                if soi < 0:
                    buf = b""
                    break
                eoi = buf.find(b"\xff\xd9", soi + 2)
                if eoi < 0:
                    # belum lengkap, potong sebelum SOI
                    buf = buf[soi:]
                    break
                # frame JPEG lengkap
                frame = buf[soi:eoi + 2]
                buf = buf[eoi + 2:]
                yield (
                    b"--" + MJPEG_BOUNDARY + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(frame)).encode() + b"\r\n"
                    b"\r\n" + frame + b"\r\n"
                )
    finally:
        try:
            proc.kill()
            proc.wait()  # pastikan proses mati bersih
        except Exception:  # noqa: BLE001
            pass


def _http_mjpeg(target: dict, username: str, password: str):
    """Proxy HTTP MJPEG stream dari kamera, re-frame dengan boundary standar.

    Kamera bisa memakai boundary yang berbeda-beda di Content-Type mereka.
    Kita parse JPEG frame dari raw byte lalu bungkus ulang dengan boundary
    yang konsisten (``MJPEG_BOUNDARY``) agar header response di sisi panel
    selalu cocok.
    """
    path = target["stream_path"] or default_stream_path(target["vendor"], target["channel"])
    url = f"{target['scheme']}://{target['ip']}:{target['port']}{path}"
    resp = _http(url, username, password, timeout=(5, 30), stream=True)
    if resp is None:
        return
    try:
        buf = b""
        for chunk in resp.iter_content(chunk_size=65536):
            if not chunk:
                continue
            buf += chunk
            # Cari JPEG frames: SOI (0xFFD8) dan EOI (0xFFD9)
            while True:
                soi = buf.find(b"\xff\xd8")
                if soi < 0:
                    buf = b""
                    break
                eoi = buf.find(b"\xff\xd9", soi + 2)
                if eoi < 0:
                    buf = buf[soi:]
                    break
                frame = buf[soi:eoi + 2]
                buf = buf[eoi + 2:]
                yield (
                    b"--" + MJPEG_BOUNDARY + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(frame)).encode() + b"\r\n"
                    b"\r\n" + frame + b"\r\n"
                )
    finally:
        resp.close()


# ------------------------------------------------------------- ping monitor
def _ping_host(ip: str) -> bool:
    try:
        return (
            subprocess.run(
                ["ping", "-c", "1", "-W", "2", ip],
                capture_output=True, timeout=4,
            ).returncode == 0
        )
    except Exception:  # noqa: BLE001
        return False


def port_open(ip: str, port: int, timeout: float = 0.35) -> bool:
    if not ip or not port:
        return False
    try:
        with socket.create_connection((ip, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def probe_ports(
    ip: str,
    port: int = 80,
    rtsp_port: int = 554,
    timeout: float = 0.35,
) -> dict:
    return {
        "web": port_open(ip, port, timeout),
        "rtsp": port_open(ip, rtsp_port, timeout),
    }


def _monitor_once() -> dict:
    db = SessionLocal()
    try:
        cams = [
            {
                "id": c.id,
                "ip": c.ip,
                "port": c.port,
                "rtsp_port": c.rtsp_port,
            }
            for c in db.query(
                Camera.id, Camera.ip, Camera.port, Camera.rtsp_port
            ).all()
        ]
    finally:
        db.close()
    if not cams:
        return {"online": 0, "offline": 0}

    workers = min(32, max(4, len(cams)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        alive = {cid for cid, ok in pool.map(
            lambda d: (
                d["id"],
                port_open(d["ip"], d["port"])
                or port_open(d["ip"], d["rtsp_port"]),
            ),
            cams,
        ) if ok}

    now = datetime.utcnow()
    stats = {"online": 0, "offline": 0}
    went_offline: list[dict] = []
    recovered: list[dict] = []
    db = SessionLocal()
    try:
        rows = {c.id: c for c in db.query(Camera).all()}
        for d in cams:
            cam = rows.get(d["id"])
            if cam is None:
                continue
            if cam.id in alive:
                _miss[cam.id] = 0
                cam.last_seen = now
                if cam.status != "ONLINE":
                    cam.status = "ONLINE"
                    stats["online"] += 1
                    db.add(
                        CameraEvent(
                            camera_id=cam.id,
                            ip=cam.ip,
                            name=cam.name,
                            event="ONLINE",
                            timestamp=now,
                        )
                    )
                    if cam.id in _alerted_offline:
                        _alerted_offline.discard(cam.id)
                        recovered.append(
                            {
                                "name": cam.name,
                                "ip": cam.ip,
                                "vendor": cam.vendor,
                            }
                        )
            else:
                n = _miss.get(cam.id, 0) + 1
                _miss[cam.id] = n
                if n >= _OFFLINE_AFTER and cam.status != "OFFLINE":
                    cam.status = "OFFLINE"
                    stats["offline"] += 1
                    db.add(
                        CameraEvent(
                            camera_id=cam.id,
                            ip=cam.ip,
                            name=cam.name,
                            event="OFFLINE",
                            timestamp=now,
                        )
                    )
                    _alerted_offline.add(cam.id)
                    went_offline.append(
                        {
                            "name": cam.name,
                            "ip": cam.ip,
                            "vendor": cam.vendor,
                        }
                    )
        db.commit()
        if went_offline or recovered:
            try:
                telegram.notify_cctv_changes(db, went_offline, recovered)
            except Exception:  # noqa: BLE001
                log.warning("gagal mengirim notifikasi Telegram CCTV", exc_info=True)
        return stats
    finally:
        db.close()


def _monitor_loop(interval: int) -> None:
    while True:
        time.sleep(interval)
        try:
            _monitor_once()
        except Exception:  # noqa: BLE001
            log.warning("camera monitor cycle failed", exc_info=True)


def start_monitor() -> None:
    threading.Thread(
        target=_monitor_loop, args=(_PING_INTERVAL,),
        daemon=True, name="cam-ping-monitor",
    ).start()
    # isi status awal tanpa menunggu interval pertama
    threading.Thread(target=_monitor_once, daemon=True, name="cam-monitor-init").start()


# ------------------------------------------------------------- status
def status_summary(db) -> dict:
    cams = db.query(Camera).all()
    return {
        "total": len(cams),
        "online": sum(1 for c in cams if c.status == "ONLINE"),
        "offline": sum(1 for c in cams if c.status == "OFFLINE"),
        "ping_interval": _PING_INTERVAL,
        "offline_after": _OFFLINE_AFTER,
    }
