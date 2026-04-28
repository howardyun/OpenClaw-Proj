from __future__ import annotations

from ..models import AnalysisResult, MatrixCategory, RuleCandidate
from .models import CascadePolicyConfig, CascadeRoute, ReviewRequest, ReviewTrigger, SkillRiskReviewRoute


def build_category_review_routes(
    skill_id: str,
    candidates: list[RuleCandidate],
    matrix_by_id: dict[str, MatrixCategory],
    config: CascadePolicyConfig,
) -> list[CascadeRoute]:
    if config.mode == "off":
        return []

    routes: list[CascadeRoute] = []
    fallback_budget = config.fallback_max_categories
    for candidate in candidates:
        triggers = _collect_candidate_triggers(candidate, matrix_by_id, config)
        if not triggers:
            continue
        fallback_allowed = config.mode == "review+fallback" and fallback_budget > 0
        if fallback_allowed:
            fallback_budget -= 1
        routes.append(
            CascadeRoute(
                skill_id=skill_id,
                candidate=candidate,
                triggers=triggers,
                fallback_allowed=fallback_allowed,
            )
        )
    return routes


def build_category_review_requests(
    skill_id: str,
    candidates: list[RuleCandidate],
    matrix_by_id: dict[str, MatrixCategory],
    config: CascadePolicyConfig,
) -> list[ReviewRequest]:
    return [route_to_review_request(route) for route in build_category_review_routes(skill_id, candidates, matrix_by_id, config)]


def route_to_review_request(route: CascadeRoute) -> ReviewRequest:
    candidate = route.candidate
    return ReviewRequest(
        skill_id=route.skill_id,
        candidate=candidate,
        supporting_evidence=candidate.supporting_evidence,
        conflicting_evidence=candidate.conflicting_evidence,
        triggers=route.triggers,
        fallback_allowed=route.fallback_allowed,
    )


def build_skill_risk_review_route(
    result: AnalysisResult,
    matrix_by_id: dict[str, MatrixCategory],
    config: CascadePolicyConfig,
    *,
    fallback_skill_has_risk: str,
) -> SkillRiskReviewRoute | None:
    if config.mode == "off":
        return None

    triggers: list[ReviewTrigger] = []
    rule_confidence_score = calculate_rule_skill_risk_confidence_score(result, fallback_skill_has_risk)
    if rule_confidence_score <= config.low_confidence_threshold:
        triggers.append(
            ReviewTrigger(
                category_id="skill_has_risk",
                layer="skill",
                trigger_type="low_confidence_skill_risk",
                reason=(
                    f"rule-based skill_has_risk={fallback_skill_has_risk} has confidence_score="
                    f"{rule_confidence_score:.2f} <= {config.low_confidence_threshold:.2f}"
                ),
            )
        )

    low_confidence_decisions = [
        decision
        for decision in result.final_decisions
        if decision.decision_status != "rejected_by_llm"
        and decision.confidence_score <= config.low_confidence_threshold
    ]
    if low_confidence_decisions:
        triggers.append(
            ReviewTrigger(
                category_id="skill_has_risk",
                layer="skill",
                trigger_type="low_confidence_final_risk",
                reason=(
                    f"{len(low_confidence_decisions)} retained decisions have confidence_score "
                    f"<= {config.low_confidence_threshold:.2f}"
                ),
            )
        )

    sparse_mismatches = [
        discrepancy
        for discrepancy in result.category_discrepancies
        if discrepancy.declaration_present != discrepancy.implementation_present
        and _support_count_for_category(result, discrepancy.category_id) <= config.high_risk_sparse_threshold
    ]
    if result.skill_level_discrepancy in {"implementation_only_high_risk", "declared_less_than_implemented"} and sparse_mismatches:
        triggers.append(
            ReviewTrigger(
                category_id="skill_has_risk",
                layer="skill",
                trigger_type="sparse_discrepancy_final_risk",
                reason=(
                    f"{result.skill_level_discrepancy} with {len(sparse_mismatches)} sparse mismatched categories "
                    f"<= {config.high_risk_sparse_threshold} supporting evidence items"
                ),
            )
        )

    high_risk_sparse = [
        decision
        for decision in result.final_decisions
        if decision.decision_status != "rejected_by_llm"
        and _is_high_risk(matrix_by_id.get(decision.category_id))
        and len(decision.supporting_evidence) <= config.high_risk_sparse_threshold
    ]
    if fallback_skill_has_risk == "yes" and high_risk_sparse:
        triggers.append(
            ReviewTrigger(
                category_id="skill_has_risk",
                layer="skill",
                trigger_type="high_risk_sparse_final_risk",
                reason=(
                    f"rule-based risk=yes with {len(high_risk_sparse)} high-risk retained decisions "
                    f"having support_count <= {config.high_risk_sparse_threshold}"
                ),
            )
        )

    if not triggers:
        return None
    return SkillRiskReviewRoute(
        skill_id=result.skill_id,
        fallback_skill_has_risk=fallback_skill_has_risk,
        triggers=triggers,
    )


def calculate_rule_skill_risk_confidence_score(result: AnalysisResult, fallback_skill_has_risk: str) -> float:
    retained_decisions = [
        decision for decision in result.final_decisions if decision.decision_status != "rejected_by_llm"
    ]
    if not retained_decisions:
        return 0.2 if fallback_skill_has_risk == "yes" else 0.6

    relevant_decisions = _risk_relevant_decisions(result, retained_decisions)
    scored_decisions = relevant_decisions or retained_decisions
    confidence_score = min(decision.confidence_score for decision in scored_decisions)

    if _has_sparse_mismatch(result):
        confidence_score = min(confidence_score, 0.4)
    if fallback_skill_has_risk == "yes" and not relevant_decisions:
        confidence_score = min(confidence_score, 0.35)
    return max(0.0, min(1.0, confidence_score))


def _collect_candidate_triggers(
    candidate: RuleCandidate,
    matrix_by_id: dict[str, MatrixCategory],
    config: CascadePolicyConfig,
) -> list[ReviewTrigger]:
    triggers: list[ReviewTrigger] = []
    if candidate.confidence_score <= config.low_confidence_threshold:
        triggers.append(
            ReviewTrigger(
                category_id=candidate.category_id,
                layer=candidate.layer,
                trigger_type="low_confidence",
                reason=f"confidence_score={candidate.confidence_score:.2f} <= {config.low_confidence_threshold:.2f}",
            )
        )
    if candidate.conflicting_evidence:
        triggers.append(
            ReviewTrigger(
                category_id=candidate.category_id,
                layer=candidate.layer,
                trigger_type="conflict",
                reason=f"conflicting_evidence={len(candidate.conflicting_evidence)}",
            )
        )
    matrix_category = matrix_by_id.get(candidate.category_id)
    if _is_high_risk(matrix_category) and len(candidate.supporting_evidence) <= config.high_risk_sparse_threshold:
        triggers.append(
            ReviewTrigger(
                category_id=candidate.category_id,
                layer=candidate.layer,
                trigger_type="high_risk_sparse_support",
                reason=(
                    f"high-risk category with support_count={len(candidate.supporting_evidence)} "
                    f"<= {config.high_risk_sparse_threshold}"
                ),
            )
        )
    if candidate.supporting_evidence and not any(
        item.evidence_strength == "strong" for item in candidate.supporting_evidence
    ):
        triggers.append(
            ReviewTrigger(
                category_id=candidate.category_id,
                layer=candidate.layer,
                trigger_type="semantic_ambiguity",
                reason="supporting evidence has no strong evidence_strength",
            )
        )
    return triggers


def _support_count_for_category(result: AnalysisResult, category_id: str) -> int:
    return sum(
        len(decision.supporting_evidence)
        for decision in result.final_decisions
        if decision.category_id == category_id and decision.decision_status != "rejected_by_llm"
    )


def _risk_relevant_decisions(
    result: AnalysisResult,
    retained_decisions,
):
    risk_statuses = {"implementation_only_high_risk", "declared_less_than_implemented"}
    if result.skill_level_discrepancy not in risk_statuses:
        return []

    implementation_gap_ids = {
        discrepancy.category_id
        for discrepancy in result.category_discrepancies
        if discrepancy.implementation_present
        and (
            not discrepancy.declaration_present
            or set(discrepancy.implementation_atomic_ids) - set(discrepancy.declaration_atomic_ids)
        )
    }
    return [
        decision
        for decision in retained_decisions
        if decision.layer == "implementation" and decision.category_id in implementation_gap_ids
    ]


def _has_sparse_mismatch(result: AnalysisResult) -> bool:
    return any(
        discrepancy.declaration_present != discrepancy.implementation_present
        and _support_count_for_category(result, discrepancy.category_id) <= 1
        for discrepancy in result.category_discrepancies
    )


def _is_high_risk(category: MatrixCategory | None) -> bool:
    if category is None:
        return False
    high_risk_codes = {"E", "D", "T", "I", "R"}
    return any(risk in high_risk_codes for risk in category.primary_risks)
