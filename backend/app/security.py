from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from pwdlib import PasswordHash

from .config import settings


ALGORITHM = "HS256"

password_hash = PasswordHash.recommended()


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return get_password_hash(password)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    to_encode = data.copy()

    if expires_delta is None:
        expires_delta = timedelta(
            minutes=settings.access_token_expire_minutes
        )

    expire = datetime.now(timezone.utc) + expires_delta
    to_encode["exp"] = expire

    return jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def create_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    return create_access_token(data, expires_delta)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
        )
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc


def decode_token(token: str) -> dict:
    return decode_access_token(token)
