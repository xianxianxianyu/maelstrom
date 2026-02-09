"""YAML 配置文件加载器 — 支持 profiles + bindings 格式"""
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

import yaml

from .config import LLMConfig

logger = logging.getLogger(__name__)

# 默认配置文件路径：项目根目录下的 key/llm_config.yaml
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "key" / "llm_config.yaml"


def _migrate_legacy(data: dict) -> Tuple[dict, dict]:
    """将旧的 functions 格式自动转换为 profiles + bindings"""
    profiles = {}
    bindings = {}
    for key, value in data.get("functions", {}).items():
        profiles[key] = value
        bindings[key] = key
    return profiles, bindings


def load_config_data(
    config_path: Optional[Path] = None,
) -> Tuple[Dict[str, LLMConfig], Dict[str, str]]:
    """从 YAML 文件加载配置，返回 (profiles, bindings)"""
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        logger.warning(f"LLM 配置文件不存在: {path}，使用空配置")
        return {}, {}

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        logger.warning(f"LLM 配置文件为空: {path}")
        return {}, {}

    # 兼容旧格式
    if "functions" in data and "profiles" not in data:
        raw_profiles, bindings = _migrate_legacy(data)
    else:
        raw_profiles = data.get("profiles", {})
        bindings = data.get("bindings", {})

    profiles: Dict[str, LLMConfig] = {}
    for name, value in raw_profiles.items():
        try:
            config = LLMConfig(
                provider=value.get("provider", ""),
                model=value.get("model", ""),
                api_key=value.get("api_key", ""),
                base_url=value.get("base_url"),
                max_tokens=value.get("max_tokens", 4096),
                temperature=value.get("temperature", 0.3),
                extra_params=value.get("extra_params", {}),
            )
            profiles[name] = config
            logger.info(f"已加载 LLM 档案: {name} -> {config.provider}/{config.model}")
        except Exception as e:
            logger.error(f"加载 LLM 档案 '{name}' 失败: {e}")

    return profiles, bindings


def save_config_data(
    profiles: Dict[str, LLMConfig],
    bindings: Dict[str, str],
    config_path: Optional[Path] = None,
) -> None:
    """将 profiles + bindings 保存到 YAML 文件"""
    path = config_path or DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {"profiles": {}, "bindings": dict(bindings)}
    for name, config in profiles.items():
        entry: dict = {
            "provider": config.provider,
            "model": config.model,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }
        if config.api_key:
            entry["api_key"] = config.api_key
        if config.base_url:
            entry["base_url"] = config.base_url
        if config.extra_params:
            entry["extra_params"] = config.extra_params
        data["profiles"][name] = entry

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info(f"已保存 {len(profiles)} 个 LLM 档案到: {path}")


# 向后兼容别名
def load_llm_configs(config_path: Optional[Path] = None) -> Dict[str, LLMConfig]:
    """向后兼容：返回 profiles 字典"""
    profiles, _ = load_config_data(config_path)
    return profiles
