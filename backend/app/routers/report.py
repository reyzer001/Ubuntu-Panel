from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import (
    get_current_user,
    require_page_access,
    require_superadmin,
)
from ..db.database import get_db
from ..services import audit
from ..services import report as report_service

router = APIRouter(prefix="/report", tags=["report"])


class ReportSettingsBody(BaseModel):
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_tls: bool = True
    smtp_ssl: bool = False
    from_addr: str = ""
    recipients: list[str] = []
    schedule: str = "0 7 * * *"
    hours: int = 24
    isp_download_mbps: float | None = None
    isp_upload_mbps: float | None = None


class SmtpTestBody(BaseModel):
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_tls: bool | None = None
    smtp_ssl: bool | None = None
    from_addr: str | None = None


@router.get("/dates", dependencies=[Depends(require_page_access("report"))])
def get_report_dates(days: int = 30, db: Session = Depends(get_db)):
    return report_service.build_available_dates(db, days)


@router.get("", dependencies=[Depends(require_page_access("report"))])
def get_report(hours: int = 24, db: Session = Depends(get_db)):
    return report_service.build_report(db, hours)


@router.get(
    "/export.csv", dependencies=[Depends(require_page_access("report"))]
)
def export_csv(hours: int = 24, db: Session = Depends(get_db)):
    data = report_service.build_report(db, hours)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return Response(
        content=report_service.report_to_csv(data).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="report-{stamp}.csv"'
        },
    )


@router.get(
    "/export.pdf", dependencies=[Depends(require_page_access("report"))]
)
def export_pdf(hours: int = 24, db: Session = Depends(get_db)):
    data = report_service.build_report(db, hours)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    try:
        content = report_service.report_to_pdf(data)
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Library PDF belum terpasang (reportlab)",
        )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="report-{stamp}.pdf"'
        },
    )


@router.post("/reset", dependencies=[Depends(require_superadmin)])
def reset_report(
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return report_service.reset_report_samples(db, user)


@router.get("/settings", dependencies=[Depends(require_superadmin)])
def get_settings(db: Session = Depends(get_db)):
    return report_service.get_report_settings(db)


@router.put("/settings", dependencies=[Depends(require_superadmin)])
def put_settings(
    body: ReportSettingsBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return report_service.save_report_settings(
            db, body.model_dump(), user
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/smtp/test", dependencies=[Depends(require_superadmin)])
def test_smtp(
    body: SmtpTestBody | None = None,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = body.model_dump(exclude_none=True) if body else {}
    try:
        return report_service.test_smtp_settings(db, data, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/send", dependencies=[Depends(require_superadmin)])
def send_now(
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = report_service.send_report_now(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        audit.record(db, user, "REPORT_SEND", "FAILED", "FAILED")
        db.commit()
        raise HTTPException(
            status_code=502, detail=f"Gagal mengirim email: {exc}"
        )
    audit.record(
        db, user, "REPORT_SEND", ", ".join(result.get("recipients", []))
    )
    db.commit()
    return result
