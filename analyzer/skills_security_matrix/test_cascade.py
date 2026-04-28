from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from analyzer.skills_security_matrix.cli import _analyze_skill
from analyzer.skills_security_matrix.exporters.csv_exporter import review_audit_rows_for_result
from analyzer.skills_security_matrix.exporters.json_exporter import review_audit_record
from analyzer.skills_security_matrix.models import (
    AnalysisResult,
    CapabilityMapping,
    CategoryDiscrepancy,
    EvidenceItem,
    FinalCategoryDecision,
    MatrixCategory,
    MatrixDefinition,
    RuleCandidate,
    SkillArtifact,
    SkillStructureProfile,
)
from analyzer.skills_security_matrix.review.cascade import (
    build_category_review_requests,
    build_skill_risk_review_route,
    calculate_rule_skill_risk_confidence_score,
)
from analyzer.skills_security_matrix.review.llm_provider import ProviderRegistry
from analyzer.skills_security_matrix.review.models import CascadePolicyConfig
from analyzer.skills_security_matrix.review.providers.mock_provider import MockReviewProvider
from analyzer.skills_security_matrix.review.skill_risk_reviewer import review_skill_risk


def test_high_confidence_candidate_stays_on_heuristic_path() -> None:
    candidate = _candidate(confidence_score=0.9, evidence_strength="strong", primary_risks=[])

    requests = build_category_review_requests(
        "skill",
        [candidate],
        {"CAT": _category(primary_risks=[])},
        _policy(),
    )

    assert requests == []


def test_low_confidence_candidate_routes_to_llm() -> None:
    candidate = _candidate(confidence_score=0.3, evidence_strength="medium", primary_risks=[])

    requests = build_category_review_requests(
        "skill",
        [candidate],
        {"CAT": _category(primary_risks=[])},
        _policy(),
    )

    assert len(requests) == 1
    assert "low_confidence" in {trigger.trigger_type for trigger in requests[0].triggers}


def test_high_risk_sparse_candidate_routes_to_llm() -> None:
    candidate = _candidate(confidence_score=0.8, evidence_strength="strong", primary_risks=["E"])

    requests = build_category_review_requests(
        "skill",
        [candidate],
        {"CAT": _category(primary_risks=["E"])},
        _policy(high_risk_sparse_threshold=1),
    )

    assert len(requests) == 1
    assert "high_risk_sparse_support" in {trigger.trigger_type for trigger in requests[0].triggers}


def test_semantic_ambiguity_candidate_routes_to_llm_without_strong_evidence() -> None:
    candidate = _candidate(confidence_score=0.8, evidence_strength="medium", primary_risks=[])

    requests = build_category_review_requests(
        "skill",
        [candidate],
        {"CAT": _category(primary_risks=[])},
        _policy(),
    )

    assert len(requests) == 1
    assert "semantic_ambiguity" in {trigger.trigger_type for trigger in requests[0].triggers}


def test_conflicting_candidate_routes_to_llm() -> None:
    candidate = _candidate(confidence_score=0.9, evidence_strength="strong", primary_risks=[])
    candidate.conflicting_evidence.append(_evidence("conflict", evidence_strength="strong"))

    requests = build_category_review_requests(
        "skill",
        [candidate],
        {"CAT": _category(primary_risks=[])},
        _policy(),
    )

    assert len(requests) == 1
    assert "conflict" in {trigger.trigger_type for trigger in requests[0].triggers}


def test_low_confidence_final_risk_routes_to_llm() -> None:
    result = AnalysisResult(
        skill_id="skill",
        root_path="/tmp/skill",
        structure_profile=SkillStructureProfile(
            has_skill_md=True,
            has_frontmatter=False,
            has_references_dir=False,
            has_scripts_dir=False,
            has_assets_dir=False,
            has_templates_dir=False,
        ),
        final_decisions=[
            FinalCategoryDecision(
                category_id="CAT",
                category_name="Category",
                layer="implementation",
                decision_status="accepted",
                supporting_evidence=[_evidence("support", evidence_strength="medium")],
                confidence="low",
                confidence_score=0.3,
            )
        ],
        skill_level_discrepancy="implementation_only_high_risk",
        category_discrepancies=[
            CategoryDiscrepancy(
                category_id="CAT",
                category_name="Category",
                status="implementation_only_high_risk",
                declaration_present=False,
                implementation_present=True,
                risks=["E"],
                controls=[],
            )
        ],
    )

    route = build_skill_risk_review_route(
        result,
        {"CAT": _category(primary_risks=["E"])},
        _policy(),
        fallback_skill_has_risk="yes",
    )

    assert route is not None
    assert "low_confidence_final_risk" in {trigger.trigger_type for trigger in route.triggers}


def test_low_confidence_rule_skill_risk_routes_to_llm_even_without_category_low_confidence() -> None:
    result = AnalysisResult(
        skill_id="skill",
        root_path="/tmp/skill",
        structure_profile=SkillStructureProfile(
            has_skill_md=True,
            has_frontmatter=False,
            has_references_dir=False,
            has_scripts_dir=False,
            has_assets_dir=False,
            has_templates_dir=False,
        ),
        final_decisions=[
            FinalCategoryDecision(
                category_id="CAT",
                category_name="Category",
                layer="implementation",
                decision_status="accepted",
                supporting_evidence=[_evidence("support", evidence_strength="strong")],
                confidence="medium",
                confidence_score=0.7,
            )
        ],
        skill_level_discrepancy="implementation_only_high_risk",
        category_discrepancies=[
            CategoryDiscrepancy(
                category_id="CAT",
                category_name="Category",
                status="implementation_only_high_risk",
                declaration_present=False,
                implementation_present=True,
                risks=["E"],
                controls=[],
            )
        ],
    )

    route = build_skill_risk_review_route(
        result,
        {"CAT": _category(primary_risks=["E"])},
        _policy(low_confidence_threshold=0.45, high_risk_sparse_threshold=0),
        fallback_skill_has_risk="yes",
    )

    assert calculate_rule_skill_risk_confidence_score(result, "yes") == 0.4
    assert route is not None
    assert "low_confidence_skill_risk" in {trigger.trigger_type for trigger in route.triggers}
    assert "low_confidence_final_risk" not in {trigger.trigger_type for trigger in route.triggers}


def test_analyze_skill_off_mode_does_not_emit_review_records(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    result = _analyze_skill(
        skill,
        _matrix_definition(),
        {"CAT": _category(primary_risks=["E"])},
        _args(llm_review_mode="off", llm_provider=None),
        _provider_registry(),
        "fail_open",
    )

    assert result.review_audit_records == []
    assert result.skill_risk_adjudication is None
    assert result.skill_has_risk == "yes"


def test_analyze_skill_review_mode_skips_high_confidence_skill_risk(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    result = _analyze_skill(
        skill,
        _matrix_definition(),
        {"CAT": _category(primary_risks=["E"])},
        _args(llm_review_mode="review", llm_provider="mock"),
        _provider_registry(),
        "fail_open",
    )

    assert {record.cascade_stage for record in result.review_audit_records} == {"category_review"}
    assert any(record.trigger_types for record in result.review_audit_records)
    assert result.skill_risk_adjudication is None
    assert result.skill_has_risk_confidence_score > 0.45


def test_analyze_skill_review_mode_routes_skill_risk_when_threshold_matches(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    result = _analyze_skill(
        skill,
        _matrix_definition(),
        {"CAT": _category(primary_risks=["E"])},
        _args(llm_review_mode="review", llm_provider="mock", llm_low_confidence_threshold=1.0),
        _provider_registry(),
        "fail_open",
    )

    assert {record.cascade_stage for record in result.review_audit_records} == {
        "category_review",
        "skill_risk_review",
    }
    assert result.skill_risk_adjudication is not None
    assert result.skill_has_risk_confidence_score == result.skill_risk_adjudication.confidence_score


def test_skill_risk_review_returns_no_when_implementation_decisions_are_empty(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    result = AnalysisResult(
        skill_id="skill",
        root_path=str(skill.root_path),
        structure_profile=skill.structure,
        final_decisions=[
            FinalCategoryDecision(
                category_id="CAT",
                category_name="Category",
                layer="declaration",
                decision_status="accepted",
                supporting_evidence=[_evidence("support", evidence_strength="strong")],
                confidence="high",
                confidence_score=1.0,
            )
        ],
    )

    skill_has_risk, adjudication = review_skill_risk(
        result,
        skill,
        {"CAT": _category(primary_risks=[])},
        _ProviderThatMustNotBeCalled(),
        model="test-model",
        timeout_seconds=30,
        fallback_skill_has_risk="no",
    )

    assert skill_has_risk == "no"
    assert adjudication.review_status == "not_applicable"
    assert adjudication.reason == "no retained implementation decisions; implementation cannot show broader capability"
    assert adjudication.confidence_score == 1.0


def test_analyze_skill_provider_unavailable_fail_open_preserves_rule_decision(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    result = _analyze_skill(
        skill,
        _matrix_definition(),
        {"CAT": _category(primary_risks=["E"])},
        _args(llm_review_mode="review", llm_provider=None),
        _provider_registry(),
        "fail_open",
    )

    assert result.final_decisions[0].decision_status == "accepted"
    assert result.review_audit_records[0].review_status == "provider_unavailable"
    assert result.review_audit_records[0].final_decision_status == "accepted"


def test_analyze_skill_provider_unavailable_fail_closed_rejects_category(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    result = _analyze_skill(
        skill,
        _matrix_definition(),
        {"CAT": _category(primary_risks=["E"])},
        _args(llm_review_mode="review", llm_provider=None),
        _provider_registry(),
        "fail_closed",
    )

    assert result.final_decisions[0].decision_status == "rejected_by_llm"
    assert result.review_audit_records[0].review_status == "provider_unavailable"
    assert result.review_audit_records[0].final_decision_status == "rejected_by_llm"


def test_review_audit_exports_include_cascade_fields(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    result = _analyze_skill(
        skill,
        _matrix_definition(),
        {"CAT": _category(primary_risks=["E"])},
        _args(llm_review_mode="review", llm_provider="mock"),
        _provider_registry(),
        "fail_open",
    )

    csv_rows = review_audit_rows_for_result(result)
    json_payload = review_audit_record(result)

    assert csv_rows
    assert csv_rows[0]["trigger_types"]
    assert csv_rows[0]["default_decision_status"]
    assert csv_rows[0]["final_decision_status"]
    assert csv_rows[0]["cascade_stage"] in {"category_review", "skill_risk_review"}
    assert "trigger_types" in json_payload["review_audit_records"][0]


def _policy(
    *,
    low_confidence_threshold: float = 0.45,
    high_risk_sparse_threshold: int = 1,
) -> CascadePolicyConfig:
    return CascadePolicyConfig(
        mode="review",
        low_confidence_threshold=low_confidence_threshold,
        high_risk_sparse_threshold=high_risk_sparse_threshold,
        fallback_max_categories=0,
        failure_policy="fail_open",
    )


def _args(
    *,
    llm_review_mode: str,
    llm_provider: str | None,
    llm_low_confidence_threshold: float = 0.45,
) -> Namespace:
    return Namespace(
        llm_review_mode=llm_review_mode,
        llm_provider=llm_provider,
        llm_model=None,
        llm_low_confidence_threshold=llm_low_confidence_threshold,
        llm_high_risk_sparse_threshold=2,
        llm_fallback_max_categories=0,
        llm_timeout_seconds=30,
        emit_review_audit=True,
    )


def _provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(MockReviewProvider())
    return registry


class _ProviderThatMustNotBeCalled(MockReviewProvider):
    provider_name = "must-not-be-called"

    def review_skill_risk(self, request, *, model, timeout_seconds):
        raise AssertionError("provider should not be called when implementation decisions are empty")


def _matrix_definition() -> MatrixDefinition:
    return MatrixDefinition(
        categories=[_category(primary_risks=["E"])],
        capability_mappings=[CapabilityMapping(atomic_id="R5", category_id="CAT")],
    )


def _write_skill(tmp_path: Path) -> SkillArtifact:
    root = tmp_path / "skill"
    root.mkdir()
    skill_md = root / "SKILL.md"
    source = root / "tool.py"
    helper = root / "helper.py"
    skill_md.write_text("---\nname: demo\n---\nRead a local project file.\n", encoding="utf-8")
    source.write_text("first = open('notes.txt').read()\n", encoding="utf-8")
    helper.write_text("second = open('more.txt').read()\n", encoding="utf-8")
    return SkillArtifact(
        skill_id="demo/skill",
        root_path=root,
        structure=SkillStructureProfile(
            has_skill_md=True,
            has_frontmatter=True,
            has_references_dir=False,
            has_scripts_dir=False,
            has_assets_dir=False,
            has_templates_dir=False,
            top_level_files=["SKILL.md", "helper.py", "tool.py"],
        ),
        file_paths=[skill_md, source, helper],
        source_files=[skill_md, source, helper],
    )


def _candidate(*, confidence_score: float, evidence_strength: str, primary_risks: list[str]) -> RuleCandidate:
    return RuleCandidate(
        candidate_id="implementation:CAT:1",
        category_id="CAT",
        category_name="Category",
        layer="implementation",
        candidate_status="supported",
        supporting_evidence=[_evidence("support", evidence_strength=evidence_strength)],
        rule_confidence="high" if confidence_score >= 0.8 else "low",
        confidence_score=confidence_score,
        trigger_reason="test",
    )


def _evidence(text: str, *, evidence_strength: str) -> EvidenceItem:
    return EvidenceItem(
        category_id="R5",
        category_name="Read local file",
        source_path="tool.py",
        layer="implementation",
        evidence_type="static_scan",
        matched_text=text,
        line_start=1,
        line_end=1,
        confidence="high" if evidence_strength == "strong" else "medium",
        rule_id="test.rule",
        evidence_strength=evidence_strength,
    )


def _category(*, primary_risks: list[str]) -> MatrixCategory:
    return MatrixCategory(
        category_id="CAT",
        major_category="Major",
        subcategory="Category",
        security_definition="Definition",
        data_level="L1",
        primary_risks=primary_risks,
        control_requirements=[],
    )
