from __future__ import annotations

from ..domain_mapping import resolve_domain_from_atomic_ids
from ..models import AnalysisResult


def build_permission_summary(result: AnalysisResult) -> dict[str, list[str]]:
    return {
        "declaration_atomic_ids": _sorted_atomic_ids(result.declaration_atomic_decisions),
        "implementation_atomic_ids": _sorted_atomic_ids(result.implementation_atomic_decisions),
    }


def build_fallback_skill_domain(result: AnalysisResult) -> str:
    implementation_atomic_ids = _sorted_atomic_ids(result.implementation_atomic_decisions, accepted_only=True)
    if implementation_atomic_ids:
        return resolve_domain_from_atomic_ids(implementation_atomic_ids)

    declaration_atomic_ids = _sorted_atomic_ids(result.declaration_atomic_decisions, accepted_only=True)
    return resolve_domain_from_atomic_ids(declaration_atomic_ids)


def build_skill_domain(result: AnalysisResult) -> str:
    return build_fallback_skill_domain(result)


def _sorted_atomic_ids(decisions, accepted_only: bool = False) -> list[str]:
    return sorted(
        {
            decision.atomic_id
            for decision in decisions
            if not accepted_only or decision.decision_status == "accepted"
        }
    )
