from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from ..core.config import get_settings

settings = get_settings()

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 30}

# Pool default SQLAlchemy (size 5 + overflow 10) cepat habis: heartbeat tiap
# 10 dtk dari puluhan agent + apmon + scheduler topologi + cek manual user
# berjalan bersamaan. Probe presence menahan satu koneksi selama ping
# (berdetik-detik) sehingga request lain timeout 30 dtk → toast "gagal".
# Naikkan khusus Postgres; SQLite tetap memakai default (single-file).
if settings.database_url.startswith("sqlite"):
    engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
else:
    engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=20,
        pool_timeout=15,
        pool_recycle=300,
    )

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragma(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
