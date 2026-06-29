from datetime import datetime
import re

from pydantic import BaseModel, Field, field_validator


USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{2,50}$")


class UserRegister(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, description="Username")
    password: str = Field(..., min_length=6, max_length=100, description="Password")

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not USERNAME_PATTERN.fullmatch(value):
            raise ValueError(
                "Username may only contain letters, numbers, underscores, and hyphens (2-50 chars)."
            )
        return value


class UserLogin(BaseModel):
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="Access token")
    token_type: str = Field(default="bearer", description="Token type")
    username: str = Field(..., description="Username")
    tenant_id: str = Field(..., description="Tenant identifier")
    expires_at: datetime | None = Field(default=None, description="Session expiry timestamp")


class UserInfoResponse(BaseModel):
    username: str = Field(..., description="Username")
    tenant_id: str = Field(..., description="Tenant identifier")
    created_at: datetime = Field(..., description="Created timestamp")
    is_temporary: bool = Field(default=False, description="Whether this is a temporary visitor")
    expires_at: datetime | None = Field(default=None, description="Temporary visitor expiry timestamp")
