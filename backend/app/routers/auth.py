from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import AuthStatusResponse, LoginRequest, RegisterRequest, TokenResponse
from ..security import (
    create_access_token,
    verify_password,
    hash_password,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.get(
    "/status",
    response_model=AuthStatusResponse,
)
def auth_status(
    db: Session = Depends(get_db),
):
    return AuthStatusResponse(
        setup_required=db.query(User.id).first() is None,
    )


@router.post(
    "/register",
    response_model=TokenResponse,
)
def register(
    data: RegisterRequest,
    db: Session = Depends(get_db),
):
    # This deployment is a single-owner command center. Public registration is
    # available only for the initial bootstrap account; all later users must log in.
    if db.query(User.id).first() is not None:
        raise HTTPException(
            status_code=403,
            detail="Initial setup is already complete. Log in with the existing account.",
        )

    existing = (
        db.query(User)
        .filter(User.username == data.username)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Username already exists",
        )

    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(
        {"sub": str(user.id)}
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
    )


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    data: LoginRequest,
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter(User.username == data.username)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    if not verify_password(
        data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    token = create_access_token(
        {"sub": str(user.id)}
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
    )
