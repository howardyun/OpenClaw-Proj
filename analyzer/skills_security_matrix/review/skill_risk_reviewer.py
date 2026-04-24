from __future__ import annotations

from ..models import AnalysisResult, MatrixCategory, SkillArtifact, SkillRiskAdjudication
from .llm_provider import LLMReviewProvider
from .models import SkillRiskReviewRequest
from .skill_description import extract_skill_description


def review_skill_risk(
    result: AnalysisResult,
    skill: SkillArtifact,
    matrix_by_id: dict[str, MatrixCategory],
    provider: LLMReviewProvider | None,
    *,
    model: str | None,
    timeout_seconds: int,
    fallback_skill_has_risk: str,
) -> tuple[str, SkillRiskAdjudication]:
    if provider is None:
        return fallback_skill_has_risk, SkillRiskAdjudication(
            review_status="provider_unavailable",
            provider=None,
            model=None,
            skill_has_risk=fallback_skill_has_risk,
            reason="provider unavailable; used rule-based fallback",
            fallback_used=True,
            schema_version="skills-skill-risk-review-v1",
        )

    request = SkillRiskReviewRequest(
        skill_id=result.skill_id,
        description=extract_skill_description(skill),
        final_decisions=result.final_decisions,
    )
    response = provider.review_skill_risk(request, model=model, timeout_seconds=timeout_seconds)
    if response.review_status != "reviewed" or response.decision is None:
        return fallback_skill_has_risk, SkillRiskAdjudication(
            review_status=response.review_status,
            provider=response.provider,
            model=response.model,
            skill_has_risk=fallback_skill_has_risk,
            reason=response.error or "skill risk review failed; used rule-based fallback",
            fallback_used=True,
            schema_version=response.schema_version,
        )

    decision = response.decision
    if decision.skill_has_risk not in {"yes", "no"}:
        return fallback_skill_has_risk, SkillRiskAdjudication(
            review_status="invalid_response",
            provider=response.provider,
            model=response.model,
            skill_has_risk=fallback_skill_has_risk,
            reason="invalid skill_has_risk in provider response; used rule-based fallback",
            fallback_used=True,
            schema_version=response.schema_version,
        )

    return decision.skill_has_risk, SkillRiskAdjudication(
        review_status=response.review_status,
        provider=response.provider,
        model=response.model,
        skill_has_risk=decision.skill_has_risk,
        reason=decision.reason,
        confidence=decision.confidence,
        confidence_score=decision.confidence_score,
        fallback_used=False,
        schema_version=response.schema_version,
    )
