from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import ManagedComputer, User, UserComputerAccess


def test_user_access_model_can_store_permissions():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        user = User(username="ops1", password_hash="x", role="admin")
        computer = ManagedComputer(name="PC-01", token="tok-01")
        db.add_all([user, computer])
        db.commit()

        access = UserComputerAccess(user_id=user.id, computer_id=computer.id)
        db.add(access)
        db.commit()

        db.refresh(user)
        assert access.user_id == user.id
        assert access.computer_id == computer.id
        assert len(user.computer_access) == 1


def test_user_activity_tracking_fields_exist():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    now = datetime.utcnow()
    with Session(engine) as db:
        user = User(
            username="viewer1",
            password_hash="x",
            role="viewer",
            last_seen_at=now,
            last_login_at=now,
        )
        db.add(user)
        db.commit()

        db.refresh(user)
        assert user.last_seen_at == now
        assert user.last_login_at == now
