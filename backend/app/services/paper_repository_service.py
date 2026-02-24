import asyncio

from agent.tools.paper_repository import PaperRepository

_repo_lock = asyncio.Lock()
_repo: PaperRepository | None = None


async def get_paper_repository() -> PaperRepository:
    global _repo
    if _repo is not None:
        return _repo

    async with _repo_lock:
        if _repo is None:
            repo = PaperRepository()
            await repo.init_db()
            _repo = repo
    return _repo
