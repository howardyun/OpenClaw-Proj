from __future__ import annotations

from .models import AnalysisResult, CategoryDiscrepancy, MatrixCategory


def compute_discrepancies(
    result: AnalysisResult,
    matrix_by_id: dict[str, MatrixCategory],
) -> tuple[str, list[CategoryDiscrepancy]]:
    declared_ids = {item.category_id for item in result.declaration_classifications}
    implemented_ids = {item.category_id for item in result.implementation_classifications}
    all_ids = sorted(set(matrix_by_id) | declared_ids | implemented_ids)
    category_discrepancies: list[CategoryDiscrepancy] = []
    for category_id in all_ids:
        matrix_category = matrix_by_id.get(category_id)
        if matrix_category is None:
            continue
        declaration_present = category_id in declared_ids
        implementation_present = category_id in implemented_ids
        if declaration_present and implementation_present:
            status = "declared_and_implemented_aligned"
        elif implementation_present and not declaration_present:
            if _has_high_risk(matrix_category):
                status = "implementation_only_high_risk"
            else:
                status = "declared_less_than_implemented"
        elif declaration_present and not implementation_present:
            status = "declared_more_than_implemented"
        else:
            continue
        category_discrepancies.append(
            CategoryDiscrepancy(
                category_id=category_id,
                category_name=matrix_category.subcategory,
                status=status,
                declaration_present=declaration_present,
                implementation_present=implementation_present,
                risks=matrix_category.primary_risks,
                controls=matrix_category.control_requirements,
            )
        )

    skill_level_discrepancy = _compute_skill_level_status(declared_ids, implemented_ids, matrix_by_id)
    return skill_level_discrepancy, category_discrepancies


def _compute_skill_level_status(
    declared_ids: set[str],
    implemented_ids: set[str],
    matrix_by_id: dict[str, MatrixCategory],
) -> str:
    if not declared_ids and not implemented_ids:
        return "insufficient_declaration_evidence"
    if not declared_ids:
        if any(_has_high_risk(matrix_by_id[category_id]) for category_id in implemented_ids):
            return "implementation_only_high_risk"
        return "insufficient_declaration_evidence"
    if not implemented_ids:
        return "insufficient_implementation_evidence"
    if declared_ids == implemented_ids:
        return "declared_and_implemented_aligned"
    if implemented_ids - declared_ids:
        if any(_has_high_risk(matrix_by_id[category_id]) for category_id in implemented_ids - declared_ids):
            return "implementation_only_high_risk"
        return "declared_less_than_implemented"
    if declared_ids - implemented_ids:
        return "declared_more_than_implemented"
    return "declared_and_implemented_aligned"


def _has_high_risk(category: MatrixCategory) -> bool:
    high_risk_codes = {"E", "D", "T", "I", "R"}
    return any(risk in high_risk_codes for risk in category.primary_risks)
