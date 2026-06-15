from fastapi import Header, HTTPException, status, Depends
from sqlalchemy.orm import Session
from core.database import get_db
from core.models import APIKeyMap

def get_auth_headers(
    x_api_key: str | None = Header(None, alias="X-API-Key", description="API 密钥"),
    db: Session = Depends(get_db)
):
    """
    轻量级 API Key 鉴权拦截依赖项：
    校验请求头中是否包含 X-API-Key，并从数据库匹配关联的 tenant_id 与 user_id。
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Header 中缺少 X-API-Key，鉴权失败。",
        )
    
    # 从数据库中检索映射关系
    mapping = db.query(APIKeyMap).filter(APIKeyMap.api_key == x_api_key).first()
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 X-API-Key，鉴权失败。",
        )
        
    return {"tenant_id": mapping.tenant_id, "user_id": mapping.user_id}
