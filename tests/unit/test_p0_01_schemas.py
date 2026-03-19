from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from maelstrom.schemas import (
    ExternalIds,
    GapAnalysisResult,
    GapItem,
    GapScores,
    LLMProfile,
    PaperRecord,
    ProtocolEnum,
    RunStatus,
    SearchResult,
    SessionStatus,
    SourceStatus,
)


def test_llm_profile_defaults():
    cfg = LLMProfile()
    assert cfg.protocol == ProtocolEnum.openai_chat
    assert cfg.model == "gpt-4o"
    assert cfg.temperature == 0.7
    assert cfg.max_tokens == 4096
    assert cfg.api_key is None
    assert cfg.base_url == "https://api.openai.com/v1"


def test_llm_profile_validation():
    with pytest.raises(ValidationError):
        LLMProfile(temperature=5)
    with pytest.raises(ValidationError):
        LLMProfile(temperature=-1)


def test_paper_record_serialization():
    now = datetime.now(timezone.utc)
    paper = PaperRecord(
        paper_id="p-001",
        title="Test Paper",
        authors=[],
        abstract="Abstract text",
        year=2024,
        venue="NeurIPS",
        doi="10.1234/test",
        external_ids=ExternalIds(arxiv_id="2401.00001"),
        source="arxiv",
        retrieved_at=now,
    )
    data = paper.model_dump(mode="json")
    restored = PaperRecord.model_validate(data)
    assert restored.paper_id == paper.paper_id
    assert restored.title == paper.title
    assert restored.external_ids.arxiv_id == "2401.00001"


def test_gap_item_fields():
    with pytest.raises(ValidationError):
        GapItem()  # missing required fields


def test_session_status_enum():
    assert SessionStatus.active == "active"
    assert SessionStatus.archived == "archived"


def test_external_ids_optional():
    ids = ExternalIds()
    assert ids.arxiv_id is None
    assert ids.s2_id is None
    assert ids.openreview_id is None
    assert ids.openalex_id is None
    assert ids.doi is None


def test_gap_analysis_result_structure():
    now = datetime.now(timezone.utc)
    result = GapAnalysisResult(
        run_id="grun-001",
        session_id="sess-001",
        topic="test topic",
        status=RunStatus.completed,
        search_result=SearchResult(
            source_statuses=[SourceStatus(source="arxiv", status="ok", count=10, latency_ms=500)]
        ),
        created_at=now,
    )
    assert result.search_result.source_statuses[0].source == "arxiv"
    assert result.status == RunStatus.completed


def test_gap_analysis_result_full_papers():
    now = datetime.now(timezone.utc)
    paper = PaperRecord(
        paper_id="p-001", title="Test", source="arxiv", retrieved_at=now
    )
    result = GapAnalysisResult(
        run_id="grun-001",
        session_id="sess-001",
        topic="test",
        status=RunStatus.completed,
        papers=[paper],
        created_at=now,
    )
    assert len(result.papers) == 1
    assert isinstance(result.papers[0], PaperRecord)
    assert result.papers[0].paper_id == "p-001"


def test_gap_analysis_result_full_matrix():
    now = datetime.now(timezone.utc)
    matrix = {
        "task1|method1|ds1|metric1": ["p-001"],
        "summary": {"tasks": 1, "methods": 1, "datasets": 1, "empty_cells_pct": 0.0},
    }
    result = GapAnalysisResult(
        run_id="grun-001",
        session_id="sess-001",
        topic="test",
        status=RunStatus.completed,
        coverage_matrix=matrix,
        created_at=now,
    )
    assert "summary" in result.coverage_matrix
    assert isinstance(result.coverage_matrix, dict)
