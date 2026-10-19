from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_write
from ..db.database import get_db
from ..services import collectors
from ..services.audit import record

router = APIRouter(prefix="/docker", tags=["docker"])


class ActionBody(BaseModel):
    action: str


class DeployBody(BaseModel):
    image: str
    name: str = ""
    ports: str = ""


class DeleteBody(BaseModel):
    remove_image: bool = False


@router.get("/containers")
def containers(_: str = Depends(get_current_user)):
    return collectors.list_containers()


@router.post("/deploy", dependencies=[Depends(require_write)])
def deploy_container(
    body: DeployBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not body.image.strip():
        raise HTTPException(status_code=400, detail="Image is required")
    try:
        result = collectors.deploy_container(
            body.image.strip(), body.name.strip(), body.ports
        )
        record(db, user, "CONTAINER_DEPLOY", body.image.strip(), "SUCCESS")
    except ValueError as exc:
        record(db, user, "CONTAINER_DEPLOY", body.image.strip(), "FAILED")
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        record(db, user, "CONTAINER_DEPLOY", body.image.strip(), "FAILED")
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return result


@router.get("/{name}/detail")
def container_detail(name: str, _: str = Depends(get_current_user)):
    try:
        return collectors.container_detail(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{name}/action", dependencies=[Depends(require_write)])
def container_action(
    name: str,
    body: ActionBody,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = collectors.container_action(name, body.action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        result = {"success": False, "output": str(exc)}
    record(
        db, user, f"CONTAINER_{body.action.upper()}", name,
        "SUCCESS" if result["success"] else "FAILED",
    )
    db.commit()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["output"])
    return result


@router.delete("/{name}", dependencies=[Depends(require_write)])
def delete_container(
    name: str,
    body: DeleteBody | None = None,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    remove_img = body.remove_image if body else False
    try:
        result = collectors.remove_container(name, remove_image=remove_img)
    except Exception as exc:
        result = {"success": False, "output": str(exc)}
    record(
        db, user, "CONTAINER_DELETE", name,
        "SUCCESS" if result["success"] else "FAILED",
    )
    db.commit()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["output"])
    return result
