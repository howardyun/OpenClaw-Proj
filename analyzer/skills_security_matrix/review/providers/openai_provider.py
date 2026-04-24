from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from typing import Any

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


class OpenAIReviewProvider(LLMReviewProvider):
    provider_name = "openai"

    def review_category(self, request: ReviewRequest, *, model: str | None, timeout_seconds: int) -> ReviewResponse:
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE_URL")
        if not api_key:
            return ReviewResponse(
                category_id=request.candidate.category_id,
                layer=request.candidate.layer,
                provider=self.provider_name,
                model=model,
                review_status="provider_error",
                error="OPENAI_API_KEY is not set",
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            return ReviewResponse(
                category_id=request.candidate.category_id,
                layer=request.candidate.layer,
                provider=self.provider_name,
                model=model,
                review_status="provider_error",
                error=f"openai package is not installed: {exc}",
            )

        try:
            model_name = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_seconds)
            parsed = _create_structured_chat_completion(
                client,
                model_name=model_name,
                system_prompt=build_review_system_prompt(),
                payload=_build_payload(request),
                schema=_review_schema(),
            )
        except Exception as exc:  # pragma: no cover - network/provider defensive path
            return ReviewResponse(
                category_id=request.candidate.category_id,
                layer=request.candidate.layer,
                provider=self.provider_name,
                model=model_name if "model_name" in locals() else model,
                review_status="provider_error",
                error=str(exc),
            )

        return ReviewResponse(
            category_id=request.candidate.category_id,
            layer=request.candidate.layer,
            provider=self.provider_name,
            model=model_name,
            review_status="reviewed",
            decision=StructuredReviewDecision(
                decision_status=str(parsed["decision_status"]),
                reason=str(parsed["reason"]),
                confidence=str(parsed["confidence"]),
                confidence_score=float(parsed["confidence_score"]),
                supporting_fingerprints=[str(item) for item in parsed.get("supporting_fingerprints", [])],
                conflicting_fingerprints=[str(item) for item in parsed.get("conflicting_fingerprints", [])],
            ),
            raw_payload=parsed,
        )

    def review_skill_risk(
        self,
        request: SkillRiskReviewRequest,
        *,
        model: str | None,
        timeout_seconds: int,
    ) -> SkillRiskReviewResponse:
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE_URL")
        if not api_key:
            return SkillRiskReviewResponse(
                skill_id=request.skill_id,
                provider=self.provider_name,
                model=model,
                review_status="provider_error",
                error="OPENAI_API_KEY is not set",
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            return SkillRiskReviewResponse(
                skill_id=request.skill_id,
                provider=self.provider_name,
                model=model,
                review_status="provider_error",
                error=f"openai package is not installed: {exc}",
            )

        try:
            model_name = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_seconds)
            parsed = _create_structured_chat_completion(
                client,
                model_name=model_name,
                system_prompt=build_skill_risk_system_prompt(),
                payload=_build_skill_risk_payload(request),
                schema=_skill_risk_schema(),
            )
        except Exception as exc:  # pragma: no cover - network/provider defensive path
            return SkillRiskReviewResponse(
                skill_id=request.skill_id,
                provider=self.provider_name,
                model=model_name if "model_name" in locals() else model,
                review_status="provider_error",
                error=str(exc),
            )

        return SkillRiskReviewResponse(
            skill_id=request.skill_id,
            provider=self.provider_name,
            model=model_name,
            review_status="reviewed",
            decision=StructuredSkillRiskDecision(
                skill_has_risk=str(parsed["skill_has_risk"]),
                reason=str(parsed["reason"]),
                confidence=str(parsed["confidence"]),
                confidence_score=float(parsed["confidence_score"]),
            ),
            raw_payload=parsed,
        )

    def review_domain(
        self,
        request: DomainReviewRequest,
        *,
        model: str | None,
        timeout_seconds: int,
    ) -> DomainReviewResponse:
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE_URL")
        if not api_key:
            return DomainReviewResponse(
                skill_id=request.skill_id,
                provider=self.provider_name,
                model=model,
                review_status="provider_error",
                error="OPENAI_API_KEY is not set",
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            return DomainReviewResponse(
                skill_id=request.skill_id,
                provider=self.provider_name,
                model=model,
                review_status="provider_error",
                error=f"openai package is not installed: {exc}",
            )

        try:
            model_name = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_seconds)
            parsed = _create_structured_chat_completion(
                client,
                model_name=model_name,
                system_prompt=build_domain_system_prompt(),
                payload=_build_domain_payload(request),
                schema=_domain_schema(request.allowed_domains),
            )
        except Exception as exc:  # pragma: no cover - network/provider defensive path
            return DomainReviewResponse(
                skill_id=request.skill_id,
                provider=self.provider_name,
                model=model_name if "model_name" in locals() else model,
                review_status="provider_error",
                error=str(exc),
            )

        return DomainReviewResponse(
            skill_id=request.skill_id,
            provider=self.provider_name,
            model=model_name,
            review_status="reviewed",
            decision=StructuredDomainDecision(
                domain=str(parsed["domain"]),
                reason=str(parsed["reason"]),
                confidence=str(parsed["confidence"]),
                confidence_score=float(parsed["confidence_score"]),
            ),
            raw_payload=parsed,
        )


def _create_structured_chat_completion(
    client: Any,
    *,
    model_name: str,
    system_prompt: str,
    payload: str,
    schema: dict[str, object],
) -> dict[str, object]:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": _build_structured_user_prompt(payload, schema)},
    ]
    base_kwargs: dict[str, object] = {
        "model": model_name,
        "messages": messages,
    }
    if model_name.lower().startswith("qwen3"):
        base_kwargs["extra_body"] = {"enable_thinking": False}

    attempts: list[dict[str, object]] = [
        {"response_format": {"type": "json_schema", "json_schema": schema}},
        {"response_format": {"type": "json_object"}},
        {},
    ]
    errors: list[str] = []
    for extra_kwargs in attempts:
        try:
            response = client.chat.completions.create(**base_kwargs, **extra_kwargs)
            content = _message_content_to_text(response.choices[0].message.content)
            return _parse_json_object(content)
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError("chat.completions failed for all structured-output modes: " + " | ".join(errors))


def _build_structured_user_prompt(payload: str, schema: dict[str, object]) -> str:
    schema_json = json.dumps(schema["schema"], ensure_ascii=False, separators=(",", ":"))
    return "\n".join(
        [
            payload,
            "",
            "Return exactly one JSON object.",
            "Do not wrap the JSON in markdown fences.",
            "Do not include any explanatory text before or after the JSON.",
            f"JSON schema: {schema_json}",
        ]
    )


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
                continue
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
                continue
            text_value = getattr(item, "text", None)
            if isinstance(text_value, str):
                text_parts.append(text_value)
        return "\n".join(part for part in text_parts if part).strip()
    raise ValueError("Provider returned empty or unsupported message content")


def _parse_json_object(content: str) -> dict[str, object]:
    text = content.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"Model did not return valid JSON: {content[:400]}")
        parsed = json.loads(text[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("Model returned JSON that is not an object")
    return parsed


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


def _build_payload(request: ReviewRequest) -> str:
    return json.dumps(
        {
            "task": "Review exactly one pre-existing category candidate and decide whether it should be accepted, downgraded, or rejected_by_llm.",
            "skill_id": request.skill_id,
            "candidate": {
                "category_id": request.candidate.category_id,
                "category_name": request.candidate.category_name,
                "layer": request.candidate.layer,
                "candidate_status": request.candidate.candidate_status,
                "rule_confidence": request.candidate.rule_confidence,
                "confidence_score": request.candidate.confidence_score,
            },
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
            "supporting_evidence": [
                {
                    "fingerprint": item.evidence_fingerprint,
                    "path": item.source_path,
                    "text": item.matched_text,
                }
                for item in request.supporting_evidence[:5]
            ],
            "conflicting_evidence": [
                {
                    "fingerprint": item.evidence_fingerprint,
                    "path": item.source_path,
                    "text": item.matched_text,
                }
                for item in request.conflicting_evidence[:5]
            ],
            "output_requirements": {
                "reason_style": "brief, concrete, evidence-focused",
                "fingerprint_rule": "Only return fingerprints that appear in the supplied evidence arrays.",
            },
        },
        ensure_ascii=False,
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


def _build_skill_risk_payload(request: SkillRiskReviewRequest) -> str:
    return json.dumps(
        {
            "task": "Decide whether this skill should be marked yes or no for skill_has_risk.",
            "skill_id": request.skill_id,
            "decision_policy": {
                "allowed_statuses": ["yes", "no"],
                "focus": "Use only final category decisions; retained implementation-layer decisions indicate realized capability.",
                "forbidden_actions": [
                    "changing category decisions",
                    "inventing categories",
                    "using evidence not present in the payload",
                ],
            },
            "final_decisions": [
                {
                    "category_id": item.category_id,
                    "category_name": item.category_name,
                    "layer": item.layer,
                    "decision_status": item.decision_status,
                    "confidence": item.confidence,
                    "confidence_score": item.confidence_score,
                }
                for item in request.final_decisions
            ],
        },
        ensure_ascii=False,
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


def _build_domain_payload(request: DomainReviewRequest) -> str:
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
