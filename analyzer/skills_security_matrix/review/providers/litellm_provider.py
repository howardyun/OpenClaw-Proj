from __future__ import annotations

import json
import os
from dataclasses import asdict

from ..llm_provider import LLMReviewProvider
from ..models import (
    DomainReviewRequest,
    DomainReviewResponse,
    ReviewRequest,
    ReviewResponse,
    SkillRiskReviewRequest,
    SkillRiskReviewResponse,
    StructuredDomainDecision,
    StructuredReviewDecision,
    StructuredSkillRiskDecision,
)
from .prompting import build_domain_system_prompt, build_review_system_prompt, build_skill_risk_system_prompt


class LiteLLMReviewProvider(LLMReviewProvider):
    provider_name = "litellm"

    def review_category(self, request: ReviewRequest, *, model: str | None, timeout_seconds: int) -> ReviewResponse:
        try:
            import litellm  # type: ignore
        except ImportError as exc:
            return ReviewResponse(
                category_id=request.candidate.category_id,
                layer=request.candidate.layer,
                provider=self.provider_name,
                model=model,
                review_status="provider_error",
                error=f"LiteLLM is not installed: {exc}",
            )

        schema = _review_schema()
        prompt = _build_prompt(request)
        try:
            response = litellm.completion(
                model=model or os.getenv("LITELLM_MODEL", ""),
                messages=[
                    {"role": "system", "content": build_review_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_schema", "json_schema": schema},
                timeout=timeout_seconds,
            )
            content = response.choices[0].message.content
            payload = json.loads(content)
        except Exception as exc:  # pragma: no cover - network/provider defensive path
            return ReviewResponse(
                category_id=request.candidate.category_id,
                layer=request.candidate.layer,
                provider=self.provider_name,
                model=model,
                review_status="provider_error",
                error=str(exc),
            )
        return ReviewResponse(
            category_id=request.candidate.category_id,
            layer=request.candidate.layer,
            provider=self.provider_name,
            model=model,
            review_status="reviewed",
            decision=_decision_from_payload(payload),
            raw_payload=payload,
        )

    def review_skill_risk(
        self,
        request: SkillRiskReviewRequest,
        *,
        model: str | None,
        timeout_seconds: int,
    ) -> SkillRiskReviewResponse:
        try:
            import litellm  # type: ignore
        except ImportError as exc:
            return SkillRiskReviewResponse(
                skill_id=request.skill_id,
                provider=self.provider_name,
                model=model,
                review_status="provider_error",
                error=f"LiteLLM is not installed: {exc}",
            )

        schema = _skill_risk_schema()
        prompt = _build_skill_risk_prompt(request)
        try:
            response = litellm.completion(
                model=model or os.getenv("LITELLM_MODEL", ""),
                messages=[
                    {"role": "system", "content": build_skill_risk_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_schema", "json_schema": schema},
                timeout=timeout_seconds,
            )
            content = response.choices[0].message.content
            payload = json.loads(content)
        except Exception as exc:  # pragma: no cover - network/provider defensive path
            return SkillRiskReviewResponse(
                skill_id=request.skill_id,
                provider=self.provider_name,
                model=model,
                review_status="provider_error",
                error=str(exc),
            )
        return SkillRiskReviewResponse(
            skill_id=request.skill_id,
            provider=self.provider_name,
            model=model,
            review_status="reviewed",
            decision=_skill_risk_decision_from_payload(payload),
            raw_payload=payload,
        )

    def review_domain(
        self,
        request: DomainReviewRequest,
        *,
        model: str | None,
        timeout_seconds: int,
    ) -> DomainReviewResponse:
        try:
            import litellm  # type: ignore
        except ImportError as exc:
            return DomainReviewResponse(
                skill_id=request.skill_id,
                provider=self.provider_name,
                model=model,
                review_status="provider_error",
                error=f"LiteLLM is not installed: {exc}",
            )

        schema = _domain_schema(request.allowed_domains)
        prompt = _build_domain_prompt(request)
        try:
            response = litellm.completion(
                model=model or os.getenv("LITELLM_MODEL", ""),
                messages=[
                    {"role": "system", "content": build_domain_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_schema", "json_schema": schema},
                timeout=timeout_seconds,
            )
            content = response.choices[0].message.content
            payload = json.loads(content)
        except Exception as exc:  # pragma: no cover - network/provider defensive path
            return DomainReviewResponse(
                skill_id=request.skill_id,
                provider=self.provider_name,
                model=model,
                review_status="provider_error",
                error=str(exc),
            )
        return DomainReviewResponse(
            skill_id=request.skill_id,
            provider=self.provider_name,
            model=model,
            review_status="reviewed",
            decision=_domain_decision_from_payload(payload),
            raw_payload=payload,
        )


def _review_schema() -> dict[str, object]:
    return {
        "name": "skills_security_matrix_review",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "decision_status": {
                    "type": "string",
                    "enum": ["accepted", "downgraded", "rejected_by_llm"],
                },
                "reason": {"type": "string"},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                "confidence_score": {"type": "number"},
                "supporting_fingerprints": {"type": "array", "items": {"type": "string"}},
                "conflicting_fingerprints": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "decision_status",
                "reason",
                "confidence",
                "confidence_score",
                "supporting_fingerprints",
                "conflicting_fingerprints",
            ],
            "additionalProperties": False,
        },
    }


def _build_prompt(request: ReviewRequest) -> str:
    support = [
        {
            "path": item.source_path,
            "lines": [item.line_start, item.line_end],
            "text": item.matched_text,
            "fingerprint": item.evidence_fingerprint,
        }
        for item in request.supporting_evidence[:5]
    ]
    conflicts = [
        {
            "path": item.source_path,
            "lines": [item.line_start, item.line_end],
            "text": item.matched_text,
            "fingerprint": item.evidence_fingerprint,
        }
        for item in request.conflicting_evidence[:5]
    ]
    return json.dumps(
        {
            "task": "Review exactly one pre-existing category candidate and decide whether it should be accepted, downgraded, or rejected_by_llm.",
            "skill_id": request.skill_id,
            "category_id": request.candidate.category_id,
            "category_name": request.candidate.category_name,
            "layer": request.candidate.layer,
            "candidate_status": request.candidate.candidate_status,
            "rule_confidence": request.candidate.rule_confidence,
            "confidence_score": request.candidate.confidence_score,
            "triggers": [asdict(trigger) for trigger in request.triggers],
            "decision_policy": {
                "allowed_statuses": ["accepted", "downgraded", "rejected_by_llm"],
                "accepted": "Use only when the evidence is direct and sufficient.",
                "downgraded": "Use when support exists but is weak, sparse, indirect, or ambiguous.",
                "rejected_by_llm": "Use when support is not grounded in the provided evidence or conflicts dominate.",
                "forbidden_actions": [
                    "inventing new categories",
                    "reclassifying the entire skill",
                    "using evidence that is not included in the payload",
                ],
            },
            "supporting_evidence": support,
            "conflicting_evidence": conflicts,
            "output_requirements": {
                "reason_style": "brief, concrete, evidence-focused",
                "fingerprint_rule": "Only return fingerprints that appear in the supplied evidence arrays.",
            },
        },
        ensure_ascii=False,
    )


def _decision_from_payload(payload: dict[str, object]) -> StructuredReviewDecision:
    return StructuredReviewDecision(
        decision_status=str(payload["decision_status"]),
        reason=str(payload["reason"]),
        confidence=str(payload["confidence"]),
        confidence_score=float(payload["confidence_score"]),
        supporting_fingerprints=[str(item) for item in payload.get("supporting_fingerprints", [])],
        conflicting_fingerprints=[str(item) for item in payload.get("conflicting_fingerprints", [])],
    )


def _skill_risk_schema() -> dict[str, object]:
    return {
        "name": "skills_skill_risk_review",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "skill_has_risk": {"type": "string", "enum": ["yes", "no"]},
                "reason": {"type": "string"},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                "confidence_score": {"type": "number"},
            },
            "required": ["skill_has_risk", "reason", "confidence", "confidence_score"],
            "additionalProperties": False,
        },
    }


def _build_skill_risk_prompt(request: SkillRiskReviewRequest) -> str:
    retained_decisions = [item for item in request.final_decisions if item.decision_status != "rejected_by_llm"]
    return json.dumps(
        {
            "task": "Decide whether this skill should be marked yes or no for skill_has_risk.",
            "skill_id": request.skill_id,
            "description": request.description,
            "decision_policy": {
                "allowed_statuses": ["yes", "no"],
                "description_role": "Use the description together with retained declaration and implementation decisions to judge whether any apparent mismatch is reasonably implied, necessary, incidental, or materially broader in context.",
                "focus": "Treat retained declaration and implementation decisions as structured signals for contextual least-privilege review, not as mechanically binding set-membership rules.",
                "implementation_decisions_empty_rule": "If implementation_decisions is empty, return skill_has_risk=no because the implementation does not show any retained capability.",
                "forbidden_actions": [
                    "changing category decisions",
                    "inventing categories",
                    "deriving retained categories from description alone",
                    "using evidence not present in the payload",
                ],
            },
            "declaration_decisions": [
                {
                    "category_id": item.category_id,
                    "category_name": item.category_name,
                    "decision_status": item.decision_status,
                    "confidence": item.confidence,
                    "confidence_score": item.confidence_score,
                }
                for item in retained_decisions
                if item.layer == "declaration"
            ],
            "implementation_decisions": [
                {
                    "category_id": item.category_id,
                    "category_name": item.category_name,
                    "decision_status": item.decision_status,
                    "confidence": item.confidence,
                    "confidence_score": item.confidence_score,
                }
                for item in retained_decisions
                if item.layer == "implementation"
            ],
        },
        ensure_ascii=False,
    )


def _skill_risk_decision_from_payload(payload: dict[str, object]) -> StructuredSkillRiskDecision:
    return StructuredSkillRiskDecision(
        skill_has_risk=str(payload["skill_has_risk"]),
        reason=str(payload["reason"]),
        confidence=str(payload["confidence"]),
        confidence_score=float(payload["confidence_score"]),
    )


def _domain_schema(allowed_domains: list[str]) -> dict[str, object]:
    return {
        "name": "skills_domain_review",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "enum": ["", *allowed_domains]},
                "reason": {"type": "string"},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                "confidence_score": {"type": "number"},
            },
            "required": ["domain", "reason", "confidence", "confidence_score"],
            "additionalProperties": False,
        },
    }


def _build_domain_prompt(request: DomainReviewRequest) -> str:
    return json.dumps(
        {
            "task": "Classify this skill into exactly one allowed domain id or an empty string using only the description.",
            "skill_id": request.skill_id,
            "description": request.description,
            "allowed_domains": request.allowed_domains,
            "domain_definitions": request.domain_definitions,
            "decision_policy": {
                "empty_string_rule": "Return an empty string when the description is too vague or does not clearly imply one domain.",
                "forbidden_actions": [
                    "using evidence outside the supplied description",
                    "inventing a new domain id",
                    "returning multiple domains",
                ],
            },
        },
        ensure_ascii=False,
    )


def _domain_decision_from_payload(payload: dict[str, object]) -> StructuredDomainDecision:
    return StructuredDomainDecision(
        domain=str(payload["domain"]),
        reason=str(payload["reason"]),
        confidence=str(payload["confidence"]),
        confidence_score=float(payload["confidence_score"]),
    )
