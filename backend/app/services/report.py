import csv
import io
import json
import logging
import os
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import and_, func, literal, text, union_all
from sqlalchemy.orm import Session

from ..core.security import decrypt_secret, encrypt_secret
from ..db.models import (
    AppSetting,
    Camera,
    CameraEvent,
    ComputerMetricHourly,
    ComputerMetricSample,
    ComputerSpeedSample,
)
from . import computer_metrics
from .audit import record
from .backup import _cron_valid

log = logging.getLogger(__name__)

_KEYS = {
    "enabled": "report_enabled",
    "smtp_host": "report_smtp_host",
    "smtp_port": "report_smtp_port",
    "smtp_username": "report_smtp_username",
    "smtp_password": "report_smtp_password_enc",
    "smtp_tls": "report_smtp_tls",
    "smtp_ssl": "report_smtp_ssl",
    "from_addr": "report_from",
    "recipients": "report_recipients",
    "schedule": "report_schedule",
    "hours": "report_hours",
    "last_sent": "report_last_sent",
    "isp_download_mbps": "report_isp_download_mbps",
    "isp_upload_mbps": "report_isp_upload_mbps",
}

DEFAULT_SCHEDULE = "0 7 * * *"
DEFAULT_HOURS = 24


def _report_utc_offset() -> int:
    try:
        value = int(os.getenv("REPORT_UTC_OFFSET_HOURS", "7"))
    except ValueError:
        value = 7
    return max(-12, min(14, value))


def _report_tz_label(offset: int) -> str:
    labels = {7: "WIB", 8: "WITA", 9: "WIT"}
    label = labels.get(offset)
    if label:
        return f"{label} (UTC{offset:+d})"
    return f"UTC{offset:+d}"


def _raw(db: Session, name: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == _KEYS[name]).first()
    if row is None or not row.value_enc:
        return default
    return row.value_enc


def _set(db: Session, name: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == _KEYS[name]).first()
    if row is None:
        db.add(AppSetting(key=_KEYS[name], value_enc=value))
    else:
        row.value_enc = value
        row.updated_at = datetime.utcnow()


def _bool(db: Session, name: str, default: bool) -> bool:
    raw = _raw(db, name, "")
    if raw == "":
        return default
    return raw == "1"


def _optional_float(db: Session, name: str) -> float | None:
    raw = _raw(db, name, "")
    if raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _parse_recipients(raw: str) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except (ValueError, TypeError):
        pass
    return [x.strip() for x in raw.split(",") if x.strip()]


def get_report_config(db: Session) -> dict:
    try:
        port = int(_raw(db, "smtp_port", "587") or 587)
    except ValueError:
        port = 587
    try:
        hours = int(_raw(db, "hours", str(DEFAULT_HOURS)) or DEFAULT_HOURS)
    except ValueError:
        hours = DEFAULT_HOURS
    return {
        "enabled": _bool(db, "enabled", False),
        "smtp_host": _raw(db, "smtp_host", ""),
        "smtp_port": port,
        "smtp_username": _raw(db, "smtp_username", ""),
        "smtp_password": decrypt_secret(_raw(db, "smtp_password", "")),
        "smtp_tls": _bool(db, "smtp_tls", True),
        "smtp_ssl": _bool(db, "smtp_ssl", False),
        "from_addr": _raw(db, "from_addr", ""),
        "recipients": _parse_recipients(_raw(db, "recipients", "")),
        "schedule": _raw(db, "schedule", DEFAULT_SCHEDULE) or DEFAULT_SCHEDULE,
        "hours": max(1, min(hours, 24 * 30)),
        "last_sent": _raw(db, "last_sent", "") or None,
        "isp_download_mbps": _optional_float(db, "isp_download_mbps"),
        "isp_upload_mbps": _optional_float(db, "isp_upload_mbps"),
    }


def get_report_settings(db: Session) -> dict:
    cfg = get_report_config(db)
    cfg.pop("smtp_password", None)
    cfg["smtp_password_set"] = bool(
        _raw(db, "smtp_password", "")
    )
    return cfg


def save_report_settings(db: Session, data: dict, username: str) -> dict:
    host = str(data.get("smtp_host", "")).strip()
    try:
        port = int(data.get("smtp_port") or 587)
    except (TypeError, ValueError):
        raise ValueError("Port SMTP tidak valid")
    if not (1 <= port <= 65535):
        raise ValueError("Port SMTP di luar range")
    try:
        hours = int(data.get("hours") or DEFAULT_HOURS)
    except (TypeError, ValueError):
        raise ValueError("Rentang jam tidak valid")
    if not (1 <= hours <= 24 * 30):
        raise ValueError("Rentang jam harus 1 - 720")
    schedule = str(data.get("schedule", "")).strip() or DEFAULT_SCHEDULE
    if not _cron_valid(schedule):
        raise ValueError("Jadwal cron tidak valid (contoh: 0 7 * * *)")
    recipients = [
        str(x).strip()
        for x in (data.get("recipients") or [])
        if str(x).strip()
    ]
    for addr in recipients:
        if "@" not in addr:
            raise ValueError(f"Alamat email tidak valid: {addr}")
    if bool(data.get("smtp_tls")) and bool(data.get("smtp_ssl")):
        raise ValueError("Pilih salah satu: STARTTLS atau SSL")

    def _limit(value, label: str) -> float | None:
        if value is None or str(value).strip() == "":
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{label} tidak valid")
        if not (0 < parsed <= 100000):
            raise ValueError(f"{label} harus antara 0 dan 100000 Mbps")
        return parsed

    isp_download = _limit(
        data.get("isp_download_mbps"), "Batas download ISP"
    )
    isp_upload = _limit(data.get("isp_upload_mbps"), "Batas upload ISP")

    _set(db, "enabled", "1" if data.get("enabled") else "0")
    _set(db, "smtp_host", host)
    _set(db, "smtp_port", str(port))
    _set(db, "smtp_username", str(data.get("smtp_username", "")).strip())
    password = str(data.get("smtp_password", "") or "")
    if password:
        _set(db, "smtp_password", encrypt_secret(password))
    _set(db, "smtp_tls", "1" if data.get("smtp_tls") else "0")
    _set(db, "smtp_ssl", "1" if data.get("smtp_ssl") else "0")
    _set(db, "from_addr", str(data.get("from_addr", "")).strip())
    _set(db, "recipients", json.dumps(recipients))
    _set(db, "schedule", schedule)
    _set(db, "hours", str(hours))
    _set(
        db,
        "isp_download_mbps",
        "" if isp_download is None else str(isp_download),
    )
    _set(
        db,
        "isp_upload_mbps",
        "" if isp_upload is None else str(isp_upload),
    )
    record(db, username, "REPORT_SETTINGS", f"{len(recipients)} penerima", "SUCCESS")
    db.commit()
    return get_report_settings(db)


def reset_report_samples(db: Session, username: str) -> dict:
    """Hapus histori metrik PC dan speed test internet dari report."""
    deleted_raw = (
        db.query(ComputerMetricSample)
        .delete(synchronize_session=False)
    )
    deleted_hourly = (
        db.query(ComputerMetricHourly)
        .delete(synchronize_session=False)
    )
    deleted_speed = (
        db.query(ComputerSpeedSample)
        .delete(synchronize_session=False)
    )
    record(
        db,
        username,
        "REPORT_RESET",
        f"computer_metric_samples={deleted_raw}, "
        f"computer_metric_hourly={deleted_hourly}, "
        f"computer_speed_samples={deleted_speed}",
        "SUCCESS",
    )
    db.commit()
    return {
        "computer_metric_samples": deleted_raw,
        "computer_metric_hourly": deleted_hourly,
        "computer_speed_samples": deleted_speed,
        "reset_at": _iso(datetime.utcnow()),
    }


def mark_sent(db: Session) -> None:
    _set(db, "last_sent", _iso(datetime.utcnow()))
    db.commit()


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def _fmt_iso(value: str | None) -> str:
    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%d/%m %H:%M")
    except ValueError:
        return value


def _camera_problems(
    cams: list,
    events_by_cam: dict,
    prev_by_cam: dict,
    window_start: datetime,
    window_end: datetime,
) -> list[dict]:
    problems: list[dict] = []

    for cam in cams:
        events = events_by_cam.get(cam.id, [])
        prev = prev_by_cam.get(cam.id)
        state = None
        offset = None

        if prev is not None:
            state = prev.event
            if state == "OFFLINE":
                offset = window_start
        elif cam.status == "ONLINE":
            state = "ONLINE"
        elif cam.last_seen is not None and cam.last_seen >= window_start:
            state = "ONLINE"
        else:
            state = "OFFLINE"
            offset = window_start

        intervals: list[tuple[datetime, datetime, bool]] = []
        for event in events:
            if event.timestamp < window_start:
                continue
            if event.timestamp > window_end:
                break
            if event.event == "OFFLINE":
                if state != "OFFLINE":
                    state = "OFFLINE"
                    offset = max(event.timestamp, window_start)
            elif event.event == "ONLINE":
                if state == "OFFLINE" and offset is not None:
                    end = min(event.timestamp, window_end)
                    if end > offset:
                        intervals.append((offset, end, False))
                    state = "ONLINE"
                    offset = None

        currently_offline = cam.status != "ONLINE"
        if state == "OFFLINE" and offset is not None:
            end = window_end
            if end > offset:
                intervals.append((offset, end, True))
        elif not intervals and currently_offline:
            start = window_start
            if cam.last_seen is not None and cam.last_seen > window_start:
                start = cam.last_seen
            if window_end > start:
                intervals.append((start, window_end, True))

        if not intervals:
            continue

        downtime = []
        total = 0
        for start, end, ongoing in intervals:
            seconds = max(0, int((end - start).total_seconds()))
            total += seconds
            downtime.append(
                {
                    "start": _iso(start),
                    "end": _iso(end),
                    "seconds": seconds,
                    "ongoing": ongoing,
                }
            )
        problems.append(
            {
                "id": cam.id,
                "name": cam.name or "-",
                "ip": cam.ip or "-",
                "status": cam.status,
                "currently_offline": currently_offline,
                "downtime": downtime,
                "total_downtime_seconds": total,
                "last_seen": _iso(cam.last_seen),
            }
        )

    problems.sort(key=lambda p: p["total_downtime_seconds"], reverse=True)
    return problems


def build_camera_report(
    db: Session, window_start: datetime, window_end: datetime
) -> dict:
    cams = db.query(Camera).order_by(Camera.ip.asc()).all()
    events = (
        db.query(CameraEvent)
        .filter(CameraEvent.timestamp >= window_start)
        .filter(CameraEvent.timestamp <= window_end)
        .order_by(CameraEvent.timestamp.asc())
        .all()
    )
    events_by_cam: dict[int | None, list] = {}
    for event in events:
        events_by_cam.setdefault(event.camera_id, []).append(event)

    prev_by_cam: dict[int | None, object] = {}
    sub = (
        db.query(
            CameraEvent.camera_id,
            func.max(CameraEvent.timestamp).label("ts"),
        )
        .filter(CameraEvent.timestamp < window_start)
        .group_by(CameraEvent.camera_id)
        .subquery()
    )
    prev_rows = (
        db.query(CameraEvent)
        .join(
            sub,
            and_(
                CameraEvent.camera_id == sub.c.camera_id,
                CameraEvent.timestamp == sub.c.ts,
            ),
        )
        .all()
    )
    for event in prev_rows:
        prev_by_cam[event.camera_id] = event

    problems = _camera_problems(
        cams, events_by_cam, prev_by_cam, window_start, window_end
    )
    online_now = sum(1 for cam in cams if cam.status == "ONLINE")
    return {
        "total": len(cams),
        "normal": max(0, len(cams) - len(problems)),
        "problem_count": len(problems),
        "online_now": online_now,
        "offline_now": len(cams) - online_now,
        "problems": problems,
    }


def _report_date_expr(db: Session, column):
    offset = _report_utc_offset()
    if offset == 0:
        return func.date(column)
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        return func.date(column, f"{offset:+d} hours")
    if dialect == "postgresql":
        return func.date(
            column + text(f"interval '{offset} hours'")
        )
    return func.date(column)


def _as_naive_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        ).replace(tzinfo=None)
    except ValueError:
        return None


def build_available_dates(
    db: Session, days: int = 30, now: datetime | None = None
) -> dict:
    """Daftar tanggal yang masih memiliki histori metrik PC."""
    days = max(1, min(int(days), 90))
    now = now or datetime.utcnow()
    since = now - timedelta(days=days)

    sources = union_all(
        db.query(
            literal("raw").label("source"),
            ComputerMetricSample.computer_id.label("computer_id"),
            ComputerMetricSample.timestamp.label("ts"),
        )
        .filter(ComputerMetricSample.timestamp >= since)
        .filter(ComputerMetricSample.timestamp < now),
        db.query(
            literal("hourly").label("source"),
            ComputerMetricHourly.computer_id.label("computer_id"),
            ComputerMetricHourly.bucket.label("ts"),
        )
        .filter(ComputerMetricHourly.bucket >= since)
        .filter(ComputerMetricHourly.bucket < now),
        db.query(
            literal("speed").label("source"),
            ComputerSpeedSample.computer_id.label("computer_id"),
            ComputerSpeedSample.received_at.label("ts"),
        )
        .filter(ComputerSpeedSample.received_at >= since)
        .filter(ComputerSpeedSample.received_at < now),
    ).subquery()

    day_expr = _report_date_expr(db, sources.c.ts)
    grouped = (
        db.query(
            day_expr.label("day"),
            sources.c.source.label("source"),
            func.count(sources.c.ts).label("samples"),
            func.min(sources.c.ts).label("first_ts"),
            func.max(sources.c.ts).label("last_ts"),
        )
        .group_by(day_expr, sources.c.source)
        .all()
    )
    computers = {
        str(row.day): int(row.computers or 0)
        for row in (
            db.query(
                day_expr.label("day"),
                func.count(
                    func.distinct(sources.c.computer_id)
                ).label("computers"),
            )
            .group_by(day_expr)
            .all()
        )
    }

    merged: dict[str, dict] = {}
    for row in grouped:
        day = str(row.day)
        item = merged.setdefault(
            day,
            {
                "date": day,
                "computers": computers.get(day, 0),
                "raw_samples": 0,
                "hourly_buckets": 0,
                "speed_samples": 0,
                "has_raw": False,
                "has_hourly": False,
                "has_speed": False,
                "first_ts": None,
                "last_ts": None,
            },
        )
        sample_count = int(row.samples or 0)
        if row.source == "raw":
            item["raw_samples"] = sample_count
            item["has_raw"] = sample_count > 0
        elif row.source == "hourly":
            item["hourly_buckets"] = sample_count
            item["has_hourly"] = sample_count > 0
        elif row.source == "speed":
            item["speed_samples"] = sample_count
            item["has_speed"] = sample_count > 0

        first = _as_naive_datetime(row.first_ts)
        last = _as_naive_datetime(row.last_ts)
        current_first = item["first_ts"]
        current_last = item["last_ts"]
        if first is not None and (
            current_first is None or first < current_first
        ):
            item["first_ts"] = first
        if last is not None and (
            current_last is None or last > current_last
        ):
            item["last_ts"] = last

    dates = []
    for day in sorted(merged.keys(), reverse=True):
        item = merged[day]
        item["first_ts"] = _iso(item["first_ts"])
        item["last_ts"] = _iso(item["last_ts"])
        dates.append(item)

    offset = _report_utc_offset()
    return {
        "generated_at": _iso(now),
        "days": days,
        "timezone": _report_tz_label(offset),
        "retention": {
            "raw_hours": computer_metrics.RAW_RETENTION_HOURS,
            "rollup_days": computer_metrics.ROLLUP_RETENTION_DAYS,
            "speed_days": computer_metrics.SPEED_RETENTION_DAYS,
        },
        "dates": dates,
    }


def build_report(db: Session, hours: int = DEFAULT_HOURS) -> dict:
    hours = max(1, min(int(hours), 24 * 30))
    now = datetime.utcnow()
    start = now - timedelta(hours=hours)
    cfg = get_report_config(db)
    speed = computer_metrics.summarize_speed_window(
        db,
        hours,
        limit=5,
        now=now,
        isp_download_mbps=cfg.get("isp_download_mbps"),
        isp_upload_mbps=cfg.get("isp_upload_mbps"),
    )

    return {
        "generated_at": _iso(now),
        "window_start": _iso(start),
        "window_end": _iso(now),
        "hours": hours,
        "computers": computer_metrics.summarize_window(
            db, hours, limit=5, now=now
        ),
        "speed": speed,
        "cctv": build_camera_report(db, start, now),
    }


def report_to_csv(report: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["REPORT"])
    writer.writerow(["Dibuat", _fmt_iso(report["generated_at"])])
    writer.writerow(
        [
            "Periode",
            f'{_fmt_iso(report["window_start"])} s/d {_fmt_iso(report["window_end"])}',
        ]
    )
    writer.writerow([])

    computers = report.get("computers") or {}
    net = computers.get("net") or {}
    writer.writerow(["METRIK PC", f'{report["hours"]} jam'])
    writer.writerow(["Metrik", "Rata-rata", "Min", "Maks"])
    for label, key in (
        ("CPU (%)", "cpu"),
        ("RAM (%)", "ram"),
    ):
        stat = computers.get(key) or {}
        writer.writerow(
            [
                label,
                stat.get("avg"),
                stat.get("min"),
                stat.get("max"),
            ]
        )
    writer.writerow(
        ["Download (byte/detik)", net.get("rx_avg_rate", 0)]
    )
    writer.writerow(
        ["Upload (byte/detik)", net.get("tx_avg_rate", 0)]
    )
    writer.writerow(
        ["Total download PC (byte)", net.get("rx_total_bytes", 0)]
    )
    writer.writerow(
        ["Total upload PC (byte)", net.get("tx_total_bytes", 0)]
    )
    writer.writerow(["Jumlah PC online", computers.get("online", 0)])
    writer.writerow(
        ["Jumlah PC dengan data", computers.get("with_data", 0)]
    )
    writer.writerow(["Jumlah sampel", computers.get("sample_count", 0)])
    writer.writerow([])

    writer.writerow(
        [
            "KOMPUTER BEBAN TERTINGGI",
            f'Top {len(computers.get("top", []))} dari '
            f'{computers.get("total", 0)} komputer',
        ]
    )
    writer.writerow(
        [
            "Peringkat",
            "Komputer",
            "IP",
            "Grup",
            "CPU rata-rata (%)",
            "CPU puncak (%)",
            "RAM rata-rata (%)",
            "RAM puncak (%)",
            "Sampel",
        ]
    )
    for index, computer in enumerate(computers.get("top", []), start=1):
        writer.writerow(
            [
                index,
                computer.get("name") or computer.get("hostname"),
                computer.get("ip"),
                computer.get("group_name"),
                computer.get("cpu_avg"),
                computer.get("cpu_max"),
                computer.get("ram_avg"),
                computer.get("ram_max"),
                computer.get("samples"),
            ]
        )
    if not computers.get("top"):
        writer.writerow(["Belum ada data histori komputer"])
    writer.writerow(["Total komputer", computers.get("total", 0)])
    writer.writerow(["Komputer online", computers.get("online", 0)])
    writer.writerow(["Komputer dengan data", computers.get("with_data", 0)])
    writer.writerow([])

    speed = report.get("speed") or {}
    isp = speed.get("isp") or {}
    writer.writerow(
        [
            "SPEEDTEST PC → INTERNET",
            f'{speed.get("hours", report["hours"])} jam',
        ]
    )
    writer.writerow(["Rata-rata download (Mbps)", speed.get("avg_download_mbps")])
    writer.writerow(["Rata-rata upload (Mbps)", speed.get("avg_upload_mbps")])
    writer.writerow(["Rata-rata skor gabungan (Mbps)", speed.get("avg_score_mbps")])
    writer.writerow(["Jumlah sampel", speed.get("sample_count", 0)])
    writer.writerow(
        ["Komputer dengan data", speed.get("computers_with_data", 0)]
    )
    writer.writerow(["Batas download ISP (Mbps)", isp.get("download_mbps")])
    writer.writerow(["Batas upload ISP (Mbps)", isp.get("upload_mbps")])
    writer.writerow(["Puncak download (Mbps)", isp.get("peak_download_mbps")])
    writer.writerow(["Puncak upload (Mbps)", isp.get("peak_upload_mbps")])
    writer.writerow(["Utilisasi batas ISP (%)", isp.get("utilization_pct")])
    writer.writerow(["Status batas ISP", isp.get("status")])
    writer.writerow([])

    speed_headers = [
        "Peringkat",
        "Komputer",
        "Grup",
        "Jalur",
        "Rata-rata download (Mbps)",
        "Rata-rata upload (Mbps)",
        "Skor gabungan (Mbps)",
        "Sampel",
        "Tes terakhir",
    ]
    for title, key in (
        ("5 PC TERCEPAT", "top_fastest"),
        ("5 PC PALING LAMBAT", "top_slowest"),
    ):
        writer.writerow([title])
        writer.writerow(speed_headers)
        rows = speed.get(key) or []
        for index, computer in enumerate(rows, start=1):
            writer.writerow(
                [
                    index,
                    computer.get("name") or computer.get("hostname"),
                    computer.get("group_name"),
                    computer.get("server_reach") or computer.get("conn_type"),
                    computer.get("avg_download_mbps"),
                    computer.get("avg_upload_mbps"),
                    computer.get("score"),
                    computer.get("samples"),
                    _fmt_iso(computer.get("last_tested_at")),
                ]
            )
        if not rows:
            writer.writerow(["Belum ada data speed test"])
        writer.writerow([])

    writer.writerow(["REKOR BANDWIDTH 24 JAM"])
    writer.writerow(
        ["Jenis", "Komputer", "Download (Mbps)", "Upload (Mbps)", "Waktu"]
    )
    for label, key in (
        ("Tertinggi", "peak"),
        ("Terendah", "lowest"),
    ):
        item = speed.get(key)
        if not item:
            writer.writerow([label, "Belum ada data"])
            continue
        writer.writerow(
            [
                label,
                item.get("name") or item.get("hostname"),
                item.get("download_mbps"),
                item.get("upload_mbps"),
                _fmt_iso(item.get("received_at") or item.get("tested_at")),
            ]
        )
    writer.writerow([])

    cctv = report["cctv"]
    writer.writerow(["CCTV"])
    writer.writerow(["Total", cctv.get("total", 0)])
    writer.writerow(["Normal", cctv.get("normal", 0)])
    writer.writerow(["Bermasalah", cctv.get("problem_count", 0)])
    writer.writerow(["Online sekarang", cctv.get("online_now", 0)])
    writer.writerow(["Offline sekarang", cctv.get("offline_now", 0)])
    writer.writerow([])
    if cctv.get("problems"):
        writer.writerow(
            ["IP", "Nama", "Status", "Rentang mati", "Total durasi (detik)"]
        )
        for problem in cctv["problems"]:
            ranges = "; ".join(
                f'{_fmt_iso(d["start"])} s/d '
                f'{"sekarang" if d["ongoing"] else _fmt_iso(d["end"])}'
                for d in problem["downtime"]
            )
            writer.writerow(
                [
                    problem["ip"],
                    problem["name"],
                    problem["status"],
                    ranges,
                    problem["total_downtime_seconds"],
                ]
            )
    else:
        writer.writerow(["Semua kamera normal"])
    writer.writerow([])
    writer.writerow(["Keterangan", "Waktu ditampilkan dalam zona waktu server"])
    return buf.getvalue()


def report_to_pdf(report: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=18 * mm,
        title="Report",
        author="Server Manager",
    )
    styles = getSampleStyleSheet()
    styles["Title"].fontSize = 20
    styles["Title"].leading = 24
    styles["Title"].spaceAfter = 0
    styles["Heading2"].fontSize = 11
    styles["Heading2"].textColor = colors.HexColor("#0f172a")
    styles["Heading2"].spaceBefore = 8
    styles["Heading2"].spaceAfter = 4
    styles["Normal"].fontSize = 9
    styles["Normal"].leading = 12
    styles["Normal"].textColor = colors.HexColor("#334155")
    cell = ParagraphStyle(
        "ReportCell",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
    )

    cctv = report["cctv"]
    computers = report.get("computers") or {}
    net = computers.get("net") or {}
    hours = report["hours"]

    story = [
        Paragraph("Report", styles["Title"]),
        Paragraph(
            f'Periode {hours} jam &nbsp;&bull;&nbsp; '
            f'{_fmt_iso(report["window_start"])} s/d '
            f'{_fmt_iso(report["window_end"])} &nbsp;&bull;&nbsp; '
            f'Dibuat {_fmt_iso(report["generated_at"])}',
            styles["Normal"],
        ),
        Spacer(1, 4 * mm),
    ]

    summary_table = Table(
        [
            [
                "CPU rata-rata PC",
                "RAM rata-rata PC",
                "Download PC",
                "CCTV normal",
            ],
            [
                f'{_num((computers.get("cpu") or {}).get("avg"))}%',
                f'{_num((computers.get("ram") or {}).get("avg"))}%',
                _bytes(net.get("rx_total_bytes", 0)),
                f'{cctv.get("normal", 0)}/{cctv.get("total", 0)}',
            ],
        ],
        colWidths=[45 * mm] * 4,
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#475569")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 1), (-1, 1), 15),
                ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#0f172a")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 3 * mm))

    metric_rows = [["Metrik", "Rata-rata", "Min", "Maks"]]
    for label, key in (
        ("CPU PC (%)", "cpu"),
        ("RAM PC (%)", "ram"),
    ):
        stat = computers.get(key) or {}
        metric_rows.append(
            [
                label,
                _num(stat.get("avg")),
                _num(stat.get("min")),
                _num(stat.get("max")),
            ]
        )
    metric_rows.append(
        [
            "Download (B/s)",
            _num(net.get("rx_avg_rate")),
            "-",
            "-",
        ]
    )
    metric_rows.append(
        [
            "Upload (B/s)",
            _num(net.get("tx_avg_rate")),
            "-",
            "-",
        ]
    )
    _add_table(story, f"Metrik PC ({hours} jam)", metric_rows, styles)
    story.append(
        Paragraph(
            f'Total download PC: {_bytes(net.get("rx_total_bytes", 0))} '
            f'&nbsp;&nbsp; Total upload PC: '
            f'{_bytes(net.get("tx_total_bytes", 0))} '
            f'&nbsp;&nbsp; PC online: {computers.get("online", 0)} '
            f'&nbsp;&nbsp; Sampel: {computers.get("sample_count", 0)}',
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("5 Komputer Beban Tertinggi", styles["Heading2"]))
    story.append(
        Paragraph(
            f'Diurutkan berdasarkan rata-rata beban CPU dan RAM '
            f'selama {hours} jam terakhir.',
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 1.5 * mm))
    top_computers = computers.get("top") or []
    if top_computers:
        rows = [
            [
                "#",
                "Komputer",
                "Grup",
                "CPU rata-rata",
                "CPU puncak",
                "RAM rata-rata",
                "RAM puncak",
            ]
        ]
        for index, computer in enumerate(top_computers, start=1):
            name = computer.get("name") or computer.get("hostname") or "-"
            group = computer.get("group_name") or "-"
            rows.append(
                [
                    str(index),
                    Paragraph(_pdf_text(name), cell),
                    Paragraph(_pdf_text(group), cell),
                    f'{_num(computer.get("cpu_avg"))}%',
                    f'{_num(computer.get("cpu_max"))}%',
                    f'{_num(computer.get("ram_avg"))}%',
                    f'{_num(computer.get("ram_max"))}%',
                ]
            )
        top_table = Table(
            rows,
            colWidths=[
                8 * mm,
                60 * mm,
                28 * mm,
                22 * mm,
                20 * mm,
                22 * mm,
                20 * mm,
            ],
            repeatRows=1,
        )
        top_table.setStyle(_table_style(colors))
        story.append(top_table)
        story.append(Spacer(1, 1.5 * mm))
        story.append(
            Paragraph(
                f'Total komputer: {computers.get("total", 0)} '
                f'&nbsp;&bull;&nbsp; Online: {computers.get("online", 0)} '
                f'&nbsp;&bull;&nbsp; Memiliki data: '
                f'{computers.get("with_data", 0)}',
                styles["Normal"],
            )
        )
    else:
        story.append(
            Paragraph(
                "Belum ada data histori komputer. Sampel mulai dikumpulkan "
                "saat agent mengirim heartbeat.",
                styles["Normal"],
            )
        )
    story.append(Spacer(1, 4 * mm))

    speed = report.get("speed") or {}
    isp = speed.get("isp") or {}
    story.append(
        Paragraph(
            f"Speedtest PC → Internet ({speed.get('hours', hours)} jam)",
            styles["Heading2"],
        )
    )
    story.append(
        Paragraph(
            f'Rata-rata download: {_mbps(speed.get("avg_download_mbps"))} '
            f'&nbsp;&bull;&nbsp; upload: {_mbps(speed.get("avg_upload_mbps"))} '
            f'&nbsp;&bull;&nbsp; skor gabungan: '
            f'{_mbps(speed.get("avg_score_mbps"))} '
            f'&nbsp;&bull;&nbsp; sampel: {speed.get("sample_count", 0)}',
            styles["Normal"],
        )
    )
    isp_status = {
        "safe": "Aman",
        "near": "Mendekati batas",
        "over": "Melewati batas",
        "unset": "Belum diatur",
    }.get(isp.get("status"), "Belum diatur")
    story.append(
        Paragraph(
            f'Batas ISP: {_mbps(isp.get("download_mbps"))} download / '
            f'{_mbps(isp.get("upload_mbps"))} upload &nbsp;&bull;&nbsp; '
            f'puncak {_mbps(isp.get("peak_download_mbps"))} / '
            f'{_mbps(isp.get("peak_upload_mbps"))} &nbsp;&bull;&nbsp; '
            f'utilisasi {_num(isp.get("utilization_pct"))}% '
            f'({isp_status})',
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 1.5 * mm))

    speed_headers = [
        "#",
        "Komputer",
        "Grup",
        "Jalur",
        "Download",
        "Upload",
        "Skor",
        "Sampel",
    ]
    for title, key in (
        ("5 PC Tercepat", "top_fastest"),
        ("5 PC Paling Lambat", "top_slowest"),
    ):
        story.append(Paragraph(title, styles["Heading2"]))
        speed_rows = [speed_headers]
        for index, item in enumerate(speed.get(key) or [], start=1):
            speed_rows.append(
                [
                    str(index),
                    Paragraph(
                        _pdf_text(item.get("name") or item.get("hostname")),
                        cell,
                    ),
                    Paragraph(_pdf_text(item.get("group_name")), cell),
                    Paragraph(
                        _pdf_text(
                            item.get("server_reach")
                            or item.get("conn_type")
                        ),
                        cell,
                    ),
                    _mbps(item.get("avg_download_mbps")),
                    _mbps(item.get("avg_upload_mbps")),
                    _mbps(item.get("score")),
                    str(item.get("samples", 0)),
                ]
            )
        if len(speed_rows) == 1:
            story.append(Paragraph("Belum ada data speed test.", styles["Normal"]))
        else:
            speed_table = Table(
                speed_rows,
                colWidths=[
                    8 * mm,
                    44 * mm,
                    26 * mm,
                    20 * mm,
                    24 * mm,
                    24 * mm,
                    22 * mm,
                    12 * mm,
                ],
                repeatRows=1,
            )
            speed_table.setStyle(_table_style(colors))
            story.append(speed_table)
        story.append(Spacer(1, 1.5 * mm))

    story.append(
        Paragraph(f"Rekor Bandwidth {hours} Jam", styles["Heading2"])
    )
    record_rows = [["Jenis", "Komputer", "Download", "Upload", "Waktu"]]
    for label, key in (("Tertinggi", "peak"), ("Terendah", "lowest")):
        item = speed.get(key)
        if not item:
            record_rows.append([label, "Belum ada data", "-", "-", "-"])
            continue
        record_rows.append(
            [
                label,
                Paragraph(
                    _pdf_text(item.get("name") or item.get("hostname")), cell
                ),
                _mbps(item.get("download_mbps")),
                _mbps(item.get("upload_mbps")),
                _fmt_iso(item.get("received_at") or item.get("tested_at")),
            ]
        )
    record_table = Table(
        record_rows,
        colWidths=[20 * mm, 62 * mm, 28 * mm, 28 * mm, 42 * mm],
        repeatRows=1,
    )
    record_table.setStyle(_table_style(colors))
    story.append(record_table)
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("CCTV", styles["Heading2"]))
    story.append(
        Paragraph(
            f'Total {cctv.get("total", 0)} &bull; '
            f'{cctv.get("normal", 0)} normal &bull; '
            f'{cctv.get("problem_count", 0)} bermasalah',
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 1.5 * mm))
    if cctv.get("problems"):
        rows = [["IP", "Nama", "Status", "Rentang mati", "Durasi"]]
        for problem in cctv["problems"]:
            ranges = "; ".join(
                f'{_fmt_iso(d["start"])} - '
                f'{"sekarang" if d["ongoing"] else _fmt_iso(d["end"])}'
                for d in problem["downtime"]
            )
            rows.append(
                [
                    Paragraph(_pdf_text(problem["ip"]), cell),
                    Paragraph(_pdf_text(problem["name"]), cell),
                    "Offline"
                    if problem["currently_offline"]
                    else "Pernah mati",
                    Paragraph(_pdf_text(ranges), cell),
                    _duration(problem["total_downtime_seconds"]),
                ]
            )
        table = Table(
            rows,
            colWidths=[24 * mm, 38 * mm, 20 * mm, 70 * mm, 28 * mm],
            repeatRows=1,
        )
        table.setStyle(_table_style(colors))
        story.append(table)
    else:
        story.append(Paragraph("Semua kamera normal.", styles["Normal"]))

    def _footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#e2e8f0"))
        canvas.line(15 * mm, 13 * mm, A4[0] - 15 * mm, 13 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(15 * mm, 9 * mm, "Server Manager - Report")
        canvas.drawRightString(
            A4[0] - 15 * mm,
            9 * mm,
            f"Halaman {document.page}",
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()

def _pdf_text(value) -> str:
    from xml.sax.saxutils import escape

    return escape(str(value or "-"))


def _num(value) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"


def _mbps(value) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f} Mbps"
    except (TypeError, ValueError):
        return "-"


def _bytes(value) -> str:
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return "0 B"


def _duration(seconds) -> str:
    try:
        seconds = int(seconds or 0)
    except (TypeError, ValueError):
        seconds = 0
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}h {hours}j {minutes}m"
    if hours:
        return f"{hours}j {minutes}m"
    return f"{minutes}m"


def _table_style(colors):
    from reportlab.platypus import TableStyle

    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.HexColor("#0f172a")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, -1),
                [colors.white, colors.HexColor("#f8fafc")],
            ),
        ]
    )


def _add_table(story, title: str, rows: list[list], styles) -> None:
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer, Table

    story.append(Paragraph(title, styles["Heading2"]))
    ncols = len(rows[0]) if rows else 2
    if ncols == 2:
        widths = [50 * mm, 130 * mm]
    else:
        widths = [40 * mm] + [140 * mm / (ncols - 1)] * (ncols - 1)
    table = Table(rows, colWidths=widths)
    table.setStyle(_table_style(colors))
    story.append(table)
    story.append(Spacer(1, 2 * mm))


def _report_text(report: dict) -> str:
    cctv = report["cctv"]
    computers = report.get("computers") or {}
    net = computers.get("net") or {}
    lines = [
        "REPORT KOMPUTER",
        f'Dibuat: {_fmt_iso(report["generated_at"])}',
        f'Periode: {_fmt_iso(report["window_start"])} s/d {_fmt_iso(report["window_end"])}',
        "",
        f'METRIK PC ({report["hours"]} jam)',
        f'CPU rata-rata: {_num((computers.get("cpu") or {}).get("avg"))}%',
        f'RAM rata-rata: {_num((computers.get("ram") or {}).get("avg"))}%',
        f'Download: {_bytes(net.get("rx_total_bytes", 0))} '
        f'({_bytes(net.get("rx_avg_rate", 0))}/s)',
        f'Upload: {_bytes(net.get("tx_total_bytes", 0))} '
        f'({_bytes(net.get("tx_avg_rate", 0))}/s)',
        "",
        f'KOMPUTER BEBAN TERTINGGI (dari {computers.get("total", 0)} komputer)',
        f'Online: {computers.get("online", 0)} | '
        f'Dengan data: {computers.get("with_data", 0)}',
    ]
    for index, computer in enumerate(computers.get("top", []), start=1):
        lines.append(
            f'{index}. {computer.get("name")} ({computer.get("ip")}) - '
            f'CPU {_num(computer.get("cpu_avg"))}% '
            f'(puncak {_num(computer.get("cpu_max"))}%), '
            f'RAM {_num(computer.get("ram_avg"))}% '
            f'(puncak {_num(computer.get("ram_max"))}%)'
        )
    if not computers.get("top"):
        lines.append("Belum ada data histori komputer.")

    speed = report.get("speed") or {}
    isp = speed.get("isp") or {}
    isp_status = {
        "safe": "Aman",
        "near": "Mendekati batas",
        "over": "Melewati batas",
        "unset": "Belum diatur",
    }.get(isp.get("status"), "Belum diatur")
    lines.extend(
        [
            "",
            f'SPEEDTEST PC → INTERNET ({speed.get("hours", report["hours"])} jam)',
            f'Rata-rata download: {_mbps(speed.get("avg_download_mbps"))}',
            f'Rata-rata upload: {_mbps(speed.get("avg_upload_mbps"))}',
            f'Rata-rata skor gabungan: {_mbps(speed.get("avg_score_mbps"))}',
            f'Sampel: {speed.get("sample_count", 0)} | '
            f'Komputer dengan data: {speed.get("computers_with_data", 0)}',
            f'Batas ISP: {_mbps(isp.get("download_mbps"))} download / '
            f'{_mbps(isp.get("upload_mbps"))} upload',
            f'Puncak: {_mbps(isp.get("peak_download_mbps"))} download / '
            f'{_mbps(isp.get("peak_upload_mbps"))} upload | '
            f'Utilisasi {_num(isp.get("utilization_pct"))}% ({isp_status})',
        ]
    )
    for title, key in (
        ("5 PC TERCEPAT", "top_fastest"),
        ("5 PC PALING LAMBAT", "top_slowest"),
    ):
        lines.append("")
        lines.append(title)
        rows = speed.get(key) or []
        for index, item in enumerate(rows, start=1):
            lines.append(
                f'{index}. {item.get("name")} - '
                f'D {_mbps(item.get("avg_download_mbps"))} / '
                f'U {_mbps(item.get("avg_upload_mbps"))} '
                f'(skor {_mbps(item.get("score"))}, '
                f'{item.get("samples", 0)} sampel)'
            )
        if not rows:
            lines.append("Belum ada data speed test.")
    lines.append("")
    lines.append(f'REKOR BANDWIDTH {report["hours"]} JAM')
    for label, key in (("Tertinggi", "peak"), ("Terendah", "lowest")):
        item = speed.get(key)
        if not item:
            lines.append(f"- {label}: belum ada data")
            continue
        lines.append(
            f'- {label}: {item.get("name")} - '
            f'D {_mbps(item.get("download_mbps"))} / '
            f'U {_mbps(item.get("upload_mbps"))} pada '
            f'{_fmt_iso(item.get("received_at") or item.get("tested_at"))}'
        )
    lines.extend(
        [
            "",
            f'CCTV: Total {cctv.get("total", 0)} | '
            f'Normal {cctv.get("normal", 0)} | '
            f'Bermasalah {cctv.get("problem_count", 0)}',
        ]
    )
    for problem in cctv.get("problems", []):
        ranges = ", ".join(
            f'{_fmt_iso(d["start"])} - '
            f'{"sekarang" if d["ongoing"] else _fmt_iso(d["end"])}'
            for d in problem["downtime"]
        )
        lines.append(
            f'- {problem["ip"]} ({problem["name"]}): {ranges} '
            f'({_duration(problem["total_downtime_seconds"])})'
        )
    return "\n".join(lines)


def _smtp_host(cfg: dict) -> str:
    return str(cfg.get("smtp_host") or "").strip()


def _smtp_port(cfg: dict) -> int:
    try:
        port = int(cfg.get("smtp_port") or 587)
    except (TypeError, ValueError):
        raise ValueError("Port SMTP tidak valid")
    if not (1 <= port <= 65535):
        raise ValueError("Port SMTP di luar range")
    return port


def _gmail_config(cfg: dict) -> bool:
    host = _smtp_host(cfg).lower()
    username = str(cfg.get("smtp_username") or "").strip().lower()
    return "gmail" in host or username.endswith("@gmail.com")


def _smtp_error_message(exc: Exception, cfg: dict) -> str:
    host = _smtp_host(cfg) or "SMTP"
    port = cfg.get("smtp_port") or 587
    gmail = _gmail_config(cfg)
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        if gmail:
            return (
                "Autentikasi Gmail gagal. Aktifkan verifikasi 2 langkah, "
                "buat App Password 16 karakter, lalu gunakan App Password "
                "itu sebagai password SMTP (bukan password login Gmail)."
            )
        return "Autentikasi SMTP gagal. Periksa username dan password."
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        if gmail:
            return (
                "Gmail memutus koneksi saat login. Gunakan App Password "
                "16 karakter (bukan password login Gmail) dan pastikan "
                "verifikasi 2 langkah aktif."
            )
        return "Server SMTP memutus koneksi. Periksa host, port, dan mode keamanan."
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "Server SMTP menolak alamat penerima."
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "Server SMTP menolak alamat pengirim."
    if isinstance(exc, smtplib.SMTPDataError):
        return "Server SMTP menolak isi email."
    if isinstance(
        exc,
        (
            smtplib.SMTPConnectError,
            ConnectionRefusedError,
            TimeoutError,
            OSError,
        ),
    ):
        return (
            f"Tidak dapat terhubung ke {host}:{port}. "
            "Periksa host, port, dan jaringan."
        )
    if isinstance(exc, smtplib.SMTPException):
        return f"Koneksi SMTP gagal: {exc}"
    return f"Koneksi SMTP gagal: {exc}"


def _open_smtp(cfg: dict):
    host = _smtp_host(cfg)
    if not host:
        raise ValueError("SMTP host belum diatur")
    port = _smtp_port(cfg)
    if cfg.get("smtp_tls") and cfg.get("smtp_ssl"):
        raise ValueError("Pilih salah satu: STARTTLS atau SSL")
    server = None
    try:
        if cfg.get("smtp_ssl"):
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.ehlo()
            if cfg.get("smtp_tls"):
                server.starttls()
                server.ehlo()
        return server
    except Exception as exc:
        if server is not None:
            try:
                server.close()
            except Exception:
                pass
        raise ValueError(_smtp_error_message(exc, cfg)) from exc


def _close_smtp(server) -> None:
    if server is None:
        return
    try:
        server.quit()
    except Exception:
        try:
            server.close()
        except Exception:
            pass


def test_smtp_connection(cfg: dict) -> dict:
    host = _smtp_host(cfg)
    if not host:
        raise ValueError("SMTP host belum diatur")
    port = _smtp_port(cfg)
    username = str(cfg.get("smtp_username") or "").strip()
    password = str(cfg.get("smtp_password") or "")
    if username and not password:
        raise ValueError("Password SMTP belum diatur")
    server = _open_smtp(cfg)
    try:
        if username:
            server.login(username, password)
        server.noop()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(_smtp_error_message(exc, cfg)) from exc
    finally:
        _close_smtp(server)
    return {
        "ok": True,
        "message": f"Koneksi SMTP ke {host}:{port} berhasil",
    }


def _smtp_test_config(db: Session, data: dict) -> dict:
    cfg = get_report_config(db)
    for name in (
        "smtp_host",
        "smtp_port",
        "smtp_username",
        "smtp_tls",
        "smtp_ssl",
        "from_addr",
    ):
        if name in data and data[name] is not None:
            cfg[name] = data[name]
    password = str(data.get("smtp_password") or "")
    if password:
        cfg["smtp_password"] = password
    return cfg


def test_smtp_settings(db: Session, data: dict, username: str) -> dict:
    cfg = _smtp_test_config(db, data)
    host = _smtp_host(cfg)
    try:
        result = test_smtp_connection(cfg)
    except ValueError:
        record(db, username, "REPORT_SMTP_TEST", host or "-", "FAILED")
        db.commit()
        raise
    record(db, username, "REPORT_SMTP_TEST", host, "SUCCESS")
    db.commit()
    return result


def send_report(report: dict, cfg: dict) -> None:
    host = _smtp_host(cfg)
    recipients = cfg.get("recipients") or []
    if not host:
        raise ValueError("SMTP host belum diatur")
    if not recipients:
        raise ValueError("Penerima email belum diatur")
    from_addr = (cfg.get("from_addr") or cfg.get("smtp_username") or "").strip()
    if not from_addr:
        raise ValueError("Alamat pengirim belum diatur")

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    msg = EmailMessage()
    msg["Subject"] = (
        f'Report Komputer - {report.get("computers", {}).get("total", 0)} PC'
    )
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
    msg.set_content(_report_text(report))
    msg.add_attachment(
        report_to_pdf(report),
        maintype="application",
        subtype="pdf",
        filename=f"report-{stamp}.pdf",
    )
    msg.add_attachment(
        report_to_csv(report).encode("utf-8"),
        maintype="text",
        subtype="csv",
        filename=f"report-{stamp}.csv",
    )

    server = _open_smtp(cfg)
    try:
        if cfg.get("smtp_username"):
            server.login(cfg["smtp_username"], cfg.get("smtp_password") or "")
        server.send_message(msg)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(_smtp_error_message(exc, cfg)) from exc
    finally:
        _close_smtp(server)


def send_report_now(db: Session) -> dict:
    cfg = get_report_config(db)
    report = build_report(db, cfg["hours"])
    send_report(report, cfg)
    mark_sent(db)
    return {
        "sent": True,
        "recipients": cfg["recipients"],
        "generated_at": report["generated_at"],
    }
