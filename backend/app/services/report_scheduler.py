import logging
import threading
import time
from datetime import datetime, timedelta

from ..db.database import SessionLocal
from . import report as report_service
from .backup import _cron_valid, cron_matches

log = logging.getLogger(__name__)

_last_fired: dict[str, datetime] = {}


def _scheduler_loop() -> None:
    while True:
        now = datetime.now()
        nxt = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        time.sleep(max(0.0, (nxt - now).total_seconds()))
        fire_minute = nxt
        db = SessionLocal()
        try:
            cfg = report_service.get_report_config(db)
            if not cfg["enabled"] or not cfg["schedule"]:
                continue
            if not _cron_valid(cfg["schedule"]):
                continue
            if not cron_matches(cfg["schedule"], fire_minute):
                continue
            if _last_fired.get("report") == fire_minute:
                continue
            _last_fired["report"] = fire_minute
            data = report_service.build_report(db, cfg["hours"])
            report_service.send_report(data, cfg)
            report_service.mark_sent(db)
            log.info("report email sent to %s", ", ".join(cfg["recipients"]))
        except Exception:
            log.warning("report scheduler error", exc_info=True)
        finally:
            db.close()


def start_scheduler() -> None:
    threading.Thread(
        target=_scheduler_loop,
        daemon=True,
        name="report-scheduler",
    ).start()
