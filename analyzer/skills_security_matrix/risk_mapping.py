from __future__ import annotations

from .models import AnalysisResult, MatrixCategory


def build_risk_mappings(result: AnalysisResult, matrix_by_id: dict[str, MatrixCategory]) -> list[dict[str, object]]:
    category_ids = {decision.category_id for decision in result.final_decisions if decision.decision_status != "rejected_by_llm"}
    mappings: list[dict[str, object]] = []
    for category_id in sorted(category_ids):
        matrix_category = matrix_by_id[category_id]
        mappings.append(
            {
                "category_id": category_id,
                "category_name": matrix_category.subcategory,
                "major_category": matrix_category.major_category,
                "risks": matrix_category.primary_risks,
                "controls": matrix_category.control_requirements,
            }
        )
    return mappings
