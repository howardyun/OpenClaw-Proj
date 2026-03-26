from __future__ import annotations

import argparse
import tempfile
from datetime import datetime
from pathlib import Path

from .discrepancy import compute_discrepancies
from .evidence.declaration import extract_declaration_evidence
from .evidence.implementation import extract_implementation_evidence
from .exporters.csv_exporter import export_csv_files
from .exporters.json_exporter import export_json_files
from .matrix_loader import parse_matrix_file
from .models import AnalysisResult, RunConfig, RunSummary
from .risk_mapping import build_risk_mappings
from .rules.declaration_rules import classify_declaration
from .rules.implementation_rules import classify_implementation
from .skill_discovery import discover_skills


DEFAULT_MATRIX_PATH = Path("analyzer/security matrix.md")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze local skill repositories against the security matrix.")
    parser.add_argument("--skills-dir", required=True, help="Top-level directory containing skill repositories.")
    parser.add_argument(
        "--output-dir",
        default="outputs/skills_security_matrix",
        help="Base output directory. A timestamped run directory will be created within it.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Analyze only the first N skills.")
    parser.add_argument("--format", default="json,csv", help="Comma-separated formats: json,csv")
    parser.add_argument("--case-study-skill", default=None, help="Skill id to highlight in the run summary.")
    parser.add_argument("--fail-on-unknown-matrix", action="store_true", help="Fail if the matrix contains unknown categories.")
    parser.add_argument("--include-hidden", action="store_true", help="Include hidden skill directories.")
    parser.add_argument(
        "--matrix-path",
        default=str(DEFAULT_MATRIX_PATH),
        help="Path to the markdown matrix table file.",
    )
    return parser


def run_analysis(args: argparse.Namespace) -> RunSummary:
    requested_formats = [value.strip() for value in args.format.split(",") if value.strip()]
    matrix_categories = parse_matrix_file(Path(args.matrix_path))
    matrix_by_id = {category.category_id: category for category in matrix_categories}

    skills = discover_skills(Path(args.skills_dir), include_hidden=args.include_hidden, limit=args.limit)
    run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_dir = Path(args.output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    results: list[AnalysisResult] = []
    skill_errors: list[dict[str, str]] = []
    for skill in skills:
        try:
            result = _analyze_skill(skill, matrix_by_id)
        except Exception as exc:  # pragma: no cover - defensive batch isolation
            skill_errors.append({"skill_id": skill.skill_id, "error": str(exc)})
            result = AnalysisResult(
                skill_id=skill.skill_id,
                root_path=str(skill.root_path),
                structure_profile=skill.structure,
                errors=[str(exc)],
            )
        results.append(result)

    summary = RunSummary(
        run_id=run_id,
        output_dir=str(run_dir),
        analyzed_skills=len(results),
        skipped_skills=0,
        errored_skills=len(skill_errors),
        config=RunConfig(
            skills_dir=args.skills_dir,
            output_dir=args.output_dir,
            requested_formats=requested_formats,
            limit=args.limit,
            case_study_skill=args.case_study_skill,
            include_hidden=args.include_hidden,
            fail_on_unknown_matrix=args.fail_on_unknown_matrix,
        ),
        skill_errors=skill_errors,
    )

    if "json" in requested_formats:
        export_json_files(run_dir, results, summary)
    if "csv" in requested_formats:
        export_csv_files(run_dir, results)

    return summary


def _analyze_skill(skill, matrix_by_id):
    declaration_evidence = extract_declaration_evidence(skill)
    implementation_evidence = extract_implementation_evidence(skill)
    declaration_classifications = classify_declaration(declaration_evidence)
    implementation_classifications = classify_implementation(implementation_evidence)
    result = AnalysisResult(
        skill_id=skill.skill_id,
        root_path=str(skill.root_path),
        structure_profile=skill.structure,
        declaration_classifications=declaration_classifications,
        implementation_classifications=implementation_classifications,
    )
    result.skill_level_discrepancy, result.category_discrepancies = compute_discrepancies(result, matrix_by_id)
    result.risk_mappings = build_risk_mappings(result, matrix_by_id)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    summary = run_analysis(args)
    print(f"Run complete: {summary.run_id}")
    print(f"Output directory: {summary.output_dir}")
    print(f"Analyzed skills: {summary.analyzed_skills}")
    print(f"Errored skills: {summary.errored_skills}")
    if summary.config.case_study_skill:
        print(f"Case study requested: {summary.config.case_study_skill}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
