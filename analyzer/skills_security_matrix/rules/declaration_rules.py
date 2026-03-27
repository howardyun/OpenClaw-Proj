from __future__ import annotations

from ..models import CategoryClassification, EvidenceItem
from .candidate_builder import build_rule_candidates, decisions_to_classifications, finalize_rule_candidates


def classify_declaration(evidence: list[EvidenceItem]) -> list[CategoryClassification]:
    candidates = build_rule_candidates(evidence, layer="declaration")
    return decisions_to_classifications(finalize_rule_candidates(candidates), layer="declaration")
