import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LOG_DIRS = (
    PROJECT_ROOT / ".run" / "logs",
    PROJECT_ROOT / "backend" / "data" / "weblogs",
)
MAX_BYTES = int(
    os.getenv("CLEANUP_LOG_MAX_BYTES", str(25 * 1024 * 1024))
)
KEEP_BYTES = int(
    os.getenv("CLEANUP_LOG_KEEP_BYTES", str(2 * 1024 * 1024))
)


def _trim_file(path: Path, max_bytes: int, keep_bytes: int) -> int:
    before = path.stat().st_size
    if before <= max_bytes:
        return 0
    keep = max(0, min(keep_bytes, before))
    with path.open("r+b") as handle:
        handle.seek(-keep, os.SEEK_END)
        tail = handle.read()
        handle.seek(0)
        handle.write(tail)
        handle.truncate()
    return before - keep


def trim_logs(
    roots: tuple[Path, ...] | None = None,
    max_bytes: int | None = None,
    keep_bytes: int | None = None,
) -> dict:
    """Pangkas log yang membengkak tanpa menghapus file aktif.

    Hanya bagian akhir log yang dipertahankan agar proses yang masih menulis
    (append) tidak kehilangan file descriptor.
    """
    roots = roots or DEFAULT_LOG_DIRS
    max_bytes = MAX_BYTES if max_bytes is None else max(0, max_bytes)
    keep_bytes = KEEP_BYTES if keep_bytes is None else max(0, keep_bytes)
    trimmed = 0
    freed = 0
    details: list[dict] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.log")):
            if not path.is_file():
                continue
            try:
                saved = _trim_file(path, max_bytes, keep_bytes)
            except OSError:
                log.warning("gagal memangkas log %s", path, exc_info=True)
                continue
            if saved <= 0:
                continue
            trimmed += 1
            freed += saved
            details.append(
                {
                    "path": str(path),
                    "bytes_freed": saved,
                    "size": path.stat().st_size,
                }
            )
    if trimmed:
        log.info("log dipangkas: %d file, %d byte", trimmed, freed)
    return {
        "files": trimmed,
        "bytes_freed": freed,
        "details": details,
    }
