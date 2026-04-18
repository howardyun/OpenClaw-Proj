from __future__ import annotations

import re
from pathlib import Path

from .models import AnalysisResult, MatrixCategory


HIGH_SEVERITY_SKILL_MD_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(exfiltrat(e|ion)|steal|harvest)\b",
        r"\b(privilege escalation|escalate privileges)\b",
        r"\b(ignore (all|previous) instructions|bypass (guardrails|safety|restrictions?))\b",
        r"\b(jailbreak|prompt injection|override safety|disable safeguards?)\b",
        r"\b(backdoor|persistence mechanism|covert channel)\b",
        r"\b(delete|drop|truncate|revoke|reset)\b.{0,40}\b(production|database|schema|table|credential|token)\b",
        r"\b(secret|token|password|credential|api key)\b.{0,40}\b(extract|dump|print|leak|expose)\b",
        r"\b(send|post|upload|export|forward)\b.{0,40}\b(secret|token|password|credential|api key|sensitive data|pii)\b",
    )
]

def determine_skill_has_risk(result: AnalysisResult, matrix_by_id: dict[str, MatrixCategory]) -> str:
    if _is_skill_md_only(result):
        return _determine_skill_md_only_risk(result)
    risky_statuses = {"implementation_only_high_risk", "declared_less_than_implemented"}
    return "yes" if result.skill_level_discrepancy in risky_statuses else "no"


def build_risk_mappings(result: AnalysisResult, matrix_by_id: dict[str, MatrixCategory]) -> list[dict[str, object]]:
    category_ids = _retained_category_ids(result)
    declaration_atomic_by_category = _group_atomic_ids(result.declaration_atomic_decisions)
    implementation_atomic_by_category = _group_atomic_ids(result.implementation_atomic_decisions)
    declaration_controls = sorted(
        {item.control_id for item in result.declaration_control_decisions if item.decision_status == "accepted"}
    )
    implementation_controls = sorted(
        {item.control_id for item in result.implementation_control_decisions if item.decision_status == "accepted"}
    )
    mappings: list[dict[str, object]] = []
    for category_id in sorted(category_ids):
        matrix_category = matrix_by_id[category_id]
        mappings.append(
            {
                "category_id": category_id,
                "category_name": matrix_category.subcategory,
                "major_category": matrix_category.major_category,
                "risks": matrix_category.primary_risks,
                "controls": matrix_category.control_requirements,
                "declaration_atomic_ids": sorted(declaration_atomic_by_category.get(category_id, set())),
                "implementation_atomic_ids": sorted(implementation_atomic_by_category.get(category_id, set())),
                "declared_control_ids": declaration_controls,
                "implemented_control_ids": implementation_controls,
                "missing_control_ids": sorted(set(declaration_controls) - set(implementation_controls)),
            }
        )
    return mappings


def _retained_category_ids(result: AnalysisResult) -> set[str]:
    return {decision.category_id for decision in result.final_decisions if decision.decision_status != "rejected_by_llm"}


def _group_atomic_ids(decisions) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = {}
    for decision in decisions:
        if decision.decision_status != "accepted":
            continue
        for category_id in decision.mapped_category_ids:
            grouped.setdefault(category_id, set()).add(decision.atomic_id)
    return grouped


def _is_skill_md_only(result: AnalysisResult) -> bool:
    profile = result.structure_profile
    return (
        profile.has_skill_md
        and profile.top_level_files == ["SKILL.md"]
        and not profile.top_level_dirs
        and not profile.has_references_dir
        and not profile.has_scripts_dir
        and not profile.has_assets_dir
        and not profile.has_templates_dir
    )


def _determine_skill_md_only_risk(result: AnalysisResult) -> str:
    skill_md_path = Path(result.root_path) / "SKILL.md"
    try:
        text = skill_md_path.read_text(encoding="utf-8")
    except OSError:
        return "no"

    return "yes" if any(pattern.search(text) for pattern in HIGH_SEVERITY_SKILL_MD_PATTERNS) else "no"
