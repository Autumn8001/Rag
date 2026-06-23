from datetime import datetime, timedelta
from fastapi import Header, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import APIKeyMap, User
from core.config import settings

import bcrypt


# 声明 OAuth2 Bearer Token 解析器（允许在 Swagger UI 或 API 请求中通过 Header 自动校验）
# auth/login 为我们的登录接口路由
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码是否与哈希密码匹配"""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    """对明文密码进行 bcrypt 哈希加密"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """生成 JWT 访问令牌 (Access Token)"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

async def get_current_user(
    authorization: str | None = Header(None, description="Bearer Token 认证"),
    x_api_key: str | None = Header(None, alias="X-API-Key", description="API 密钥 (向下兼容旧版)"),
    db: Session = Depends(get_db)
) -> User:
    """
    统一登录鉴权依赖项：
    1. 优先提取 Authorization Header 中的 Bearer JWT 令牌进行校验并获取当前用户。
    2. 若未携带 JWT 令牌，则退化检测 X-API-Key 进行身份映射（保证历史评测与测试脚本平滑兼容）。
    """
    # 优先解析 JWT Bearer Token
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    
    if token:
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="凭证校验失败，令牌可能已失效或被篡改。",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                raise credentials_exception
        except JWTError:
            raise credentials_exception
            
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户不存在，鉴权失败。",
            )
        return user

    # 兼容退化方案：检测 X-API-Key
    if x_api_key:
        mapping = db.query(APIKeyMap).filter(APIKeyMap.api_key == x_api_key).first()
        if not mapping:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的 X-API-Key，鉴权失败。",
            )
        # 构造虚拟临时用户返回，保证原有 RAG 和评测逻辑无痛运行
        virtual_user = User(
            username=mapping.user_id,
            tenant_id=mapping.tenant_id
        )
        return virtual_user

    # 两者皆无，抛出未授权异常
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未提供认证令牌（Authorization Header）或 API 密钥（X-API-Key），请登录后再操作。",
        headers={"WWW-Authenticate": "Bearer"},
    )
