"""Topologi auto-check IP untuk komputer terkelola.

Status online komputer digabung dari DUA sumber:
  1. Heartbeat agent (sudah ada) — PC aktif mengirim data ke server.
  2. Cocok IP di inventori Access Point (hasil AP ping-monitor).
     Jika IP komputer (ip, wifi_ip, daftar interfaces) cocok dengan
     perangkat access_points berstatus ONLINE → komputer dianggap ONLINE,
     walau heartbeat sempat terblokir (mis. UFW saat IP berubah).

Tambahan "update IP dari hasil check": bila MAC komputer cocok dengan
perangkat ONLINE di inventory access_points, IP-komputer yang lama (basi)
diperbarui ke IP terkini yang tercatat di AP — menangani kasus PC pindah
WiFi atau WiFi <-> LAN sehingga IP-nya berubah.

Berjalan otomatis (scheduler di main.py) dan bisa dipicu manual (endpoint).
"""

import ipaddress
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..db.database import SessionLocal
from ..db.models import AccessPoint, ManagedComputer

log = logging.getLogger(__name__)

# Periode auto-check topologi di background (detik).
_CHECK_INTERVAL = int(os.environ.get("TOPOLOGY_CHECK_INTERVAL", "60"))
# Umur max (detik) bukti cocok-IP-AP agar komputer tetap dianggap online.
# Setelah lebih lama dari ini tanpa bukti baru, komputer balik offline.
_AP_EVIDENCE_TTL = int(os.environ.get("TOPOLOGY_AP_TTL", "120"))

_lock = threading.Lock()
_running = False
_last_run: datetime | None = None
_last_result = ""


def _valid(ip: str) -> bool:
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return False
    if addr.is_loopback or addr.is_link_local or addr.is_unspecified:
        return False
    return True


def _norm_mac(mac: str) -> str:
    return (mac or "").strip().lower().replace("-", ":")


def _collect_ips(c: ManagedComputer) -> list[str]:
    """Kumpulkan kandidat IP komputer (unik, valid, maks 6)."""
    ips: list[str] = []
    for raw in (c.ip, c.wifi_ip):
        raw = (raw or "").strip()
        if _valid(raw) and raw not in ips:
            ips.append(raw)
    try:
        extra = [i.get("ip", "") for i in json.loads(c.interfaces or "[]")]
    except (ValueError, TypeError):
        extra = []
    for raw in extra:
        raw = (raw or "").strip()
        if _valid(raw) and raw not in ips:
            ips.append(raw)
    return ips[:6]


def topology_check(db: Session, computer_ids: list[int] | None = None) -> dict:
    """Satu putaran pengecekan topologi (tanpa I/O jaringan — hanya baca
    tabel access_points yang sudah di-update AP ping-monitor, lalu tulis).

    Melakukan:
      - Untuk tiap komputer: online bila IP cocok perangkat ONLINE di AP.
      - Update IP komputer bila MAC cocok dengan perangkat ONLINE di AP.
      - Menyegarkan ap_seen_at sehingga status online gabungan tetap aktif.
    """
    now = datetime.utcnow()

    # Snapshot inventori AP (transaksi singkat).
    aps = db.query(AccessPoint).all()
    online_ips: set[str] = set()
    aps_by_mac: dict[str, AccessPoint] = {}
    for ap in aps:
        ip = (ap.ip or "").strip()
        if _valid(ip) and ap.status == "ONLINE":
            online_ips.add(ip)
        m = _norm_mac(ap.mac)
        if m:
            aps_by_mac.setdefault(m, ap)

    # Total perangkat ONLINE di inventory — bila 0, hasil "0 online" bukan
    # berarti semua PC mati, melainkan AP monitor belum memindai / basi.
    # Disampaikan sebagai `note` agar UI bisa memberi hint, bukan toast gagal.
    online_ap_total = sum(1 for ap in aps if ap.status == "ONLINE")

    q = db.query(ManagedComputer)
    if computer_ids:
        ids = list(dict.fromkeys(computer_ids))
        q = q.filter(ManagedComputer.id.in_(ids))
    computers = q.all()

    results: list[dict] = []
    updated_ip = 0
    now_online = 0
    for c in computers:
        # 1) Bukti STRONG: MAC cocok dgn perangkat ONLINE di AP → dapat IP terkini.
        mac_match = None
        cm = _norm_mac(c.mac)
        if cm:
            ap = aps_by_mac.get(cm)
            if ap is not None and ap.status == "ONLINE" and _valid(ap.ip):
                mac_match = ap

        # 2) Bukti LEMAH/standar: ada kandidat IP yg cocok dgn perangkat ONLINE.
        ip_match = False
        if mac_match is None:
            for ip in _collect_ips(c):
                if ip in online_ips:
                    ip_match = True
                    break

        matched_ap = mac_match
        online = matched_ap is not None or ip_match
        if online:
            c.ap_seen_at = now
            now_online += 1
            # Update IP komputer dari AP bila MAC cocok & IP berbeda/lebih baru.
            if matched_ap is not None and matched_ap.ip != (c.ip or "").strip():
                old = (c.ip or "").strip()
                c.ip = matched_ap.ip[:45]
                updated_ip += 1
                results.append({
                    "id": c.id,
                    "name": c.name or c.hostname or str(c.id),
                    "matched": "mac",
                    "ip_from": old or "-",
                    "ip_to": matched_ap.ip,
                    "ap_ip": matched_ap.ip,
                    "ap_status": matched_ap.status,
                })

    try:
        db.commit()
    except Exception:
        # Deadlock / pool timeout saat heartbeat + scan AP bersamaan:
        # batalkan tulis agar koneksi kembali ke pool, biarkan endpoint
        # mengubahnya jadi 503 yang jelas (bukan 500 misterius).
        db.rollback()
        raise

    global _last_run, _last_result
    _last_run = now
    _last_result = (
        f"{len(computers)} komputer dicek · {now_online} online (cocok IP AP) · "
        f"{updated_ip} IP diperbarui"
    )
    note = ""
    if online_ap_total == 0:
        note = (
            "Inventory Access Point tidak ada yang ONLINE — jalankan scan AP "
            "atau tunggu monitor AP, hasil 0 online belum tentu PC mati."
        )
    return {
        "checked": len(computers),
        "online_ap": now_online,
        "updated_ip": updated_ip,
        "updated": results,
        "last_run": now.isoformat() + "Z",
        "note": note,
    }


def run_check(computer_ids: list[int] | None = None) -> dict:
    """Panggil dari endpoint — endpoint yang membuka Session sendiri."""
    db = SessionLocal()
    try:
        return topology_check(db, computer_ids)
    finally:
        db.close()


def status_info() -> dict:
    return {
        "interval": _CHECK_INTERVAL,
        "ap_ttl": _AP_EVIDENCE_TTL,
        "running": _running,
        "last_run": _last_run.isoformat() + "Z" if _last_run else None,
        "last_result": _last_result,
    }


def _scheduler_loop(interval: int) -> None:
    global _running
    while True:
        time.sleep(interval)
        try:
            with _lock:
                if _running:
                    continue
                _running = True
            try:
                run_check()
            finally:
                with _lock:
                    _running = False
        except Exception:  # noqa: BLE001 — scheduler tidak boleh mati
            log.exception("topologi auto-check gagal")


def start_scheduler() -> None:
    threading.Thread(
        target=_scheduler_loop, args=(_CHECK_INTERVAL,), daemon=True,
        name="topology-check",
    ).start()


def evidence_ttl() -> int:
    return _AP_EVIDENCE_TTL
