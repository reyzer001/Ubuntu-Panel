import ipaddress
import json
import logging
import os
import re
import secrets
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError, TimeoutError

from ..core.deps import get_current_role, get_current_user, require_write
from ..core.config import get_settings
from ..db.database import get_db
from ..db.models import (
    APScanTarget,
    AccessPoint,
    ManagedComputer,
    SharedPrinter,
    User,
    UserComputerAccess,
)
from ..services.audit import record
from ..services.apmon import oui_vendor
from ..services import computer_metrics
from ..services import topology as topology_svc

log = logging.getLogger(__name__)

router = APIRouter(prefix="/computers", tags=["computers"])

AGENT_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent.parent / "agent" / "panel_agent.py"
)
HEARTBEAT_INTERVAL = 10          # detik antar heartbeat dari agent
OFFLINE_AFTER = HEARTBEAT_INTERVAL * 3 + 10   # dianggap offline jika lebih lama
# Perintah yang tidak terambil agent (PC offline) dibersihkan otomatis setelah
# selang ini agar tidak menggantung "waiting" selamanya di UI. Set 0 untuk menonaktifkan.
PENDING_EXPIRY_SECONDS = int(os.getenv("PENDING_EXPIRY_SECONDS", "86400"))
SOFTWARE_CATALOG = {
    "7zip": {"name": "7-Zip", "windows": "7zip.7zip", "linux": "p7zip-full"},
    "vlc": {"name": "VLC", "windows": "VideoLAN.VLC", "linux": "vlc"},
    "notepad-plus-plus": {"name": "Notepad++", "windows": "Notepad++.Notepad++", "linux": "notepadqq"},
    "google-chrome": {"name": "Google Chrome", "windows": "Google.Chrome", "linux": "google-chrome-stable"},
}

# Prefix perintah yang boleh dikirim ke agent lewat heartbeat (selain
# restart/shutdown/update/cleanup-nodelete). Daftar ini juga dipakai agent
# untuk parsing.
COMMAND_PREFIXES = ("install:", "share-printer:", "unshare-printer:")

# Perintah fixed tanpa parameter path bebas: hapus sisa rollout lama
# C:\nodelete + varian user-mode legacy. Whitelist path ada di agent
# (do_cleanup_nodelete) — server hanya mengirim nama perintah ini.
CLEANUP_CMD = "cleanup-nodelete"
AGENT_COMMANDS = ("restart", "shutdown", "update", CLEANUP_CMD)


class CreateBody(BaseModel):
    name: str = ""


def _expire_stale_commands(db: Session, user: str = "system") -> None:
    """Bersihkan perintah yang menggantung terlalu lama karena agent tidak online,
    agar status "waiting" tidak muncul selamanya di UI."""
    if PENDING_EXPIRY_SECONDS <= 0:
        return
    cutoff = datetime.utcnow() - timedelta(seconds=PENDING_EXPIRY_SECONDS)
    stale = (
        db.query(ManagedComputer)
        .filter(
            ManagedComputer.pending_cmd.isnot(None),
            ManagedComputer.cmd_issued_at.isnot(None),
            ManagedComputer.cmd_issued_at < cutoff,
        )
        .all()
    )
    for c in stale:
        record(
            db,
            user,
            "COMPUTER_CMD_EXPIRED",
            f"{c.name or c.id}: {c.pending_cmd}",
            "EXPIRED",
        )
        c.pending_cmd = None
        c.cmd_issued_at = None
    if stale:
        db.commit()
        log.info("expired %d stale pending command(s)", len(stale))


def _user_allowed_computer_ids(
    db: Session, username: str, role: str
) -> set[int] | None:
    """Set komputer yang boleh dikelola seorang user; None = semua (bebas).

    Aturan:
      - superadmin → bebas kelola SEMUA komputer (None).
      - admin/viewer → hanya komputer yang terdaftar di `computer_access`.
        Daftar kosong (belum diberi akses apa pun) → tidak boleh mengelola
        komputer mana pun.
      - user bukan panel (username tidak ada di users) → tidak boleh apa pun.
    """
    if role == "superadmin":
        return None
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        return set()
    return {
        row.computer_id
        for row in db.query(
            UserComputerAccess.computer_id
        )
        .filter(UserComputerAccess.user_id == user.id)
        .all()
    }


def _assert_can_manage(
    db: Session, username: str, role: str, computer: ManagedComputer
) -> None:
    """403 bila user tidak berhak mengelola komputer tertentu.

    Lewat untuk superadmin / user tanpa catatan akses (bebas). Ditolak bila
    komputer tidak ada di daftar `computer_access` user.
    """
    if role == "superadmin":
        return
    allowed = _user_allowed_computer_ids(db, username, role)
    if allowed is None or computer.id in allowed:
        return
    raise HTTPException(
        status_code=403,
        detail="Anda tidak memiliki akses untuk mengelola komputer ini",
    )


def _assert_can_manage_many(
    db: Session, username: str, role: str, computers: list[ManagedComputer]
) -> None:
    """403 bila ada komputer di daftar yang tidak boleh dikelola user."""
    if role == "superadmin":
        return
    allowed = _user_allowed_computer_ids(db, username, role)
    if allowed is None:
        return
    denied = [c for c in computers if c.id not in allowed]
    if denied:
        raise HTTPException(
            status_code=403,
            detail=(
                "Anda tidak memiliki akses untuk mengelola komputer: "
                + ", ".join(c.name or str(c.id) for c in denied)
            ),
        )


def _serialize(c: ManagedComputer) -> dict:
    heartbeat_age = (
        round((datetime.utcnow() - c.last_seen).total_seconds(), 1)
        if c.last_seen
        else None
    )
    hb_online = heartbeat_age is not None and heartbeat_age <= OFFLINE_AFTER
    # Bukti online dari topologi (cocok IP perangkat ONLINE di Access Point).
    ap_age = (
        round((datetime.utcnow() - c.ap_seen_at).total_seconds(), 1)
        if c.ap_seen_at
        else None
    )
    ap_online = ap_age is not None and ap_age <= topology_svc.evidence_ttl()
    online = hb_online or ap_online
    if hb_online and ap_online:
        online_source = "both"
    elif ap_online:
        online_source = "ap"
    elif hb_online:
        online_source = "heartbeat"
    else:
        online_source = "none"
    try:
        interfaces = json.loads(c.interfaces or "[]")
    except ValueError:
        interfaces = []
    return {
        "id": c.id,
        "name": c.name or c.hostname,
        "group_name": c.group_name or "",
        "hostname": c.hostname,
        "ip": c.ip,
        "mac": c.mac,
        "merk": oui_vendor(c.mac),
        "os_info": c.os_info,
        "interfaces": interfaces,
        "cpu": c.cpu,
        "mem": c.mem,
        # Nilai ini berasal dari heartbeat terakhir. Jangan tampilkan sebagai
        # data live setelah komputer melewati batas offline.
        "internet_up": c.internet_up if online else None,
        "latency_ms": c.latency_ms if online else None,
        "download_mbps": c.download_mbps if online else None,
        "upload_mbps": c.upload_mbps if online else None,
        "speed_test_at": c.speed_test_at.strftime("%Y-%m-%d %H:%M:%S") if c.speed_test_at else None,
        "agent_version": c.agent_version,
        "autostart_mode": c.autostart_mode,
        "smb_open": c.smb_open if online else None,
        "conn_type": c.conn_type,
        "ssid": c.ssid,
        "iface_name": c.iface_name,
        "wifi_ip": c.wifi_ip,
        "ap_ip": c.ap_ip,
        "ap_mac": c.ap_mac,
        "latency_srv_ms": c.latency_srv_ms if online else None,
        "server_reach": c.server_reach,
        "pending_cmd": c.pending_cmd,
        "cmd_issued_at": (
            c.cmd_issued_at.strftime("%d/%m %H:%M") if c.cmd_issued_at else None
        ),
        "last_cmd_result": c.last_cmd_result,
        # ONLINE | OFFLINE | WAITING (belum pernah heartbeat / belum terdeteksi)
        "status": "online" if online else ("offline" if c.last_seen else "waiting"),
        "online_source": online_source,
        "ap_seen_at": c.ap_seen_at.strftime("%Y-%m-%d %H:%M:%S") if c.ap_seen_at else None,
        "heartbeat_age": heartbeat_age,
        "last_seen": c.last_seen.strftime("%Y-%m-%d %H:%M:%S") if c.last_seen else None,
        "created_at": c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "",
    }


@router.get("")
def list_computers(_: str = Depends(get_current_user), db: Session = Depends(get_db)):
    _expire_stale_commands(db)
    rows = db.query(ManagedComputer).order_by(ManagedComputer.id).all()
    return {"computers": [_serialize(c) for c in rows], "interval": HEARTBEAT_INTERVAL}


@router.get("/software/catalog")
def software_catalog(_: str = Depends(get_current_user)):
    return {"software": [{"id": key, **value} for key, value in SOFTWARE_CATALOG.items()]}


@router.post("", dependencies=[Depends(require_write)])
def create_computer(
    body: CreateBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token = "pca_" + secrets.token_hex(16)
    c = ManagedComputer(name=body.name.strip()[:128], token=token)
    db.add(c)
    db.commit()
    record(db, user, "COMPUTER_ADD", body.name.strip(), "SUCCESS")
    db.commit()
    return {"success": True, "computer": _serialize(c), "token": token}


@router.delete("/{computer_id}", dependencies=[Depends(require_write)])
def delete_computer(
    computer_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    c = db.query(ManagedComputer).filter(ManagedComputer.id == computer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Komputer tidak ditemukan")
    record(db, user, "COMPUTER_DELETE", c.name or str(c.id), "SUCCESS")
    db.delete(c)
    db.commit()
    return {"success": True}


class RenameBody(BaseModel):
    name: str | None = None
    group_name: str | None = None


@router.patch("/{computer_id}", dependencies=[Depends(require_write)])
def rename_computer(
    computer_id: int,
    body: RenameBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ganti nama komputer — berguna untuk entri hasil auto-register
    yang namanya otomatis diambil dari hostname PC."""
    c = db.query(ManagedComputer).filter(ManagedComputer.id == computer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Komputer tidak ditemukan")
    if body.name is None and body.group_name is None:
        raise HTTPException(status_code=400, detail="Tidak ada perubahan")
    if body.name is not None:
        name = body.name.strip()[:128]
        if not name:
            raise HTTPException(status_code=400, detail="Nama tidak boleh kosong")
        old = c.name
        c.name = name
        record(db, user, "COMPUTER_RENAME", f"{old} -> {name}", "SUCCESS")
    if body.group_name is not None:
        group_name = body.group_name.strip()[:64]
        old_group = c.group_name or "Tanpa grup"
        c.group_name = group_name
        record(db, user, "COMPUTER_GROUP", f"{old_group} -> {group_name or 'Tanpa grup'}", "SUCCESS")
    db.commit()
    return {"success": True, "computer": _serialize(c)}


# ------------------------------------------------------------------ agent

def _client_is_lan(request: Request) -> bool:
    """Auto-register hanya dari jaringan privat/LAN/VPN — publik ditolak.

    Hanya percaya alamat koneksi langsung (request.client.host). Header
    X-Forwarded-For tidak dipakai karena backend tidak berada di belakang
    trusted proxy — header itu bisa dipalsukan dari jaringan publik.
    """
    client_ip = getattr(request.client, "host", "") if request.client else ""
    try:
        ip = ipaddress.ip_address(client_ip)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or (ip in ipaddress.ip_network("100.64.0.0/10"))
        )
    except (ValueError, AttributeError):
        return False


def _detect_server_reach(db: Session, pc_ip: str, ap_mac: str, ap_ip: str) -> str:
    """Deteksi jalur koneksi PC → server: LAN atau INTERNET.

    Logika:
      1. PC IP masuk ke salah satu subnet target scan → LAN
      2. PC ap_mac cocok dengan AccessPoint yang dikenal → LAN
      3. PC ap_ip cocok dengan AccessPoint.ip → LAN
      4. PC IP adalah IP privat & server juga di IP privat → LAN (heuristik)
      5. Selain itu → INTERNET
    """
    if not pc_ip:
        return ""
    try:
        pc_addr = ipaddress.ip_address(pc_ip)
    except ValueError:
        return ""

    # 1. cek apakah PC IP masuk ke subnet yang di-scan server
    try:
        targets = [
            t.cidr for t in db.query(APScanTarget.cidr).all()
        ]
        for cidr in targets:
            try:
                net = ipaddress.ip_network(cidr.strip(), strict=False)
                if pc_addr in net:
                    return "LAN"
            except ValueError:
                continue
    except Exception:
        pass

    # 2. cek apakah ap_mac dikenal di inventory AP
    if ap_mac:
        try:
            ap = db.query(AccessPoint).filter(
                AccessPoint.mac.ilike(ap_mac.strip())
            ).first()
            if ap:
                return "LAN"
        except Exception:
            pass

    # 3. cek apakah ap_ip dikenal di inventory AP
    if ap_ip:
        try:
            ap = db.query(AccessPoint).filter(AccessPoint.ip == ap_ip.strip()).first()
            if ap:
                return "LAN"
        except Exception:
            pass

    # 4. heuristik: keduanya IP privat → kemungkinan besar LAN
    if pc_addr.is_private:
        return "LAN"

    return "INTERNET"


class RegisterBody(BaseModel):
    hostname: str = ""
    mac: str = ""
    ip: str = ""
    os_info: str = ""
    agent_version: str = ""


def _new_computer_with_unique_name(db: Session, hostname: str) -> ManagedComputer:
    name, n = hostname[:128], 2
    while db.query(ManagedComputer).filter(ManagedComputer.name == name).first():
        name = f"{hostname[:120]}-{n}"[:128]
        n += 1
    return ManagedComputer(name=name, token="pca_" + secrets.token_hex(16))


def _upsert_by_mac(
    db: Session,
    hostname: str,
    mac: str,
    ip: str = "",
    os_info: str = "",
    agent_version: str = "",
) -> tuple[ManagedComputer, bool]:
    """Cari entri komputer berdasar MAC address; buat baru bila belum ada.

    Balik (komputer, apakah_entri_baru). Identitas MAC membuat agent
    yang sama selalu dikenali walau token lokalnya hilang/basi.
    """
    c = None
    if mac:
        c = db.query(ManagedComputer).filter(ManagedComputer.mac == mac).first()
    created = False
    if c is None:
        # Cek apakah ada entri komputer yang belum terisi MAC dengan nama sama (mis. dibuat manual dari panel)
        if hostname:
            c = (
                db.query(ManagedComputer)
                .filter(
                    (ManagedComputer.mac == None) | (ManagedComputer.mac == ""),
                    ManagedComputer.name.ilike(hostname.strip()[:128]),
                )
                .first()
            )
    if c is None:
        created = True
        c = _new_computer_with_unique_name(db, hostname)
    # `or ""` membela terhadap kolom lama yang masih NULL di database
    c.hostname = (hostname or c.hostname or "")[:128]
    c.mac = mac or c.mac or ""
    c.ip = (ip or c.ip or "")[:45]
    c.os_info = (os_info or c.os_info or "")[:256]
    c.agent_version = (agent_version or c.agent_version or "")[:32]
    if created:
        db.add(c)
        record(db, "agent", "COMPUTER_AUTO_REGISTER", c.name, "NEW")
    else:
        record(db, "agent", "COMPUTER_AUTO_REGISTER", c.name, "REBIND")
    db.commit()
    return c, created


@router.post("/register")
def auto_register(
    body: RegisterBody,
    request: Request,
    db: Session = Depends(get_db),
):
    """Zero-config: PC klien mendaftar sendiri, identitas = MAC address.

    Belum ada → entri baru (nama = hostname). Sudah ada → token lama
    dikirim ulang (re-bind, mis. setelah instalasi ulang agent).
    Hanya diizinkan dari jaringan privat/LAN.
    """
    if not _client_is_lan(request):
        raise HTTPException(
            403, "auto-register hanya untuk jaringan LAN/privat"
        )
    hostname = body.hostname.strip()[:128]
    mac = body.mac.strip()[:128]
    if not hostname or not mac:
        raise HTTPException(400, "hostname dan mac wajib")

    c, created = _upsert_by_mac(
        db, hostname, mac, body.ip.strip(), body.os_info.strip(),
        body.agent_version.strip(),
    )
    return {
        "success": True,
        "registered": created,
        "computer": _serialize(c),
        "token": c.token,
    }


def _agent_computer(
    x_agent_token: str = Header(default=""),
    db: Session = Depends(get_db),
) -> ManagedComputer:
    if not x_agent_token:
        raise HTTPException(status_code=401, detail="Agent token required")
    c = (
        db.query(ManagedComputer)
        .filter(ManagedComputer.token == x_agent_token)
        .first()
    )
    if not c:
        raise HTTPException(status_code=401, detail="Unknown agent token")
    return c


class HeartbeatBody(BaseModel):
    hostname: str = ""
    ip: str = ""
    mac: str = ""
    os_info: str = ""
    interfaces: list[dict] = []
    local_arp: list[dict] = []
    printers: list[dict] = []
    cpu: float | None = None
    mem: float | None = None
    internet_up: bool | None = None
    latency_ms: float | None = None
    download_mbps: float | None = None
    upload_mbps: float | None = None
    speed_test_at: str = ""
    speed_test_source: str = ""
    net_rx_bytes: float | None = None
    net_tx_bytes: float | None = None
    net_seconds: float | None = None
    agent_version: str = ""
    autostart_mode: str = ""  # task-scheduler+hklm-run+common-startup | hkcu-run | system
    smb_open: bool | None = None
    conn_type: str = ""      # LAN | WIFI
    ssid: str = ""
    iface_name: str = ""
    wifi_ip: str = ""
    ap_ip: str = ""
    ap_mac: str = ""


def _ping_host(ip: str) -> float | None:
    """Ping server→PC (1 paket ICMP). Balik ms, None jika gagal/tak bisa."""
    if not ip:
        return None
    t0 = time.monotonic()
    cmds = [
        ["ping", "-c", "1", "-W", "2", ip],      # linux/macos
        ["ping", "-n", "1", "-w", "2000", ip],   # windows
    ]
    for cmd in cmds:
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=5)
        except FileNotFoundError:
            continue          # flag OS lain — coba varian berikutnya
        except Exception:
            return None
        if r.returncode == 0:
            return round((time.monotonic() - t0) * 1000, 1)
        return None           # tool ada tapi host tak merespons
    return None


def _ip_neigh(ip: str) -> tuple[str | None, str | None]:
    """Ambil (lladdr, state) sebuah IP dari tabel `ip neigh` (Linux).

    lladdr ada ⇒ host pernah/telah membalas ARP di L2 — bukti PC menyala
    sekalipun ICMP diblokir firewall. Berbeda-format tetap dinormalisasi."""
    try:
        out = subprocess.run(
            ["ip", "neigh", "show", ip], capture_output=True, text=True, timeout=3
        ).stdout
    except Exception:
        return None, None
    parts = out.split()
    lladdr: str | None = None
    state: str | None = None
    if "lladdr" in parts:
        i = parts.index("lladdr")
        if i + 1 < len(parts):
            lladdr = parts[i + 1]
    for p in parts:
        if p in ("REACHABLE", "STALE", "DELAY", "PROBE", "INCOMPLETE", "FAILED", "PERMANENT", "NOARP"):
            state = p
    return lladdr, state


def _normalize_mac(mac: str) -> str:
    """'98-BD-80-39-93-29' / '98:bd:80:39:93:29' -> '98bd80399329'."""
    return re.sub(r"[^0-9a-fA-F]", "", mac or "").lower()


def _process_local_arp(db: Session, local_arp: list[dict]) -> None:
    """Perbarui MAC address asli dan vendor untuk perangkat di subnet
    yang sebelumnya hanya terdeteksi via IP (ip-xxx) oleh server lintas VLAN/subnet."""
    if not local_arp:
        return
    claimed_macs: set[str] = set()
    for item in local_arp:
        ip = str(item.get("ip", "")).strip()
        mac = str(item.get("mac", "")).strip().lower()
        if not ip or not mac or mac.count(":") != 5:
            continue
        if mac in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"):
            continue
        # Satu MAC tidak boleh dipasang ke lebih dari satu row AP.
        if mac in claimed_macs:
            continue

        ap = (
            db.query(AccessPoint)
            .filter((AccessPoint.ip == ip) & (AccessPoint.mac.like("ip-%")))
            .first()
        )
        if ap:
            existing_mac = (
                db.query(AccessPoint)
                .filter(AccessPoint.mac == mac, AccessPoint.id != ap.id)
                .first()
            )
            if not existing_mac:
                claimed_macs.add(mac)
                ap.mac = mac
                if not ap.vendor:
                    from ..services.apmon import _classify, oui_vendor
                    ap.vendor = oui_vendor(mac)
                    is_ap, model = _classify(ap.vendor, "")
                    if is_ap:
                        ap.is_ap = True
                    if model and not ap.model:
                        ap.model = model


def _ap_rename_wifi(
    db: Session,
    computer: ManagedComputer,
    local_arp: list[dict] | None = None,
) -> bool:
    """Cocokkan BSSID radio AP komputer dengan inventory Access Point.

    Pencarian IP AP:
    1. BSSID radio cocok persis di inventory AccessPoint.
    2. BSSID radio (atau prefix MAC vendor AP) cocok di tabel ARP lokal PC klien.
    3. Prefix MAC 5-oktet cocok di database (banyak vendor AP membagi MAC port ethernet
       dan radio secara berurutan pada 5 oktet pertama, mis. c4:b2:5b:2d:1c:xx).

    PENTING: Default Gateway jaringan TIDAK otomatis di-rename agar tidak menimpa
    router pusat.
    """
    if computer.conn_type != "WIFI" or not computer.ap_mac:
        return False

    bssid = computer.ap_mac.strip().lower()
    if bssid.count(":") != 5 or bssid in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"):
        return False

    bssid_prefix = bssid[:14]  # 5 oktet pertama: "xx:xx:xx:xx:xx"
    ap: AccessPoint | None = None

    # 1. Cari exact MAC match di database
    ap = db.query(AccessPoint).filter(AccessPoint.mac.ilike(bssid)).first()

    # 2. Cari dari local_arp PC klien bila ada
    if ap is None and local_arp:
        matched_ip = ""
        for item in local_arp:
            m = str(item.get("mac", "")).strip().lower()
            if m == bssid or (len(m) >= 14 and m[:14] == bssid_prefix):
                matched_ip = str(item.get("ip", "")).strip()
                break
        if matched_ip:
            ap = db.query(AccessPoint).filter(AccessPoint.ip == matched_ip).first()

    # 3. Cari dari ap_ip jika sudah terisi (dari local_arp match di agent)
    if ap is None and computer.ap_ip:
        ap = db.query(AccessPoint).filter(AccessPoint.ip == computer.ap_ip).first()

    # 4. Cari prefix MAC match di database (5 oktet pertama vendor yang sama di subnet PC)
    if ap is None:
        ap_candidates = db.query(AccessPoint).filter(
            AccessPoint.mac.ilike(f"{bssid_prefix}%"),
            ~AccessPoint.mac.like("ip-%"),
        ).all()
        if ap_candidates:
            if computer.wifi_ip and "." in computer.wifi_ip:
                pc_subnet = ".".join(computer.wifi_ip.split(".")[:3]) + "."
                for cand in ap_candidates:
                    if cand.ip.startswith(pc_subnet):
                        ap = cand
                        break
            if ap is None:
                ap = ap_candidates[0]

    if ap is None:
        return False

    # Jangan menimpa SSID jika sudah ada
    if not ap.ssid and computer.ssid:
        ap.ssid = computer.ssid.strip()[:256]
        ap.is_ap = True
        record(
            db, "agent", "AP_AUTO_SSID",
            target=f"{ap.ip} ({ap.mac}) → {ap.ssid}",
            result="SUCCESS",
        )
        return True
    return False


def _upsert_printers(db: Session, computer: ManagedComputer, printers: list[dict]) -> None:
    """Simpan daftar printer yang dilaporkan agent; tandai yang hilang offline.

    Keyed by (computer_id, name). Printer yang tidak lagi dilaporkan pada
    heartbeat ini ditandai offline (tetap tersimpan sebagai riwayat).
    """
    seen: set[str] = set()
    now = datetime.utcnow()
    for item in printers[:32]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()[:128]
        if not name:
            continue
        seen.add(name)
        share_name = str(item.get("share_name", "") or "").strip()[:128]
        row = (
            db.query(SharedPrinter)
            .filter(
                SharedPrinter.computer_id == computer.id,
                SharedPrinter.name == name,
            )
            .first()
        )
        if row is None:
            row = SharedPrinter(computer_id=computer.id, name=name)
            db.add(row)
        row.share_name = share_name
        row.platform = str(item.get("platform", "") or "")[:16]
        row.driver = str(item.get("driver", "") or "")[:160]
        row.port = str(item.get("port", "") or "")[:160]
        row.is_shared = bool(item.get("shared")) and bool(share_name)
        row.online = True
        row.updated_at = now
    stale = (
        db.query(SharedPrinter)
        .filter(
            SharedPrinter.computer_id == computer.id,
            SharedPrinter.online.is_(True),
        )
        .all()
    )
    for row in stale:
        if row.name not in seen:
            row.online = False
            row.updated_at = now


@router.post("/heartbeat")
def heartbeat(
    body: HeartbeatBody,
    request: Request,
    x_agent_token: str = Header(default=""),
    db: Session = Depends(get_db),
):
    # --- autentikasi lentur agar agent versi lama ikut tersembuhkan ---
    mac = body.mac.strip()[:128]
    computer = None
    if x_agent_token:
        computer = (
            db.query(ManagedComputer)
            .filter(ManagedComputer.token == x_agent_token)
            .first()
        )
    if computer is None:
        # token kosong/basi → kenali dari MAC di payload:
        #   MAC sudah terdaftar → terima (re-bind, tanpa duplikat)
        #   MAC baru + dari LAN → daftarkan otomatis (zero-config)
        if not _client_is_lan(request):
            raise HTTPException(
                403, "agent hanya boleh mengirim dari jaringan LAN/privat"
            )
        if body.hostname.strip():
            if mac:
                computer, _created = _upsert_by_mac(
                    db,
                    hostname=body.hostname.strip()[:128],
                    mac=mac,
                    ip=body.ip.strip(),
                    os_info=body.os_info.strip(),
                    agent_version=body.agent_version.strip(),
                )
            else:
                # agent versi SANGAT lama yang belum mengirim MAC —
                # kenali dari hostname (fallback, LAN saja)
                computer = (
                    db.query(ManagedComputer)
                    .filter(
                        ManagedComputer.hostname.ilike(
                            body.hostname.strip()[:128]
                        )
                    )
                    .first()
                )
                if computer is not None:
                    computer.ip = (body.ip or computer.ip or "")[:45]
                    db.commit()
        if computer is None:
            raise HTTPException(401, "Unknown agent token")

    computer.hostname = (body.hostname or computer.hostname or "")[:128]
    computer.ip = (body.ip or computer.ip or "")[:45]
    computer.mac = (body.mac or computer.mac or "")[:128]
    computer.os_info = (body.os_info or computer.os_info or "")[:256]
    computer.interfaces = json.dumps(body.interfaces[:16])
    computer.cpu = body.cpu
    computer.mem = body.mem
    pending_rx = float(computer.net_rx_pending or 0.0) + max(
        0.0, min(float(body.net_rx_bytes or 0.0), 1e12)
    )
    pending_tx = float(computer.net_tx_pending or 0.0) + max(
        0.0, min(float(body.net_tx_bytes or 0.0), 1e12)
    )
    saved_sample = computer_metrics.record_sample(
        db,
        computer.id,
        body.cpu,
        body.mem,
        net_rx_bytes=pending_rx,
        net_tx_bytes=pending_tx,
    )
    if saved_sample:
        computer.net_rx_pending = 0.0
        computer.net_tx_pending = 0.0
    else:
        computer.net_rx_pending = pending_rx
        computer.net_tx_pending = pending_tx
    computer.internet_up = body.internet_up
    computer.latency_ms = body.latency_ms
    if body.download_mbps is not None:
        computer.download_mbps = max(0.0, min(body.download_mbps, 100000.0))
    if body.upload_mbps is not None:
        computer.upload_mbps = max(0.0, min(body.upload_mbps, 100000.0))
    tested_at = None
    if body.speed_test_at:
        try:
            tested_at = datetime.fromisoformat(body.speed_test_at)
            computer.speed_test_at = tested_at
        except ValueError:
            pass
    if tested_at is not None:
        computer_metrics.record_speed_sample(
            db,
            computer.id,
            tested_at,
            body.download_mbps,
            body.upload_mbps,
            source=body.speed_test_source,
        )
    computer.agent_version = (body.agent_version or computer.agent_version or "")[:32]
    computer.autostart_mode = (body.autostart_mode or computer.autostart_mode or "")[:64]
    if body.smb_open is not None:
        computer.smb_open = body.smb_open
    # info jalur koneksi
    ctype = (body.conn_type or "").strip().upper()[:16]
    if ctype in ("LAN", "WIFI"):
        computer.conn_type = ctype
    computer.ssid = (body.ssid or computer.ssid or "")[:64]
    computer.iface_name = (body.iface_name or computer.iface_name or "")[:32]
    computer.wifi_ip = (body.wifi_ip or computer.wifi_ip or "")[:45]
    computer.ap_ip = (body.ap_ip or "")[:45] if ctype == "WIFI" else ""
    computer.ap_mac = (body.ap_mac or "")[:128] if ctype == "WIFI" else ""
    computer.last_seen = datetime.utcnow()

    # Data ARP bersifat tambahan; konflik MAC tidak boleh membatalkan heartbeat.
    try:
        with db.begin_nested():
            _process_local_arp(db, body.local_arp)
    except IntegrityError:
        pass
    _ap_rename_wifi(db, computer, body.local_arp)

    # printer yang di-share pemilik (dan printer lokal lain) → direktori
    if body.printers:
        try:
            with db.begin_nested():
                _upsert_printers(db, computer, body.printers)
        except Exception:
            log.warning("upsert printers failed for %s", computer.name, exc_info=True)

    resp = {"ok": True, "interval": HEARTBEAT_INTERVAL}
    # sertakan token yang sah — agent bisa menyimpan ulang bila perlu
    resp["token"] = computer.token
    cmd = computer.pending_cmd
    if cmd and (cmd in AGENT_COMMANDS
                or cmd.startswith(COMMAND_PREFIXES)):
        resp["command"] = cmd
        computer.pending_cmd = None      # sekali kirim — agent yang ACK hasilnya
        computer.cmd_issued_at = None

    pc_ip = computer.ip
    ap_mac = computer.ap_mac
    ap_ip = computer.ap_ip
    computer_id = computer.id
    # Commit dulu: probe jaringan di bawah bisa makan beberapa detik dan
    # tidak boleh menahan transaksi/AccessShareLock di managed_computers.
    db.commit()

    try:
        server_reach = _detect_server_reach(db, pc_ip, ap_mac, ap_ip)
        # Tutup transaksi baca dari _detect_server_reach sebelum ping.
        db.commit()
        latency_srv_ms = _ping_host(pc_ip)
        (
            db.query(ManagedComputer)
            .filter(ManagedComputer.id == computer_id)
            .update(
                {
                    ManagedComputer.server_reach: server_reach,
                    ManagedComputer.latency_srv_ms: latency_srv_ms,
                },
                synchronize_session=False,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        log.warning("server reach probe failed for %s", pc_ip, exc_info=True)

    return resp


@router.get("/speed-test")
def speed_test(
    bytes: int = 262144,
    computer: ManagedComputer = Depends(_agent_computer),
):
    """Payload kecil untuk mengukur throughput PC ke backend."""
    size = max(65536, min(bytes, 1048576))
    return Response(content=b"0" * size, media_type="application/octet-stream",
                    headers={"Cache-Control": "no-store"})


@router.post("/speed-test")
async def speed_test_upload(
    payload: bytes = Body(default=b""),
    computer: ManagedComputer = Depends(_agent_computer),
):
    if len(payload) > 2 * 1024 * 1024:
        raise HTTPException(413, "Payload terlalu besar (maks 2 MB)")
    return {"ok": True, "bytes": len(payload)}


class AckBody(BaseModel):
    action: str = ""
    status: str = ""


@router.post("/ack")
def agent_ack(
    body: AckBody,
    computer: ManagedComputer = Depends(_agent_computer),
    db: Session = Depends(get_db),
):
    stamp = datetime.utcnow().strftime("%d/%m %H:%M")
    computer.last_cmd_result = f"[{stamp}] {body.action}: {body.status}"[:160]
    record(db, "agent", "COMPUTER_CMD_RESULT", computer.name, body.status[:20])
    db.commit()
    return {"ok": True}


class CommandBody(BaseModel):
    action: str   # restart | shutdown | update


class SoftwareInstallBody(BaseModel):
    package_id: str


class SoftwareBulkBody(BaseModel):
    computer_ids: list[int]
    package_id: str


def _software_command(package_id: str) -> str:
    package = SOFTWARE_CATALOG.get(package_id.strip().lower())
    if not package:
        raise HTTPException(400, "Software tidak ada di katalog")
    return f"install:{package_id.strip().lower()}"


@router.post("/{computer_id}/software", dependencies=[Depends(require_write)])
def install_software(
    computer_id: int,
    body: SoftwareInstallBody,
    user: str = Depends(get_current_user),
    role: str = Depends(get_current_role),
    db: Session = Depends(get_db),
):
    c = db.query(ManagedComputer).filter(ManagedComputer.id == computer_id).first()
    if not c:
        raise HTTPException(404, "Komputer tidak ditemukan")
    _assert_can_manage(db, user, role, c)
    c.pending_cmd = _software_command(body.package_id)
    c.cmd_issued_at = datetime.utcnow()
    record(db, user, "COMPUTER_INSTALL_SOFTWARE", f"{c.name}: {body.package_id}", "PENDING")
    db.commit()
    return {"success": True, "detail": f"Instalasi {SOFTWARE_CATALOG[body.package_id.strip().lower()]['name']} dikirim ke {c.name}"}


@router.post("/software/bulk-install", dependencies=[Depends(require_write)])
def bulk_install_software(
    body: SoftwareBulkBody,
    user: str = Depends(get_current_user),
    role: str = Depends(get_current_role),
    db: Session = Depends(get_db),
):
    command = _software_command(body.package_id)
    ids = list(dict.fromkeys(body.computer_ids))
    computers = db.query(ManagedComputer).filter(ManagedComputer.id.in_(ids)).all()
    if not ids or len(computers) != len(ids):
        raise HTTPException(404, "Ada komputer yang tidak ditemukan")
    _assert_can_manage_many(db, user, role, computers)
    for c in computers:
        c.pending_cmd = command
        c.cmd_issued_at = datetime.utcnow()
        record(db, user, "COMPUTER_INSTALL_SOFTWARE", f"{c.name}: {body.package_id}", "PENDING")
    db.commit()
    return {"success": True, "count": len(computers), "detail": f"Instalasi dikirim ke {len(computers)} komputer"}


class BulkCommandBody(BaseModel):
    ids: list[int]
    action: str   # restart | shutdown | update | cleanup-nodelete


@router.post("/bulk-command", dependencies=[Depends(require_write)])
def issue_bulk_command(
    body: BulkCommandBody,
    user: str = Depends(get_current_user),
    role: str = Depends(get_current_role),
    db: Session = Depends(get_db),
):
    action = body.action.strip().lower()
    if action not in AGENT_COMMANDS:
        raise HTTPException(400, "action harus 'restart', 'shutdown', 'update', atau 'cleanup-nodelete'")
    if action in ("restart", "shutdown", CLEANUP_CMD) and role != "superadmin":
        raise HTTPException(403, "Hanya superadmin yang dapat restart, shutdown, atau cleanup komputer")
    ids = list(dict.fromkeys(body.ids))
    if not ids:
        raise HTTPException(400, "Pilih minimal satu komputer")
    computers = db.query(ManagedComputer).filter(ManagedComputer.id.in_(ids)).all()
    found_ids = {computer.id for computer in computers}
    missing = [str(computer_id) for computer_id in ids if computer_id not in found_ids]
    if missing:
        raise HTTPException(404, f"Komputer tidak ditemukan: {', '.join(missing)}")
    _assert_can_manage_many(db, user, role, computers)
    issued_at = datetime.utcnow()
    queued: list[ManagedComputer] = []
    skipped: list[str] = []
    # cleanup-nodelete diantrekan juga untuk PC offline (jalan saat heartbeat
    # berikutnya, maks 24 jam via PENDING_EXPIRY_SECONDS) agar PC yang mati
    # 8 jam tetap bersih saat dinyalakan.
    queue_offline = action == CLEANUP_CMD
    audit_tag = "COMPUTER_CLEANUP" if action == CLEANUP_CMD else f"COMPUTER_{action.upper()}"
    for computer in computers:
        if not _is_online(computer) and not queue_offline:
            # PC mati tidak bisa mengambil perintah → jangan biarkan menggantung
            # sebagai "waiting"; skip dan laporkan agar jelas.
            skipped.append(computer.name or str(computer.id))
            record(
                db, user, f"COMPUTER_{action.upper()}",
                computer.name or str(computer.id), "SKIPPED_OFFLINE",
            )
            continue
        computer.pending_cmd = action
        computer.cmd_issued_at = issued_at
        record(
            db, user, audit_tag,
            computer.name or str(computer.id), "PENDING",
        )
        queued.append(computer)
    db.commit()
    detail = f"Perintah {action} dikirim ke {len(queued)} komputer"
    if skipped:
        detail += (
            f" · {len(skipped)} dilewati (offline): {', '.join(skipped[:8])}"
            + (" …" if len(skipped) > 8 else "")
        )
    return {
        "success": True,
        "count": len(queued),
        "skipped": skipped,
        "detail": detail,
    }


def _is_online(c: ManagedComputer) -> bool:
    return (
        c.last_seen is not None
        and (datetime.utcnow() - c.last_seen).total_seconds() <= OFFLINE_AFTER
    )


@router.post("/{computer_id}/command", dependencies=[Depends(require_write)])
def issue_command(
    computer_id: int,
    body: CommandBody,
    user: str = Depends(get_current_user),
    role: str = Depends(get_current_role),
    db: Session = Depends(get_db),
):
    action = body.action.strip().lower()
    if action not in AGENT_COMMANDS:
        raise HTTPException(400, "action harus 'restart', 'shutdown', 'update', atau 'cleanup-nodelete'")
    if action in ("restart", "shutdown", CLEANUP_CMD) and role != "superadmin":
        raise HTTPException(403, "Hanya superadmin yang dapat restart, shutdown, atau cleanup komputer")
    c = db.query(ManagedComputer).filter(ManagedComputer.id == computer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Komputer tidak ditemukan")
    _assert_can_manage(db, user, role, c)
    c.pending_cmd = action
    c.cmd_issued_at = datetime.utcnow()
    record(db, user, f"COMPUTER_{action.upper()}", c.name or str(c.id), "PENDING")
    db.commit()
    online = _is_online(c)
    return {
        "success": True,
        "detail": (
            f"Perintah {action} dikirim ke {c.name or c.id} — "
            "dieksekusi agent pada heartbeat berikutnya (maks "
            f"{HEARTBEAT_INTERVAL}s)"
            if online
            else f"PC {c.name or c.id} OFFLINE — perintah {action} diantrekan "
            "dan akan dijalankan otomatis saat PC kembali online."
        ),
    }


@router.post("/{computer_id}/cancel-command", dependencies=[Depends(require_write)])
def cancel_command(
    computer_id: int,
    user: str = Depends(get_current_user),
    role: str = Depends(get_current_role),
    db: Session = Depends(get_db),
):
    """Batalkan perintah tertunda (mis. update) yang belum diambil agent."""
    c = db.query(ManagedComputer).filter(ManagedComputer.id == computer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Komputer tidak ditemukan")
    _assert_can_manage(db, user, role, c)
    if not c.pending_cmd:
        return {"success": True, "detail": f"Tidak ada perintah tertunda pada {c.name or c.id}"}
    pending = c.pending_cmd
    c.pending_cmd = None
    c.cmd_issued_at = None
    record(db, user, "COMPUTER_CMD_CANCEL", f"{c.name or c.id}: {pending}", "CANCELLED")
    db.commit()
    return {"success": True, "detail": f"Perintah {pending} dibatalkan untuk {c.name or c.id}"}


class BulkCancelBody(BaseModel):
    # Kosong = batalkan SEMUA perintah tertunda (mis. sisa update massal).
    ids: list[int] = []


@router.post("/bulk-cancel", dependencies=[Depends(require_write)])
def bulk_cancel(
    body: BulkCancelBody,
    user: str = Depends(get_current_user),
    role: str = Depends(get_current_role),
    db: Session = Depends(get_db),
):
    query = db.query(ManagedComputer).filter(ManagedComputer.pending_cmd.isnot(None))
    if body.ids:
        ids = list(dict.fromkeys(body.ids))
        if not ids:
            raise HTTPException(400, "ids kosong")
        query = query.filter(ManagedComputer.id.in_(ids))
    rows = query.all()
    _assert_can_manage_many(db, user, role, rows)
    for c in rows:
        pending = c.pending_cmd
        c.pending_cmd = None
        c.cmd_issued_at = None
        record(db, user, "COMPUTER_CMD_CANCEL", f"{c.name or c.id}: {pending}", "CANCELLED")
    db.commit()
    return {
        "success": True,
        "count": len(rows),
        "detail": f"{len(rows)} perintah tertunda dibatalkan",
    }


class _ApMini:
    """Baris ringan inventori AP untuk pencocokan MAC presence/topologi.

    Memuat SEMUA AP (1291+ row) sebagai objek ORM penuh per sekali cek
    menahan koneksi pool lama + boros memori. Mini ini hanya membawa kolom
    yang dipakai _presence_evidence (duck-typed: atribut sama)."""

    __slots__ = ("mac", "ip", "model", "is_ap", "status", "last_seen")

    def __init__(self, mac: str, ip: str, model: str, is_ap: bool, status: str, last_seen):
        self.mac = mac
        self.ip = ip
        self.model = model
        self.is_ap = is_ap
        self.status = status
        self.last_seen = last_seen


def _ap_minis(db: Session) -> list:
    """Ambil kandidat AP se-ringan mungkin (kolom yang dipakai saja)."""
    rows = (
        db.query(
            AccessPoint.mac,
            AccessPoint.ip,
            AccessPoint.model,
            AccessPoint.is_ap,
            AccessPoint.status,
            AccessPoint.last_seen,
        )
        .filter(~AccessPoint.mac.like("ip-%"))
        .all()
    )
    return [_ApMini(*r) for r in rows]


def _safe_record(db: Session, username: str, action: str, target: str, result: str) -> None:
    """Audit log tidak boleh menggagalkan response pengecekan.

    Sebelumnya `record()` + `commit()` yang gagal (pool habis / deadlock)
    mengubah hasil cek yang sebenarnya sukses menjadi HTTP 500 → user hanya
    melihat toast merah "gagal". Kini kegagalan audit ditelan + rollback
    agar hasil cek tetap terkirim."""
    try:
        record(db, username, action, target, result)
        db.commit()
    except (TimeoutError, OperationalError, DBAPIError):
        db.rollback()
        log.warning("audit %s gagal disimpan (DB sibuk) — hasil cek tetap dikirim", action)
    except Exception:
        db.rollback()
        log.warning("audit %s gagal", action, exc_info=True)


def _presence_evidence(c: ManagedComputer, aps: list) -> dict:
    """Probe kehadiran jaringan satu komputer dari server.

    Bukti: balasan ICMP ping (lintas segment) + tabel ARP/`ip neigh`
    (hanya untuk host satu L2 — balasan ARP tak terblokir firewall)
    + kecocokan MAC di inventory access_points (hasil scan apmon).
    """

    def _valid(ip: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if addr.is_loopback or addr.is_link_local or addr.is_unspecified:
            return False
        return True

    ips: list[str] = []
    for ip in (c.ip, c.wifi_ip):
        ip = (ip or "").strip()
        if ip and _valid(ip) and ip not in ips:
            ips.append(ip)
    try:
        extra = [i.get("ip", "") for i in json.loads(c.interfaces or "[]")]
    except Exception:
        extra = []
    for ip in extra:
        ip = (ip or "").strip()
        if ip and _valid(ip) and ip not in ips:
            ips.append(ip)
    ips = ips[:4]

    checks: list[dict] = []
    alive = False
    if ips:
        with ThreadPoolExecutor(max_workers=len(ips)) as pool:
            ping_futs = {pool.submit(_ping_host, ip): ip for ip in ips}
            neigh_futs = {pool.submit(_ip_neigh, ip): ip for ip in ips}
        ping_by_ip = {ip: f.result() for f, ip in ping_futs.items()}
        neigh_by_ip = {ip: f.result() for f, ip in neigh_futs.items()}
        for ip in ips:
            ping_ms = ping_by_ip.get(ip)
            lladdr, state = neigh_by_ip.get(ip) or (None, None)
            checks.append(
                {
                    "ip": ip,
                    "ping_ms": ping_ms,
                    "neigh_state": state,
                    "neigh_mac": (lladdr.lower() if lladdr else None),
                    # Ada entry L2 (lladdr atau INCOMPLETE/FAILED) ⇒ server satu
                    # segmen dengan host → absensi/presensi ARP bisa dibuktikan.
                    "same_lan": bool(lladdr or state),
                }
            )
            if ping_ms is not None:
                alive = True
            if lladdr and state in ("REACHABLE", "STALE", "DELAY", "PROBE", "PERMANENT"):
                alive = True

    ap_matches: list[dict] = []
    db_mac = _normalize_mac(c.mac)
    if db_mac:
        for ap in aps:
            if _normalize_mac(ap.mac) == db_mac:
                ap_matches.append(
                    {
                        "mac": ap.mac,
                        "ip": ap.ip,
                        "model": ap.model,
                        "is_ap": ap.is_ap,
                        "status": ap.status,
                        "last_seen": ap.last_seen.strftime("%Y-%m-%d %H:%M:%S")
                        if ap.last_seen
                        else None,
                    }
                )

    if not ips:
        verdict = "no_ip"
        summary = "Tidak ada alamat IP valid untuk dicoba (agent belum pernah melaporkan IP / hanya APIPA)."
    elif alive:
        verdict = "alive"
        summary = "PC merespons ping dan/atau ARP — perangkat HIDUP di jaringan; yang mati hanya aplikasi agent."
    elif any(k["same_lan"] for k in checks):
        verdict = "dead"
        summary = "Tidak ada balasan ICMP maupun ARP pada segmen yang sama — PC kemungkinan mati, off, atau kabel lepas."
    else:
        verdict = "unknown"
        summary = "Tidak ada balasan ICMP. PC lintas subnet — kemungkinan ICMP diblokir firewall Windows; belum tentu PC mati."

    return {
        "verdict": verdict,
        "summary": summary,
        "mac_db": c.mac,
        "checks": checks,
        "ap_matches": ap_matches,
    }


@router.get("/{computer_id}/presence")
def presence_check(
    computer_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    c = db.query(ManagedComputer).filter(ManagedComputer.id == computer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Komputer tidak ditemukan")
    try:
        aps = _ap_minis(db)
    except (TimeoutError, OperationalError, DBAPIError) as e:
        raise HTTPException(
            status_code=503,
            detail="Database sibuk (banyak heartbeat bersamaan) — coba lagi beberapa detik",
        ) from e
    # Lepas objek & tutup transaksi sebelum ping/ARP: probe bisa berdetik-detik
    # dan tidak boleh menahan AccessShareLock di managed_computers.
    db.expunge_all()
    db.rollback()
    result = _presence_evidence(c, aps)
    _safe_record(db, user, "COMPUTER_PRESENCE", c.name or str(c.id), result["verdict"])
    return result


class BulkPresenceBody(BaseModel):
    ids: list[int] = []   # kosong = semua komputer


@router.post("/bulk-presence")
def bulk_presence(
    body: BulkPresenceBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pengetesan kehadiran jaringan SERENTAK untuk banyak PC.

    Warna agregat:
      green  = semua normal (online / PC hidup semua)
      yellow = ada masalah (agent mati / IP tak terkonfirmasi), tapi tidak semua mati
      red    = semua tidak terdeteksi / mati di jaringan
    """
    q = db.query(ManagedComputer)
    if body.ids:
        ids = list(dict.fromkeys(body.ids))
        found = q.filter(ManagedComputer.id.in_(ids)).all()
        if len(found) != len(ids):
            raise HTTPException(404, "Ada komputer yang tidak ditemukan")
        computers = found
    else:
        computers = q.all()
    try:
        aps = _ap_minis(db)
    except (TimeoutError, OperationalError, DBAPIError) as e:
        raise HTTPException(
            status_code=503,
            detail="Database sibuk (banyak heartbeat bersamaan) — coba lagi beberapa detik",
        ) from e

    # Lepas objek & tutup transaksi sebelum ping/ARP serentak; jangan biarkan
    # probe jaringan menahan lock tabel managed_computers.
    db.expunge_all()
    db.rollback()

    now = datetime.utcnow()

    def _online(c: ManagedComputer) -> bool:
        return bool(c.last_seen) and (now - c.last_seen).total_seconds() <= OFFLINE_AFTER

    def _evaluate(c: ManagedComputer) -> dict:
        evidence = _presence_evidence(c, aps)
        if _online(c):
            color = "green"
        elif evidence["verdict"] == "dead":
            color = "red"
        elif evidence["verdict"] == "alive":
            color = "yellow"
        else:
            color = "yellow"
        return {
            "id": c.id,
            "name": c.name or c.hostname or str(c.id),
            "status_agent": "online" if _online(c) else ("offline" if c.last_seen else "waiting"),
            "verdict": evidence["verdict"],
            "summary": evidence["summary"],
            "color": color,
            "ping": [k for k in evidence["checks"] if k["ping_ms"] is not None],
        }

    with ThreadPoolExecutor(max_workers=min(len(computers) or 1, 32)) as pool:
        results = list(pool.map(_evaluate, computers))

    colors = [r["color"] for r in results]
    if not colors or all(x == "green" for x in colors):
        overall = "green"
        label = "Semua normal — tidak ada masalah"
    elif all(x == "red" for x in colors):
        overall = "red"
        label = "Semua PC tidak terdeteksi di jaringan"
    else:
        overall = "yellow"
        label = "Ada masalah — sebagian agent mati / IP tidak terkonfirmasi"

    _safe_record(
        db, user, "COMPUTER_PRESENCE_BULK",
        f"{len(results)} komputer",
        overall,
    )
    return {
        "overall": overall,
        "label": label,
        "counts": {
            "total": len(results),
            "green": colors.count("green"),
            "yellow": colors.count("yellow"),
            "red": colors.count("red"),
        },
        "computers": results,
    }


class TopologyBody(BaseModel):
    ids: list[int] = []   # kosong = semua komputer


@router.get("/topology")
def topology_status(
    _: str = Depends(get_current_user),
):
    """Info status auto-check IP topologi (jadwal otomatis + jendela waktu)."""
    return topology_svc.status_info()


@router.post("/topology-check", dependencies=[Depends(require_write)])
def topology_check(
    body: TopologyBody = Body(default=TopologyBody()),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cek IP manual: cocokkan IP tiap komputer dengan inventori Access Point
    yang ONLINE, perbarui IP komputer bila MAC cocok di AP, lalu tandai online.

    ids kosong = semua komputer. Menyegarkan ap_seen_at sehingga status
    online gabungan (heartbeat ATAU cocok IP AP) ikut ter-update.
    """
    if body.ids:
        ids = list(dict.fromkeys(body.ids))
        found = db.query(ManagedComputer.id).filter(ManagedComputer.id.in_(ids)).all()
        if len(found) != len(ids):
            have = {r[0] for r in found}
            missing = [str(i) for i in ids if i not in have]
            raise HTTPException(
                status_code=404,
                detail=f"Komputer tidak ditemukan: {', '.join(missing)}",
            )
    try:
        result = topology_svc.topology_check(db, body.ids)
    except (TimeoutError, OperationalError, DBAPIError) as e:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Database sibuk (banyak heartbeat bersamaan) — coba lagi beberapa detik",
        ) from e
    _safe_record(
        db, user, "COMPUTER_TOPO_CHECK",
        f"{result['checked']} komputer · {result['online_ap']} online-AP · "
        f"{result['updated_ip']} IP diperbarui",
        "SUCCESS",
    )
    return result


@router.get("/agent-script", response_class=PlainTextResponse)
def agent_script(request: Request):
    """Kirim script agent dengan alamat server DITANAM otomatis.

    Alamat default dipatok ke IP LAN kantor agar agent tetap memakai jalur LAN
    yang sama saat PC klien berpindah lokasi dalam jaringan kantor.
    """
    if not AGENT_SCRIPT.exists():
        raise HTTPException(status_code=404, detail="Script agent tidak ditemukan")
    text = AGENT_SCRIPT.read_text(encoding="utf-8")
    target_server = get_settings().panel_agent_server.rstrip("/")

    if 'PANEL_SERVER_INJECTED = ""' in text:
        text = text.replace(
            'PANEL_SERVER_INJECTED = ""',
            f'PANEL_SERVER_INJECTED = "{target_server}"',
            1,
        )
    return PlainTextResponse(text)


# ------------------------------------------- bootstrap Windows (winget-style)

AGENT_INSTALL_PS1 = r"""# Ubuntu Panel Agent - bootstrap berbasis Python (install / update)
# Dipakai via:  powershell -c "irm <server>/api/computers/agent-install.ps1 | iex"
$ErrorActionPreference = 'Stop'
$server = '{{SERVER}}'

Write-Host '== Ubuntu Panel Agent bootstrap =='
Write-Host ("Server : " + $server)

# Agent selalu dipasang machine-wide ke %ProgramData%\PanelAgent:
#  1/3 Tugas boot-SYSTEM AtStartup (delay 30s, tunggu network) + AtLogOn
#  2/3 HKLM Run (semua user) + 3/3 Common Startup VBS (cadangan).
#  Berlaku untuk SEMUA akun Windows termasuk user baru, + SMB dibuka
#  otomatis untuk share printer guest.
$installDir = Join-Path $env:ProgramData 'PanelAgent'
$cfg = Join-Path $installDir 'agent.ini'

# 1) naikkan hak ke Administrator sekali (syarat tugas boot)
$princ = New-Object System.Security.Principal.WindowsPrincipal(
    [System.Security.Principal.WindowsIdentity]::GetCurrent()
)
if (-not $princ.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'Merestart sebagai Administrator (satu prompt UAC) ...'
    # dijalankan ulang via URL (bukan -File) agar tetap jalan walau script
    # dimuat lewat "irm ... | iex" (PSCommandPath kosong)
    $cmd = "irm '" + $server + "/api/computers/agent-install.ps1' | iex"
    Start-Process powershell.exe -Verb RunAs -ArgumentList (
        '-ExecutionPolicy','Bypass','-NoProfile','-Command',$cmd
    )
    exit
}

# 1b) sekarang admin -> tentukan mode (UPDATE vs INSTALL BARU)
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
$updated = Test-Path $cfg
if ($updated) {
    Write-Host 'Mode   : UPDATE ---- token lama dipakai ulang (PC tidak diduplikasi)'
} else {
    Write-Host 'Mode   : INSTALL BARU ---- registrasi otomatis via MAC'
}

# 2) cari Python VALID (bukan sekadar ada di PATH).
#    Kasus nyata (PC Poli THT): C:\WINDOWS\py.exe ADA tapi tanpa runtime
#    Python -> `py -3` gagal "No installed Python found!" (exit 112) dan
#    panel_agent.py tidak pernah jalan. Karena itu tiap kandidat WAJIB
#    diuji `--version` sebelum dipakai.
function Test-PythonCandidate($exe, $cargs) {
    try {
        & $exe @cargs --version 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}
$pyExe = ''
$pyArgs = @()
$pyDiag = @()
$pyUserLocal = ''
# 2a) lokasi machine-wide DULU (Task SYSTEM tidak bisa pakai user-profile:
#     C:\Users\...\AppData tidak terbaca SYSTEM + ada spasi di "IGD 02").
$commonPaths = @(
    'C:\Python314\python.exe',
    'C:\Python313\python.exe',
    'C:\Python312\python.exe',
    'C:\Python311\python.exe',
    'C:\Python310\python.exe',
    'C:\Program Files\Python314\python.exe',
    'C:\Program Files\Python313\python.exe'
)
foreach ($base in @('C:\Program Files\Python3*', 'C:\Program Files (x86)\Python3*')) {
    try {
        foreach ($f in (Get-ChildItem $base -Filter python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)) {
            $commonPaths += $f
        }
    } catch { }
}
foreach ($p in $commonPaths) {
    if ($p -and (Test-Path $p) -and (Test-PythonCandidate $p @())) { $pyExe = $p; $pyArgs = @(); break }
}
# 2b) python.exe di PATH (bisa user-local Microsoft Store: catat, jangan langsung pakai)
$cmd = Get-Command python -ErrorAction SilentlyContinue
if ($cmd) {
    if (Test-PythonCandidate $cmd.Source @()) {
        $src = $cmd.Source
        $isUserLocal = ($src -like ($env:LOCALAPPDATA + '*')) -or ($src -like '*\Users\*') -or ($src -like '*\AppData\*') -or ($src -like '*WindowsApps*')
        if ($isUserLocal) { $pyUserLocal = $src; $pyDiag += ('python user-local (tidak untuk SYSTEM): ' + $src) }
        elseif (-not $pyExe) { $pyExe = $src; $pyArgs = @() }
    }
    else { $pyDiag += ('python di PATH rusak: ' + $cmd.Source) }
}
# 2c) terakhir: py launcher, HANYA bila `py -3 --version` benar-benar jalan
if (-not $pyExe) {
    $cmd = Get-Command py -ErrorAction SilentlyContinue
    if ($cmd) {
        if (Test-PythonCandidate $cmd.Source @('-3')) {
            # resolve ke interpreter asli agar Task SYSTEM tidak tergantung shim
            $realPy = ''
            try { $realPy = ((& $cmd.Source -3 -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1) + '').Trim() } catch { }
            if ($realPy -and (Test-Path $realPy)) { $pyExe = $realPy; $pyArgs = @() }
            else { $pyExe = $cmd.Source; $pyArgs = @('-3') }
        } else {
            $pyDiag += 'py launcher ada tapi tanpa runtime (No installed Python found!)'
            try { $lp = ((& $cmd.Source -0p 2>&1 | Out-String) + '').Trim(); if ($lp) { $pyDiag += $lp } } catch { }
        }
    }
}
# 2d) auto-remediasi via winget bila belum ada Python MACHINE-WIDE valid.
#     User-local (Store/AppData) tidak bisa dipakai Task SYSTEM, jadi walau
#     $pyUserLocal ada, tetap coba pasang machine-wide dulu.
if (-not $pyExe) {
    if ($pyUserLocal) {
        Write-Host ('Python machine-wide TIDAK ada; hanya user-local: ' + $pyUserLocal)
        Write-Host '  User-local TIDAK bisa dipakai Task SYSTEM (jalan sebelum login).'
    } else {
        Write-Host 'Python 3 valid TIDAK ditemukan.'
    }
    foreach ($d in $pyDiag) { Write-Host ('  diag: ' + $d) }
    $wg = Get-Command winget -ErrorAction SilentlyContinue
    if ($wg) {
        Write-Host 'Mencoba pasang Python 3.14 otomatis via winget (machine-wide) ...'
        try {
            winget install --id Python.Python.3.14 --scope machine --silent --accept-package-agreements --accept-source-agreements
            $env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
            $cmd2 = Get-Command python -ErrorAction SilentlyContinue
            if ($cmd2 -and (Test-PythonCandidate $cmd2.Source @())) { $pyExe = $cmd2.Source; $pyArgs = @() }
            elseif ((Test-Path 'C:\Python314\python.exe') -and (Test-PythonCandidate 'C:\Python314\python.exe' @())) { $pyExe = 'C:\Python314\python.exe'; $pyArgs = @() }
        } catch { Write-Host ('  winget gagal: ' + $_.Exception.Message) }
    } else {
        Write-Host 'winget tidak tersedia di PC ini.'
    }
    # winget gagal/tidak ada: uji ulang lokasi machine-wide (mungkin sudah ada tapi PATH belum refresh)
    if (-not $pyExe) {
        foreach ($p in @('C:\Python314\python.exe', 'C:\Program Files\Python314\python.exe')) {
            if ((Test-Path $p) -and (Test-PythonCandidate $p @())) { $pyExe = $p; $pyArgs = @(); break }
        }
    }
    # terakhir: pakai user-local apa adanya (login-only, Task SYSTEM kemungkinan gagal)
    if ((-not $pyExe) -and $pyUserLocal) {
        $pyExe = $pyUserLocal; $pyArgs = @()
        Write-Host 'PERINGATAN: memakai Python user-local darurat (Task boot-SYSTEM kemungkinan GAGAL).'
        Write-Host '  Segera pasang Python machine-wide agar agent jalan sebelum login.'
    }
}
if (-not $pyExe) {
    Write-Host 'GAGAL: Python 3 tidak terpasang / rusak.'
    Write-Host '  Solusi manual (pilih satu):'
    Write-Host '    1) winget install --id Python.Python.3.14 --scope machine'
    Write-Host '    2) Install dari python.org ke C:\Python314 (centang Add to PATH + for all users),'
    Write-Host '       lalu jalankan installer ini sekali lagi.'
    Write-Host 'Jendela ini boleh ditutup.'
    exit 1
}
Write-Host ('Python : ' + $pyExe + ' ' + ($pyArgs -join ' '))
try { & $pyExe @pyArgs --version } catch { }

# 3) HENTIKAN SEMUA agent lama (di lokasi mana pun) & cabut autostart lama,
#    supaya tidak ada agent ganda / per-user / sisa instalasi lama.
try {
    Get-ScheduledTask -TaskName 'panel-agent' -ErrorAction SilentlyContinue | ForEach-Object {
        Stop-ScheduledTask -TaskName $_.TaskName -ErrorAction SilentlyContinue | Out-Null
        Unregister-ScheduledTask -TaskName $_.TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
    }
} catch { }
cmd.exe /c "schtasks /end /tn panel-agent >nul 2>nul" | Out-Null
cmd.exe /c "schtasks /delete /tn panel-agent /f >nul 2>nul" | Out-Null

# pengaman: hapus task lain (nama apa pun) yang menjalankan panel_agent.py / panel-agent
try {
    Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
        $a = $_.Actions | Select-Object -First 1
        $cmd = "$($a.Execute) $($a.Arguments)"
        ($cmd -like '*panel_agent.py*') -or ($cmd -like '*panel-agent*')
    } | Unregister-ScheduledTask -Confirm:$false -ErrorAction SilentlyContinue
} catch { }

# hapus nilai Run lama (HKCU + HKLM): nilai bernama panel-agent, plus nilai
# lain yang data-nya menunjuk ke panel_agent.py / panel-agent
foreach ($keyPath in @(
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run',
    'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run'
)) {
    if (Test-Path $keyPath) {
        Remove-ItemProperty -Path $keyPath -Name 'panel-agent' -ErrorAction SilentlyContinue
        try {
            $prop = Get-ItemProperty -Path $keyPath -ErrorAction SilentlyContinue
            if ($prop) {
                $prop.PSObject.Properties | Where-Object {
                    $_.Value -and (($_.Value -like '*panel_agent.py*') -or ($_.Value -like '*panel-agent*'))
                } | ForEach-Object {
                    Remove-ItemProperty -Path $keyPath -Name $_.Name -ErrorAction SilentlyContinue
                }
            }
        } catch { }
    }
}

# hentikan semua proses agent yang masih berjalan: skrip python (nama apa pun),
# exe legacy panel-agent, atau apa pun yang lokasinya di C:\nodelete.
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $nm = $_.Name
        $cl = $_.CommandLine
        $ep = $_.ExecutablePath
        (($nm -match '^(python|py)') -and ($cl -like '*panel_agent*')) -or
        ($nm -like 'panel-agent*') -or
        (($ep -like 'C:\nodelete\*') -and ($cl -like '*nodelete*'))
    } |
    ForEach-Object {
        try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
    }
Start-Sleep -Milliseconds 1200

# 3b) HAPUS salinan lama (rollout manual C:\nodelete + varian user-mode/legacy).
#     Proses sudah dimatikan dulu; bila masih gagal (file terkunci/ACL) dicoba
#     ulang beberapa kali dan dilaporkan supaya penyebabnya terlihat.
function Remove-AgentDir($p) {
    if (-not (Test-Path $p)) { return $true }
    for ($i = 1; $i -le 3; $i++) {
        try {
            (Get-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue).Attributes = 'Normal'
            Get-ChildItem -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
                $_.Attributes = 'Normal'
            }
        } catch { }
        cmd.exe /c "attrib -h -s -r `"$p`" /s /d >nul 2>nul" | Out-Null
        try {
            Remove-Item -Path $p -Recurse -Force -ErrorAction Stop
        } catch { }
        if (-not (Test-Path $p)) { return $true }
        cmd.exe /c "rd /s /q `"$p`" >nul 2>nul" | Out-Null
        if (-not (Test-Path $p)) { return $true }
        if ($i -lt 3) { Start-Sleep -Seconds 2 }
    }
    return $false
}

foreach ($p in @(
    'C:\nodelete',
    (Join-Path $env:LOCALAPPDATA 'PanelAgent'),
    (Join-Path $env:LOCALAPPDATA 'panel-agent'),
    (Join-Path $env:ProgramData 'panel-agent')
)) {
    if (-not (Test-Path $p)) { continue }
    if (Remove-AgentDir $p) {
        Write-Host ("Hapus " + $p + " -> OK")
    } else {
        Write-Host ("Hapus " + $p + " -> GAGAL (folder masih ada)")
        Get-ChildItem -Force $p -ErrorAction SilentlyContinue | Select-Object -First 5 |
            ForEach-Object { Write-Host ("   - masih ada: " + $_.FullName) }
    }
}
# bersihkan sisa unduhan bootstrap lama dari TEMP + VBS common-startup lama
if (Test-Path $env:TEMP) {
    Get-ChildItem $env:TEMP -Filter 'panel_agent_setup_*.py' -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
}
$commonVbs = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\StartUp\panel-agent.vbs'
if (Test-Path $commonVbs) { Remove-Item -Force $commonVbs -ErrorAction SilentlyContinue }

# 4) unduh script agent terbaru LANGSUNG ke lokasi instalasi permanen (bukan
#    TEMP): agent membaca agent.ini di sebelahnya -> token lama dipakai ulang
#    (update tanpa registrasi ulang / tanpa duplikat), dan file yang dijalankan
#    identik dengan yang dipakai tugas boot saat boot.
$dest = Join-Path $installDir 'panel_agent.py'
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
Write-Host 'Mengunduh panel_agent.py ...'
Invoke-WebRequest -Uri ($server + '/api/computers/agent-script') -OutFile $dest -UseBasicParsing

# 5) pasang autostart & konfigurasi agent (tugas boot-SYSTEM + registry Run + SMB):
#     Dijalankan sinkron (bukan background) agar exit code & error terlihat.
#     WAJIB admin: tanpa admin hasilnya hanya login-only (HKCU Run).
$isAdmin = $princ.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host 'PERINGATAN: BUKAN Administrator (UAC ditolak?) -> hasil hanya login-only.'
    Write-Host '  Klik kanan PowerShell > Run as Administrator, masukkan password admin, ulangi.'
}
Write-Host 'Memasang service dan konfigurasi autostart ...'
& $pyExe @pyArgs $dest --setup-autostart --server $server
$setupCode = $LASTEXITCODE
Write-Host ("setup-autostart exit code : " + $setupCode)

# 5b) VERIFIKASI pasif: pastikan tugas boot-SYSTEM benar-benar ada.
#     CATATAN: pembuatan tugas terjadwal TIDAK dilakukan di sini (pembuatan
#     dari dalam script unduhan-remote memicu blokir antivirus). Pembuatan
#     dikerjakan oleh agent Python (--setup-autostart di atas).
$taskOk = $false
try {
    $t = Get-ScheduledTask -TaskName 'panel-agent' -ErrorAction SilentlyContinue
    if ($t) { $taskOk = $true }
} catch { }
if (-not $taskOk) {
    Write-Host 'Task panel-agent TIDAK ditemukan setelah setup.'
    if ($setupCode -ne 0) {
        Write-Host ("  Penyebab paling umum: setup-autostart gagal (exit " + $setupCode + ").")
        Write-Host '  - exit 112 + "No installed Python found!" = py launcher tanpa runtime Python.'
        Write-Host '    Installer di atas SEHARUSNYA sudah menolak py rusak; bila masih lolos,'
        Write-Host '    install Python ke C:\Python314 lalu ulangi installer ini.'
        Write-Host '  - exit bukan 0 lainnya = Task diblokir AV/kebijakan, pythonw tidak absolut,'
        Write-Host '    file agent terkunci (agent lama masih jalan), atau Python user-local'
        Write-Host '    tak terbaca SYSTEM. Lihat traceback di atas untuk baris gagalnya.'
    } else {
        Write-Host '  setup-autostart exit 0 tapi task tidak ada: kemungkinan AV menghapus task,'
        Write-Host '  kebijakan GPO melarang Task Scheduler, atau path Python berspasi.'
        Write-Host '  Solusi: install Python ke C:\Python314 (tanpa spasi), lalu ulangi installer ini.'
    }
    try {
        $pyList = Get-Command py -ErrorAction SilentlyContinue
        if ($pyList) { Write-Host ('  diag py -0p:'); & $pyList.Source -0p 2>&1 | ForEach-Object { Write-Host ('    ' + $_) } }
    } catch { }
}

# 5c) ringkasan autostart apa adanya (jujur, bukan klaim sukses)
$hklmOk = $false
$vbsOk = $false
try {
    $rv = Get-ItemProperty -Path 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'panel-agent' -ErrorAction SilentlyContinue
    if ($rv) { $hklmOk = $true }
} catch { }
if (Test-Path $commonVbs) { $vbsOk = $true }
Write-Host '--- ringkasan autostart ---'
Write-Host ("  Tugas boot-SYSTEM     : " + $(if ($taskOk) { 'OK (boot/SYSTEM)' } else { 'GAGAL' }))
Write-Host ("  HKLM Run (semua user) : " + $(if ($hklmOk) { 'OK' } else { 'tidak ada' }))
Write-Host ("  Common Startup VBS    : " + $(if ($vbsOk) { 'OK' } else { 'tidak ada' }))
if (-not $taskOk) {
    Write-Host '  => Tanpa tugas boot, PC ini hanya login-only: agent TIDAK jalan sebelum ada user login.'
}

# 6) jalankan agent sekarang agar langsung mengirim heartbeat tanpa perlu reboot:
Write-Host 'Menjalankan agent ...'
try {
    Start-ScheduledTask -TaskName 'panel-agent' -ErrorAction SilentlyContinue | Out-Null
} catch { }
cmd.exe /c "schtasks /run /tn panel-agent >nul 2>nul" | Out-Null

Start-Sleep -Seconds 4

# Verifikasi proses agent sudah aktif
$agentProc = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    ($_.Name -match '^(python|py)') -and ($_.CommandLine -like '*panel_agent.py*')
}
if ($agentProc) {
    Write-Host 'Proses agent : OK (heartbeat akan masuk < 1 menit)'
} else {
    # Fallback sinkron foreground (bukan Hidden): tanpa jendela tersembunyi
    # agar tidak cocok dengan tanda tangan antivirus AMSI.
    # $pyExe di atas sudah tervalidasi --version, jadi kegagalan di sini
    # berarti agent crash / tidak bisa hubungi server, bukan Python hilang.
    Write-Host 'Task belum start -> jalankan agent sekali secara langsung ...'
    if ($setupCode -ne 0) { Write-Host ('  (catatan: setup-autostart exit ' + $setupCode + ' -> boot-task/HKLM/VBS mungkin parsial, cek ringkasan di atas)') }
    & $pyExe @pyArgs $dest --server $server --once-loop
    $fallbackCode = $LASTEXITCODE
    Start-Sleep -Seconds 3
    $agentProc2 = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        ($_.Name -match '^(python|py)') -and ($_.CommandLine -like '*panel_agent.py*')
    }
    if ($agentProc2) { Write-Host 'Proses agent : OK' }
    # --once-loop sekali-jalan lalu keluar: exit 0 + "heartbeat OK" = agent
    # sehat & server terjangkau, walau tidak ada proses persisten (task boot
    # masih GAGAL -> perbaiki Python machine-wide / Task agar persisten).
    elseif ($fallbackCode -eq 0) { Write-Host 'Proses agent : heartbeat OK sekali-jalan (agent sehat, tapi TIDAK persisten: Task boot masih GAGAL, PC login-only sampai task diperbaiki)' }
    else { Write-Host 'Proses agent : GAGAL dicek manual di Task Manager (cari pythonw + panel_agent.py)' }
}

Write-Host 'Selesai.'
Write-Host 'Cek di panel: Management Computer (badge boot/SYSTEM + HB / HB+AP).'
Write-Host ''
Write-Host 'Jendela ini boleh ditutup.'
"""


@router.get("/agent-install.ps1", response_class=PlainTextResponse)
def agent_install_script():
    """Bootstrap Windows gaya 'salin-link' (mirip curl | python3 di Linux).

    Berbasis Python (bukan .exe): mengunduh panel_agent.py, meminta elevate
    sekali, lalu memasang ke %ProgramData%\\PanelAgent + Task Scheduler SYSTEM
    AtStartup. PC yang sudah terdaftar (agent.ini ada) -> UPDATE memakai token
    lama (re-bind via MAC, tidak duplikat). PC kosong -> registrasi via MAC.
    """
    target_server = get_settings().panel_agent_server.rstrip("/")
    return PlainTextResponse(AGENT_INSTALL_PS1.replace("{{SERVER}}", target_server))


# ---------------------------------------------------------------- binary agent

AGENT_DIST_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "agent" / "dist"
)


def _agent_version() -> str:
    """Versi agent diambil dari AGENT_VERSION di panel_agent.py."""
    try:
        m = re.search(r'AGENT_VERSION\s*=\s*"([^"]+)"', AGENT_SCRIPT.read_text(encoding="utf-8"))
        return m.group(1) if m else "?"
    except OSError:
        return "?"


def _dist_artifacts() -> dict:
    """Hasil build PyInstaller di agent/dist (build-windows.bat menghasilkan .exe).

    Mengembalikan {"windows": Path|None, "linux": Path|None} — file terbaru
    dipilih jika ada lebih dari satu hasil build.
    """
    exe = None
    elf = None
    if AGENT_DIST_DIR.is_dir():
        files = sorted(
            (p for p in AGENT_DIST_DIR.iterdir() if p.is_file() and not p.name.startswith(".")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for p in files:
            if exe is None and p.suffix.lower() == ".exe":
                exe = p
            elif elf is None and p.suffix.lower() != ".exe":
                elf = p
    return {"windows": exe, "linux": elf}


@router.get("/agent-artifacts")
def agent_artifacts():
    """Daftar binary agent yang tersedia untuk diunduh (Windows .exe / Linux)."""
    arts = _dist_artifacts()
    out: dict = {"version": _agent_version()}
    for key, path in (("windows", arts["windows"]), ("linux", arts["linux"])):
        if path is None:
            out[key] = {"available": False}
        else:
            st = path.stat()
            out[key] = {
                "available": True,
                "filename": path.name,
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime, tz=datetime.now().astimezone().tzinfo).isoformat(),
            }
    return out


@router.get("/agent-download")
def agent_download(platform: str = "windows"):
    """Unduh binary agent hasil build. platform = windows | linux."""
    if platform not in ("windows", "linux"):
        raise HTTPException(status_code=400, detail="platform harus 'windows' atau 'linux'")

    path = _dist_artifacts()[platform]
    if path is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Binary agent belum ada di agent/dist/. Bangun dulu di PC Windows: "
                "jalankan agent/build-windows.bat (alasan server otomatis ditanam), "
                "lalu salin dist/panel-agent.exe ke agent/dist/ di server."
            ),
        )
    return FileResponse(path, filename=path.name)
