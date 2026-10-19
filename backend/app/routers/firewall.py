from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_write
from ..db.database import get_db
from ..services import collectors
from ..services.audit import record

router = APIRouter(prefix="/firewall", tags=["firewall"])


class RuleBody(BaseModel):
    port: str
    protocol: str = "tcp"
    action: str = "allow"
    source: str = ""


@router.get("")
def status(_: str = Depends(get_current_user)):
    return collectors.ufw_status()


@router.post("/rules", dependencies=[Depends(require_write)])
def add_rule(
    body: RuleBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = collectors.ufw_add_rule(
            body.port, body.protocol, body.action, (body.source or "").strip()
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    record(
        db, user, "FIREWALL_ADD", f"{body.port}/{body.protocol} {body.action}"
        + (f" from {body.source}" if body.source else ""),
        "SUCCESS" if result["success"] else "FAILED",
    )
    db.commit()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["output"])
    return result


@router.delete("/rules/{port}/{protocol}", dependencies=[Depends(require_write)])
def delete_rule(
    port: str,
    protocol: str,
    source: str = "",
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = collectors.ufw_delete_rule(port, protocol, source.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    record(db, user, "FIREWALL_DELETE", f"{port}/{protocol}"
           + (f" from {source}" if source else ""), "SUCCESS" if result["success"] else "FAILED")
    db.commit()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["output"])
    return result
