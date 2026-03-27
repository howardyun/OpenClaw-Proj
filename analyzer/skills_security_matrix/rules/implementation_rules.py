from __future__ import annotations

from ..models import CategoryClassification, EvidenceItem
from .candidate_builder import build_rule_candidates, decisions_to_classifications, finalize_rule_candidates


def classify_implementation(evidence: list[EvidenceItem]) -> list[CategoryClassification]:
    candidates = build_rule_candidates(evidence, layer="implementation")
    return decisions_to_classifications(finalize_rule_candidates(candidates), layer="implementation")
