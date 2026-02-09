"""LLM 配置 CRUD API — profiles + bindings 模式"""
import logging
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.llm import get_llm_manager, load_config_data, LLMConfig
from core.llm.loader import save_config_data, DEFAULT_CONFIG_PATH

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm-config", tags=["llm-config"])


class ProfileRequest(BaseModel):
    """单个档案配置"""
    provider: str
    model: str
    api_key: Optional[str] = ""
    base_url: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 4096


class LLMConfigSaveRequest(BaseModel):
    """保存请求：profiles + bindings"""
    profiles: Dict[str, ProfileRequest]
    bindings: Dict[str, str]


@router.get("")
async def get_llm_config():
    """读取当前 LLM 配置（profiles + bindings）"""
    manager = get_llm_manager()
    profiles = manager.get_all_profiles()
    bindings = manager.get_all_bindings()

    # 如果内存为空，尝试从文件加载
    if not profiles:
        profiles, bindings = load_config_data()

    result_profiles = {}
    for name, config in profiles.items():
        result_profiles[name] = {
            "provider": config.provider,
            "model": config.model,
            "api_key": config.api_key,
            "base_url": config.base_url,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }

    return {"profiles": result_profiles, "bindings": bindings}


@router.post("")
async def save_llm_config(request: LLMConfigSaveRequest):
    """保存 LLM 配置到 YAML 并注册到 LLMManager"""
    manager = get_llm_manager()
    profiles_to_save = {}

    for name, prof in request.profiles.items():
        config = LLMConfig(
            provider=prof.provider,
            model=prof.model,
            api_key=prof.api_key or "",
            base_url=prof.base_url,
            temperature=prof.temperature,
            max_tokens=prof.max_tokens,
        )
        profiles_to_save[name] = config
        manager.register_profile(name, config)

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
    """从 YAML 重新加载配置"""
    manager = get_llm_manager()

    try:
        profiles, bindings = load_config_data()
    except Exception as e:
        logger.error(f"加载 LLM 配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"加载配置失败: {e}")

    for name, config in profiles.items():
        manager.register_profile(name, config)
    manager.set_bindings(bindings)

    return {
        "message": f"已重新加载 {len(profiles)} 个档案",
        "loaded_profiles": list(profiles.keys()),
    }
