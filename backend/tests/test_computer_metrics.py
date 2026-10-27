from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import (
    AppSetting,
    ComputerMetricHourly,
    ComputerMetricSample,
    ManagedComputer,
)
from app.services import computer_metrics


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _computer(db: Session, name: str, token: str) -> ManagedComputer:
    computer = ManagedComputer(name=name, token=token)
    db.add(computer)
    db.commit()
    return computer


def test_record_sample_is_throttled_per_interval():
    db = _session()
    try:
        computer = _computer(db, "PC-01", "tok-01")
        now = datetime(2026, 1, 1, 10, 0, 0)

        assert computer_metrics.record_sample(db, computer.id, 10, 20, now)
        db.commit()
        assert not computer_metrics.record_sample(
            db, computer.id, 11, 21, now + timedelta(seconds=30)
        )
        assert computer_metrics.record_sample(
            db, computer.id, 12, 22, now + timedelta(seconds=61)
        )
        db.commit()
        assert db.query(ComputerMetricSample).count() == 2
    finally:
        db.close()


def test_rollup_aggregates_hour_and_is_idempotent():
    db = _session()
    try:
        computer = _computer(db, "PC-01", "tok-01")
        now = datetime(2026, 1, 1, 12, 0, 0)
        bucket = now.replace(hour=10, minute=0)
        for minute in range(0, 60, 10):
            db.add(
                ComputerMetricSample(
                    computer_id=computer.id,
                    cpu=10 + minute / 10,
                    mem=20 + minute / 10,
                    timestamp=bucket + timedelta(minutes=minute),
                )
            )
        db.commit()

        assert computer_metrics.rollup_completed_hours(db, now) == 1
        db.commit()

        row = db.query(ComputerMetricHourly).one()
        assert row.computer_id == computer.id
        assert row.bucket == bucket
        assert row.samples == 6
        assert round(row.cpu_avg, 2) == round((10 + 11 + 12 + 13 + 14 + 15) / 6, 2)
        assert row.cpu_min == 10
        assert row.cpu_max == 15
        assert row.mem_max == 25

        assert computer_metrics.rollup_completed_hours(db, now) == 0
        assert db.query(ComputerMetricHourly).count() == 1
    finally:
        db.close()


def test_rollup_catches_up_samples_older_than_raw_retention():
    db = _session()
    try:
        computer = _computer(db, "PC-01", "tok-01")
        now = datetime(2026, 1, 3, 12, 0, 0)
        old_bucket = (now - timedelta(hours=60)).replace(
            minute=0, second=0, microsecond=0
        )
        db.add(
            ComputerMetricSample(
                computer_id=computer.id,
                cpu=10,
                mem=20,
                timestamp=old_bucket + timedelta(minutes=5),
            )
        )
        db.add(
            AppSetting(
                key="computer_rollup_watermark",
                value_enc=(now - timedelta(hours=72)).isoformat(),
            )
        )
        db.commit()

        assert computer_metrics.rollup_completed_hours(db, now) == 1
        db.commit()
        assert db.query(ComputerMetricHourly).count() == 1

        raw_deleted, _ = computer_metrics.cleanup_metrics(db, now)
        db.commit()
        assert raw_deleted == 1
        row = db.query(ComputerMetricHourly).one()
        assert row.bucket == old_bucket
        assert row.samples == 1
    finally:
        db.close()


def test_summarize_window_returns_top_five_by_average_load():
    db = _session()
    try:
        now = datetime(2026, 1, 1, 12, 0, 0)
        for index in range(6):
            computer = _computer(db, f"PC-{index}", f"tok-{index}")
            for offset in (60, 30):
                db.add(
                    ComputerMetricSample(
                        computer_id=computer.id,
                        cpu=index * 10 + 1,
                        mem=index * 10 + 1,
                        timestamp=now - timedelta(minutes=offset),
                    )
                )
        db.commit()

        summary = computer_metrics.summarize_window(db, 24, limit=5, now=now)
        assert summary["total"] == 6
        assert summary["with_data"] == 6
        assert summary["sample_count"] == 12
        assert len(summary["top"]) == 5
        assert summary["top"][0]["name"] == "PC-5"
        assert summary["top"][0]["cpu_avg"] == 51
        assert summary["top"][0]["cpu_max"] == 51
        assert summary["top"][-1]["name"] == "PC-1"
    finally:
        db.close()


def test_summarize_window_combines_hourly_and_raw_without_double_count():
    db = _session()
    try:
        computer = _computer(db, "PC-01", "tok-01")
        now = datetime(2026, 1, 1, 12, 0, 0)

        db.add(
            ComputerMetricHourly(
                computer_id=computer.id,
                bucket=now - timedelta(hours=50),
                cpu_avg=80,
                cpu_min=70,
                cpu_max=90,
                mem_avg=60,
                mem_min=50,
                mem_max=70,
                samples=60,
            )
        )
        db.add(
            ComputerMetricSample(
                computer_id=computer.id,
                cpu=20,
                mem=40,
                timestamp=now - timedelta(hours=1),
            )
        )
        db.commit()

        summary = computer_metrics.summarize_window(db, 72, now=now)
        row = summary["top"][0]
        assert row["samples"] == 61
        assert abs(row["cpu_avg"] - ((80 * 60 + 20) / 61)) < 0.2
        assert row["cpu_max"] == 90
        assert abs(row["ram_avg"] - ((60 * 60 + 40) / 61)) < 0.2
    finally:
        db.close()


def test_summarize_window_returns_fleet_stats_and_network():
    db = _session()
    try:
        now = datetime(2026, 1, 1, 12, 0, 0)
        a = _computer(db, "PC-A", "tok-a")
        b = _computer(db, "PC-B", "tok-b")
        db.add_all(
            [
                ComputerMetricSample(
                    computer_id=a.id,
                    cpu=10,
                    mem=20,
                    net_rx_bytes=1000,
                    net_tx_bytes=500,
                    net_seconds=60,
                    timestamp=now - timedelta(minutes=2),
                ),
                ComputerMetricSample(
                    computer_id=a.id,
                    cpu=20,
                    mem=30,
                    net_rx_bytes=2000,
                    net_tx_bytes=1000,
                    net_seconds=60,
                    timestamp=now - timedelta(minutes=1),
                ),
                ComputerMetricSample(
                    computer_id=b.id,
                    cpu=30,
                    mem=40,
                    net_rx_bytes=3000,
                    net_tx_bytes=1500,
                    net_seconds=120,
                    timestamp=now - timedelta(minutes=1),
                ),
            ]
        )
        db.commit()

        summary = computer_metrics.summarize_window(db, 24, now=now)

        assert summary["cpu"]["avg"] == 20.0
        assert summary["cpu"]["min"] == 10.0
        assert summary["cpu"]["max"] == 30.0
        assert summary["ram"]["avg"] == 30.0
        assert summary["net"]["rx_total_bytes"] == 6000
        assert summary["net"]["tx_total_bytes"] == 3000
        assert summary["net"]["rx_avg_rate"] == 50.0
        assert summary["net"]["tx_avg_rate"] == 25.0
        assert summary["series"][-1]["rx"] == 6000
        assert summary["series"][-1]["tx"] == 3000
    finally:
        db.close()
