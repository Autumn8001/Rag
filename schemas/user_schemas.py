from pydantic import BaseModel, Field, validator
from datetime import datetime
import re

class UserRegister(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码，长度不低于 6 位")

    @validator("username")
    def validate_username(cls, v):
        if not re.match(r"^[a-zA-Z0-9_-]{2,50}$", v):
            raise ValueError("用户名只允许包含字母、数字、下划线(_)或连字符(-)，长度为 2-50 位。")
        return v

class UserLogin(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")

class TokenResponse(BaseModel):
    access_token: str = Field(..., description="访问令牌")
    token_type: str = Field("bearer", description="令牌类型")
    username: str = Field(..., description="用户名")
    tenant_id: str = Field(..., description="分配或绑定的隔离租户 ID")

class UserInfoResponse(BaseModel):
    username: str = Field(..., description="用户名")
    tenant_id: str = Field(..., description="隔离租户 ID")
    created_at: datetime = Field(..., description="创建时间")
