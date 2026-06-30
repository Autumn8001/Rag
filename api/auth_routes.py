import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.config import settings
from core.auth import (
    create_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from core.database import get_db
from core.models import User
from schemas.user_schemas import TokenResponse, UserInfoResponse, UserLogin, UserRegister


router = APIRouter(prefix="/auth", tags=["Auth"])


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _build_token_payload(user: User, expires_at: datetime | None = None) -> dict:
    access_token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "tenant_id": user.tenant_id,
        }
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username,
        "tenant_id": user.tenant_id,
        "expires_at": expires_at,
    }


@router.post(
    "/register",
    response_model=UserInfoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register_user(payload: UserRegister, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == payload.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists.",
        )

    tenant_suffix = uuid.uuid4().hex[:8]
    tenant_id = f"tenant_{payload.username}_{tenant_suffix}"
    new_user = User(
        username=payload.username,
        hashed_password=get_password_hash(payload.password),
        tenant_id=tenant_id,
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register user: {exc}",
        ) from exc


@router.post("/login", response_model=TokenResponse, summary="Log in")
async def login_user(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    if user.is_temporary and user.expires_at and user.expires_at <= _utc_now_naive():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Temporary visitor account has expired.",
        )

    return _build_token_payload(user, user.expires_at if user.is_temporary else None)


@router.post(
    "/visitor-login",
    response_model=TokenResponse,
    summary="Create an isolated temporary visitor session",
)
async def visitor_login(db: Session = Depends(get_db)):
    suffix = uuid.uuid4().hex[:12]
    now = _utc_now_naive()
    expires_at = now + timedelta(minutes=settings.VISITOR_SESSION_TTL_MINUTES)
    visitor = User(
        username=f"visitor_{suffix}",
        hashed_password=get_password_hash(uuid.uuid4().hex),
        tenant_id=f"tenant_visitor_{suffix}",
        created_at=now,
        is_temporary=True,
        expires_at=expires_at,
        last_active_at=now,
    )

    try:
        db.add(visitor)
        db.commit()
        db.refresh(visitor)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create visitor session: {exc}",
        ) from exc

    return _build_token_payload(visitor, expires_at)


@router.get("/me", response_model=UserInfoResponse, summary="Current user info")
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
