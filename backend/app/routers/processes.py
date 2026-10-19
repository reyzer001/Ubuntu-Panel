from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_write
from ..db.database import get_db
from ..services import collectors
from ..services.audit import record

router = APIRouter(prefix="/processes", tags=["processes"])


class KillBody(BaseModel):
    confirm: bool = True


@router.get("")
def processes(_: str = Depends(get_current_user)):
    return {"processes": collectors.list_processes()}


@router.post("/{pid}/kill", dependencies=[Depends(require_write)])
def kill(pid: int, user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    if pid <= 1:
        raise HTTPException(status_code=400, detail="Refusing to kill PID 1")
    result = collectors.kill_process(pid)
    record(db, user, "PROCESS_KILL", str(pid), "SUCCESS" if result["success"] else "FAILED")
    db.commit()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["output"])
    return result
