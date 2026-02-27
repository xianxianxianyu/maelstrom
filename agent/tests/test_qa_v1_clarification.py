from agent.qa_context_v1.clarification import ClarificationManager
from agent.qa_context_v1.models import Stage2Result


def test_clarification_manager_merge():
    manager = ClarificationManager()
    merged = manager.merge_clarification("这个怎么做", "针对发布流程，给我分步骤")
    assert "这个怎么做" in merged
    assert "发布流程" in merged


def test_clarification_manager_should_clarify():
    manager = ClarificationManager()
    stage2 = Stage2Result(sub_problems=[], routing_plan=[], clarification_needed=True)
    assert manager.should_clarify(stage2) is True
