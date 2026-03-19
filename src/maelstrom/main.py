from contextlib import asynccontextmanager

from fastapi import FastAPI

from maelstrom.api.chat import router as chat_router
from maelstrom.api.config import router as config_router
from maelstrom.api.docs import router as docs_router
from maelstrom.api.gap import router as gap_router
from maelstrom.api.router import router as router_router
from maelstrom.api.sessions import router as sessions_router
from maelstrom.api.synthesis import router as synthesis_router
from maelstrom.api.planning import router as planning_router
from maelstrom.api.experiment import router as experiment_router
from maelstrom.api.artifacts import router as artifacts_router
from maelstrom.api.traces import router as traces_router
from maelstrom.api.evidence import router as evidence_router
from maelstrom.api.auth import router as auth_router
from maelstrom.api.mcp import router as mcp_router
from maelstrom.api.approvals import router as approvals_router
from maelstrom.api.policies import router as policies_router
from maelstrom.api.settings import router as settings_router
from maelstrom.api.eval import router as eval_router
from maelstrom.db.database import close_db, get_db
from maelstrom.db.migrations import run_migrations


async def _mark_orphaned_runs() -> None:
    """Mark any runs left in 'running' status as failed (orphaned by restart)."""
    import logging
    logger = logging.getLogger(__name__)
    db = await get_db()
    for table in ("gap_runs", "synthesis_runs", "planning_runs", "experiment_runs"):
        try:
            cur = await db.execute(
                f"UPDATE {table} SET status = 'failed' WHERE status = 'running'"
            )
            if cur.rowcount:
                logger.warning("Marked %d orphaned %s as failed", cur.rowcount, table)
            await db.commit()
        except Exception as e:
            logger.warning("Orphan scan for %s failed: %s", table, e)


@asynccontextmanager
async def lifespan(application: FastAPI):
    db = await get_db()
    await run_migrations(db)
    await _mark_orphaned_runs()
    # Register MCP built-in tools
    from maelstrom.mcp.tools import register_builtin_tools
    register_builtin_tools()
    yield
    await close_db()


app = FastAPI(title="Maelstrom", version="0.2.0", lifespan=lifespan)
app.include_router(chat_router)
app.include_router(config_router)
app.include_router(sessions_router)
app.include_router(docs_router)
app.include_router(gap_router)
app.include_router(router_router)
app.include_router(synthesis_router)
app.include_router(planning_router)
app.include_router(experiment_router)
app.include_router(artifacts_router)
app.include_router(traces_router)
app.include_router(evidence_router)
app.include_router(auth_router)
app.include_router(mcp_router)
app.include_router(approvals_router)
app.include_router(policies_router)
app.include_router(settings_router)
app.include_router(eval_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
