import logging
import logging.config
import sys
from pathlib import Path

# 将项目根目录添加到 sys.path，确保 core 包可导入
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── 统一日志配置 ──
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
            "datefmt": "%H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        # 压掉 httpx 每次请求的 INFO 日志，只保留 WARNING+
        "httpx": {"level": "WARNING"},
        "httpcore": {"level": "WARNING"},
        # uvicorn access log 保持 INFO
        "uvicorn.access": {"level": "INFO"},
    },
    "root": {
        "level": "INFO",
        "handlers": ["console"],
    },
}
logging.config.dictConfig(LOGGING_CONFIG)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import pdf, models, keys
from app.api.routes import llm_config as llm_config_route
from app.api.routes import ocr_config as ocr_config_route
from app.api.routes import translations as translations_route
from app.api.routes import agent as agent_route
from app.api.routes import sse as sse_route
from app.api.routes import terminology as terminology_route
from app.api.routes import quality as quality_route
from core.llm import get_llm_manager, load_config_data
from core.ocr import get_ocr_manager, load_ocr_config_data
from app.core.key_store import key_store

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Maelstrom",
    description="Multi-agent PDF translation system — devour documents, distill knowledge",
    version="1.0.0"
)

# Configure CORS - allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(pdf.router)
app.include_router(models.router)
app.include_router(keys.router)
app.include_router(llm_config_route.router)
app.include_router(ocr_config_route.router)
app.include_router(translations_route.router)
app.include_router(agent_route.router)
app.include_router(sse_route.router)
app.include_router(terminology_route.router)
app.include_router(quality_route.router)


@app.get("/")
async def root():
    return {
        "message": "Maelstrom API",
        "version": "1.0.0",
        "endpoints": {
            "upload": "/api/pdf/upload",
            "models": "/api/models/",
            "keys": "/api/keys/",
            "llm_config": "/api/llm-config",
            "ocr_config": "/api/ocr-config",
        }
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.on_event("startup")
async def startup_load_llm_configs():
    """启动时从 YAML 加载 LLM 配置到 LLMManager，并注入 key_resolver"""
    try:
        manager = get_llm_manager()
        # 注入 backend 的 KeyStore 作为 key_resolver
        manager.set_key_resolver(lambda provider: key_store.get_key(provider))

        profiles, bindings = load_config_data()
        for name, config in profiles.items():
            manager.register_profile(name, config)
            # 将 YAML 中的 api_key 注入 KeyStore
            if config.api_key:
                key_store.set_key(config.provider, config.api_key)
        manager.set_bindings(bindings)
        logger.info(f"已从 YAML 加载 {len(profiles)} 个 LLM 档案")
    except Exception as e:
        logger.warning(f"加载 LLM 配置失败（不影响启动）: {e}")

    # 加载 OCR 配置
    try:
        ocr_mgr = get_ocr_manager()
        ocr_mgr.set_key_resolver(lambda provider: key_store.get_key(provider))

        ocr_profiles, ocr_bindings = load_ocr_config_data()
        for name, config in ocr_profiles.items():
            ocr_mgr.register_profile(name, config)
        ocr_mgr.set_bindings(ocr_bindings)
        logger.info(f"已从 YAML 加载 {len(ocr_profiles)} 个 OCR 档案")
    except Exception as e:
        logger.warning(f"加载 OCR 配置失败（不影响启动）: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=3301)
