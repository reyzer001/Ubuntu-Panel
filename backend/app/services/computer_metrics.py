import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db.models import (
    AppSetting,
    ComputerMetricHourly,
    ComputerMetricSample,
    ComputerSpeedSample,
    ManagedComputer,
)
from . import topology as topology_svc

log = logging.getLogger(__name__)

SAMPLE_INTERVAL_SECONDS = int(
    os.getenv("COMPUTER_METRICS_SAMPLE_SECONDS", "60")
)
RAW_RETENTION_HOURS = int(os.getenv("CLEANUP_COMPUTER_RAW_HOURS", "48"))
ROLLUP_RETENTION_DAYS = int(
    os.getenv("CLEANUP_COMPUTER_ROLLUP_DAYS", "30")
)
SPEED_RETENTION_DAYS = int(
    os.getenv("CLEANUP_COMPUTER_SPEED_DAYS", "30")
)
OFFLINE_AFTER = int(os.getenv("COMPUTER_OFFLINE_AFTER", "40"))
WATERMARK_KEY = "computer_rollup_watermark"


def _get_setting(db: Session, key: str) -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value_enc if row and row.value_enc else ""


def _set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row is None:
        db.add(AppSetting(key=key, value_enc=value))
    else:
        row.value_enc = value
        row.updated_at = datetime.utcnow()


def record_sample(
    db: Session,
    computer_id: int,
    cpu: float | None,
    mem: float | None,
    now: datetime | None = None,
    net_rx_bytes: float = 0.0,
    net_tx_bytes: float = 0.0,
) -> bool:
    """Simpan sampel mentah maksimal sekali per interval sampling."""
    if cpu is None or mem is None:
        return False
    now = now or datetime.utcnow()
    try:
        with db.begin_nested():
            last = (
                db.query(func.max(ComputerMetricSample.timestamp))
                .filter(ComputerMetricSample.computer_id == computer_id)
                .scalar()
            )
            if (
                last is not None
                and (now - last).total_seconds() < SAMPLE_INTERVAL_SECONDS
            ):
                return False
            elapsed = (
                max(0.0, (now - last).total_seconds()) if last else 0.0
            )
            db.add(
                ComputerMetricSample(
                    computer_id=computer_id,
                    cpu=float(cpu),
                    mem=float(mem),
                    net_rx_bytes=max(0.0, float(net_rx_bytes or 0.0)),
                    net_tx_bytes=max(0.0, float(net_tx_bytes or 0.0)),
                    net_seconds=elapsed,
                    timestamp=now,
                )
            )
        return True
    except Exception:  # noqa: BLE001 — histori tidak boleh memutus heartbeat
        log.warning("gagal menyimpan metrik komputer %s", computer_id, exc_info=True)
        return False


def _merge(
    acc: dict[int, dict],
    computer_id: int,
    cpu_sum: float,
    cpu_min: float,
    cpu_max: float,
    mem_sum: float,
    mem_min: float,
    mem_max: float,
    count: int,
    net_rx_sum: float = 0.0,
    net_tx_sum: float = 0.0,
    net_seconds: float = 0.0,
) -> None:
    item = acc.setdefault(
        computer_id,
        {
            "cpu_sum": 0.0,
            "cpu_min": float("inf"),
            "cpu_max": 0.0,
            "mem_sum": 0.0,
            "mem_min": float("inf"),
            "mem_max": 0.0,
            "count": 0,
            "net_rx_sum": 0.0,
            "net_tx_sum": 0.0,
            "net_seconds": 0.0,
        },
    )
    item["cpu_sum"] += float(cpu_sum or 0)
    item["cpu_min"] = min(item["cpu_min"], float(cpu_min or 0))
    item["cpu_max"] = max(item["cpu_max"], float(cpu_max or 0))
    item["mem_sum"] += float(mem_sum or 0)
    item["mem_min"] = min(item["mem_min"], float(mem_min or 0))
    item["mem_max"] = max(item["mem_max"], float(mem_max or 0))
    item["count"] += int(count or 0)
    item["net_rx_sum"] += float(net_rx_sum or 0.0)
    item["net_tx_sum"] += float(net_tx_sum or 0.0)
    item["net_seconds"] += float(net_seconds or 0.0)


def rollup_completed_hours(
    db: Session, now: datetime | None = None
) -> int:
    """Rekap sampel mentah per jam agar bisa dihapus tanpa kehilangan data."""
    now = now or datetime.utcnow()
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    watermark_raw = _get_setting(db, WATERMARK_KEY)
    watermark = None
    if watermark_raw:
        try:
            watermark = datetime.fromisoformat(watermark_raw)
        except ValueError:
            watermark = None

    raw_floor = current_hour - timedelta(hours=RAW_RETENTION_HOURS)
    rollup_floor = current_hour - timedelta(days=ROLLUP_RETENTION_DAYS)
    # Jangan lewati jam yang belum direkap hanya karena sampelnya sudah
    # melewati batas retensi mentah (mis. backend sempat mati > 48 jam).
    start = max(watermark or raw_floor, rollup_floor)
    if start >= current_hour:
        return 0

    rows = (
        db.query(ComputerMetricSample)
        .filter(ComputerMetricSample.timestamp >= start)
        .filter(ComputerMetricSample.timestamp < current_hour)
        .order_by(ComputerMetricSample.timestamp.asc())
        .all()
    )

    groups: dict[tuple[int, datetime], list[ComputerMetricSample]] = {}
    for row in rows:
        bucket = row.timestamp.replace(minute=0, second=0, microsecond=0)
        groups.setdefault((row.computer_id, bucket), []).append(row)

    existing = {
        (row.computer_id, row.bucket): row
        for row in db.query(ComputerMetricHourly)
        .filter(ComputerMetricHourly.bucket >= start)
        .filter(ComputerMetricHourly.bucket < current_hour)
        .all()
    }

    for (computer_id, bucket), samples in groups.items():
        cpu_values = [float(s.cpu) for s in samples]
        mem_values = [float(s.mem) for s in samples]
        target = existing.get((computer_id, bucket))
        if target is None:
            target = ComputerMetricHourly(
                computer_id=computer_id,
                bucket=bucket,
            )
            db.add(target)
        target.cpu_avg = sum(cpu_values) / len(cpu_values)
        target.cpu_min = min(cpu_values)
        target.cpu_max = max(cpu_values)
        target.mem_avg = sum(mem_values) / len(mem_values)
        target.mem_min = min(mem_values)
        target.mem_max = max(mem_values)
        target.net_rx_bytes = sum(float(s.net_rx_bytes or 0.0) for s in samples)
        target.net_tx_bytes = sum(float(s.net_tx_bytes or 0.0) for s in samples)
        target.net_seconds = sum(float(s.net_seconds or 0.0) for s in samples)
        target.samples = len(samples)

    _set_setting(db, WATERMARK_KEY, current_hour.isoformat())
    return len(groups)


def cleanup_metrics(
    db: Session, now: datetime | None = None
) -> tuple[int, int]:
    now = now or datetime.utcnow()
    raw_cutoff = now - timedelta(hours=RAW_RETENTION_HOURS)
    raw_deleted = (
        db.query(ComputerMetricSample)
        .filter(ComputerMetricSample.timestamp < raw_cutoff)
        .delete(synchronize_session=False)
    )
    hourly_cutoff = now - timedelta(days=ROLLUP_RETENTION_DAYS)
    hourly_deleted = (
        db.query(ComputerMetricHourly)
        .filter(ComputerMetricHourly.bucket < hourly_cutoff)
        .delete(synchronize_session=False)
    )
    return raw_deleted, hourly_deleted


def record_speed_sample(
    db: Session,
    computer_id: int,
    tested_at: datetime | None,
    download_mbps: float | None,
    upload_mbps: float | None,
    received_at: datetime | None = None,
    source: str = "server",
) -> bool:
    """Simpan satu hasil speed test; heartbeat berulang tidak membuat duplikat."""
    if tested_at is None or download_mbps is None or upload_mbps is None:
        return False
    try:
        download = max(0.0, min(float(download_mbps), 100000.0))
        upload = max(0.0, min(float(upload_mbps), 100000.0))
    except (TypeError, ValueError):
        return False
    if tested_at.tzinfo is not None:
        tested_at = tested_at.astimezone(timezone.utc).replace(tzinfo=None)
    received_at = received_at or datetime.utcnow()
    try:
        with db.begin_nested():
            exists = (
                db.query(ComputerSpeedSample.id)
                .filter(
                    ComputerSpeedSample.computer_id == computer_id,
                    ComputerSpeedSample.tested_at == tested_at,
                )
                .first()
            )
            if exists is not None:
                return False
            db.add(
                ComputerSpeedSample(
                    computer_id=computer_id,
                    tested_at=tested_at,
                    received_at=received_at,
                    download_mbps=download,
                    upload_mbps=upload,
                    source="internet" if source == "internet" else "server",
                )
            )
        return True
    except Exception:  # noqa: BLE001 — histori tidak boleh memutus heartbeat
        log.warning(
            "gagal menyimpan speed test komputer %s", computer_id, exc_info=True
        )
        return False


def cleanup_speed_samples(
    db: Session, now: datetime | None = None
) -> int:
    now = now or datetime.utcnow()
    if SPEED_RETENTION_DAYS <= 0:
        return 0
    cutoff = now - timedelta(days=SPEED_RETENTION_DAYS)
    return (
        db.query(ComputerSpeedSample)
        .filter(ComputerSpeedSample.received_at < cutoff)
        .delete(synchronize_session=False)
    )


def _speed_iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def _speed_computer(computer: ManagedComputer | None) -> dict:
    if computer is None:
        return {
            "id": None,
            "name": "-",
            "hostname": "",
            "ip": "-",
            "group_name": "",
            "conn_type": "",
            "server_reach": "",
            "status": "unknown",
        }
    return {
        "id": computer.id,
        "name": computer.name or computer.hostname or "-",
        "hostname": computer.hostname or "",
        "ip": computer.ip or "-",
        "group_name": computer.group_name or "",
        "conn_type": computer.conn_type or "",
        "server_reach": computer.server_reach or "",
        "status": (
            "online"
            if _is_online(computer, datetime.utcnow())
            else ("offline" if computer.last_seen else "waiting")
        ),
    }


def _speed_sample_item(
    sample: ComputerSpeedSample | None,
    computers: dict[int, ManagedComputer],
) -> dict | None:
    if sample is None:
        return None
    item = _speed_computer(computers.get(sample.computer_id))
    down = round(float(sample.download_mbps), 2)
    up = round(float(sample.upload_mbps), 2)
    item.update(
        {
            "download_mbps": down,
            "upload_mbps": up,
            "score": round((down + up) / 2.0, 2),
            "tested_at": _speed_iso(sample.tested_at),
            "received_at": _speed_iso(sample.received_at),
        }
    )
    return item


def _isp_status(utilization_pct: float | None) -> str:
    if utilization_pct is None:
        return "unset"
    if utilization_pct >= 100:
        return "over"
    if utilization_pct >= 90:
        return "near"
    return "safe"


def summarize_speed_window(
    db: Session,
    hours: int = 24,
    limit: int = 5,
    now: datetime | None = None,
    isp_download_mbps: float | None = None,
    isp_upload_mbps: float | None = None,
) -> dict:
    """Rekap speed test PC→internet untuk report internet."""
    hours = max(1, min(int(hours), 24 * 30))
    now = now or datetime.utcnow()
    start = now - timedelta(hours=hours)
    window = (
        ComputerSpeedSample.received_at >= start,
        ComputerSpeedSample.received_at < now,
        ComputerSpeedSample.source == "internet",
    )

    computers = db.query(ManagedComputer).all()
    by_id = {computer.id: computer for computer in computers}

    grouped = (
        db.query(
            ComputerSpeedSample.computer_id,
            func.count(ComputerSpeedSample.id),
            func.avg(ComputerSpeedSample.download_mbps),
            func.avg(ComputerSpeedSample.upload_mbps),
            func.min(ComputerSpeedSample.download_mbps),
            func.max(ComputerSpeedSample.download_mbps),
            func.min(ComputerSpeedSample.upload_mbps),
            func.max(ComputerSpeedSample.upload_mbps),
            func.max(ComputerSpeedSample.tested_at),
            func.max(ComputerSpeedSample.received_at),
        )
        .filter(*window)
        .group_by(ComputerSpeedSample.computer_id)
        .all()
    )

    rows: list[dict] = []
    total_samples = 0
    weighted_download = 0.0
    weighted_upload = 0.0
    for (
        computer_id,
        count,
        down_avg,
        up_avg,
        down_min,
        down_max,
        up_min,
        up_max,
        last_tested,
        last_received,
    ) in grouped:
        computer = by_id.get(computer_id)
        if computer is None or not count:
            continue
        count = int(count)
        down_avg = float(down_avg or 0.0)
        up_avg = float(up_avg or 0.0)
        total_samples += count
        weighted_download += down_avg * count
        weighted_upload += up_avg * count
        item = _speed_computer(computer)
        item.update(
            {
                "avg_download_mbps": round(down_avg, 2),
                "avg_upload_mbps": round(up_avg, 2),
                "score": round((down_avg + up_avg) / 2.0, 2),
                "min_download_mbps": round(float(down_min or 0.0), 2),
                "max_download_mbps": round(float(down_max or 0.0), 2),
                "min_upload_mbps": round(float(up_min or 0.0), 2),
                "max_upload_mbps": round(float(up_max or 0.0), 2),
                "samples": count,
                "last_tested_at": _speed_iso(last_tested),
                "last_received_at": _speed_iso(last_received),
            }
        )
        rows.append(item)

    fastest = sorted(
        rows,
        key=lambda row: (
            -row["score"],
            -row["avg_download_mbps"],
            -row["samples"],
        ),
    )
    slowest = sorted(
        rows,
        key=lambda row: (
            row["score"],
            row["avg_download_mbps"],
            -row["samples"],
        ),
    )

    score_expr = (
        ComputerSpeedSample.download_mbps
        + ComputerSpeedSample.upload_mbps
    ) / 2.0
    peak = (
        db.query(ComputerSpeedSample)
        .filter(*window)
        .order_by(score_expr.desc(), ComputerSpeedSample.received_at.asc())
        .first()
    )
    lowest = (
        db.query(ComputerSpeedSample)
        .filter(*window)
        .filter(score_expr > 0)
        .order_by(score_expr.asc(), ComputerSpeedSample.received_at.asc())
        .first()
    )
    peak_download = (
        db.query(ComputerSpeedSample)
        .filter(*window)
        .order_by(
            ComputerSpeedSample.download_mbps.desc(),
            ComputerSpeedSample.received_at.asc(),
        )
        .first()
    )
    peak_upload = (
        db.query(ComputerSpeedSample)
        .filter(*window)
        .order_by(
            ComputerSpeedSample.upload_mbps.desc(),
            ComputerSpeedSample.received_at.asc(),
        )
        .first()
    )

    peak_down_value = (
        float(peak_download.download_mbps) if peak_download else None
    )
    peak_up_value = (
        float(peak_upload.upload_mbps) if peak_upload else None
    )
    down_pct = (
        round(peak_down_value / isp_download_mbps * 100.0, 1)
        if peak_down_value is not None
        and isp_download_mbps
        and isp_download_mbps > 0
        else None
    )
    up_pct = (
        round(peak_up_value / isp_upload_mbps * 100.0, 1)
        if peak_up_value is not None
        and isp_upload_mbps
        and isp_upload_mbps > 0
        else None
    )
    utilization = max(
        [value for value in (down_pct, up_pct) if value is not None],
        default=None,
    )

    return {
        "hours": hours,
        "total": len(computers),
        "computers_with_data": len(rows),
        "sample_count": total_samples,
        "avg_download_mbps": (
            round(weighted_download / total_samples, 2)
            if total_samples
            else None
        ),
        "avg_upload_mbps": (
            round(weighted_upload / total_samples, 2)
            if total_samples
            else None
        ),
        "avg_score_mbps": (
            round((weighted_download + weighted_upload) / (total_samples * 2), 2)
            if total_samples
            else None
        ),
        "top_fastest": fastest[:limit],
        "top_slowest": slowest[:limit],
        "peak": _speed_sample_item(peak, by_id),
        "lowest": _speed_sample_item(lowest, by_id),
        "peak_download": _speed_sample_item(peak_download, by_id),
        "peak_upload": _speed_sample_item(peak_upload, by_id),
        "isp": {
            "download_mbps": isp_download_mbps,
            "upload_mbps": isp_upload_mbps,
            "peak_download_mbps": peak_down_value,
            "peak_upload_mbps": peak_up_value,
            "utilization_download_pct": down_pct,
            "utilization_upload_pct": up_pct,
            "utilization_pct": utilization,
            "status": _isp_status(utilization),
        },
    }


def _raw_stats(
    db: Session, start: datetime, end: datetime
) -> dict[int, dict]:
    rows = (
        db.query(
            ComputerMetricSample.computer_id,
            func.sum(ComputerMetricSample.cpu),
            func.min(ComputerMetricSample.cpu),
            func.max(ComputerMetricSample.cpu),
            func.sum(ComputerMetricSample.mem),
            func.min(ComputerMetricSample.mem),
            func.max(ComputerMetricSample.mem),
            func.count(ComputerMetricSample.id),
            func.sum(ComputerMetricSample.net_rx_bytes),
            func.sum(ComputerMetricSample.net_tx_bytes),
            func.sum(ComputerMetricSample.net_seconds),
        )
        .filter(ComputerMetricSample.timestamp >= start)
        .filter(ComputerMetricSample.timestamp < end)
        .group_by(ComputerMetricSample.computer_id)
        .all()
    )
    acc: dict[int, dict] = {}
    for (
        computer_id,
        cpu_sum,
        cpu_min,
        cpu_max,
        mem_sum,
        mem_min,
        mem_max,
        count,
        net_rx_sum,
        net_tx_sum,
        net_seconds,
    ) in rows:
        _merge(
            acc,
            computer_id,
            cpu_sum,
            cpu_min,
            cpu_max,
            mem_sum,
            mem_min,
            mem_max,
            count,
            net_rx_sum,
            net_tx_sum,
            net_seconds,
        )
    return acc


def _hourly_stats(
    db: Session, start: datetime, end: datetime
) -> dict[int, dict]:
    rows = (
        db.query(
            ComputerMetricHourly.computer_id,
            func.sum(
                ComputerMetricHourly.cpu_avg * ComputerMetricHourly.samples
            ),
            func.min(ComputerMetricHourly.cpu_min),
            func.max(ComputerMetricHourly.cpu_max),
            func.sum(
                ComputerMetricHourly.mem_avg * ComputerMetricHourly.samples
            ),
            func.min(ComputerMetricHourly.mem_min),
            func.max(ComputerMetricHourly.mem_max),
            func.sum(ComputerMetricHourly.samples),
            func.sum(ComputerMetricHourly.net_rx_bytes),
            func.sum(ComputerMetricHourly.net_tx_bytes),
            func.sum(ComputerMetricHourly.net_seconds),
        )
        .filter(ComputerMetricHourly.bucket >= start)
        .filter(ComputerMetricHourly.bucket < end)
        .group_by(ComputerMetricHourly.computer_id)
        .all()
    )
    acc: dict[int, dict] = {}
    for (
        computer_id,
        cpu_sum,
        cpu_min,
        cpu_max,
        mem_sum,
        mem_min,
        mem_max,
        count,
        net_rx_sum,
        net_tx_sum,
        net_seconds,
    ) in rows:
        _merge(
            acc,
            computer_id,
            cpu_sum,
            cpu_min,
            cpu_max,
            mem_sum,
            mem_min,
            mem_max,
            count,
            net_rx_sum,
            net_tx_sum,
            net_seconds,
        )
    return acc


def _fleet_series(
    db: Session, start: datetime, now: datetime
) -> list[dict]:
    """Rata-rata CPU/RAM dan trafik seluruh PC per jam untuk grafik."""
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    buckets: dict[datetime, dict] = {}

    def add_bucket(
        bucket: datetime,
        cpu_sum: float,
        mem_sum: float,
        count: int,
        rx: float = 0.0,
        tx: float = 0.0,
    ) -> None:
        if count <= 0:
            return
        item = buckets.setdefault(
            bucket,
            {"cpu": 0.0, "mem": 0.0, "count": 0, "rx": 0.0, "tx": 0.0},
        )
        item["cpu"] += float(cpu_sum or 0.0)
        item["mem"] += float(mem_sum or 0.0)
        item["count"] += int(count)
        item["rx"] += float(rx or 0.0)
        item["tx"] += float(tx or 0.0)

    last_hourly = None
    if start < current_hour:
        rows = (
            db.query(
                ComputerMetricHourly.bucket,
                func.sum(
                    ComputerMetricHourly.cpu_avg
                    * ComputerMetricHourly.samples
                ),
                func.sum(
                    ComputerMetricHourly.mem_avg
                    * ComputerMetricHourly.samples
                ),
                func.sum(ComputerMetricHourly.samples),
                func.sum(ComputerMetricHourly.net_rx_bytes),
                func.sum(ComputerMetricHourly.net_tx_bytes),
            )
            .filter(ComputerMetricHourly.bucket >= start)
            .filter(ComputerMetricHourly.bucket < current_hour)
            .group_by(ComputerMetricHourly.bucket)
            .order_by(ComputerMetricHourly.bucket.asc())
            .all()
        )
        for bucket, cpu_sum, mem_sum, count, rx, tx in rows:
            add_bucket(bucket, cpu_sum, mem_sum, count, rx, tx)
            last_hourly = bucket

    raw_start = (
        max(start, last_hourly + timedelta(hours=1))
        if last_hourly is not None
        else start
    )
    if raw_start < now:
        rows = (
            db.query(
                ComputerMetricSample.timestamp,
                ComputerMetricSample.cpu,
                ComputerMetricSample.mem,
                ComputerMetricSample.net_rx_bytes,
                ComputerMetricSample.net_tx_bytes,
            )
            .filter(ComputerMetricSample.timestamp >= raw_start)
            .filter(ComputerMetricSample.timestamp < now)
            .all()
        )
        for timestamp, cpu, mem, rx, tx in rows:
            bucket = timestamp.replace(minute=0, second=0, microsecond=0)
            add_bucket(bucket, cpu, mem, 1, rx, tx)

    return [
        {
            "t": _speed_iso(bucket),
            "cpu": round(item["cpu"] / item["count"], 1),
            "ram": round(item["mem"] / item["count"], 1),
            "rx": int(item["rx"]),
            "tx": int(item["tx"]),
        }
        for bucket, item in sorted(buckets.items())
    ]


def _is_online(computer: ManagedComputer, now: datetime) -> bool:
    if (
        computer.last_seen is not None
        and (now - computer.last_seen).total_seconds() <= OFFLINE_AFTER
    ):
        return True
    if computer.ap_seen_at is not None:
        age = (now - computer.ap_seen_at).total_seconds()
        if age <= topology_svc.evidence_ttl():
            return True
    return False


def summarize_window(
    db: Session,
    hours: int = 24,
    limit: int = 5,
    now: datetime | None = None,
) -> dict:
    hours = max(1, min(int(hours), 24 * 30))
    now = now or datetime.utcnow()
    start = now - timedelta(hours=hours)
    raw_start = max(start, now - timedelta(hours=RAW_RETENTION_HOURS))

    acc: dict[int, dict] = {}
    if start < raw_start:
        acc.update(_hourly_stats(db, start, raw_start))
    if raw_start < now:
        for computer_id, item in _raw_stats(db, raw_start, now).items():
            _merge(
                acc,
                computer_id,
                item["cpu_sum"],
                item["cpu_min"],
                item["cpu_max"],
                item["mem_sum"],
                item["mem_min"],
                item["mem_max"],
                item["count"],
                item["net_rx_sum"],
                item["net_tx_sum"],
                item["net_seconds"],
            )

    computers = db.query(ManagedComputer).all()
    by_id = {computer.id: computer for computer in computers}
    online = sum(1 for computer in computers if _is_online(computer, now))

    rows: list[dict] = []
    for computer_id, item in acc.items():
        computer = by_id.get(computer_id)
        if computer is None or item["count"] <= 0:
            continue
        count = item["count"]
        cpu_avg = item["cpu_sum"] / count
        mem_avg = item["mem_sum"] / count
        rows.append(
            {
                "id": computer.id,
                "name": computer.name or computer.hostname or "-",
                "hostname": computer.hostname or "",
                "ip": computer.ip or "-",
                "group_name": computer.group_name or "",
                "status": (
                    "online"
                    if _is_online(computer, now)
                    else ("offline" if computer.last_seen else "waiting")
                ),
                "cpu_avg": round(cpu_avg, 1),
                "cpu_max": round(item["cpu_max"], 1),
                "ram_avg": round(mem_avg, 1),
                "ram_max": round(item["mem_max"], 1),
                "score": round((cpu_avg + mem_avg) / 2.0, 1),
                "samples": count,
            }
        )

    rows.sort(key=lambda row: (-row["score"], -row["cpu_max"]))

    active = [item for item in acc.values() if item["count"] > 0]
    total_samples = sum(item["count"] for item in active)
    net_seconds = max(
        (item["net_seconds"] for item in active), default=0.0
    )
    rx_total = sum(item["net_rx_sum"] for item in active)
    tx_total = sum(item["net_tx_sum"] for item in active)

    def _fleet_stat(
        sum_key: str, min_key: str, max_key: str
    ) -> dict:
        if not active or total_samples <= 0:
            return {"avg": None, "min": None, "max": None}
        return {
            "avg": round(
                sum(item[sum_key] for item in active) / total_samples, 2
            ),
            "min": round(min(item[min_key] for item in active), 2),
            "max": round(max(item[max_key] for item in active), 2),
        }

    return {
        "total": len(computers),
        "online": online,
        "with_data": len(rows),
        "sample_count": total_samples,
        "cpu": _fleet_stat("cpu_sum", "cpu_min", "cpu_max"),
        "ram": _fleet_stat("mem_sum", "mem_min", "mem_max"),
        "net": {
            "rx_total_bytes": int(rx_total),
            "tx_total_bytes": int(tx_total),
            "rx_avg_rate": (
                round(rx_total / net_seconds, 1) if net_seconds > 0 else 0.0
            ),
            "tx_avg_rate": (
                round(tx_total / net_seconds, 1) if net_seconds > 0 else 0.0
            ),
        },
        "series": _fleet_series(db, start, now),
        "top": rows[:limit],
    }
