"""Eval framework — replay recorded LLM responses, validate output schema and quality."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, patch

import jsonschema

logger = logging.getLogger(__name__)


@dataclass
class EvalCase:
    id: str
    engine: str  # "gap" | "synthesis" | "planning" | "experiment"
    input_params: dict = field(default_factory=dict)
    recorded_llm_responses: list[str] = field(default_factory=list)
    expected_output_schema: dict = field(default_factory=dict)
    quality_criteria: dict = field(default_factory=dict)


@dataclass
class EvalResult:
    case_id: str
    passed: bool
    schema_valid: bool = True
    quality_checks: dict = field(default_factory=dict)
    error: str | None = None
    output: dict = field(default_factory=dict)


@dataclass
class EvalSuiteResult:
    total: int = 0
    passed: int = 0
    failed: int = 0
    results: list[EvalResult] = field(default_factory=list)


class EvalRunner:
    """Run eval cases by mocking LLM calls with recorded responses."""

    async def run_case(self, case: EvalCase) -> EvalResult:
        try:
            output = await self._execute_engine(case)
            schema_valid = self._validate_schema(output, case.expected_output_schema)
            quality_checks = self._check_quality(output, case.quality_criteria)
            all_quality_passed = all(quality_checks.values()) if quality_checks else True
            passed = schema_valid and all_quality_passed
            return EvalResult(
                case_id=case.id, passed=passed, schema_valid=schema_valid,
                quality_checks=quality_checks, output=output,
            )
        except Exception as e:
            logger.exception("Eval case %s failed", case.id)
            return EvalResult(case_id=case.id, passed=False, error=str(e))

    async def run_suite(self, cases: list[EvalCase]) -> EvalSuiteResult:
        results = []
        for case in cases:
            result = await self.run_case(case)
            results.append(result)
        passed = sum(1 for r in results if r.passed)
        return EvalSuiteResult(total=len(results), passed=passed, failed=len(results) - passed, results=results)

    async def _execute_engine(self, case: EvalCase) -> dict:
        responses = list(case.recorded_llm_responses)
        call_idx = {"i": 0}

        async def mock_llm(prompt, profile, **kwargs):
            idx = call_idx["i"]
            call_idx["i"] += 1
            if idx < len(responses):
                return responses[idx]
            return "{}"

        with patch("maelstrom.services.llm_client.call_llm", side_effect=mock_llm):
            if case.engine == "gap":
                return await self._run_gap(case.input_params)
            elif case.engine == "synthesis":
                return await self._run_synthesis(case.input_params)
            elif case.engine == "planning":
                return await self._run_planning(case.input_params)
            elif case.engine == "experiment":
                return await self._run_experiment(case.input_params)
            else:
                raise ValueError(f"Unknown engine: {case.engine}")

    async def _run_gap(self, params: dict) -> dict:
        from maelstrom.services import gap_service
        run_id = await gap_service.start_run(
            params["session_id"], params["topic"], params["profile"],
        )
        import asyncio
        for _ in range(60):
            status = await gap_service.get_status(run_id)
            if status and status["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(0.1)
        result = await gap_service.get_result(run_id)
        return result or {}

    async def _run_synthesis(self, params: dict) -> dict:
        from maelstrom.services import synthesis_service
        run_id = await synthesis_service.start_run(
            params["session_id"], params["topic"], params["profile"],
        )
        import asyncio
        for _ in range(60):
            status = await synthesis_service.get_status(run_id)
            if status and status["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(0.1)
        result = await synthesis_service.get_result(run_id)
        return result or {}

    async def _run_planning(self, params: dict) -> dict:
        from maelstrom.services import planning_service
        run_id = await planning_service.start_run(
            params["session_id"], params["topic"], params["profile"],
        )
        import asyncio
        for _ in range(60):
            status = await planning_service.get_status(run_id)
            if status and status["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(0.1)
        result = await planning_service.get_result(run_id)
        return result or {}

    async def _run_experiment(self, params: dict) -> dict:
        from maelstrom.services import experiment_service
        run_id = await experiment_service.start_run(
            params["session_id"], params["topic"], params["profile"],
        )
        import asyncio
        for _ in range(60):
            status = await experiment_service.get_status(run_id)
            if status and status["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(0.1)
        result = await experiment_service.get_result(run_id)
        return result or {}

    def _validate_schema(self, output: dict, schema: dict) -> bool:
        if not schema:
            return True
        try:
            jsonschema.validate(output, schema)
            return True
        except jsonschema.ValidationError:
            return False

    def _check_quality(self, output: dict, criteria: dict) -> dict:
        results = {}
        for key, expected in criteria.items():
            if key.startswith("min_"):
                field_name = key[4:]
                actual = output.get(field_name)
                if isinstance(actual, list):
                    results[key] = len(actual) >= expected
                elif isinstance(actual, (int, float)):
                    results[key] = actual >= expected
                else:
                    results[key] = False
            elif key.startswith("has_"):
                field_name = key[4:]
                results[key] = bool(output.get(field_name))
            else:
                results[key] = output.get(key) == expected
        return results


def load_case_from_file(path: str) -> EvalCase:
    with open(path) as f:
        data = json.load(f)
    return EvalCase(**data)
