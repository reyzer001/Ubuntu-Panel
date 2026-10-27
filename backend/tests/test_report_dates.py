from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import (
    ComputerMetricHourly,
    ComputerMetricSample,
    ComputerSpeedSample,
    ManagedComputer,
)
from app.services import report as report_service


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_build_available_dates_merges_metric_sources():
    db = _session()
    try:
        pc1 = ManagedComputer(name="PC-01", token="tok-01")
        pc2 = ManagedComputer(name="PC-02", token="tok-02")
        db.add_all([pc1, pc2])
        db.commit()

        day1 = datetime(2026, 1, 1, 10, 0, 0)
        day2 = datetime(2026, 1, 2, 10, 0, 0)
        db.add_all(
            [
                ComputerMetricSample(
                    computer_id=pc1.id,
                    cpu=10,
                    mem=20,
                    timestamp=day1,
                ),
                ComputerMetricSample(
                    computer_id=pc2.id,
                    cpu=30,
                    mem=40,
                    timestamp=day1.replace(hour=11),
                ),
                ComputerMetricSample(
                    computer_id=pc1.id,
                    cpu=15,
                    mem=25,
                    timestamp=day2,
                ),
                ComputerMetricHourly(
                    computer_id=pc1.id,
                    bucket=day1,
                    cpu_avg=10,
                    mem_avg=20,
                    samples=1,
                ),
                ComputerMetricHourly(
                    computer_id=pc2.id,
                    bucket=day1.replace(hour=11),
                    cpu_avg=30,
                    mem_avg=40,
                    samples=1,
                ),
                ComputerSpeedSample(
                    computer_id=pc2.id,
                    tested_at=day1.replace(hour=12),
                    received_at=day1.replace(hour=12),
                    download_mbps=90,
                    upload_mbps=20,
                    source="internet",
                ),
                ComputerSpeedSample(
                    computer_id=pc1.id,
                    tested_at=day2.replace(hour=11),
                    received_at=day2.replace(hour=11),
                    download_mbps=80,
                    upload_mbps=10,
                    source="internet",
                ),
            ]
        )
        db.commit()

        result = report_service.build_available_dates(
            db, days=30, now=datetime(2026, 1, 3, 12, 0, 0)
        )

        assert result["timezone"].startswith("WIB")
        assert result["retention"]["raw_hours"] == 48
        assert [row["date"] for row in result["dates"]] == [
            "2026-01-02",
            "2026-01-01",
        ]

        first, second = result["dates"]
        assert first["computers"] == 1
        assert first["raw_samples"] == 1
        assert first["hourly_buckets"] == 0
        assert first["speed_samples"] == 1
        assert first["has_raw"] is True
        assert first["has_hourly"] is False
        assert first["has_speed"] is True
        assert first["first_ts"] == "2026-01-02T10:00:00Z"
        assert first["last_ts"] == "2026-01-02T11:00:00Z"

        assert second["computers"] == 2
        assert second["raw_samples"] == 2
        assert second["hourly_buckets"] == 2
        assert second["speed_samples"] == 1
        assert second["has_raw"] is True
        assert second["has_hourly"] is True
        assert second["has_speed"] is True
        assert second["first_ts"] == "2026-01-01T10:00:00Z"
        assert second["last_ts"] == "2026-01-01T12:00:00Z"
    finally:
        db.close()
