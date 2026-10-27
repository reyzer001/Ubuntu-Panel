import os
import threading
import time
from datetime import datetime, timedelta

from ..db.database import SessionLocal
from ..db.models import MetricSample
from . import collectors

_INTERVAL = int(os.environ.get("METRICS_SAMPLE_INTERVAL", "60"))
# Jangan integrasikan trafik melewati gap panjang (backend mati/restart).
_MAX_GAP_SECONDS = int(
    os.environ.get("METRICS_MAX_GAP_SECONDS", str(max(180, _INTERVAL * 3)))
)

_started = False
_start_lock = threading.Lock()


def sample_once() -> None:
    try:
        m = collectors.get_metrics()
    except Exception:
        return
    db = SessionLocal()
    try:
        temp = m.get("cpu_temperature")
        try:
            temp = float(temp) if temp is not None else None
        except (TypeError, ValueError):
            temp = None
        db.add(
            MetricSample(
                timestamp=datetime.utcnow(),
                cpu=float(m.get("cpu") or 0.0),
                ram=float(m.get("ram") or 0.0),
                disk=float(m.get("disk") or 0.0),
                load1=float(m.get("load1") or 0.0),
                net_rx_rate=float(m.get("net_rx_rate") or 0.0),
                net_tx_rate=float(m.get("net_tx_rate") or 0.0),
                temp=temp,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _loop(interval: int) -> None:
    while True:
        sample_once()
        time.sleep(max(10, interval))


def start_sampler() -> None:
    global _started
    with _start_lock:
        if _started:
            return
        _started = True
    threading.Thread(
        target=_loop,
        args=(_INTERVAL,),
        daemon=True,
        name="metrics-sampler",
    ).start()


def _stat(values: list[float]) -> dict:
    if not values:
        return {"avg": None, "min": None, "max": None}
    return {
        "avg": round(sum(values) / len(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def _series(rows: list[MetricSample], hours: int) -> list[dict]:
    if not rows:
        return []
    step = 1 if hours <= 72 else max(1, hours // 48)
    buckets: dict[datetime, list[float]] = {}
    for row in rows:
        hour = row.timestamp.replace(minute=0, second=0, microsecond=0)
        bucket = hour - timedelta(hours=hour.hour % step)
        item = buckets.setdefault(bucket, [0.0, 0.0, 0])
        item[0] += float(row.cpu)
        item[1] += float(row.ram)
        item[2] += 1
    return [
        {
            "t": _iso(bucket),
            "cpu": round(value[0] / value[2], 1),
            "ram": round(value[1] / value[2], 1),
        }
        for bucket, value in sorted(buckets.items())
    ]


def summarize_rows(rows: list[MetricSample], hours: int = 24) -> dict:
    if not rows:
        return {
            "hours": hours,
            "sample_count": 0,
            "first_sample": None,
            "last_sample": None,
            "cpu": _stat([]),
            "ram": _stat([]),
            "disk": _stat([]),
            "load1": _stat([]),
            "net_rx_rate": _stat([]),
            "net_tx_rate": _stat([]),
            "temp": _stat([]),
            "series": [],
            "rx_total_bytes": 0,
            "tx_total_bytes": 0,
        }

    rx_total = 0.0
    tx_total = 0.0
    for prev, cur in zip(rows, rows[1:]):
        dt = (cur.timestamp - prev.timestamp).total_seconds()
        if dt <= 0 or dt > _MAX_GAP_SECONDS:
            continue
        rx_total += (
            (float(prev.net_rx_rate) + float(cur.net_rx_rate)) / 2.0
        ) * dt
        tx_total += (
            (float(prev.net_tx_rate) + float(cur.net_tx_rate)) / 2.0
        ) * dt

    return {
        "hours": hours,
        "sample_count": len(rows),
        "first_sample": _iso(rows[0].timestamp),
        "last_sample": _iso(rows[-1].timestamp),
        "cpu": _stat([float(r.cpu) for r in rows]),
        "ram": _stat([float(r.ram) for r in rows]),
        "disk": _stat([float(r.disk) for r in rows]),
        "load1": _stat([float(r.load1) for r in rows]),
        "net_rx_rate": _stat([float(r.net_rx_rate) for r in rows]),
        "net_tx_rate": _stat([float(r.net_tx_rate) for r in rows]),
        "temp": _stat(
            [float(r.temp) for r in rows if r.temp is not None]
        ),
        "series": _series(rows, hours),
        "rx_total_bytes": int(rx_total),
        "tx_total_bytes": int(tx_total),
    }


def summarize_window(hours: int = 24) -> dict:
    hours = max(1, min(int(hours), 24 * 30))
    since = datetime.utcnow() - timedelta(hours=hours)
    db = SessionLocal()
    try:
        rows = (
            db.query(MetricSample)
            .filter(MetricSample.timestamp >= since)
            .order_by(MetricSample.timestamp.asc())
            .all()
        )
    finally:
        db.close()
    return summarize_rows(rows, hours)
