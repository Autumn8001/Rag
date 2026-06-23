import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import User
from core.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user
)
from schemas.user_schemas import UserRegister, UserLogin, TokenResponse, UserInfoResponse

router = APIRouter(prefix="/auth", tags=["认证模块"])

@router.post("/register", response_model=UserInfoResponse, status_code=status.HTTP_201_CREATED, summary="用户注册")
async def register_user(payload: UserRegister, db: Session = Depends(get_db)):
    """
    注册新用户，并为其自动分配唯一的默认隔离租户 ID。
    """
    # 检查用户名是否重复
    existing_user = db.query(User).filter(User.username == payload.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该用户名已被注册，请尝试其他用户名。",
        )
    
    # 自动生成随机租户 ID
    tenant_suffix = uuid.uuid4().hex[:8]
    tenant_id = f"tenant_{payload.username}_{tenant_suffix}"
    
    # 哈希加密密码
    hashed_pwd = get_password_hash(payload.password)
    
    # 创建用户
    new_user = User(
        username=payload.username,
        hashed_password=hashed_pwd,
        tenant_id=tenant_id
    )
    
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"注册失败，数据库异常: {str(e)}"
        )

@router.post("/login", response_model=TokenResponse, summary="用户登录")
async def login_user(payload: UserLogin, db: Session = Depends(get_db)):
    """
    用户登录认证，成功后返回 JWT Token 及对应的租户信息。
    """
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误，请重新输入。",
        )
    
    # 签发 token，携带用户名、用户 ID 和租户 ID
    token_data = {
        "sub": user.username,
        "user_id": user.id,
        "tenant_id": user.tenant_id
    }
    access_token = create_access_token(data=token_data)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username,
        "tenant_id": user.tenant_id
    }

@router.get("/me", response_model=UserInfoResponse, summary="当前用户信息")
async def get_me(current_user: User = Depends(get_current_user)):
    """
    解析令牌获取当前登录的用户名与对应的隔离租户 ID。
    """
    return current_user
