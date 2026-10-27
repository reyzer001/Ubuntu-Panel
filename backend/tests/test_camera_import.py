from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import AccessPoint, Camera
from app.routers.cameras import _create_cctv_cameras_from_aps


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_auto_import_skips_aps_without_camera_ports(monkeypatch):
    db = _session()
    try:
        reachable = AccessPoint(
            mac="aa:bb:cc:dd:ee:01",
            ip="10.0.0.10",
            vendor="Dahua",
        )
        unreachable = AccessPoint(
            mac="aa:bb:cc:dd:ee:02",
            ip="10.0.0.20",
            vendor="Hikvision",
        )
        db.add_all([reachable, unreachable])
        db.commit()

        def fake_probe(ip, port=80, rtsp_port=554, timeout=0.35):
            open_port = ip == "10.0.0.10"
            return {"web": open_port, "rtsp": open_port}

        monkeypatch.setattr(
            "app.routers.cameras.cammon.probe_ports", fake_probe
        )

        created = _create_cctv_cameras_from_aps(
            db, [reachable, unreachable]
        )
        db.commit()

        assert created == 1
        assert [cam.ip for cam in db.query(Camera).all()] == ["10.0.0.10"]
    finally:
        db.close()
