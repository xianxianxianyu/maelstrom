import asyncio

from agent.qa_context_v1.kernel import QAContextKernel
from agent.qa_context_v1.models import QueryRequest


def test_kernel_persists_fixed_turn_schema(tmp_path):
    base_dir = tmp_path / "sessions"
    kernel = QAContextKernel.create_default(base_dir=str(base_dir))

    result = asyncio.run(
        kernel.handle_query(
            QueryRequest(
                query="请总结 Python logging 的最佳实践",
                session_id="sess_a",
                doc_scope=["logging.md"],
            )
        )
    )

    assert result.status == "completed"
    turn = kernel.get_turn("sess_a", result.turn_id)
    assert turn is not None
    assert turn["schema_version"] == "qa-turn-v1"
    assert turn["summary"]
    assert turn["tags"]
    assert turn["intent_tag"] in {"DOC_QA", "MULTI_PART", "CHAT", "AMBIGUOUS"}


def test_kernel_session_storage_isolated(tmp_path):
    base_dir = tmp_path / "sessions"
    kernel = QAContextKernel.create_default(base_dir=str(base_dir))

    result_1 = asyncio.run(kernel.handle_query(QueryRequest(query="A 会话问题", session_id="s1")))
    result_2 = asyncio.run(kernel.handle_query(QueryRequest(query="B 会话问题", session_id="s2")))

    turns_s1 = kernel.list_turns("s1")
    turns_s2 = kernel.list_turns("s2")

    assert any(item["turn_id"] == result_1.turn_id for item in turns_s1)
    assert all(item["session_id"] == "s1" for item in turns_s1)
    assert any(item["turn_id"] == result_2.turn_id for item in turns_s2)
    assert all(item["session_id"] == "s2" for item in turns_s2)

    assert (base_dir / "s1" / "context.db").exists()
    assert (base_dir / "s2" / "context.db").exists()


def test_kernel_clarification_flow(tmp_path):
    base_dir = tmp_path / "sessions"
    kernel = QAContextKernel.create_default(base_dir=str(base_dir))

    pending = asyncio.run(kernel.handle_query(QueryRequest(query="这个", session_id="s3")))
    assert pending.status == "clarification_pending"
    assert pending.clarification is not None

    thread_id = pending.clarification["thread_id"]
    resumed = asyncio.run(
        kernel.handle_clarification(
            session_id="s3",
            thread_id=thread_id,
            answer="我想看本周发布计划和风险项",
        )
    )

    assert resumed.status == "completed"
    assert resumed.answer
    assert resumed.session_id == "s3"
