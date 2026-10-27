"""API Manajemen CCTV: inventory kamera, kredensial, snapshot/stream proxy.

Semua endpoint di router ini dijaga dua lapis:
1. ``require_page_access("cctv")`` — superadmin, atau role admin yang
   diberi izin superadmin.
2. ``require_step_up("cctv")`` — wajib verifikasi ulang password.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.deps import (
    get_current_user,
    require_page_access,
    require_step_up,
)
from ..core.security import encrypt_secret
from ..db.database import get_db
from ..db.models import AccessPoint, APGroup, Camera, CameraCredential, CameraGroup
from ..services import audit, cammon

router = APIRouter(
    prefix="/cameras",
    tags=["cameras"],
    dependencies=[
        Depends(require_page_access("cctv")),
        Depends(require_step_up("cctv")),
    ],
)

# Ringkasan status (read-only) TANPA step-up: cukup JWT + page access "cctv".
# Dipakai tampilan admin — hanya jumlah ON/MATI + daftar IP/merk kamera mati,
# tanpa kredensial atau kontrol apa pun.
view_router = APIRouter(
    prefix="/cameras",
    tags=["cameras"],
    dependencies=[Depends(require_page_access("cctv"))],
)

_CAMERA_VENDOR_HINTS = (
    "hikvision", "ezviz", "dahua", "amcrest", "reolink", "axis",
    "uniview", "unv", "hanwha", "vivotek", "foscam", "xiongmai",
    "bosch", "pelco", "geovision", "tiandy", "xm", "gwell",
)


def _cred_dict(cred: CameraCredential, active_id: int | None) -> dict:
    return {
        "id": cred.id,
        "username": cred.username,
        "order_index": cred.order_index,
        "active": cred.id == active_id,
        "last_ok_at": cred.last_ok_at.isoformat() + "Z" if cred.last_ok_at else None,
    }


def _cam_dict(camera: Camera, group_name: str = "") -> dict:
    return {
        "id": camera.id,
        "name": camera.name,
        "ip": camera.ip,
        "port": camera.port,
        "rtsp_port": camera.rtsp_port,
        "scheme": camera.scheme,
        "channel": camera.channel,
        "protocol": camera.protocol,
        "vendor": camera.vendor,
        "model": camera.model,
        "mac": camera.mac,
        "group_id": camera.group_id,
        "group_name": group_name,
        "snapshot_path": camera.snapshot_path,
        "stream_path": camera.stream_path,
        "source": camera.source,
        "ap_id": camera.ap_id,
        "active_credential_id": camera.active_credential_id,
        "status": camera.status,
        "notes": camera.notes,
        "web_url": cammon.web_url(camera) if camera.ip else "",
        "last_seen": camera.last_seen.isoformat() + "Z" if camera.last_seen else None,
        "credentials": [
            _cred_dict(c, camera.active_credential_id) for c in camera.credentials
        ],
    }


def _group_names(db: Session) -> dict[int, str]:
    return {g.id: g.name for g in db.query(CameraGroup).all()}


# ------------------------------------------------------------- inventory
@router.get("")
def list_cameras(
    q: str = "",
    group_id: int | None = None,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Camera)
    if group_id is not None:
        query = query.filter(Camera.group_id == group_id)
    if q:
        like = f"%{q}%"
        query = query.filter(
            Camera.name.ilike(like)
            | Camera.ip.ilike(like)
            | Camera.vendor.ilike(like)
            | Camera.model.ilike(like)
        )
    cams = query.order_by(Camera.name.asc(), Camera.ip.asc()).all()
    names = _group_names(db)
    return {
        "cameras": [_cam_dict(c, names.get(c.group_id, "")) for c in cams],
        "summary": cammon.status_summary(db),
    }


@view_router.get("/status-overview")
def camera_status_overview(
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ringkasan status untuk tampilan admin (read-only, tanpa step-up)."""
    cams = db.query(Camera).order_by(Camera.name.asc(), Camera.ip.asc()).all()
    offline = [
        {
            "id": c.id,
            "name": c.name,
            "ip": c.ip,
            "vendor": c.vendor or "-",
            "model": c.model or "-",
            "last_seen": c.last_seen.isoformat() + "Z" if c.last_seen else None,
        }
        for c in cams
        if c.status != "ONLINE"
    ]
    return {"summary": cammon.status_summary(db), "offline_cameras": offline}


class CredentialIn(BaseModel):
    id: int | None = None
    username: str = ""
    password: str = ""


class CameraIn(BaseModel):
    name: str = ""
    ip: str = Field(min_length=3, max_length=45)
    port: int = 80
    rtsp_port: int = 554
    scheme: str = "http"
    channel: int = 1
    protocol: str = "http"
    vendor: str = ""
    model: str = ""
    group_id: int | None = None
    snapshot_path: str = ""
    stream_path: str = ""
    notes: str = ""
    credentials: list[CredentialIn] = []


def _validate_scheme(scheme: str) -> str:
    scheme = (scheme or "http").lower()
    if scheme not in ("http", "https"):
        raise HTTPException(400, "scheme harus http atau https")
    return scheme


def _validate_protocol(protocol: str) -> str:
    protocol = (protocol or "http").lower()
    if protocol not in ("http", "rtsp", "onvif"):
        raise HTTPException(400, "protocol harus http, rtsp, atau onvif")
    return protocol


def _replace_credentials(db, camera: Camera, creds: list[CredentialIn]) -> None:
    """Sinkronkan kredensial manual kamera tanpa menghapus password lama.

    Semantik:
    - ``id`` cocok dengan kredensial lama → update username/urutan; password
      kosong berarti PERTAHANKAN password lama (tidak ditampilkan di UI).
    - ``id`` tidak dikirim → dianggap dihapus.
    - baris baru wajib punya username + password; baris kosong diabaikan.
    """
    existing = {
        c.id: c
        for c in db.query(CameraCredential)
        .filter(CameraCredential.camera_id == camera.id)
        .all()
    }
    kept: set[int] = set()

    for idx, item in enumerate(creds):
        username = (item.username or "").strip()
        password = item.password or ""
        old = existing.get(item.id) if item.id else None

        if old is not None:
            if not username and not password:
                # Baris lama dikosongkan user → hapus.
                continue
            old.username = username[:128]
            old.order_index = idx
            if password:
                old.password_enc = encrypt_secret(password)
            kept.add(old.id)
            continue

        if not username or not password:
            continue
        db.add(
            CameraCredential(
                camera_id=camera.id,
                username=username[:128],
                password_enc=encrypt_secret(password),
                order_index=idx,
            )
        )

    for cred_id, obj in existing.items():
        if cred_id in kept:
            continue
        if camera.active_credential_id == cred_id:
            camera.active_credential_id = None
        db.delete(obj)
    db.flush()


@router.post("", status_code=201)
def create_camera(
    body: CameraIn,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.group_id is not None and not db.get(CameraGroup, body.group_id):
        raise HTTPException(400, "Grup tidak ditemukan")
    cam = Camera(
        name=body.name.strip()[:128],
        ip=body.ip.strip(),
        port=body.port or 80,
        rtsp_port=body.rtsp_port or 554,
        scheme=_validate_scheme(body.scheme),
        channel=body.channel or 1,
        protocol=_validate_protocol(body.protocol),
        vendor=body.vendor.strip()[:128],
        model=body.model.strip()[:128],
        group_id=body.group_id,
        snapshot_path=body.snapshot_path.strip(),
        stream_path=body.stream_path.strip(),
        notes=body.notes.strip(),
        source="manual",
    )
    db.add(cam)
    db.flush()
    _replace_credentials(db, cam, body.credentials)
    audit.record(db, username, "CAM_CREATE", f"{cam.name} ({cam.ip})")
    db.commit()
    return {"ok": True, "id": cam.id}


@router.put("/{camera_id}")
def update_camera(
    camera_id: int,
    body: CameraIn,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cam = db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Kamera tidak ditemukan")
    if body.group_id is not None and not db.get(CameraGroup, body.group_id):
        raise HTTPException(400, "Grup tidak ditemukan")
    cam.name = body.name.strip()[:128]
    cam.ip = body.ip.strip()
    cam.port = body.port or 80
    cam.rtsp_port = body.rtsp_port or 554
    cam.scheme = _validate_scheme(body.scheme)
    cam.channel = body.channel or 1
    cam.protocol = _validate_protocol(body.protocol)
    cam.vendor = body.vendor.strip()[:128]
    cam.model = body.model.strip()[:128]
    cam.group_id = body.group_id
    cam.snapshot_path = body.snapshot_path.strip()
    cam.stream_path = body.stream_path.strip()
    cam.notes = body.notes.strip()
    if body.credentials:
        _replace_credentials(db, cam, body.credentials)
    audit.record(db, username, "CAM_EDIT", f"{cam.name} ({cam.ip})")
    db.commit()
    return {"ok": True}


@router.delete("/{camera_id}")
def delete_camera(
    camera_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cam = db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Kamera tidak ditemukan")
    audit.record(db, username, "CAM_DELETE", f"{cam.name} ({cam.ip})")
    db.delete(cam)
    db.commit()
    return {"ok": True}


@router.post("/{camera_id}/test")
def test_camera(
    camera_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Coba login berurutan sekarang juga; kembalikan kredensial yang berhasil."""
    cam = db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Kamera tidak ditemukan")
    result = cammon.resolve_credential(db, cam, force=True)
    ok = result is not None
    audit.record(
        db, username, "CAM_TEST",
        f"{cam.name} ({cam.ip})",
        "SUCCESS" if ok else "FAILED",
    )
    db.commit()
    return {
        "ok": ok,
        "username": result[0] if result else "",
        "message": "Login berhasil" if ok else "Semua kredensial gagal. Coba periksa path snapshot/stream atau set kredensial global yang sesuai.",
    }


@router.get("/{camera_id}/credential-status")
def credential_status(
    camera_id: int,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Diagnosis ringan kenapa tile gagal — tanpa streaming.

    reason: ok | bad_credential | no_credentials | locked | cooldown.
    Dipakai overlay tile agar pesan presisi (mis. "kamera mengunci login"
    vs "password tidak cocok"), karena <img> tidak bisa membaca status HTTP.
    """
    import time as _time

    cam = db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Kamera tidak ditemukan")
    lock_until = cammon._locked_until.get(cam.id, 0)
    if lock_until and _time.time() < lock_until:
        return {
            "ok": False,
            "reason": "locked",
            "retry_in": int(lock_until - _time.time()),
            "message": "Kamera mengunci login sementara (anti-bruteforce). Tunggu sebentar lalu Coba lagi.",
        }
    from ..routers import settings as _settings

    g_un, _ = _settings.get_cctv_global_cam_cred(db)
    has_manual = db.query(CameraCredential).filter(
        CameraCredential.camera_id == cam.id
    ).first() is not None
    if not g_un and not has_manual:
        return {
            "ok": False,
            "reason": "no_credentials",
            "message": "Belum ada kredensial (global maupun manual). Isi manual kredensial kamera ini.",
        }
    result = cammon.resolve_credential(db, cam)
    if result is not None:
        return {"ok": True, "reason": "ok", "username": result[0], "message": "Kredensial cocok."}
    return {
        "ok": False,
        "reason": "bad_credential",
        "message": "Password global tidak cocok — isi kredensial kamera ini secara manual.",
    }


# ------------------------------------------------------------- media proxy
@router.get("/{camera_id}/snapshot")
def camera_snapshot(
    camera_id: int,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cam = db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Kamera tidak ditemukan")
    cred = cammon.resolve_credential(db, cam)
    if cred is None:
        raise HTTPException(502, "Tidak bisa login ke kamera (kredensial gagal)")
    
    # Coba dapatkan dari cache snapshot dulu (TTL 5 detik)
    cached = cammon._snapshot_cache_get(cam.id)
    if cached:
        data, ct = cached
        return Response(
            content=data,
            media_type=ct or "image/jpeg",
            headers={"Cache-Control": "no-store"},
        )
    
    result = cammon.fetch_snapshot(cam, cred[0], cred[1])
    if result is None:
        raise HTTPException(502, "Gagal mengambil snapshot")
    data, content_type = result
    
    # Simpan ke cache in-memory
    cammon._snapshot_cache_set(cam.id, data, content_type)
    
    return Response(
        content=data,
        media_type=content_type or "image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{camera_id}/stream")
def camera_stream(
    camera_id: int,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cam = db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Kamera tidak ditemukan")
    cred = cammon.resolve_credential(db, cam)
    if cred is None:
        raise HTTPException(502, "Tidak bisa login ke kamera (kredensial gagal)")
    if not cammon.acquire_stream_slot():
        raise HTTPException(
            503,
            "Server sibuk: semua slot livestream penuh. "
            "Tutup sebagian live view atau kecilkan jumlah tampil per halaman, lalu coba lagi.",
        )
    target = cammon.stream_target(cam)
    return StreamingResponse(
        cammon.mjpeg_stream(target, cred[0], cred[1]),
        media_type=f"multipart/x-mixed-replace; boundary={cammon.MJPEG_BOUNDARY.decode()}",
    )



@router.post("/{camera_id}/autodetect")
def autodetect_camera(
    camera_id: int,
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deep-scan path snapshot: coba (global, lalu manual) x daftar path luas.

    Tidak lewat resolve_credential — justru untuk kasus resolve gagal karena
    path salah/tebakan vendor meleset. Dipicu manual per kamera dari UI
    (tombol Deteksi), jadi daftar path boleh luas.
    """
    import time as _time

    from ..core.security import decrypt_secret

    cam = db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Kamera tidak ditemukan")
    lock_until = cammon._locked_until.get(cam.id, 0)
    if lock_until and _time.time() < lock_until:
        raise HTTPException(
            502,
            f"Kamera mengunci login sementara (anti-bruteforce, sisa {int(lock_until - _time.time())} dtk). Tunggu lalu ulangi Deteksi.",
        )

    # Kandidat kredensial: global dulu, lalu manual per kamera.
    cred_candidates: list[tuple[str, str, str]] = []
    try:
        from ..routers import settings as _settings

        g_un, g_pw = _settings.get_cctv_global_cam_cred(db)
        if g_un and g_pw:
            cred_candidates.append((g_un, g_pw, "global"))
    except Exception:
        pass
    for cc in sorted(cam.credentials, key=lambda c: c.order_index):
        try:
            cc_pw = decrypt_secret(cc.password_enc)
        except Exception:
            continue
        if cc.username and cc_pw:
            cred_candidates.append((cc.username, cc_pw, f"manual:{cc.username}"))
    if not cred_candidates:
        raise HTTPException(
            502,
            "Belum ada kredensial (global maupun manual). Isi kredensial dulu, baru Deteksi.",
        )

    ch = cam.channel or 1
    candidates_snap = []
    if cam.snapshot_path:
        candidates_snap.append(cam.snapshot_path)
    candidates_snap.extend([
        cammon.default_snapshot_path(cam.vendor, ch),
        cammon.default_snapshot_path((cam.vendor or "").lower(), ch),
        f"/ISAPI/Streaming/channels/{ch}01/picture",
        f"/ISAPI/Streaming/channels/{ch}02/picture",
        f"/cgi-bin/snapshot.cgi?channel={ch}",
        f"/cgi-bin/snapshot.cgi?chn={ch}",
        f"/cgi-bin/api.cgi?cmd=Snap&channel={ch}&rs=snap",
        f"/axis-cgi/jpg/image.cgi?camera={ch}",
        "/snapshot.jpg",
        "/snap.jpg",
        "/img/snapshot.cgi",
        "/image.jpg",
        "/tmpfs/snap.jpg",
        "/tmpfs/auto.jpg",
    ])
    seen = set()
    snap_ok = []
    for un, pw, via in cred_candidates:
        for sp in candidates_snap:
            if sp in seen:
                continue
            seen.add(sp)
            try:
                url = f"{cammon._base(cam)}{sp}"
                resp = cammon._http(url, un, pw, timeout=6)
                if resp is not None:
                    try:
                        ct = resp.headers.get("Content-Type", "")
                        if resp.status_code < 400 and resp.content and len(resp.content) > 50 and (resp.content[:2] == b"\xFF\xD8" or "image" in ct.lower()):
                            snap_ok.append({"path": sp, "content_type": ct, "size": len(resp.content), "via": via})
                            if len(snap_ok) >= 8:
                                break
                    finally:
                        resp.close()
            except Exception:
                pass
        if len(snap_ok) >= 8:
            break
    return {"snapshot_candidates": snap_ok, "tried_credentials": len(cred_candidates)}
# ------------------------------------------------------------- discovery
@router.get("/discoverable")
def discoverable(
    _: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Perangkat Access Point yang kemungkinan kamera & belum diimpor."""
    imported_ap_ids = {
        ap_id
        for (ap_id,) in db.query(Camera.ap_id)
        .filter(Camera.ap_id.isnot(None)).all()
    }
    imported_ips = {
        ip
        for (ip,) in db.query(Camera.ip).all()
        if ip
    }
    # Ambil ID grup AP yang bernama CCTV
    cctv_group_ids = {
        g.id
        for g in db.query(APGroup).all()
        if "cctv" in g.name.lower()
    }

    devices = []
    seen_ips = set()
    for ap in db.query(AccessPoint).order_by(AccessPoint.ip).all():
        if not ap.ip or ap.ip in imported_ips or ap.id in imported_ap_ids or ap.ip in seen_ips:
            continue
        v = (ap.vendor or "").lower()
        seg = (ap.segment or "").lower()
        in_cctv_group = ap.group_id in cctv_group_ids if ap.group_id else False
        looks_cam = (
            in_cctv_group
            or "cctv" in seg
            or any(h in v for h in _CAMERA_VENDOR_HINTS)
        )
        if not looks_cam:
            continue
        seen_ips.add(ap.ip)
        devices.append({
            "ap_id": ap.id,
            "ip": ap.ip,
            "mac": ap.mac,
            "vendor": ap.vendor,
            "model": ap.model,
            "segment": ap.segment,
            "status": ap.status,
            "in_cctv_group": in_cctv_group,
        })
    return {"devices": devices}


class ImportBody(BaseModel):
    ap_ids: list[int] = []
    all_cctv: bool = False


class PortCheckBody(BaseModel):
    camera_ids: list[int] = []


def _create_cctv_cameras_from_aps(db: Session, aps: list[AccessPoint]) -> int:
    """Helper untuk membuat Camera dari AccessPoint dengan deduplikasi ketat."""
    if not aps:
        return 0

    existing_ips = {c.ip for c in db.query(Camera.ip).all() if c.ip}
    existing_ap_ids = {c.ap_id for c in db.query(Camera.ap_id).filter(Camera.ap_id.isnot(None)).all()}

    # Buat atau ambil CameraGroup CCTV agar semua kamera terorganisir
    cam_group = db.query(CameraGroup).filter(CameraGroup.name.ilike("cctv")).first()
    if not cam_group:
        cam_group = CameraGroup(name="CCTV")
        db.add(cam_group)
        db.flush()

    candidates: list[AccessPoint] = []
    seen_candidate_ips: set[str] = set()
    for ap in aps:
        if not ap.ip:
            continue
        if (
            ap.id in existing_ap_ids
            or ap.ip in existing_ips
            or ap.ip in seen_candidate_ips
        ):
            continue
        seen_candidate_ips.add(ap.ip)
        candidates.append(ap)

    if not candidates:
        return 0

    with ThreadPoolExecutor(
        max_workers=min(24, max(4, len(candidates)))
    ) as pool:
        port_map = dict(
            pool.map(
                lambda ap: (ap.id, cammon.probe_ports(ap.ip)),
                candidates,
            )
        )

    reachable = [
        ap
        for ap in candidates
        if any(port_map.get(ap.id, {}).values())
    ]
    if not reachable:
        return 0

    created = 0
    seen_batch_ips = set()
    for ap in reachable:
        if ap.ip in seen_batch_ips:
            continue

        seen_batch_ips.add(ap.ip)
        existing_ips.add(ap.ip)
        if ap.id:
            existing_ap_ids.add(ap.id)

        v = (ap.vendor or "").lower()
        protocol = "http"
        snapshot_path = ""
        stream_path = ""
        vendor_name = ap.vendor.strip()[:128] if ap.vendor else ""

        if "tiandy" in v:
            protocol = "rtsp"
            stream_path = "/live/ch0"
            vendor_name = vendor_name or "Tiandy"
        elif "dahua" in v:
            snapshot_path = "/cgi-bin/snapshot.cgi?channel=1"
            stream_path = "/cam/realmonitor?channel=1&subtype=0"
            vendor_name = vendor_name or "Dahua"
        elif "hikvision" in v:
            snapshot_path = "/ISAPI/Streaming/channels/101/picture"
            stream_path = "/Streaming/Channels/101"
            vendor_name = vendor_name or "Hikvision"
        else:
            # Auto-detect cepat berdasarkan respon web kamera
            import requests as _rq
            is_detected = False
            try:
                r_t = _rq.get(f"http://{ap.ip}/conf/conf.js", timeout=0.6)
                if "tiandy" in r_t.text.lower():
                    protocol = "rtsp"
                    stream_path = "/live/ch0"
                    vendor_name = "Tiandy"
                    is_detected = True
            except Exception:
                pass
            if not is_detected:
                try:
                    r_d = _rq.get(f"http://{ap.ip}/cgi-bin/snapshot.cgi?channel=1", timeout=0.6)
                    if r_d.status_code in [200, 401, 403] and ("digest" in r_d.headers.get("www-authenticate", "").lower() or "dahua" in r_d.text.lower()):
                        snapshot_path = "/cgi-bin/snapshot.cgi?channel=1"
                        stream_path = "/cam/realmonitor?channel=1&subtype=0"
                        vendor_name = "Dahua"
                        is_detected = True
                except Exception:
                    pass
            if not is_detected:
                # Default untuk kamera IP tanpa snapshot: gunakan RTSP /live/ch0
                protocol = "rtsp"
                stream_path = "/live/ch0"

        name = (ap.model or vendor_name or ap.ip or f"Camera {ap.id}").strip()[:128]
        cam = Camera(
            name=name,
            ip=ap.ip.strip(),
            port=80,
            rtsp_port=554,
            scheme="http",
            channel=1,
            protocol=protocol,
            vendor=vendor_name,
            model=ap.model.strip()[:128] if ap.model else "",
            mac=ap.mac.strip() if ap.mac else "",
            group_id=cam_group.id,
            snapshot_path=snapshot_path,
            stream_path=stream_path,
            ap_id=ap.id,
            source="auto",
        )
        db.add(cam)
        created += 1

    return created


@router.post("/import")
def import_cameras(
    body: ImportBody,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.all_cctv:
        # Impor semua dari grup/segmen CCTV
        cctv_group_ids = {g.id for g in db.query(APGroup).all() if "cctv" in g.name.lower()}
        aps = db.query(AccessPoint).filter(
            (AccessPoint.group_id.in_(cctv_group_ids)) | (AccessPoint.segment.ilike("%cctv%"))
        ).all()
    else:
        ids = list(dict.fromkeys(body.ap_ids))
        aps = db.query(AccessPoint).filter(AccessPoint.id.in_(ids)).all() if ids else []

    created = _create_cctv_cameras_from_aps(db, aps)
    audit.record(db, username, "CAM_IMPORT", f"{created} kamera")
    db.commit()

    # Segera perbarui status ping kamera di background
    try:
        import threading
        threading.Thread(target=cammon._monitor_once, daemon=True).start()
    except Exception:
        pass

    return {"ok": True, "created": created}


@router.post("/import-auto-cctv")
def import_auto_cctv(
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Impor otomatis seluruh perangkat yang terdaftar di Grup / Segmen CCTV Access Point."""
    cctv_group_ids = {g.id for g in db.query(APGroup).all() if "cctv" in g.name.lower()}
    aps = db.query(AccessPoint).filter(
        (AccessPoint.group_id.in_(cctv_group_ids)) | (AccessPoint.segment.ilike("%cctv%"))
    ).all()
    created = _create_cctv_cameras_from_aps(db, aps)
    audit.record(db, username, "CAM_IMPORT_AUTO", f"{created} kamera otomatis")
    db.commit()

    try:
        import threading
        threading.Thread(target=cammon._monitor_once, daemon=True).start()
    except Exception:
        pass

    total_cameras = db.query(Camera).count()
    return {"ok": True, "created": created, "total": total_cameras}


@router.post("/port-check")
def check_camera_ports(
    body: PortCheckBody | None = None,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cek port web/RTSP kamera dan sinkronkan status ONLINE/OFFLINE."""
    query = db.query(Camera)
    if body and body.camera_ids:
        ids = list(dict.fromkeys(body.camera_ids))
        query = query.filter(Camera.id.in_(ids))
    cams = query.order_by(Camera.ip.asc()).all()
    if not cams:
        return {
            "checked": 0,
            "open": 0,
            "closed": 0,
            "cameras": [],
        }

    with ThreadPoolExecutor(
        max_workers=min(24, max(4, len(cams)))
    ) as pool:
        checks = dict(
            pool.map(
                lambda cam: (
                    cam.id,
                    cammon.probe_ports(
                        cam.ip, cam.port, cam.rtsp_port
                    ),
                ),
                cams,
            )
        )

    now = datetime.utcnow()
    results = []
    opened = 0
    for cam in cams:
        ports = checks.get(cam.id, {})
        is_open = bool(ports.get("web") or ports.get("rtsp"))
        if is_open:
            opened += 1
            cam.status = "ONLINE"
            cam.last_seen = now
        else:
            cam.status = "OFFLINE"
        results.append(
            {
                "id": cam.id,
                "name": cam.name,
                "ip": cam.ip,
                "web_open": bool(ports.get("web")),
                "rtsp_open": bool(ports.get("rtsp")),
                "open": is_open,
            }
        )

    audit.record(
        db,
        username,
        "CAM_PORT_CHECK",
        f"{opened}/{len(cams)} kamera port terbuka",
    )
    db.commit()
    return {
        "checked": len(cams),
        "open": opened,
        "closed": len(cams) - opened,
        "cameras": results,
    }


# ------------------------------------------------------------- credentials
class CredentialsBody(BaseModel):
    credentials: list[CredentialIn] = []


@router.put("/{camera_id}/credentials")
def set_credentials(
    camera_id: int,
    body: CredentialsBody,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cam = db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(404, "Kamera tidak ditemukan")
    _replace_credentials(db, cam, body.credentials)
    audit.record(
        db, username, "CAM_CREDENTIALS",
        f"{cam.name} ({len(body.credentials)} kredensial)",
    )
    db.commit()
    db.refresh(cam)
    return {
        "ok": True,
        "credentials": [
            _cred_dict(c, cam.active_credential_id) for c in cam.credentials
        ],
    }


# ----------------------------------------------------------------- groups
@router.get("/groups")
def list_groups(_: str = Depends(get_current_user), db: Session = Depends(get_db)):
    counts: dict[int, int] = {}
    for (gid,) in db.query(Camera.group_id).all():
        if gid is not None:
            counts[gid] = counts.get(gid, 0) + 1
    groups = db.query(CameraGroup).order_by(CameraGroup.name).all()
    return {
        "groups": [
            {"id": g.id, "name": g.name, "count": counts.get(g.id, 0)}
            for g in groups
        ]
    }


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


@router.post("/groups", status_code=201)
def add_group(
    body: GroupCreate,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Nama grup kosong")
    if db.query(CameraGroup).filter_by(name=name).first():
        raise HTTPException(409, f"Grup '{name}' sudah ada")
    g = CameraGroup(name=name)
    db.add(g)
    audit.record(db, username, "CAM_GROUP_ADD", name)
    db.commit()
    return {"ok": True, "id": g.id}


@router.delete("/groups/{group_id}")
def delete_group(
    group_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    g = db.get(CameraGroup, group_id)
    if not g:
        raise HTTPException(404, "Grup tidak ditemukan")
    db.query(Camera).filter(Camera.group_id == group_id).update(
        {Camera.group_id: None}
    )
    audit.record(db, username, "CAM_GROUP_DELETE", g.name)
    db.delete(g)
    db.commit()
    return {"ok": True}
