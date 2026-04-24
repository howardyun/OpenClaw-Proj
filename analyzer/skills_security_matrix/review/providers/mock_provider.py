from __future__ import annotations

from ..llm_provider import LLMReviewProvider
from ..models import DomainReviewRequest, DomainReviewResponse, ReviewRequest, ReviewResponse, StructuredDomainDecision
from ..models import SkillRiskReviewRequest, SkillRiskReviewResponse, StructuredReviewDecision, StructuredSkillRiskDecision


class MockReviewProvider(LLMReviewProvider):
    provider_name = "mock"

    def review_category(self, request: ReviewRequest, *, model: str | None, timeout_seconds: int) -> ReviewResponse:
        candidate = request.candidate
        support = candidate.supporting_evidence
        if candidate.confidence_score < 0.2:
            decision_status = "rejected_by_llm"
            confidence = "low"
            confidence_score = 0.0
        elif candidate.confidence_score < 0.55:
            decision_status = "downgraded"
            confidence = "low"
            confidence_score = min(candidate.confidence_score, 0.35)
        else:
            decision_status = "accepted"
            confidence = candidate.rule_confidence
            confidence_score = candidate.confidence_score

        return ReviewResponse(
            category_id=candidate.category_id,
            layer=candidate.layer,
            provider=self.provider_name,
            model=model,
            review_status="reviewed",
            decision=StructuredReviewDecision(
                decision_status=decision_status,
                reason=f"mock review applied from confidence_score={candidate.confidence_score:.2f}",
                confidence=confidence,
                confidence_score=confidence_score,
                supporting_fingerprints=[item.evidence_fingerprint for item in support[:3]],
                conflicting_fingerprints=[item.evidence_fingerprint for item in candidate.conflicting_evidence[:3]],
            ),
            raw_payload={"mock": True, "timeout_seconds": timeout_seconds},
        )

    def review_skill_risk(
        self,
        request: SkillRiskReviewRequest,
        *,
        model: str | None,
        timeout_seconds: int,
    ) -> SkillRiskReviewResponse:
        declaration_ids = {
            item.category_id
            for item in request.final_decisions
            if item.layer == "declaration" and item.decision_status != "rejected_by_llm"
        }
        implementation_ids = {
            item.category_id
            for item in request.final_decisions
            if item.layer == "implementation" and item.decision_status != "rejected_by_llm"
        }
        skill_has_risk = "yes" if implementation_ids - declaration_ids else "no"
        return SkillRiskReviewResponse(
            skill_id=request.skill_id,
            provider=self.provider_name,
            model=model,
            review_status="reviewed",
            decision=StructuredSkillRiskDecision(
                skill_has_risk=skill_has_risk,
                reason="mock skill risk review applied from declaration and implementation decisions",
                confidence="medium",
                confidence_score=0.7 if skill_has_risk == "yes" else 0.6,
            ),
            raw_payload={"mock": True, "timeout_seconds": timeout_seconds},
        )

    def review_domain(
        self,
        request: DomainReviewRequest,
        *,
        model: str | None,
        timeout_seconds: int,
    ) -> DomainReviewResponse:
        description = request.description.lower()
        if "schedule" in description or "monitor" in description:
            domain = "Dom-16"
        elif "search" in description and ("api" in description or "web" in description):
            domain = "Dom-3"
        elif "draft" in description or "content" in description:
            domain = "Dom-1"
        else:
            domain = ""

        return DomainReviewResponse(
            skill_id=request.skill_id,
            provider=self.provider_name,
            model=model,
            review_status="reviewed",
            decision=StructuredDomainDecision(
                domain=domain,
                reason="mock domain review applied from description keywords",
                confidence="medium" if domain else "low",
                confidence_score=0.7 if domain else 0.2,
            ),
            raw_payload={"mock": True, "timeout_seconds": timeout_seconds},
        )
