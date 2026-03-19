"""P3-00: Synthesis Engine Artifact Schema tests."""
from datetime import datetime, timezone

import pytest

from maelstrom.schemas.claim import Claim, ClaimType
from maelstrom.schemas.evidence import Evidence
from maelstrom.schemas.feasibility import FeasibilityMemo, FeasibilityVerdict
from maelstrom.schemas.review_report import ConflictPoint, ConsensusPoint, ReviewReport
from maelstrom.schemas.synthesis import SynthesisRunState
from maelstrom.schemas.common import RunStatus


NOW = datetime.now(timezone.utc)


def _make_claim(**kw):
    defaults = dict(
        claim_id="c1", paper_id="p1", claim_type=ClaimType.method_effectiveness,
        text="BERT outperforms LSTM on NER", confidence=0.9,
    )
    defaults.update(kw)
    return Claim(**defaults)


def _make_evidence(**kw):
    defaults = dict(evidence_id="e1", source_id="p1", snippet="Table 3 shows...", created_at=NOW)
    defaults.update(kw)
    return Evidence(**defaults)


def _make_report(**kw):
    defaults = dict(report_id="r1", session_id="s1", topic="NER", created_at=NOW)
    defaults.update(kw)
    return ReviewReport(**defaults)


def _make_memo(**kw):
    defaults = dict(
        memo_id="m1", report_id="r1", verdict=FeasibilityVerdict.advance,
        gap_validity="valid", existing_progress="partial", resource_assessment="reasonable",
        reasoning="Worth pursuing", confidence=0.8, created_at=NOW,
    )
    defaults.update(kw)
    return FeasibilityMemo(**defaults)


# --- Claim ---
def test_claim_schema():
    c = _make_claim(evidence_refs=["e1"], extracted_fields={"method": "BERT"})
    assert c.claim_id == "c1"
    assert c.claim_type == ClaimType.method_effectiveness
    assert c.evidence_refs == ["e1"]
    assert c.extracted_fields["method"] == "BERT"
    assert 0 <= c.confidence <= 1


def test_claim_type_enum():
    assert len(ClaimType) == 6
    names = {e.value for e in ClaimType}
    assert "method_effectiveness" in names
    assert "negative_result" in names


# --- Evidence ---
def test_evidence_schema():
    e = _make_evidence(source_span="page 4", modality="table", retrieved_via="fts")
    assert e.evidence_id == "e1"
    assert e.modality == "table"
    assert e.retrieved_via == "fts"


# --- ReviewReport ---
def test_review_report_schema():
    claim = _make_claim()
    evidence = _make_evidence()
    consensus = ConsensusPoint(statement="BERT is effective", supporting_claim_ids=["c1"], strength="strong")
    conflict = ConflictPoint(statement="Dataset size matters", claim_ids=["c1", "c2"], requires_followup=True)
    r = _make_report(
        claims=[claim], evidences=[evidence],
        consensus_points=[consensus], conflict_points=[conflict],
        open_questions=["What about low-resource?"], paper_count=5,
    )
    assert len(r.claims) == 1
    assert len(r.consensus_points) == 1
    assert r.conflict_points[0].requires_followup is True
    assert r.open_questions == ["What about low-resource?"]
    assert r.paper_count == 5


# --- FeasibilityMemo ---
def test_feasibility_memo_schema():
    m = _make_memo()
    assert m.verdict == FeasibilityVerdict.advance
    assert m.gap_validity == "valid"
    assert m.existing_progress == "partial"
    assert m.resource_assessment == "reasonable"
    assert 0 <= m.confidence <= 1


def test_feasibility_verdict_enum():
    assert len(FeasibilityVerdict) == 3
    assert set(v.value for v in FeasibilityVerdict) == {"advance", "revise", "reject"}


# --- SynthesisRunState ---
def test_synthesis_run_state():
    state = SynthesisRunState(
        run_id="run1", session_id="s1", topic="NER", created_at=NOW,
    )
    assert state.status == RunStatus.pending
    assert state.current_step == "pending"
    assert state.targeted_papers == []
    assert state.claims == []
    assert state.review_report is None
    assert state.feasibility_memo is None


# --- Serialization roundtrip ---
def test_serialization_roundtrip():
    claim = _make_claim()
    evidence = _make_evidence()
    memo = _make_memo()
    report = _make_report(claims=[claim], evidences=[evidence], paper_count=3)
    state = SynthesisRunState(
        run_id="run1", session_id="s1", topic="NER", created_at=NOW,
        claims=[claim], evidences=[evidence],
        review_report=report, feasibility_memo=memo,
    )
    data = state.model_dump(mode="json")
    restored = SynthesisRunState.model_validate(data)
    assert restored.run_id == "run1"
    assert len(restored.claims) == 1
    assert restored.review_report.report_id == "r1"
    assert restored.feasibility_memo.verdict == FeasibilityVerdict.advance
