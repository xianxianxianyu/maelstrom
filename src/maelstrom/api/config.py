from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from maelstrom.schemas.llm_config import LLMProfile, MaelstromConfig
from maelstrom.services.llm_config_service import (
    create_profile,
    delete_profile,
    get_config,
    get_config_masked,
    set_active_profile,
    update_config,
    update_profile,
)

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=MaelstromConfig)
async def get_full_config():
    return get_config_masked()


@router.put("", response_model=MaelstromConfig)
async def put_full_config(config: MaelstromConfig):
    return update_config(config)


@router.get("/profiles", response_model=dict[str, LLMProfile])
async def list_profiles():
    return get_config_masked().profiles


@router.post("/profiles/{slug}", response_model=MaelstromConfig)
async def add_profile(slug: str, profile: LLMProfile):
    try:
        return create_profile(slug, profile)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/profiles/{slug}", response_model=MaelstromConfig)
async def edit_profile(slug: str, profile: LLMProfile):
    try:
        return update_profile(slug, profile)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/profiles/{slug}", response_model=MaelstromConfig)
async def remove_profile(slug: str):
    try:
        return delete_profile(slug)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/active", response_model=MaelstromConfig)
async def switch_active(slug: str):
    try:
        return set_active_profile(slug)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Test endpoints ────────────────────────────────────────────────────


class TestRequest(BaseModel):
    profile: LLMProfile | None = None
    slug: str | None = None


class TestResult(BaseModel):
    ok: bool
    message: str
    latency_ms: int | None = None


@router.post("/test/llm", response_model=TestResult)
async def test_llm(req: TestRequest):
    """Send a minimal LLM request to verify connectivity and auth."""
    import time
    from maelstrom.services.llm_client import call_llm

    # Resolve profile: explicit > slug > active
    profile_obj = req.profile
    if profile_obj is None and req.slug:
        cfg = get_config()
        profile_obj = cfg.profiles.get(req.slug)
    if profile_obj is None:
        cfg = get_config()
        profile_obj = cfg.get_active_profile()
    if profile_obj is None:
        return TestResult(ok=False, message="No profile configured")

    profile_dict = profile_obj.model_dump() if hasattr(profile_obj, "model_dump") else dict(profile_obj)

    try:
        t0 = time.monotonic()
        reply = await call_llm(
            "Reply with exactly: OK", profile_dict,
            max_tokens=16, timeout=15.0,
        )
        ms = int((time.monotonic() - t0) * 1000)
        return TestResult(ok=True, message=reply.strip()[:200], latency_ms=ms)
    except Exception as e:
        return TestResult(ok=False, message=str(e)[:500])


class EmbeddingTestRequest(BaseModel):
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None


@router.post("/test/embedding", response_model=TestResult)
async def test_embedding(req: EmbeddingTestRequest | None = None):
    """Send a minimal embedding request to verify connectivity."""
    import time
    import httpx

    cfg = get_config()
    profile = cfg.get_active_profile()
    emb = cfg.embedding

    # Use inline values if provided, otherwise fall back to saved config
    api_key = (req and req.api_key) or emb.api_key or (profile.api_key if profile else None) or ""
    base_url = ((req and req.base_url) or emb.base_url or (profile.base_url if profile else None) or "https://api.openai.com/v1").rstrip("/")
    model = (req and req.model) or emb.model or "text-embedding-3-small"

    url = f"{base_url}/embeddings"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"model": model, "input": "test"}

    try:
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        ms = int((time.monotonic() - t0) * 1000)
        dim = len(data.get("data", [{}])[0].get("embedding", []))
        return TestResult(ok=True, message=f"OK — {model}, {dim} dimensions", latency_ms=ms)
    except Exception as e:
        return TestResult(ok=False, message=str(e)[:500])
