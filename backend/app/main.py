import asyncio
import logging
import socket
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from .core.config import get_settings
from .core.security import decode_token
from .db.database import engine
from .db.seed import run_seed

log = logging.getLogger(__name__)

DISCOVERY_PORT = 8001
DISCOVERY_MAGIC = b"PANEL_DISCOVERY"
DISCOVERY_RESPONSE_PREFIX = b"PANEL_SERVER|"


def _get_lan_ip() -> str:
    """IP LAN utama (bukan loopback)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _discovery_listener(tcp_port: int) -> None:
    """UDP listener — jawab broadcast discovery dari agent di LAN."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", DISCOVERY_PORT))
        sock.settimeout(1)
        log.info("discovery UDP listener started on port %d", DISCOVERY_PORT)
    except OSError as exc:
        log.warning("discovery UDP bind failed: %s", exc)
        return

    lan_ip = _get_lan_ip()
    response = f"{DISCOVERY_RESPONSE_PREFIX.decode()}{lan_ip}|{tcp_port}".encode()

    while True:
        try:
            data, addr = sock.recvfrom(1024)
            if data.strip() == DISCOVERY_MAGIC:
                sock.sendto(response, addr)
                log.debug("discovery reply to %s:%d", addr[0], addr[1])
        except socket.timeout:
            continue
        except OSError:
            break
    sock.close()


def _auto_migrate() -> None:
    """Tambah kolom baru ke tabel yang sudah ada tanpa bergantung ke SQLite-only DDL."""
    try:
        inspector = inspect(engine)
        additions = {
            "access_points": [("segment", "VARCHAR(64)", "''")],
            "managed_computers": [
                ("smb_open", "BOOLEAN", "NULL"),
                ("server_reach", "VARCHAR(16)", "''"),
                ("download_mbps", "FLOAT", "NULL"),
                ("upload_mbps", "FLOAT", "NULL"),
                ("speed_test_at", "TIMESTAMP", "NULL"),
                ("ap_seen_at", "TIMESTAMP", "NULL"),
                ("net_rx_pending", "FLOAT", "0"),
                ("net_tx_pending", "FLOAT", "0"),
            ],
            "web_services": [("tunnel_auto", "BOOLEAN", "false")],
            "metric_samples": [("temp", "FLOAT", "NULL")],
            "computer_metric_samples": [
                ("net_rx_bytes", "FLOAT", "0"),
                ("net_tx_bytes", "FLOAT", "0"),
                ("net_seconds", "FLOAT", "0"),
            ],
            "computer_metric_hourly": [
                ("net_rx_bytes", "FLOAT", "0"),
                ("net_tx_bytes", "FLOAT", "0"),
                ("net_seconds", "FLOAT", "0"),
            ],
            "computer_speed_samples": [
                ("source", "VARCHAR(16)", "'server'"),
            ],
        }

        for table, cols in additions.items():
            if not inspector.has_table(table):
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            for col_name, col_type, default in cols:
                if col_name in existing:
                    continue
                try:
                    with engine.begin() as conn:
                        conn.execute(text("SET LOCAL lock_timeout = '5s'"))
                        conn.execute(
                            text(
                                f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type} DEFAULT {default}"
                            )
                        )
                    log.info("auto-migrate: added %s.%s", table, col_name)
                except Exception as exc:
                    # Tabel sedang di-lock transaksi lain: lewati kolom ini
                    # agar startup tidak menggantung selamanya.
                    log.warning(
                        "auto-migrate: lewati %s.%s (%s)", table, col_name, exc
                    )
    except Exception as exc:
        log.warning("auto-migrate failed: %s", exc)
from .routers import (
    accesspoints,
    auth,
    backup,
    cameras,
    computers,
    docker,
    files,
    firewall,
    logs,
    maintenance,
    myzrok,
    panel_users,
    printers,
    processes,
    report,
    services,
    settings,
    system,
    terminal,
    users,
    websites,
)
from .services import apmon
from .services import cammon
from .services import backup as backup_service
from .services import collectors
from .services import topology as topology_service
from .services import dbcleanup as dbcleanup_service
from .services import metrics_history
from .services import report_scheduler
from .services import websites as webrunner


@asynccontextmanager
async def lifespan(app: FastAPI):
    _auto_migrate()
    run_seed()
    backup_service.start_scheduler()
    apmon.start_scheduler()
    cammon.start_monitor()
    topology_service.start_scheduler()
    dbcleanup_service.start_scheduler()
    metrics_history.start_sampler()
    report_scheduler.start_scheduler()
    webrunner.start_monitor()
    t = threading.Thread(
        target=_discovery_listener,
        args=(8000,),
        daemon=True,
    )
    t.start()
    yield


app_settings = get_settings()

app = FastAPI(title=app_settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    auth,
    system,
    services,
    processes,
    logs,
    users,
    panel_users,
    docker,
    firewall,
    terminal,
    backup,
    maintenance,
    accesspoints,
    websites,
    files,
    computers,
    printers,
    cameras,
    report,
    settings,
    myzrok,
):
    app.include_router(router.router, prefix="/api")

app.include_router(cameras.view_router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "version": app_settings.app_version}


@app.websocket("/api/ws/metrics")
async def metrics_ws(websocket: WebSocket, token: str = ""):
    if decode_token(token) is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(collectors.get_metrics())
            await asyncio.sleep(2)
    except (WebSocketDisconnect, Exception):
        try:
            await websocket.close()
        except Exception:
            pass
