from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_write
from ..db.database import get_db
from ..services import collectors
from ..services.audit import record

router = APIRouter(prefix="/users", tags=["users"])


class CreateUserBody(BaseModel):
    username: str


@router.get("")
def users(_: str = Depends(get_current_user)):
    return {"users": collectors.list_users()}


@router.post("", dependencies=[Depends(require_write)])
def create_user(
    body: CreateUserBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = collectors.create_user(body.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    record(db, user, "USER_CREATE", body.username, "SUCCESS" if result["success"] else "FAILED")
    db.commit()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["output"])
    return result


@router.delete("/{username}", dependencies=[Depends(require_write)])
def delete_user(
    username: str,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = collectors.delete_user(username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    record(db, user, "USER_DELETE", username, "SUCCESS" if result["success"] else "FAILED")
    db.commit()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["output"])
    return result
