from __future__ import annotations

import json
import os
import platform
import stat
import subprocess
from pathlib import Path

from maelstrom.schemas.llm_config import EmbeddingConfig, LLMProfile, MaelstromConfig

_config: MaelstromConfig | None = None

CONFIG_DIR = Path.home() / ".maelstrom"
CONFIG_FILE = CONFIG_DIR / "config.json"


# ── File I/O ──────────────────────────────────────────────────────────


def _ensure_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _set_file_permissions(path: Path) -> None:
    """Set file to owner-only read/write (600)."""
    if platform.system() == "Windows":
        try:
            user = os.environ.get("USERNAME", "")
            if user:
                subprocess.run(
                    ["icacls", str(path), "/inheritance:r",
                     "/grant:r", f"{user}:(R,W)"],
                    capture_output=True, check=False,
                )
        except Exception:
            pass
    else:
        try:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass


def _load_from_disk() -> MaelstromConfig:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return MaelstromConfig.model_validate(data)
        except Exception:
            pass
    return MaelstromConfig()


def _save_to_disk(config: MaelstromConfig) -> None:
    _ensure_dir()
    CONFIG_FILE.write_text(
        config.model_dump_json(indent=2), encoding="utf-8"
    )
    _set_file_permissions(CONFIG_FILE)


# ── Key masking ───────────────────────────────────────────────────────


def mask_key(key: str | None) -> str | None:
    if not key or len(key) < 8:
        return key
    return key[:3] + "***" + key[-4:]


def _mask_profile(profile: LLMProfile) -> LLMProfile:
    return profile.model_copy(update={"api_key": mask_key(profile.api_key)})


def _mask_config(config: MaelstromConfig) -> MaelstromConfig:
    masked_profiles = {k: _mask_profile(v) for k, v in config.profiles.items()}
    masked_embedding = config.embedding.model_copy(
        update={"api_key": mask_key(config.embedding.api_key)}
    )
    return config.model_copy(update={
        "profiles": masked_profiles,
        "embedding": masked_embedding,
    })


def _is_masked(key: str | None) -> bool:
    return key is not None and "***" in key


def _merge_key(new_key: str | None, old_key: str | None) -> str | None:
    """If the incoming key is masked, keep the original."""
    if new_key is None:
        return None
    if _is_masked(new_key):
        return old_key
    return new_key


# ── Public API ────────────────────────────────────────────────────────


def get_config() -> MaelstromConfig:
    global _config
    if _config is None:
        _config = _load_from_disk()
    return _config


def get_config_masked() -> MaelstromConfig:
    return _mask_config(get_config())


def get_active_profile() -> LLMProfile:
    return get_config().get_active_profile_or_raise()


def get_active_profile_dict() -> dict:
    return get_active_profile().model_dump()


def update_config(new_config: MaelstromConfig) -> MaelstromConfig:
    global _config
    old = get_config()
    # Merge masked keys back from old config
    merged_profiles: dict[str, LLMProfile] = {}
    for slug, profile in new_config.profiles.items():
        old_profile = old.profiles.get(slug)
        old_key = old_profile.api_key if old_profile else None
        merged_profiles[slug] = profile.model_copy(
            update={"api_key": _merge_key(profile.api_key, old_key)}
        )
    merged_embedding = new_config.embedding.model_copy(
        update={"api_key": _merge_key(new_config.embedding.api_key, old.embedding.api_key)}
    )
    _config = new_config.model_copy(update={
        "profiles": merged_profiles,
        "embedding": merged_embedding,
    })
    # Validate active_profile points to an existing profile
    if _config.profiles and _config.active_profile not in _config.profiles:
        _config.active_profile = next(iter(_config.profiles))
    _save_to_disk(_config)
    return _config


def create_profile(slug: str, profile: LLMProfile) -> MaelstromConfig:
    config = get_config()
    if slug in config.profiles:
        raise ValueError(f"Profile '{slug}' already exists")
    config.profiles[slug] = profile
    # Auto-set active if this is the first profile or active is dangling
    if len(config.profiles) == 1 or config.active_profile not in config.profiles:
        config.active_profile = slug
    _save_to_disk(config)
    return config


def update_profile(slug: str, profile: LLMProfile) -> MaelstromConfig:
    config = get_config()
    if slug not in config.profiles:
        raise ValueError(f"Profile '{slug}' not found")
    old_key = config.profiles[slug].api_key
    config.profiles[slug] = profile.model_copy(
        update={"api_key": _merge_key(profile.api_key, old_key)}
    )
    _save_to_disk(config)
    return config


def delete_profile(slug: str) -> MaelstromConfig:
    config = get_config()
    if slug not in config.profiles:
        raise ValueError(f"Profile '{slug}' not found")
    if config.active_profile == slug:
        raise ValueError("Cannot delete the active profile")
    del config.profiles[slug]
    _save_to_disk(config)
    return config


def set_active_profile(slug: str) -> MaelstromConfig:
    config = get_config()
    if slug not in config.profiles:
        raise ValueError(f"Profile '{slug}' not found")
    config.active_profile = slug
    _save_to_disk(config)
    return config
