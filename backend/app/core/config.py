from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # File handling
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS: set = {".pdf"}

    # Paths
    UPLOAD_DIR: str = "uploads"
    TEMP_DIR: str = "temp"

    # CORS
    CORS_ORIGINS: list[str] = ["*"]

    # Note: API Keys are managed in memory via key_store.py
    # Not stored in files for security


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance"""
    return Settings()
