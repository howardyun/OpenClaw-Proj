from __future__ import annotations

from collections import defaultdict

from ..models import CategoryClassification, EvidenceItem, FinalCategoryDecision, RuleCandidate
from .catalog import bucket_confidence, highest_confidence


def build_rule_candidates(evidence: list[EvidenceItem], layer: str) -> list[RuleCandidate]:
    grouped: dict[tuple[str, str], list[EvidenceItem]] = defaultdict(list)
    for item in evidence:
        grouped[(item.category_id, item.category_name)].append(item)

    candidates: list[RuleCandidate] = []
    for category_index, ((category_id, category_name), items) in enumerate(sorted(grouped.items()), start=1):
        confidence_score = _calculate_confidence_score(items)
        candidates.append(
            RuleCandidate(
                candidate_id=f"{layer}:{category_id}:{category_index}",
                category_id=category_id,
                category_name=category_name,
                layer=layer,
                candidate_status="supported",
                supporting_evidence=_dedupe_evidence(items)[:10],
                conflicting_evidence=[],
                rule_confidence=bucket_confidence(confidence_score),
                confidence_score=confidence_score,
                trigger_reason="deterministic_rule_match",
            )
        )
    return candidates


def finalize_rule_candidates(candidates: list[RuleCandidate]) -> list[FinalCategoryDecision]:
    decisions: list[FinalCategoryDecision] = []
    for candidate in candidates:
        decisions.append(
            FinalCategoryDecision(
                category_id=candidate.category_id,
                category_name=candidate.category_name,
                layer=candidate.layer,
                decision_status="accepted" if candidate.supporting_evidence else "insufficient_evidence",
                supporting_evidence=candidate.supporting_evidence,
                conflicting_evidence=candidate.conflicting_evidence,
                confidence=candidate.rule_confidence,
                confidence_score=candidate.confidence_score,
                source_candidate_ids=[candidate.candidate_id],
            )
        )
    return decisions


def decisions_to_classifications(decisions: list[FinalCategoryDecision], layer: str) -> list[CategoryClassification]:
    filtered = [decision for decision in decisions if decision.layer == layer and decision.decision_status != "rejected_by_llm"]
    classifications: list[CategoryClassification] = []
    for decision in filtered:
        evidence = _dedupe_evidence(decision.supporting_evidence + decision.conflicting_evidence)[:10]
        classifications.append(
            CategoryClassification(
                category_id=decision.category_id,
                category_name=decision.category_name,
                evidence=evidence,
                confidence=decision.confidence,
                confidence_score=decision.confidence_score,
                decision_status=decision.decision_status,
            )
        )
    return classifications


def _calculate_confidence_score(items: list[EvidenceItem]) -> float:
    if not items:
        return 0.0
    support_count = min(len(items), 4) * 0.15
    unique_sources = len({item.source_path for item in items}) * 0.1
    reference_bonus = 0.1 if any(item.support_reference_mode == "referenced_by_skill_md" for item in items) else 0.0
    direct_bonus = 0.15 if any(item.source_kind in {"skill_md_frontmatter", "skill_md_body"} for item in items) else 0.0
    lexical_bonus = 0.1 if highest_confidence([item.confidence for item in items]) == "high" else 0.0
    return min(1.0, support_count + unique_sources + reference_bonus + direct_bonus + lexical_bonus)


def _dedupe_evidence(items: list[EvidenceItem]) -> list[EvidenceItem]:
    unique: dict[str, EvidenceItem] = {}
    for item in items:
        unique.setdefault(item.evidence_fingerprint, item)
    return list(unique.values())
