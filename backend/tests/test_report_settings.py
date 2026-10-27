import smtplib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.services import report as report_service


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _payload(**overrides) -> dict:
    data = {
        "enabled": True,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_username": "panel@gmail.com",
        "smtp_password": "app-password",
        "smtp_tls": True,
        "smtp_ssl": False,
        "from_addr": "panel@gmail.com",
        "recipients": ["ops@example.com"],
        "schedule": "0 7 * * *",
        "hours": 24,
    }
    data.update(overrides)
    return data


def test_report_settings_can_be_saved_repeatedly():
    db = _session()
    try:
        first = report_service.save_report_settings(
            db, _payload(), "superadmin"
        )
        assert first["smtp_host"] == "smtp.gmail.com"
        assert first["recipients"] == ["ops@example.com"]
        assert first["smtp_password_set"] is True

        second = report_service.save_report_settings(
            db,
            _payload(
                smtp_host="smtp.example.com",
                smtp_port=465,
                smtp_tls=False,
                smtp_ssl=True,
                smtp_password="",
                recipients=["a@example.com", "b@example.com"],
            ),
            "superadmin",
        )
        assert second["smtp_host"] == "smtp.example.com"
        assert second["smtp_port"] == 465
        assert second["smtp_tls"] is False
        assert second["smtp_ssl"] is True
        assert second["recipients"] == [
            "a@example.com",
            "b@example.com",
        ]
        assert report_service.get_report_config(db)["smtp_password"] == (
            "app-password"
        )

        third = report_service.save_report_settings(
            db,
            _payload(
                smtp_host="smtp.office365.com",
                smtp_password="new-app-password",
                recipients=["c@example.com"],
            ),
            "superadmin",
        )
        assert third["smtp_host"] == "smtp.office365.com"
        assert third["recipients"] == ["c@example.com"]
        assert report_service.get_report_config(db)["smtp_password"] == (
            "new-app-password"
        )
    finally:
        db.close()


def _fake_smtp(monkeypatch, exc: Exception | None = None):
    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, username, password):
            if exc is not None:
                raise exc

        def noop(self):
            pass

        def quit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(report_service.smtplib, "SMTP", FakeSMTP)


def _smtp_cfg(**overrides) -> dict:
    cfg = {
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_username": "panel@gmail.com",
        "smtp_password": "app-password",
        "smtp_tls": True,
        "smtp_ssl": False,
    }
    cfg.update(overrides)
    return cfg


def test_smtp_connection_reports_success(monkeypatch):
    _fake_smtp(monkeypatch)
    result = report_service.test_smtp_connection(_smtp_cfg())
    assert result["ok"] is True
    assert "berhasil" in result["message"]


def test_smtp_connection_gmail_auth_error_mentions_app_password(monkeypatch):
    _fake_smtp(
        monkeypatch,
        smtplib.SMTPAuthenticationError(
            535, b"5.7.8 Username and Password not accepted"
        ),
    )
    with pytest.raises(ValueError) as exc:
        report_service.test_smtp_connection(_smtp_cfg())
    assert "App Password" in str(exc.value)


def test_smtp_connection_requires_password(monkeypatch):
    _fake_smtp(monkeypatch)
    with pytest.raises(ValueError) as exc:
        report_service.test_smtp_connection(_smtp_cfg(smtp_password=""))
    assert "Password SMTP" in str(exc.value)
