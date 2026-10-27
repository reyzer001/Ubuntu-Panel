"""API toggle akses publik lewat zrok2 — khusus superadmin."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.deps import (
    get_current_user,
    require_step_up,
    require_superadmin,
)
from ..db.database import get_db
from ..services import audit
from ..services import myzrok

router = APIRouter(prefix="/myzrok", tags=["myzrok"])


@router.get("/status", dependencies=[Depends(require_superadmin)])
def share_status():
    return myzrok.status()


@router.post(
    "/enable",
    dependencies=[
        Depends(require_superadmin),
        Depends(require_step_up("myzrok")),
    ],
)
def share_enable(
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = myzrok.start()
    except RuntimeError as exc:
        audit.record(db, username, "MYZROK_ENABLE", "", "FAILED")
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    audit.record(db, username, "MYZROK_ENABLE", result.get("url", ""))
    db.commit()
    return result


@router.post(
    "/disable",
    dependencies=[
        Depends(require_superadmin),
        Depends(require_step_up("myzrok")),
    ],
)
def share_disable(
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = myzrok.stop()
    except RuntimeError as exc:
        audit.record(db, username, "MYZROK_DISABLE", "", "FAILED")
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    audit.record(db, username, "MYZROK_DISABLE", result.get("url", ""))
    db.commit()
    return result
