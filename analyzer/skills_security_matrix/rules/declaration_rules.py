from __future__ import annotations

from collections import defaultdict

from ..models import CategoryClassification, EvidenceItem


def classify_declaration(evidence: list[EvidenceItem]) -> list[CategoryClassification]:
    return _classify(evidence)


def _classify(evidence: list[EvidenceItem]) -> list[CategoryClassification]:
    grouped: dict[tuple[str, str], list[EvidenceItem]] = defaultdict(list)
    for item in evidence:
        grouped[(item.category_id, item.category_name)].append(item)

    classifications: list[CategoryClassification] = []
    for (category_id, category_name), items in sorted(grouped.items()):
        classifications.append(
            CategoryClassification(
                category_id=category_id,
                category_name=category_name,
                evidence=items[:10],
                confidence=_highest_confidence(items),
            )
        )
    return classifications


def _highest_confidence(items: list[EvidenceItem]) -> str:
    priorities = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
    return max((item.confidence for item in items), key=lambda value: priorities.get(value, 0))
