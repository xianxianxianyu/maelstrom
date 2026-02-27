from fastapi import APIRouter

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/list")
async def list_agents():
    return {
        "agents": [
            {
                "name": "qa",
                "description": "Context-first QA V1 endpoint at /api/qa/v1/query",
                "available": True,
            }
        ]
    }
