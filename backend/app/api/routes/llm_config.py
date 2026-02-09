"""LLM 配置 CRUD API — profiles + bindings 模式

Key 安全策略：
- API Key 只保存在 key/ 目录的 YAML 文件中
- 启动时从 YAML 加载到内存 KeyStore
- GET 接口不返回 api_key（前端永远看不到）
- POST 保存时 api_key 不能为空
"""
import logging
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.llm import get_llm_manager, load_config_data, LLMConfig
from core.llm.loader import save_config_data
from app.core.key_store import key_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm-config", tags=["llm-config"])


class ProfileRequest(BaseModel):
    """单个档案配置"""
    provider: str
    model: str
    api_key: str = ""
    base_url: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 4096


class LLMConfigSaveRequest(BaseModel):
    """保存请求：profiles + bindings"""
    profiles: Dict[str, ProfileRequest]
    bindings: Dict[str, str]


@router.get("")
async def get_llm_config():
    """读取当前 LLM 配置（profiles + bindings）— 只返回 YAML 持久化的档案，不返回运行时临时注册的"""
    # 始终从 YAML 读取，避免运行时注册的幽灵档案（如 translation、qa）混入
    profiles, bindings = load_config_data()

    result_profiles = {}
    for name, config in profiles.items():
        result_profiles[name] = {
            "provider": config.provider,
            "model": config.model,
            "has_key": bool(config.api_key or key_store.get_key(config.provider)),
            "base_url": config.base_url,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }

    return {"profiles": result_profiles, "bindings": bindings}


@router.post("")
async def save_llm_config(request: LLMConfigSaveRequest):
    """保存 LLM 配置到 YAML 并注册到 LLMManager + KeyStore"""
    manager = get_llm_manager()
    profiles_to_save = {}

    for name, prof in request.profiles.items():
        # 处理 __KEEP__ 占位符：保留原有 key
        actual_key = prof.api_key.strip()
        if actual_key == "__KEEP__":
            # 从现有 profile 或 KeyStore 获取原 key
            existing = manager.get_profile(name)
            if existing and existing.api_key:
                actual_key = existing.api_key
            else:
                actual_key = key_store.get_key(prof.provider) or ""

        # 校验 api_key 不能为空
        if not actual_key:
            raise HTTPException(
                status_code=400,
                detail=f"档案 '{name}' 的 API Key 不能为空",
            )

        config = LLMConfig(
            provider=prof.provider,
            model=prof.model,
            api_key=actual_key,
            base_url=prof.base_url,
            temperature=prof.temperature,
            max_tokens=prof.max_tokens,
        )
        profiles_to_save[name] = config

    # 先清除 manager 中所有用户档案，再重新注册，确保删除操作生效
    # （保留运行时临时档案如 translation/qa，它们会在下次翻译时自动重建）
    old_profiles = set(manager.get_all_profiles().keys())
    for old_name in old_profiles:
        manager.remove_profile(old_name)

    for name, config in profiles_to_save.items():
        manager.register_profile(name, config)
        key_store.set_key(config.provider, config.api_key)

    manager.set_bindings(request.bindings)

    try:
        save_config_data(profiles_to_save, request.bindings)
    except Exception as e:
        logger.error(f"保存 LLM 配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"保存配置失败: {e}")

    return {
        "message": f"已保存 {len(profiles_to_save)} 个档案",
        "saved_profiles": list(profiles_to_save.keys()),
    }


@router.post("/reload")
async def reload_llm_config():
    """从 YAML 重新加载配置，并将 key 注入 KeyStore"""
    manager = get_llm_manager()

    try:
        profiles, bindings = load_config_data()
    except Exception as e:
        logger.error(f"加载 LLM 配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"加载配置失败: {e}")

    for name, config in profiles.items():
        manager.register_profile(name, config)
        # 注入 KeyStore
        if config.api_key:
            key_store.set_key(config.provider, config.api_key)

    manager.set_bindings(bindings)

    return {
        "message": f"已重新加载 {len(profiles)} 个档案",
        "loaded_profiles": list(profiles.keys()),
    }
