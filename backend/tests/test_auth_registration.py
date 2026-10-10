from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import User
from app.routers.auth import register
from app.schemas import RegisterRequest


def test_public_registration_is_closed_after_initial_owner_exists():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(User(username="owner", password_hash="already-hashed"))
    db.commit()

    with pytest.raises(HTTPException) as exc:
        register(RegisterRequest(username="another-user", password="unused-long-password"), db=db)

    assert exc.value.status_code == 403
    assert db.query(User).count() == 1
