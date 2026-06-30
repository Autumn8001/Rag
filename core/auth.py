from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db
from core.models import APIKeyMap, User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire_at = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire_at})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def temporary_visitor_expiry_from(now: datetime) -> datetime:
    return now + timedelta(minutes=settings.VISITOR_SESSION_TTL_MINUTES)


def _build_auth_exception(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    authorization: str | None = Header(None, description="Bearer token"),
    x_api_key: str | None = Header(
        None,
        alias="X-API-Key",
        description="Legacy API key compatibility header",
    ),
    db: Session = Depends(get_db),
) -> User:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    if token:
        credentials_exception = _build_auth_exception(
            "登录凭证无效或已过期。"
        )
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            username = payload.get("sub")
            if not username:
                raise credentials_exception
        except JWTError:
            raise credentials_exception

        user = db.query(User).filter(User.username == username).first()
        if user is None:
            raise _build_auth_exception("用户不存在。")

        if user.is_temporary and user.expires_at:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if user.expires_at <= now:
                raise _build_auth_exception("访客会话已过期，请重新登录。")
            user.last_active_at = now
            db.commit()
            db.refresh(user)
        return user

    if x_api_key:
        mapping = db.query(APIKeyMap).filter(APIKeyMap.api_key == x_api_key).first()
        if mapping is None:
            raise _build_auth_exception("X-API-Key 无效。")
        user = (
            db.query(User)
            .filter(User.username == mapping.user_id, User.tenant_id == mapping.tenant_id)
            .first()
        )
        if user is not None:
            return user

        # Keep legacy API key clients working even if the mapped user record is absent.
        return User(
            username=mapping.user_id,
            tenant_id=mapping.tenant_id,
            hashed_password="",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            is_temporary=False,
            expires_at=None,
            last_active_at=None,
        )

    raise _build_auth_exception(
        "缺少认证令牌，请先登录。"
    )
