from __future__ import annotations

from analyzer.skills_security_matrix.discrepancy import compute_discrepancies
from analyzer.skills_security_matrix.matrix_definition_builtin import get_builtin_matrix_definition
from analyzer.skills_security_matrix.models import AnalysisResult, AtomicEvidenceDecision, SkillStructureProfile
from analyzer.skills_security_matrix.risk_mapping import determine_skill_has_risk


def test_redundant_implementation_atomics_do_not_create_skill_risk() -> None:
    matrix = get_builtin_matrix_definition()
    result = _result(
        implementation_atomic_ids=["R1", "R2", "Q1", "W1", "W2", "G1", "G2", "A1", "A2"],
    )

    _compute(result, matrix)

    assert result.skill_has_risk == "no"
    assert result.skill_level_discrepancy == "insufficient_declaration_evidence"
    assert all(
        discrepancy.status != "implementation_only_high_risk"
        for discrepancy in result.category_discrepancies
    )


def test_redundant_implementation_gap_does_not_create_underreported_risk() -> None:
    matrix = get_builtin_matrix_definition()
    result = _result(
        declaration_atomic_ids=["G1"],
        implementation_atomic_ids=["G1", "G2", "W1"],
    )

    _compute(result, matrix)

    assert result.skill_has_risk == "no"
    assert result.skill_level_discrepancy == "declared_and_implemented_aligned"


def test_non_redundant_implementation_gap_still_creates_skill_risk() -> None:
    matrix = get_builtin_matrix_definition()
    result = _result(
        implementation_atomic_ids=["W1", "X1"],
    )

    _compute(result, matrix)

    assert result.skill_has_risk == "yes"
    assert result.skill_level_discrepancy == "implementation_only_high_risk"
    assert any(
        discrepancy.category_id == "code_computation_execution"
        and discrepancy.status == "implementation_only_high_risk"
        for discrepancy in result.category_discrepancies
    )


def test_discrepancies_preserve_original_redundant_atomic_ids_for_audit() -> None:
    matrix = get_builtin_matrix_definition()
    result = _result(
        implementation_atomic_ids=["W1"],
    )

    _compute(result, matrix)

    external_access = next(
        discrepancy
        for discrepancy in result.category_discrepancies
        if discrepancy.category_id == "external_information_access"
    )
    assert external_access.implementation_atomic_ids == ["W1"]
    assert external_access.mismatch_ids == []
    assert result.skill_has_risk == "no"


def _compute(result: AnalysisResult, matrix) -> None:
    matrix_by_id = {category.category_id: category for category in matrix.categories}
    result.skill_level_discrepancy, result.category_discrepancies = compute_discrepancies(
        result,
        matrix_by_id,
        matrix.capability_mappings,
        matrix.control_semantics,
    )
    result.skill_has_risk = determine_skill_has_risk(result, matrix_by_id)


def _result(
    *,
    declaration_atomic_ids: list[str] | None = None,
    implementation_atomic_ids: list[str] | None = None,
) -> AnalysisResult:
    return AnalysisResult(
        skill_id="test/skill",
        root_path="/tmp/test-skill",
        structure_profile=SkillStructureProfile(
            has_skill_md=True,
            has_frontmatter=True,
            has_references_dir=False,
            has_scripts_dir=False,
            has_assets_dir=False,
            has_templates_dir=False,
            top_level_files=["SKILL.md", "tool.py"],
        ),
        declaration_atomic_decisions=[
            _atomic_decision(atomic_id, layer="declaration")
            for atomic_id in declaration_atomic_ids or []
        ],
        implementation_atomic_decisions=[
            _atomic_decision(atomic_id, layer="implementation")
            for atomic_id in implementation_atomic_ids or []
        ],
    )


def _atomic_decision(atomic_id: str, *, layer: str) -> AtomicEvidenceDecision:
    return AtomicEvidenceDecision(
        atomic_id=atomic_id,
        atomic_name=atomic_id,
        layer=layer,
        decision_status="accepted",
        confidence="high",
        confidence_score=1.0,
    )
