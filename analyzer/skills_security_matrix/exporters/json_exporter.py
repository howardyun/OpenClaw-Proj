from __future__ import annotations

import json
from pathlib import Path

from ..models import AnalysisResult, RunSummary, dataclass_to_dict
from .no_classifications import no_classification_record, no_classification_results
from .permission_summary import build_permission_summary
from ..tier_mapping import (
    build_exported_category_lookup,
    export_classification,
    export_discrepancy,
    export_final_decision,
    export_risk_mapping,
    export_rule_candidate,
)


def export_json_files(
    output_dir: Path,
    results: list[AnalysisResult],
    summary: RunSummary,
    *,
    emit_category_discrepancies: bool = False,
    emit_risk_mappings: bool = False,
) -> None:
    _write_json(output_dir / "skills.json", [skill_record(result) for result in results])
    _write_json(output_dir / "rule_candidates.json", [candidate_record(result) for result in results])
    _write_json(
        output_dir / "classifications.json",
        [classification_record(result, emit_risk_mappings=emit_risk_mappings) for result in results],
    )
    if emit_category_discrepancies:
        _write_json(output_dir / "discrepancies.json", [discrepancy_record(result) for result in results])
    _write_json(
        output_dir / "implementation_only_high_risk.json",
        [discrepancy_record(result) for result in implementation_only_high_risk_results(results)],
    )
    _write_json(
        output_dir / "no_classifications.json",
        [no_classification_record(result) for result in no_classification_results(results)],
    )
    if emit_risk_mappings:
        _write_json(output_dir / "risk_mappings.json", [risk_mapping_record(result) for result in results])
    _write_json(output_dir / "review_audit.json", [review_audit_record(result) for result in results])
    _write_json(output_dir / "run_manifest.json", dataclass_to_dict(summary))
    if summary.validation_summary is not None:
        _write_json(output_dir / "validation.json", summary.validation_summary)

    cases_dir = output_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    for result in results:
        _write_json(
            cases_dir / f"{_safe_filename(result.skill_id)}.json",
            case_record(
                result,
                emit_category_discrepancies=emit_category_discrepancies,
                emit_risk_mappings=emit_risk_mappings,
            ),
        )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_filename(value: str) -> str:
    return value.replace("/", "__")


def implementation_only_high_risk_results(results: list[AnalysisResult]) -> list[AnalysisResult]:
    return [result for result in results if result.skill_level_discrepancy == "implementation_only_high_risk"]


def skill_record(result: AnalysisResult) -> dict[str, object]:
    return {
        "skill_id": result.skill_id,
        "domain": result.domain,
        "root_path": result.root_path,
        "structure_profile": dataclass_to_dict(result.structure_profile),
        "domain_adjudication": dataclass_to_dict(result.domain_adjudication),
        "skill_has_risk": result.skill_has_risk,
        "skill_risk_adjudication": dataclass_to_dict(result.skill_risk_adjudication),
        "errors": result.errors,
    }


def classification_record(result: AnalysisResult, *, emit_risk_mappings: bool = False) -> dict[str, object]:
    payload = {
        "skill_id": result.skill_id,
        "domain": result.domain,
        "domain_adjudication": dataclass_to_dict(result.domain_adjudication),
        "skill_has_risk": result.skill_has_risk,
        "permission_summary": build_permission_summary(result),
        "declaration_atomic_decisions": [dataclass_to_dict(item) for item in result.declaration_atomic_decisions],
        "implementation_atomic_decisions": [dataclass_to_dict(item) for item in result.implementation_atomic_decisions],
        "declaration_control_decisions": [dataclass_to_dict(item) for item in result.declaration_control_decisions],
        "implementation_control_decisions": [dataclass_to_dict(item) for item in result.implementation_control_decisions],
        "final_decisions": [dataclass_to_dict(export_final_decision(item)) for item in result.final_decisions],
        "declaration_classifications": [dataclass_to_dict(export_classification(item)) for item in result.declaration_classifications],
        "implementation_classifications": [dataclass_to_dict(export_classification(item)) for item in result.implementation_classifications],
        "skill_risk_adjudication": dataclass_to_dict(result.skill_risk_adjudication),
        "errors": result.errors,
    }
    if emit_risk_mappings:
        payload["risk_mappings"] = [export_risk_mapping(item) for item in result.risk_mappings]
    return payload


def candidate_record(result: AnalysisResult) -> dict[str, object]:
    return {
        "skill_id": result.skill_id,
        "skill_has_risk": result.skill_has_risk,
        "rule_candidates": [dataclass_to_dict(export_rule_candidate(item)) for item in result.rule_candidates],
        "skill_risk_adjudication": dataclass_to_dict(result.skill_risk_adjudication),
        "errors": result.errors,
    }


def discrepancy_record(result: AnalysisResult) -> dict[str, object]:
    return {
        "skill_id": result.skill_id,
        "skill_has_risk": result.skill_has_risk,
        "skill_level_discrepancy": result.skill_level_discrepancy,
        "category_discrepancies": [dataclass_to_dict(export_discrepancy(item)) for item in result.category_discrepancies],
        "skill_risk_adjudication": dataclass_to_dict(result.skill_risk_adjudication),
        "errors": result.errors,
    }


def risk_mapping_record(result: AnalysisResult) -> dict[str, object]:
    return {
        "skill_id": result.skill_id,
        "skill_has_risk": result.skill_has_risk,
        "risk_mappings": [export_risk_mapping(item) for item in result.risk_mappings],
        "skill_risk_adjudication": dataclass_to_dict(result.skill_risk_adjudication),
        "errors": result.errors,
    }


def review_audit_record(result: AnalysisResult) -> dict[str, object]:
    category_lookup = build_exported_category_lookup(result)
    return {
        "skill_id": result.skill_id,
        "skill_has_risk": result.skill_has_risk,
        "review_audit_records": [
            {
                **dataclass_to_dict(item),
                "category_id": category_lookup.get(item.category_id, (item.category_id, ""))[0],
            }
            for item in result.review_audit_records
        ],
        "skill_risk_adjudication": dataclass_to_dict(result.skill_risk_adjudication),
        "errors": result.errors,
    }


def case_record(
    result: AnalysisResult,
    *,
    emit_category_discrepancies: bool = False,
    emit_risk_mappings: bool = False,
) -> dict[str, object]:
    category_lookup = build_exported_category_lookup(result)
    payload = dataclass_to_dict(result)
    payload["rule_candidates"] = [dataclass_to_dict(export_rule_candidate(item)) for item in result.rule_candidates]
    payload["final_decisions"] = [dataclass_to_dict(export_final_decision(item)) for item in result.final_decisions]
    payload["declaration_classifications"] = [
        dataclass_to_dict(export_classification(item)) for item in result.declaration_classifications
    ]
    payload["implementation_classifications"] = [
        dataclass_to_dict(export_classification(item)) for item in result.implementation_classifications
    ]
    if emit_category_discrepancies:
        payload["category_discrepancies"] = [
            dataclass_to_dict(export_discrepancy(item)) for item in result.category_discrepancies
        ]
    else:
        payload.pop("category_discrepancies", None)
    if emit_risk_mappings:
        payload["risk_mappings"] = [export_risk_mapping(item) for item in result.risk_mappings]
    else:
        payload.pop("risk_mappings", None)
    payload["review_audit_records"] = [
        {
            **dataclass_to_dict(item),
            "category_id": category_lookup.get(item.category_id, (item.category_id, ""))[0],
        }
        for item in result.review_audit_records
    ]
    return payload
