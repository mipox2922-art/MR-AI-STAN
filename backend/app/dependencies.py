from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import decode_token

security = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    try:
        payload = decode_token(credentials.credentials)

        if not isinstance(payload, dict):
            raise ValueError("Invalid token payload")

        user_id = payload.get("sub")

        if user_id is None:
            raise ValueError("Token subject missing")

        user = db.query(User).filter(User.id == int(user_id)).first()

        if user is None:
            raise ValueError("User not found")

        return user

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
        )
