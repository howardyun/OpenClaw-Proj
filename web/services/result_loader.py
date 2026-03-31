from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ResultLoadError(FileNotFoundError):
    """Raised when a run manifest or case payload cannot be loaded."""


@dataclass(slots=True)
class FinalDecisionView:
    category_id: str
    category_name: str
    layer: str
    decision_status: str
    confidence: str
    confidence_score: float
    support_count: int
    conflict_count: int


@dataclass(slots=True)
class CategoryDiscrepancyView:
    category_id: str
    category_name: str
    status: str
    declaration_present: bool
    implementation_present: bool
    risks: list[str]
    controls: list[str]


@dataclass(slots=True)
class RiskMappingView:
    category_id: str
    category_name: str
    primary_risks: list[str]
    control_requirements: list[str]


@dataclass(slots=True)
class StructureItem:
    label: str
    value: str


@dataclass(slots=True)
class CaseViewModel:
    run_id: str
    skill_key: str
    skill_id: str
    root_path: str
    structure_items: list[StructureItem]
    final_decisions: list[FinalDecisionView]
    skill_level_discrepancy: str
    category_discrepancies: list[CategoryDiscrepancyView]
    risk_mappings: list[RiskMappingView]
    errors: list[str]
    rule_candidates_json: str
    review_audit_json: str
    manifest: dict[str, Any]
    raw_case: dict[str, Any]


def load_case_result(
    run_id: str,
    skill_key: str,
    *,
    output_root: str | Path = "outputs/web_runs",
) -> CaseViewModel:
    run_dir = Path(output_root) / run_id
    if not run_dir.is_dir():
        raise ResultLoadError(f"run 不存在：{run_id}")

    manifest_path = run_dir / "run_manifest.json"
    case_path = run_dir / "cases" / f"{skill_key}.json"
    manifest = _load_json(manifest_path, "manifest")
    case_payload = _load_json(case_path, "case")

    structure_profile = case_payload.get("structure_profile") or {}
    structure_items = [
        StructureItem("包含 SKILL.md", _yes_no(structure_profile.get("has_skill_md"))),
        StructureItem("包含 frontmatter", _yes_no(structure_profile.get("has_frontmatter"))),
        StructureItem("包含 references 目录", _yes_no(structure_profile.get("has_references_dir"))),
        StructureItem("包含 scripts 目录", _yes_no(structure_profile.get("has_scripts_dir"))),
        StructureItem("包含 assets 目录", _yes_no(structure_profile.get("has_assets_dir"))),
        StructureItem("包含 templates 目录", _yes_no(structure_profile.get("has_templates_dir"))),
        StructureItem("顶层文件", _join_items(structure_profile.get("top_level_files"))),
        StructureItem("顶层目录", _join_items(structure_profile.get("top_level_dirs"))),
    ]

    final_decisions = [
        FinalDecisionView(
            category_id=item.get("category_id", ""),
            category_name=item.get("category_name", ""),
            layer=item.get("layer", ""),
            decision_status=item.get("decision_status", ""),
            confidence=item.get("confidence", "unknown"),
            confidence_score=float(item.get("confidence_score", 0.0) or 0.0),
            support_count=len(item.get("supporting_evidence") or []),
            conflict_count=len(item.get("conflicting_evidence") or []),
        )
        for item in case_payload.get("final_decisions") or []
    ]

    category_discrepancies = [
        CategoryDiscrepancyView(
            category_id=item.get("category_id", ""),
            category_name=item.get("category_name", ""),
            status=item.get("status", ""),
            declaration_present=bool(item.get("declaration_present")),
            implementation_present=bool(item.get("implementation_present")),
            risks=list(item.get("risks") or []),
            controls=list(item.get("controls") or []),
        )
        for item in case_payload.get("category_discrepancies") or []
    ]

    risk_mappings = [
        RiskMappingView(
            category_id=item.get("category_id", ""),
            category_name=item.get("category_name", ""),
            primary_risks=list(item.get("primary_risks") or item.get("risks") or []),
            control_requirements=list(item.get("control_requirements") or item.get("controls") or []),
        )
        for item in case_payload.get("risk_mappings") or []
    ]

    return CaseViewModel(
        run_id=run_id,
        skill_key=skill_key,
        skill_id=case_payload.get("skill_id", skill_key),
        root_path=case_payload.get("root_path", ""),
        structure_items=structure_items,
        final_decisions=final_decisions,
        skill_level_discrepancy=case_payload.get("skill_level_discrepancy", "unknown"),
        category_discrepancies=category_discrepancies,
        risk_mappings=risk_mappings,
        errors=list(case_payload.get("errors") or []),
        rule_candidates_json=_pretty_json(case_payload.get("rule_candidates") or []),
        review_audit_json=_pretty_json(case_payload.get("review_audit_records") or []),
        manifest=manifest,
        raw_case=case_payload,
    )


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ResultLoadError(f"{label} 文件不存在：{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ResultLoadError(f"{label} 文件不是合法 JSON：{path}") from exc


def _pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _join_items(items: Any) -> str:
    values = list(items or [])
    return "、".join(values) if values else "无"


def _yes_no(value: Any) -> str:
    return "是" if bool(value) else "否"
