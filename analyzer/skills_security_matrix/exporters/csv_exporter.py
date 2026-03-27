from __future__ import annotations

import csv
from pathlib import Path

from ..models import AnalysisResult


def export_csv_files(output_dir: Path, results: list[AnalysisResult]) -> None:
    _write_csv(
        output_dir / "skills.csv",
        ["skill_id", "root_path", "has_skill_md", "has_frontmatter", "has_references_dir", "has_scripts_dir", "has_assets_dir"],
        [
            {
                "skill_id": result.skill_id,
                "root_path": result.root_path,
                "has_skill_md": result.structure_profile.has_skill_md,
                "has_frontmatter": result.structure_profile.has_frontmatter,
                "has_references_dir": result.structure_profile.has_references_dir,
                "has_scripts_dir": result.structure_profile.has_scripts_dir,
                "has_assets_dir": result.structure_profile.has_assets_dir,
            }
            for result in results
        ],
    )
    _write_csv(
        output_dir / "classifications.csv",
        [
            "skill_id",
            "layer",
            "category_id",
            "category_name",
            "confidence",
            "source_path",
            "line_start",
            "rule_id",
            "matched_text",
        ],
        _classification_rows(results),
    )
    _write_csv(
        output_dir / "rule_candidates.csv",
        [
            "skill_id",
            "candidate_id",
            "layer",
            "category_id",
            "category_name",
            "candidate_status",
            "rule_confidence",
            "confidence_score",
            "support_count",
            "conflict_count",
            "trigger_reason",
        ],
        _candidate_rows(results),
    )
    _write_csv(
        output_dir / "discrepancies.csv",
        ["skill_id", "skill_level_discrepancy", "category_id", "category_name", "status", "declaration_present", "implementation_present"],
        _discrepancy_rows(results),
    )
    _write_csv(
        output_dir / "review_audit.csv",
        ["skill_id", "category_id", "layer", "review_status", "provider", "model", "reason", "schema_version"],
        _review_audit_rows(results),
    )


def _classification_rows(results: list[AnalysisResult]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for result in results:
        for layer, classifications in (
            ("declaration", result.declaration_classifications),
            ("implementation", result.implementation_classifications),
        ):
            for classification in classifications:
                for evidence in classification.evidence:
                    rows.append(
                        {
                            "skill_id": result.skill_id,
                            "layer": layer,
                            "category_id": classification.category_id,
                            "category_name": classification.category_name,
                            "confidence": classification.confidence,
                            "source_path": evidence.source_path,
                            "line_start": evidence.line_start,
                            "rule_id": evidence.rule_id,
                            "matched_text": evidence.matched_text,
                        }
                    )
    return rows


def _discrepancy_rows(results: list[AnalysisResult]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for result in results:
        if not result.category_discrepancies:
            rows.append(
                {
                    "skill_id": result.skill_id,
                    "skill_level_discrepancy": result.skill_level_discrepancy,
                    "category_id": "",
                    "category_name": "",
                    "status": result.skill_level_discrepancy,
                    "declaration_present": "",
                    "implementation_present": "",
                }
            )
            continue
        for item in result.category_discrepancies:
            rows.append(
                {
                    "skill_id": result.skill_id,
                    "skill_level_discrepancy": result.skill_level_discrepancy,
                    "category_id": item.category_id,
                    "category_name": item.category_name,
                    "status": item.status,
                    "declaration_present": item.declaration_present,
                    "implementation_present": item.implementation_present,
                }
            )
    return rows


def _candidate_rows(results: list[AnalysisResult]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for result in results:
        for candidate in result.rule_candidates:
            rows.append(
                {
                    "skill_id": result.skill_id,
                    "candidate_id": candidate.candidate_id,
                    "layer": candidate.layer,
                    "category_id": candidate.category_id,
                    "category_name": candidate.category_name,
                    "candidate_status": candidate.candidate_status,
                    "rule_confidence": candidate.rule_confidence,
                    "confidence_score": candidate.confidence_score,
                    "support_count": len(candidate.supporting_evidence),
                    "conflict_count": len(candidate.conflicting_evidence),
                    "trigger_reason": candidate.trigger_reason,
                }
            )
    return rows


def _review_audit_rows(results: list[AnalysisResult]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for result in results:
        for record in result.review_audit_records:
            rows.append(
                {
                    "skill_id": result.skill_id,
                    "category_id": record.category_id,
                    "layer": record.layer,
                    "review_status": record.review_status,
                    "provider": record.provider or "",
                    "model": record.model or "",
                    "reason": record.reason or "",
                    "schema_version": record.schema_version or "",
                }
            )
    return rows


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
