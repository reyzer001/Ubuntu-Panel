from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import (
    AuditLog,
    ComputerMetricHourly,
    ComputerMetricSample,
    ComputerSpeedSample,
    ManagedComputer,
    MetricSample,
)
from app.services import report as report_service


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_reset_report_samples_deletes_only_computer_history():
    db = _session()
    try:
        now = datetime(2026, 10, 23, 10, 0, 0)
        computer = ManagedComputer(
            name="pc-a", hostname="pc-a", token="token-a", ip="10.0.0.1"
        )
        db.add(computer)
        db.commit()
        db.refresh(computer)
        db.add_all(
            [
                MetricSample(timestamp=now, net_rx_rate=100.0),
                MetricSample(timestamp=now, net_rx_rate=200.0),
                ComputerSpeedSample(
                    computer_id=computer.id,
                    tested_at=now,
                    received_at=now,
                    download_mbps=90.0,
                    upload_mbps=20.0,
                    source="internet",
                ),
                ComputerMetricSample(
                    computer_id=computer.id,
                    cpu=10.0,
                    mem=20.0,
                    net_rx_bytes=1000.0,
                    net_tx_bytes=500.0,
                    net_seconds=60.0,
                    timestamp=now,
                ),
                ComputerMetricHourly(
                    computer_id=computer.id,
                    bucket=now,
                    cpu_avg=10.0,
                    mem_avg=20.0,
                    net_rx_bytes=1000.0,
                    net_tx_bytes=500.0,
                    net_seconds=60.0,
                    samples=1,
                ),
            ]
        )
        db.commit()

        result = report_service.reset_report_samples(db, "superadmin")

        assert result["computer_metric_samples"] == 1
        assert result["computer_metric_hourly"] == 1
        assert result["computer_speed_samples"] == 1
        assert result["reset_at"].endswith("Z")
        assert db.query(MetricSample).count() == 2
        assert db.query(ComputerSpeedSample).count() == 0
        assert db.query(ManagedComputer).count() == 1
        assert db.query(ComputerMetricSample).count() == 0
        assert db.query(ComputerMetricHourly).count() == 0
        audit = db.query(AuditLog).filter(AuditLog.action == "REPORT_RESET").one()
        assert audit.username == "superadmin"
    finally:
        db.close()
