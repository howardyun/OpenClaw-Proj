from __future__ import annotations

from dataclasses import replace

from .models import CategoryDiscrepancy, CategoryClassification, EvidenceItem, FinalCategoryDecision, RuleCandidate


TIER_PRIORITY = {
    "tier_1": 1,
    "tier_2": 2,
    "tier_3": 3,
    "tier_4": 4,
}

TIER_NAMES = {
    "tier_1": "Tier 1: 资源感知层",
    "tier_2": "Tier 2: 交互通信层",
    "tier_3": "Tier 3: 环境管控层",
    "tier_4": "Tier 4: 代理协同层",
}

ATOMIC_PREFIX_TO_TIER = {
    "R": "tier_1",
    "Q": "tier_1",
    "S": "tier_1",
    "W": "tier_2",
    "U": "tier_2",
    "C": "tier_2",
    "X": "tier_3",
    "G": "tier_3",
    "O": "tier_3",
    "K": "tier_3",
    "A": "tier_4",
    "I": "tier_4",
}

CATEGORY_TIER_FALLBACK = {
    "session_context_access": ("tier_2", TIER_NAMES["tier_2"]),
    "file_knowledge_access": ("tier_1", TIER_NAMES["tier_1"]),
    "external_information_access": ("tier_2", TIER_NAMES["tier_2"]),
    "retrieval_query_execution": ("tier_1", TIER_NAMES["tier_1"]),
    "code_computation_execution": ("tier_3", TIER_NAMES["tier_3"]),
    "content_generation_file_processing": ("tier_3", TIER_NAMES["tier_3"]),
    "draft_suggestion_write": ("tier_3", TIER_NAMES["tier_3"]),
    "confirmed_single_write": ("tier_4", TIER_NAMES["tier_4"]),
    "automatic_batch_write": ("tier_4", TIER_NAMES["tier_4"]),
    "cross_app_identity_proxy": ("tier_4", TIER_NAMES["tier_4"]),
    "scheduled_periodic_automation": ("tier_4", TIER_NAMES["tier_4"]),
    "conditional_trigger_monitoring_automation": ("tier_4", TIER_NAMES["tier_4"]),
}


def atomic_id_to_tier(atomic_id: str) -> tuple[str, str] | None:
    if not atomic_id:
        return None
    tier_id = ATOMIC_PREFIX_TO_TIER.get(atomic_id[0].upper())
    if tier_id is None:
        return None
    return tier_id, TIER_NAMES[tier_id]


def resolve_tier_from_atomic_ids(atomic_ids: list[str] | set[str] | tuple[str, ...]) -> tuple[str, str] | None:
    resolved = [atomic_id_to_tier(atomic_id) for atomic_id in atomic_ids]
    tiers = [item for item in resolved if item is not None]
    if not tiers:
        return None
    return max(tiers, key=lambda item: TIER_PRIORITY[item[0]])


def resolve_tier_from_evidence(evidence: list[EvidenceItem]) -> tuple[str, str] | None:
    atomic_ids = [
        item.category_id
        for item in evidence
        if item.subject_type == "atomic_capability"
    ]
    return resolve_tier_from_atomic_ids(atomic_ids)


def apply_tier_export(
    category_id: str,
    category_name: str,
    *,
    atomic_ids: list[str] | set[str] | tuple[str, ...] | None = None,
    evidence: list[EvidenceItem] | None = None,
) -> tuple[str, str]:
    tier = None
    if atomic_ids:
        tier = resolve_tier_from_atomic_ids(atomic_ids)
    if tier is None and evidence:
        tier = resolve_tier_from_evidence(evidence)
    if tier is None:
        return CATEGORY_TIER_FALLBACK.get(category_id, (category_id, category_name))
    return tier


def export_rule_candidate(candidate: RuleCandidate) -> RuleCandidate:
    category_id, category_name = apply_tier_export(
        candidate.category_id,
        candidate.category_name,
        evidence=candidate.supporting_evidence or candidate.conflicting_evidence,
    )
    return replace(candidate, category_id=category_id, category_name=category_name)


def export_final_decision(decision: FinalCategoryDecision) -> FinalCategoryDecision:
    category_id, category_name = apply_tier_export(
        decision.category_id,
        decision.category_name,
        evidence=decision.supporting_evidence or decision.conflicting_evidence,
    )
    return replace(decision, category_id=category_id, category_name=category_name)


def export_classification(classification: CategoryClassification) -> CategoryClassification:
    category_id, category_name = apply_tier_export(
        classification.category_id,
        classification.category_name,
        evidence=classification.evidence,
    )
    return replace(classification, category_id=category_id, category_name=category_name)


def export_discrepancy(discrepancy: CategoryDiscrepancy) -> CategoryDiscrepancy:
    atomic_ids = discrepancy.declaration_atomic_ids + discrepancy.implementation_atomic_ids
    category_id, category_name = apply_tier_export(
        discrepancy.category_id,
        discrepancy.category_name,
        atomic_ids=atomic_ids,
    )
    return replace(discrepancy, category_id=category_id, category_name=category_name)


def export_risk_mapping(mapping: dict[str, object]) -> dict[str, object]:
    atomic_ids = [
        *mapping.get("declaration_atomic_ids", []),
        *mapping.get("implementation_atomic_ids", []),
    ]
    category_id, category_name = apply_tier_export(
        str(mapping.get("category_id", "")),
        str(mapping.get("category_name", "")),
        atomic_ids=atomic_ids,
    )
    exported = dict(mapping)
    exported["category_id"] = category_id
    exported["category_name"] = category_name
    return exported


def build_exported_category_lookup(result) -> dict[str, tuple[str, str]]:
    lookup: dict[str, tuple[str, str]] = {}
    for candidate in result.rule_candidates:
        lookup[candidate.category_id] = apply_tier_export(
            candidate.category_id,
            candidate.category_name,
            evidence=candidate.supporting_evidence or candidate.conflicting_evidence,
        )
    for decision in result.final_decisions:
        lookup[decision.category_id] = apply_tier_export(
            decision.category_id,
            decision.category_name,
            evidence=decision.supporting_evidence or decision.conflicting_evidence,
        )
    for discrepancy in result.category_discrepancies:
        atomic_ids = discrepancy.declaration_atomic_ids + discrepancy.implementation_atomic_ids
        lookup[discrepancy.category_id] = apply_tier_export(
            discrepancy.category_id,
            discrepancy.category_name,
            atomic_ids=atomic_ids,
        )
    for mapping in result.risk_mappings:
        atomic_ids = [
            *mapping.get("declaration_atomic_ids", []),
            *mapping.get("implementation_atomic_ids", []),
        ]
        lookup[str(mapping.get("category_id", ""))] = apply_tier_export(
            str(mapping.get("category_id", "")),
            str(mapping.get("category_name", "")),
            atomic_ids=atomic_ids,
        )
    return lookup
