from __future__ import annotations

from ..models import AnalysisResult


def no_classification_results(results: list[AnalysisResult]) -> list[AnalysisResult]:
    return [
        result
        for result in results
        if not result.declaration_classifications and not result.implementation_classifications
    ]


def no_classification_record(result: AnalysisResult) -> dict[str, str]:
    return {
        "skill_id": result.skill_id,
        "domain": result.domain,
        "error": "; ".join(result.errors),
    }
