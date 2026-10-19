"""File manager: browse, download, upload, mkdir, delete via API panel.

Semua endpoint butuh auth Bearer token; aksesnya lewat hostname browser
(localhost / IP LAN / IP Tailscale) sehingga transfer file bisa dilakukan
dari perangkat mana pun di jaringan.
"""

import json
import os
import shutil
import stat as statmod
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_write
from ..db.database import get_db
from ..services import audit

router = APIRouter(tags=["files"])

_CHUNK = 8 * 1024 * 1024
_MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "5120")) * 1024 * 1024

# direktori level-atas yang boleh DIBUKA tapi tidak boleh DIHAPUS utuh
_PROTECTED_ROOTS = {
    "/",
    "/bin",
    "/boot",
    "/dev",
    "/etc",
    "/home",
    "/lib",
    "/lib32",
    "/lib64",
    "/libx32",
    "/proc",
    "/root",
    "/run",
    "/sbin",
    "/srv",
    "/sys",
    "/tmp",
    "/usr",
    "/var",
    "/snap",
}


def _safe(path: str) -> Path:
    if "\x00" in path:
        raise HTTPException(400, "Path tidak valid")
    p = Path(os.path.abspath(os.path.expanduser(path.strip() or "/")))
    if not p.exists():
        raise HTTPException(404, f"Tidak ditemukan: {path}")
    return p


def _safe_unlink(p: str) -> None:
    try:
        os.unlink(p)
    except OSError:
        pass


def _entry(e: Path) -> dict:
    try:
        st = e.lstat()
        is_dir = e.is_dir()
        size = 0 if is_dir else st.st_size
        mode = statmod.filemode(st.st_mode)
        mtime = int(st.st_mtime)
    except OSError:
        is_dir, size, mode, mtime = False, 0, "?", 0
    return {
        "name": e.name,
        "path": str(e),
        "is_dir": is_dir,
        "is_symlink": e.is_symlink(),
        "size": size,
        "mode": mode,
        "mtime": mtime,
    }


# ------------------------------------------------------------------ list
@router.get("/files/list", dependencies=[Depends(require_write)])
def list_dir(
    path: str = "",
    show_hidden: bool = False,
    _: str = Depends(get_current_user),
):
    target = _safe(path) if path.strip() else Path.home().resolve()
    if not target.is_dir():
        raise HTTPException(400, f"Bukan folder: {target}")
    try:
        children = list(target.iterdir())
    except PermissionError:
        raise HTTPException(403, "Akses ditolak oleh sistem")
    entries = []
    for child in sorted(children, key=lambda c: c.name.lower()):
        if not show_hidden and child.name.startswith("."):
            continue
        entries.append(_entry(child))
    entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    parent = str(target.parent) if target.parent != target else None
    free = None
    try:
        usage = shutil.disk_usage(target)
        free = usage.free
    except OSError:
        pass
    return {"path": str(target), "parent": parent, "entries": entries, "free": free}


# -------------------------------------------------------------- download
@router.get("/files/download", dependencies=[Depends(require_write)])
def download(
    path: str,
    background: BackgroundTasks,
    _: str = Depends(get_current_user),
):
    p = _safe(path)
    if not os.access(p, os.R_OK):
        raise HTTPException(403, "Tidak bisa dibaca")
    # file biasa → unduh langsung
    if not p.is_dir():
        return FileResponse(p, filename=p.name)
    # folder → kompres jadi .zip (stream hasil ke temp, hapus setelah terkirim)
    fd, tmp = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(p):
                for name in files:
                    full = os.path.join(root, name)
                    if not os.access(full, os.R_OK):
                        continue
                    rel = os.path.relpath(full, p.parent)
                    zf.write(full, rel)
    except Exception as e:
        _safe_unlink(tmp)
        raise HTTPException(500, f"Gagal membuat arsip zip: {e}")
    background.add_task(_safe_unlink, tmp)
    return FileResponse(
        tmp,
        filename=(p.name or "folder") + ".zip",
        media_type="application/zip",
    )


# ---------------------------------------------------------------- upload
@router.post("/files/upload", dependencies=[Depends(require_write)])
async def upload(
    path: str = Form(...),
    relative_path: str = Form(""),
    file: UploadFile = File(...),
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target_dir = _safe(path)
    if not target_dir.is_dir():
        raise HTTPException(400, f"Bukan folder: {target_dir}")
    rel = (relative_path or file.filename or "").replace("\\", "/").lstrip("/")
    rel_path = Path(rel)
    if not rel or rel_path.is_absolute() or ".." in rel_path.parts:
        raise HTTPException(400, "Path file tidak valid")
    name = rel_path.name
    if not name or name in {".", ".."}:
        raise HTTPException(400, "Nama file tidak valid")
    dest = target_dir / rel_path
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise HTTPException(500, f"Gagal membuat folder: {e}")
    written = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(_CHUNK)
                if not chunk:
                    break
                written += len(chunk)
                if written > _MAX_UPLOAD_BYTES:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        413,
                        f"Ukuran melebihi batas {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB "
                        "(naikkan MAX_UPLOAD_MB bila perlu)",
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except OSError as e:
        raise HTTPException(500, f"Gagal menulis file: {e}")
    finally:
        await file.close()

    audit.record(db, username, "FILE_UPLOAD", target=str(dest))
    db.commit()
    return {"ok": True, "path": str(dest), "size": written}


# ------------------------------------------------------------ upload batch
@router.post("/files/upload-batch", dependencies=[Depends(require_write)])
async def upload_batch(
    path: str = Form(...),
    relative_paths: str = Form("[]"),
    files: list[UploadFile] = File(...),
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload beberapa file sekaligus (untuk upload folder).
    relative_paths = JSON array of string, satu per file — relative path
    dari root folder yang dipilih (mis. "myfolder/sub/file.txt").
    Bila kosong, pakai filename masing-masing.
    """
    target_dir = _safe(path)
    if not target_dir.is_dir():
        raise HTTPException(400, f"Bukan folder: {target_dir}")

    try:
        rpaths = json.loads(relative_paths)
    except (json.JSONDecodeError, TypeError):
        rpaths = []

    if len(rpaths) > 0 and len(rpaths) != len(files):
        raise HTTPException(400, "Jumlah paths tidak cocok dengan jumlah file")

    results: list[dict] = []
    total_written = 0

    for i, fobj in enumerate(files):
        # tentukan relative path
        if i < len(rpaths) and rpaths[i]:
            rel = rpaths[i]
        else:
            rel = Path(fobj.filename or "").name

        # bersihkan path: buang leading slash, normalisasi
        rel = rel.lstrip("/").replace("\\", "/")
        rel_path = Path(rel)
        if (
            not rel
            or rel_path.is_absolute()
            or ".." in rel_path.parts
            or (rel.startswith(".") and len(rel_path.parts) == 1)
        ):
            continue  # skip hidden root entries

        # buat subfolder jika perlu
        parts = rel_path.parts
        if len(parts) > 1:
            subdir = target_dir
            for part in parts[:-1]:
                subdir = subdir / part
                subdir.mkdir(parents=True, exist_ok=True)

        name = parts[-1] if parts else Path(fobj.filename or "").name
        if not name or name in {".", ".."}:
            continue

        dest = target_dir / rel
        written = 0
        try:
            with dest.open("wb") as out:
                while True:
                    chunk = await fobj.read(_CHUNK)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > _MAX_UPLOAD_BYTES:
                        results.append({
                            "path": rel,
                            "error": f"Melebihi batas {_MAX_UPLOAD_BYTES // (1024*1024)} MB",
                        })
                        break
                    out.write(chunk)
            total_written += written
            results.append({"path": rel, "ok": True, "size": written})
        except OSError as e:
            results.append({"path": rel, "error": str(e)})
        finally:
            await fobj.close()

    audit.record(db, username, "FILE_UPLOAD_BATCH", target=str(target_dir))
    db.commit()
    return {"ok": True, "results": results, "total": total_written}


# ----------------------------------------------------------------- mkdir
class MkdirIn(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    name: str = Field(min_length=1, max_length=255)


@router.post("/files/mkdir", dependencies=[Depends(require_write)])
def mkdir(
    body: MkdirIn,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    parent = _safe(body.path)
    if not parent.is_dir():
        raise HTTPException(400, f"Bukan folder: {parent}")
    name = body.name.strip()
    if "/" in name or "\x00" in name or name in {".", ".."}:
        raise HTTPException(400, "Nama folder tidak valid")
    dest = parent / name
    if dest.exists():
        raise HTTPException(409, f"Sudah ada: {dest}")
    try:
        dest.mkdir(parents=False)
    except OSError as e:
        raise HTTPException(500, f"Gagal membuat folder: {e}")
    audit.record(db, username, "FILE_MKDIR", target=str(dest))
    db.commit()
    return {"ok": True, "path": str(dest)}


# ---------------------------------------------------------------- delete
@router.delete("/files", dependencies=[Depends(require_write)])
def delete(
    path: str,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = _safe(path)
    # larang hapus file/folder di dalam protected roots
    if any(str(p) == root or str(p).startswith(root + "/") for root in _PROTECTED_ROOTS):
        raise HTTPException(403, f"Dilarang menghapus {p}")
    try:
        if p.is_symlink() or not p.is_dir():
            p.unlink()
        else:
            shutil.rmtree(p)
    except OSError as e:
        raise HTTPException(500, f"Gagal menghapus: {e}")
    audit.record(db, username, "FILE_DELETE", target=str(p))
    db.commit()
    return {"ok": True}
