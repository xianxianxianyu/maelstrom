"""OCR YAML 配置文件加载器"""
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

import yaml

from .config import OCRConfig

logger = logging.getLogger(__name__)

DEFAULT_OCR_CONFIG_PATH = Path(__file__).parent.parent.parent / "key" / "ocr_config.yaml"


def load_ocr_config_data(
    config_path: Optional[Path] = None,
) -> Tuple[Dict[str, OCRConfig], Dict[str, str]]:
    """从 YAML 文件加载 OCR 配置，返回 (profiles, bindings)"""
    path = config_path or DEFAULT_OCR_CONFIG_PATH
    if not path.exists():
        logger.warning(f"OCR 配置文件不存在: {path}，使用空配置")
        return {}, {}

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        logger.warning(f"OCR 配置文件为空: {path}")
        return {}, {}

    raw_profiles = data.get("profiles", {})
    bindings = data.get("bindings", {})

    profiles: Dict[str, OCRConfig] = {}
    for name, value in raw_profiles.items():
        try:
            config = OCRConfig(
                provider=value.get("provider", "paddleocr"),
                mode=value.get("mode", "sync"),
                api_url=value.get("api_url", ""),
                token=value.get("token", ""),
                model=value.get("model", ""),
                use_chart_recognition=value.get("use_chart_recognition", False),
                use_doc_orientation_classify=value.get("use_doc_orientation_classify", False),
                use_doc_unwarping=value.get("use_doc_unwarping", False),
                extra_params=value.get("extra_params", {}),
            )
            profiles[name] = config
            logger.info(f"已加载 OCR 档案: {name} -> {config.provider}/{config.mode}")
        except Exception as e:
            logger.error(f"加载 OCR 档案 '{name}' 失败: {e}")

    return profiles, bindings


def save_ocr_config_data(
    profiles: Dict[str, OCRConfig],
    bindings: Dict[str, str],
    config_path: Optional[Path] = None,
) -> None:
    """将 OCR profiles + bindings 保存到 YAML 文件"""
    path = config_path or DEFAULT_OCR_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {"profiles": {}, "bindings": dict(bindings)}
    for name, config in profiles.items():
        entry: dict = {
            "provider": config.provider,
            "mode": config.mode,
        }
        if config.api_url:
            entry["api_url"] = config.api_url
        if config.token:
            entry["token"] = config.token
        if config.model:
            entry["model"] = config.model
        entry["use_chart_recognition"] = config.use_chart_recognition
        entry["use_doc_orientation_classify"] = config.use_doc_orientation_classify
        entry["use_doc_unwarping"] = config.use_doc_unwarping
        if config.extra_params:
            entry["extra_params"] = config.extra_params
        data["profiles"][name] = entry

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info(f"已保存 {len(profiles)} 个 OCR 档案到: {path}")
