"""
API Key 管理路由
- 设置/删除/查询 Key 状态
- Key 只存在内存中
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.key_store import key_store

router = APIRouter(prefix="/api/keys", tags=["keys"])


class SetKeyRequest(BaseModel):
    provider: str
    api_key: str


class KeyStatusResponse(BaseModel):
    provider: str
    has_key: bool


@router.post("/set")
async def set_api_key(request: SetKeyRequest):
    """设置 API Key 到内存缓存"""
    if not request.api_key or not request.api_key.strip():
        raise HTTPException(status_code=400, detail="API key cannot be empty")

    key_store.set_key(request.provider, request.api_key.strip())
    return {"message": f"API key for {request.provider} has been set", "provider": request.provider}


@router.delete("/{provider}")
async def delete_api_key(provider: str):
    """删除内存中的 API Key"""
    if key_store.delete_key(provider):
        return {"message": f"API key for {provider} has been deleted", "provider": provider}
    else:
        raise HTTPException(status_code=404, detail=f"No API key found for {provider}")


@router.get("/status")
async def get_key_status():
    """查看哪些 provider 有 Key（不返回实际值）"""
    status = key_store.get_status()
    providers = ["zhipuai", "openai", "deepseek"]
    return {
        "keys": [
            {"provider": p, "has_key": p in status}
            for p in providers
        ]
    }
