"""OCR 配置 CRUD API — profiles + bindings 模式"""
import logging
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.ocr import get_ocr_manager, load_ocr_config_data, OCRConfig
from core.ocr.loader import save_ocr_config_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ocr-config", tags=["ocr-config"])


class OCRProfileRequest(BaseModel):
    """单个 OCR 档案配置"""
    provider: str = "paddleocr"
    mode: str = "sync"
    api_url: Optional[str] = ""
    token: Optional[str] = ""
    model: Optional[str] = ""
    use_chart_recognition: bool = False
    use_doc_orientation_classify: bool = False
    use_doc_unwarping: bool = False


class OCRConfigSaveRequest(BaseModel):
    """保存请求：profiles + bindings"""
    profiles: Dict[str, OCRProfileRequest]
    bindings: Dict[str, str]


@router.get("")
async def get_ocr_config():
    """读取当前 OCR 配置"""
    manager = get_ocr_manager()
    profiles = manager.get_all_profiles()
    bindings = manager.get_all_bindings()

    if not profiles:
        profiles, bindings = load_ocr_config_data()

    result_profiles = {}
    for name, config in profiles.items():
        result_profiles[name] = {
            "provider": config.provider,
            "mode": config.mode,
            "api_url": config.api_url,
            "token": config.token,
            "model": config.model,
            "use_chart_recognition": config.use_chart_recognition,
            "use_doc_orientation_classify": config.use_doc_orientation_classify,
            "use_doc_unwarping": config.use_doc_unwarping,
        }

    return {"profiles": result_profiles, "bindings": bindings}


@router.post("")
async def save_ocr_config(request: OCRConfigSaveRequest):
    """保存 OCR 配置到 YAML 并注册到 OCRManager"""
    manager = get_ocr_manager()
    valid_providers = set(manager._provider_registry.keys())
    profiles_to_save = {}

    for name, prof in request.profiles.items():
        # 校验 provider 是否合法
        if prof.provider not in valid_providers:
            raise HTTPException(
                status_code=400,
                detail=f"档案 '{name}' 的 provider '{prof.provider}' 不合法，可选: {', '.join(valid_providers)}",
            )
        # 校验 MineRU 必须有 token
        if prof.provider == "mineru" and not (prof.token or "").strip():
            logger.warning(f"档案 '{name}' 使用 MineRU 但未配置 Token")

        config = OCRConfig(
            provider=prof.provider,
            mode=prof.mode,
            api_url=prof.api_url or "",
            token=prof.token or "",
            model=prof.model or "",
            use_chart_recognition=prof.use_chart_recognition,
            use_doc_orientation_classify=prof.use_doc_orientation_classify,
            use_doc_unwarping=prof.use_doc_unwarping,
        )
        profiles_to_save[name] = config
        manager.register_profile(name, config)

    manager.set_bindings(request.bindings)

    # 校验 bindings 引用的 profile 必须存在
    for key, profile_name in request.bindings.items():
        if profile_name and profile_name not in profiles_to_save:
            logger.warning(f"绑定 '{key}' -> '{profile_name}' 引用了不存在的档案")

    try:
        save_ocr_config_data(profiles_to_save, request.bindings)
    except Exception as e:
        logger.error(f"保存 OCR 配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"保存配置失败: {e}")

    return {
        "message": f"已保存 {len(profiles_to_save)} 个 OCR 档案",
        "saved_profiles": list(profiles_to_save.keys()),
    }


@router.post("/reload")
async def reload_ocr_config():
    """从 YAML 重新加载 OCR 配置"""
    manager = get_ocr_manager()

    try:
        profiles, bindings = load_ocr_config_data()
    except Exception as e:
        logger.error(f"加载 OCR 配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"加载配置失败: {e}")

    for name, config in profiles.items():
        manager.register_profile(name, config)
    manager.set_bindings(bindings)

    return {
        "message": f"已重新加载 {len(profiles)} 个 OCR 档案",
        "loaded_profiles": list(profiles.keys()),
    }
