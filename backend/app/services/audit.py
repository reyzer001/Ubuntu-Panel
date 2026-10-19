from sqlalchemy.orm import Session

from ..db.models import AuditLog


def record(db: Session, username: str, action: str, target: str = "", result: str = "SUCCESS") -> None:
    # Truncate ke batas kolom (models.AuditLog) agar nilai panjang tidak
    # memicu StringDataRightTruncation (500) di PostgreSQL.
    db.add(
        AuditLog(
            username=(username or "")[:64],
            action=(action or "")[:128],
            target=(target or "")[:256],
            result=(result or "")[:32],
        )
    )
