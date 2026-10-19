from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import get_current_user
from ..db.database import get_db
from ..services import collectors

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("")
def logs(
    lines: int = 200,
    level: str = "ALL",
    _: str = Depends(get_current_user),
):
    if level not in ("ALL", "INFO", "WARN", "ERROR"):
        raise HTTPException(status_code=400, detail="Invalid level")
    lines = max(1, min(lines, 2000))
    return {"entries": collectors.read_logs(lines=lines, level=level)}
