from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.security import hash_password
from .database import Base, engine, SessionLocal
from .models import User


def _add_column_if_missing(table_name: str, column_name: str, ddl: str) -> None:
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        return
    existing = {col["name"] for col in inspector.get_columns(table_name)}
    if column_name in existing:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))


def _migrate_user_columns() -> None:
    """DB lama belum punya kolom baru di users — tambahkan lewat ALTER TABLE."""
    required = {
        "role": "VARCHAR(20) NOT NULL DEFAULT 'superadmin'",
        "full_name": "VARCHAR(128) NOT NULL DEFAULT ''",
        "email": "VARCHAR(128) NOT NULL DEFAULT ''",
        "phone": "VARCHAR(32) NOT NULL DEFAULT ''",
        "last_login_at": "TIMESTAMP",
        "last_seen_at": "TIMESTAMP",
        "logout_at": "TIMESTAMP",
    }
    for column_name, ddl in required.items():
        _add_column_if_missing("users", column_name, ddl)


def _migrate_computer_columns() -> None:
    """DB lama belum punya kolom baru di managed_computers — ALTER TABLE."""
    required = {
        "group_name": "VARCHAR(64) NOT NULL DEFAULT ''",
        "conn_type": "VARCHAR(16) NOT NULL DEFAULT ''",
        "ssid": "VARCHAR(64) NOT NULL DEFAULT ''",
        "iface_name": "VARCHAR(32) NOT NULL DEFAULT ''",
        "wifi_ip": "VARCHAR(45) NOT NULL DEFAULT ''",
        "ap_ip": "VARCHAR(45) NOT NULL DEFAULT ''",
        "ap_mac": "VARCHAR(128) NOT NULL DEFAULT ''",
        "autostart_mode": "VARCHAR(64) NOT NULL DEFAULT ''",
        "smb_open": "BOOLEAN",
        "latency_srv_ms": "REAL",
        "pending_cmd": "VARCHAR(200)",
        "cmd_issued_at": "TIMESTAMP",
        "last_cmd_result": "VARCHAR(160) NOT NULL DEFAULT ''",
    }
    for column_name, ddl in required.items():
        _add_column_if_missing("managed_computers", column_name, ddl)
    _widen_pending_cmd()


def _widen_pending_cmd() -> None:
    """DB lama menyimpan pending_cmd di VARCHAR(16) — perlebar agar perintah
    seperti 'install:notepad-plus-plus' atau 'share-printer:<key>' tidak terpotong."""
    inspector = inspect(engine)
    if not inspector.has_table("managed_computers"):
        return
    try:
        with engine.begin() as conn:
            if str(engine.url).startswith("sqlite"):
                return  # SQLite mengabaikan panjang VARCHAR — tidak perlu ALTER
            conn.execute(
                text("ALTER TABLE managed_computers "
                     "ALTER COLUMN pending_cmd TYPE VARCHAR(200)")
            )
    except Exception:
        pass


def _migrate_web_app_columns() -> None:
    """Tambahkan metadata runtime website pada DB lama."""
    required = {
        "runtime": "VARCHAR(16) NOT NULL DEFAULT 'native'",
        "php_version": "VARCHAR(16) NOT NULL DEFAULT ''",
        "docker_image": "VARCHAR(256) NOT NULL DEFAULT ''",
        "dockerfile": "VARCHAR(1024) NOT NULL DEFAULT ''",
        "docker_container": "VARCHAR(128) NOT NULL DEFAULT ''",
        "docker_status": "VARCHAR(32) NOT NULL DEFAULT ''",
        "compose_file": "TEXT NOT NULL DEFAULT ''",
        "compose_project": "VARCHAR(128) NOT NULL DEFAULT ''",
    }
    for column_name, ddl in required.items():
        _add_column_if_missing("web_apps", column_name, ddl)


def run_seed() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_user_columns()
    _migrate_computer_columns()
    _migrate_web_app_columns()
    db: Session = SessionLocal()
    try:
        if db.query(User).count() == 0:
            settings = get_settings()
            db.add(
                User(
                    username=settings.admin_username,
                    password_hash=hash_password(settings.admin_password),
                    role="superadmin",
                )
            )
            db.commit()
            print(
                f"[seed] Created default superadmin '{settings.admin_username}' "
                "- change the password in production (ADMIN_PASSWORD env)."
            )
    finally:
        db.close()
