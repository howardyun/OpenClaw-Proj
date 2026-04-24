from __future__ import annotations

from ..domain_mapping import allowed_domain_definitions, allowed_domain_ids
from ..exporters.permission_summary import build_fallback_skill_domain
from ..models import AnalysisResult, DomainAdjudication, SkillArtifact
from .llm_provider import LLMReviewProvider
from .models import DomainReviewRequest
from .skill_description import extract_skill_description


DOMAIN_SCHEMA_VERSION = "skills-domain-review-v1"


def review_domain(
    result: AnalysisResult,
    skill: SkillArtifact,
    provider: LLMReviewProvider | None,
    *,
    model: str | None,
    timeout_seconds: int,
) -> tuple[str, DomainAdjudication]:
    fallback_domain = build_fallback_skill_domain(result)
    description = extract_skill_description(skill)
    if not description:
        return fallback_domain, DomainAdjudication(
            review_status="description_missing",
            provider=None,
            model=None,
            domain=fallback_domain,
            reason="description missing; used rule-based fallback",
            fallback_used=True,
            schema_version=DOMAIN_SCHEMA_VERSION,
        )

    if provider is None:
        return fallback_domain, DomainAdjudication(
            review_status="provider_unavailable",
            provider=None,
            model=None,
            domain=fallback_domain,
            reason="provider unavailable; used rule-based fallback",
            fallback_used=True,
            schema_version=DOMAIN_SCHEMA_VERSION,
        )

    request = DomainReviewRequest(
        skill_id=result.skill_id,
        description=description,
        allowed_domains=allowed_domain_ids(),
        domain_definitions=allowed_domain_definitions(),
    )
    response = provider.review_domain(request, model=model, timeout_seconds=timeout_seconds)
    if response.review_status != "reviewed" or response.decision is None:
        return fallback_domain, DomainAdjudication(
            review_status=response.review_status,
            provider=response.provider,
            model=response.model,
            domain=fallback_domain,
            reason=response.error or "domain review failed; used rule-based fallback",
            fallback_used=True,
            schema_version=response.schema_version,
        )

    decision = response.decision
    if decision.domain not in {"", *request.allowed_domains}:
        return fallback_domain, DomainAdjudication(
            review_status="invalid_response",
            provider=response.provider,
            model=response.model,
            domain=fallback_domain,
            reason="invalid domain in provider response; used rule-based fallback",
            fallback_used=True,
            schema_version=response.schema_version,
        )

    return decision.domain, DomainAdjudication(
        review_status=response.review_status,
        provider=response.provider,
        model=response.model,
        domain=decision.domain,
        reason=decision.reason,
        confidence=decision.confidence,
        confidence_score=decision.confidence_score,
        fallback_used=False,
        schema_version=response.schema_version,
    )


def build_rule_based_domain_adjudication(result: AnalysisResult) -> DomainAdjudication:
    fallback_domain = build_fallback_skill_domain(result)
    return DomainAdjudication(
        review_status="rule_based",
        provider=None,
        model=None,
        domain=fallback_domain,
        reason="llm review disabled; used rule-based fallback",
        fallback_used=True,
        schema_version=DOMAIN_SCHEMA_VERSION,
    )
