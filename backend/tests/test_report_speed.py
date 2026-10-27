from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import ComputerSpeedSample, ManagedComputer
from app.services import computer_metrics
from app.services import report as report_service


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _computer(db: Session, name: str, token: str) -> ManagedComputer:
    computer = ManagedComputer(
        name=name,
        hostname=name.lower(),
        token=token,
        ip=f"10.0.0.{len(name)}",
    )
    db.add(computer)
    db.commit()
    db.refresh(computer)
    return computer


def _sample(
    db: Session,
    computer: ManagedComputer,
    tested_at: datetime,
    download: float,
    upload: float,
    source: str = "internet",
) -> None:
    db.add(
        ComputerSpeedSample(
            computer_id=computer.id,
            tested_at=tested_at,
            received_at=tested_at,
            download_mbps=download,
            upload_mbps=upload,
            source=source,
        )
    )


def test_record_speed_sample_deduplicates_heartbeat():
    db = _session()
    try:
        computer = _computer(db, "pc-a", "token-a")
        tested_at = datetime(2026, 10, 23, 8, 0, 0)

        assert computer_metrics.record_speed_sample(
            db, computer.id, tested_at, 100.0, 50.0
        )
        assert not computer_metrics.record_speed_sample(
            db, computer.id, tested_at, 100.0, 50.0
        )
        db.commit()

        assert db.query(ComputerSpeedSample).count() == 1
    finally:
        db.close()


def test_summarize_speed_window_ranks_combined_download_upload():
    db = _session()
    try:
        now = datetime(2026, 10, 23, 10, 0, 0)
        a = _computer(db, "pc-a", "token-a")
        b = _computer(db, "pc-b", "token-b")
        c = _computer(db, "pc-c", "token-c")
        _sample(db, a, now - timedelta(minutes=30), 100.0, 60.0)
        _sample(db, a, now - timedelta(minutes=15), 120.0, 40.0)
        _sample(db, b, now - timedelta(minutes=20), 20.0, 10.0)
        _sample(db, c, now - timedelta(minutes=10), 50.0, 30.0)
        db.commit()

        summary = computer_metrics.summarize_speed_window(
            db,
            hours=24,
            now=now,
            isp_download_mbps=200.0,
            isp_upload_mbps=200.0,
        )

        assert summary["sample_count"] == 4
        assert summary["computers_with_data"] == 3
        assert summary["top_fastest"][0]["name"] == "pc-a"
        assert summary["top_fastest"][0]["score"] == 80.0
        assert summary["top_slowest"][0]["name"] == "pc-b"
        assert summary["top_slowest"][0]["score"] == 15.0
        assert summary["peak"]["name"] == "pc-a"
        assert summary["lowest"]["name"] == "pc-b"
        assert summary["peak_download"]["download_mbps"] == 120.0
        assert summary["isp"]["utilization_pct"] == 60.0
        assert summary["isp"]["status"] == "safe"
        assert summary["peak"]["received_at"].endswith("Z")
    finally:
        db.close()


def test_summarize_speed_window_marks_isp_over_limit():
    db = _session()
    try:
        now = datetime(2026, 10, 23, 10, 0, 0)
        computer = _computer(db, "pc-a", "token-a")
        _sample(db, computer, now - timedelta(minutes=5), 150.0, 40.0)
        db.commit()

        summary = computer_metrics.summarize_speed_window(
            db,
            hours=24,
            now=now,
            isp_download_mbps=100.0,
            isp_upload_mbps=100.0,
        )

        assert summary["isp"]["utilization_download_pct"] == 150.0
        assert summary["isp"]["status"] == "over"
    finally:
        db.close()


def test_summarize_speed_window_ignores_old_samples():
    db = _session()
    try:
        now = datetime(2026, 10, 23, 10, 0, 0)
        computer = _computer(db, "pc-a", "token-a")
        _sample(db, computer, now - timedelta(hours=25), 100.0, 50.0)
        _sample(db, computer, now - timedelta(hours=1), 10.0, 5.0)
        db.commit()

        summary = computer_metrics.summarize_speed_window(
            db, hours=24, now=now
        )

        assert summary["sample_count"] == 1
        assert summary["avg_download_mbps"] == 10.0
    finally:
        db.close()


def test_report_settings_save_isp_limits():
    db = _session()
    try:
        base = {
            "enabled": False,
            "smtp_host": "",
            "smtp_port": 587,
            "smtp_username": "",
            "smtp_password": "",
            "smtp_tls": True,
            "smtp_ssl": False,
            "from_addr": "",
            "recipients": [],
            "schedule": "0 7 * * *",
            "hours": 24,
        }
        saved = report_service.save_report_settings(
            db,
            {
                **base,
                "isp_download_mbps": 100.0,
                "isp_upload_mbps": 50.0,
            },
            "superadmin",
        )
        assert saved["isp_download_mbps"] == 100.0
        assert saved["isp_upload_mbps"] == 50.0

        cleared = report_service.save_report_settings(
            db,
            {**base, "isp_download_mbps": None, "isp_upload_mbps": None},
            "superadmin",
        )
        assert cleared["isp_download_mbps"] is None
        assert cleared["isp_upload_mbps"] is None

        with pytest.raises(ValueError):
            report_service.save_report_settings(
                db,
                {**base, "isp_download_mbps": -1},
                "superadmin",
            )
    finally:
        db.close()


def test_summarize_speed_window_only_uses_internet_source():
    db = _session()
    try:
        now = datetime(2026, 10, 23, 10, 0, 0)
        computer = _computer(db, "pc-a", "token-a")
        _sample(
            db,
            computer,
            now - timedelta(minutes=20),
            500.0,
            500.0,
            source="server",
        )
        internet = ComputerSpeedSample(
            computer_id=computer.id,
            tested_at=now - timedelta(minutes=10),
            received_at=now - timedelta(minutes=10),
            download_mbps=90.0,
            upload_mbps=30.0,
            source="internet",
        )
        db.add(internet)
        db.commit()

        summary = computer_metrics.summarize_speed_window(
            db, hours=24, now=now
        )

        assert summary["sample_count"] == 1
        assert summary["avg_download_mbps"] == 90.0
        assert summary["peak"]["name"] == "pc-a"
    finally:
        db.close()
