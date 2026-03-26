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
        output_dir / "discrepancies.csv",
        ["skill_id", "skill_level_discrepancy", "category_id", "category_name", "status", "declaration_present", "implementation_present"],
        _discrepancy_rows(results),
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


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
