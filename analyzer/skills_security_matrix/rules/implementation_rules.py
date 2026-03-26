from __future__ import annotations

from .declaration_rules import _classify
from ..models import CategoryClassification, EvidenceItem


def classify_implementation(evidence: list[EvidenceItem]) -> list[CategoryClassification]:
    return _classify(evidence)
