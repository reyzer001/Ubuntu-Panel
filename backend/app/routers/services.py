from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_write
from ..db.database import get_db
from ..services import collectors
from ..services.audit import record

router = APIRouter(prefix="/services", tags=["services"])


@router.get("")
def services(_: str = Depends(get_current_user)):
    return collectors.list_services()


@router.post("/{name}/{action}", dependencies=[Depends(require_write)])
def service_action(
    name: str,
    action: str,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = collectors.service_action(name, action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        result = {"success": False, "output": str(exc)}

    record(
        db,
        user,
        f"SERVICE_{action.upper()}",
        name,
        "SUCCESS" if result["success"] else "FAILED",
    )
    db.commit()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["output"])
    return result
