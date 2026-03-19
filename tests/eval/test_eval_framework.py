"""Tests for the eval framework itself."""
import pytest
from tests.eval.framework import EvalCase, EvalRunner, EvalSuiteResult


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_eval_case_creation():
    case = EvalCase(
        id="test-1",
        engine="gap",
        input_params={"topic": "test", "session_id": "s1"},
        recorded_llm_responses=["response1"],
        expected_output_schema={},
        quality_criteria={"min_gaps": 1},
    )
    assert case.id == "test-1"
    assert case.engine == "gap"


def test_quality_check():
    runner = EvalRunner()
    output = {"gaps": [1, 2, 3], "hypothesis": "test"}
    criteria = {"min_gaps": 2, "has_hypothesis": True}
    results = runner._check_quality(output, criteria)
    assert results["min_gaps"] is True
    assert results["has_hypothesis"] is True


def test_quality_check_fail():
    runner = EvalRunner()
    output = {"gaps": [1], "hypothesis": ""}
    criteria = {"min_gaps": 3, "has_hypothesis": True}
    results = runner._check_quality(output, criteria)
    assert results["min_gaps"] is False
    assert results["has_hypothesis"] is False


def test_schema_validation():
    runner = EvalRunner()
    schema = {
        "type": "object",
        "required": ["status"],
        "properties": {"status": {"type": "string"}},
    }
    assert runner._validate_schema({"status": "ok"}, schema) is True
    assert runner._validate_schema({"other": 1}, schema) is False
    assert runner._validate_schema({}, {}) is True
