from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analyzer.env import load_environment
from analyzer.skills_security_matrix.cli import _analyze_skill, _build_provider_registry
from analyzer.skills_security_matrix.exporters.csv_exporter import export_csv_files
from analyzer.skills_security_matrix.exporters.json_exporter import export_json_files
from analyzer.skills_security_matrix.matrix_loader import parse_matrix_file
from analyzer.skills_security_matrix.models import RunConfig, RunSummary
from analyzer.skills_security_matrix.skill_discovery import discover_skills
from crawling.skills.skills_sh.download_skills import extract_github_repo


IGNORED_DIR_NAMES = {".claude", ".agents", ".cursor", ".codex", ".opencode", ".git"}


@dataclass(frozen=True, slots=True)
class SkillRecord:
    skill_id: str
    source: str
    source_url: str


@dataclass(frozen=True, slots=True)
class ResolvedSkill:
    skill_dir: Path
    repo: str
    repo_root: Path
    slug: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve skills.sh skill paths from the DB and run the analyzer."
    )
    parser.add_argument("--db", default="crawling/skills/skills_sh/skills.db", help="Path to skills.sh SQLite DB.")
    parser.add_argument("--repos-root", default="skills/skill_sh_test", help="Root directory of downloaded repos.")
    parser.add_argument("--skill-id", default=None, help="Optional target skills.sh skill id, e.g. aahl/skills/mcp-vods.")
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python interpreter used to invoke main.py. Defaults to the current interpreter.",
    )
    parser.add_argument("--output-dir", default="outputs/skills_security_matrix")
    parser.add_argument("--format", default="json,csv")
    parser.add_argument("--case-study-skill", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--include-hidden", action="store_true")
    parser.add_argument("--matrix-path", default="analyzer/security matrix.md")
    parser.add_argument("--fail-on-unknown-matrix", action="store_true")
    parser.add_argument("--llm-review-mode", default="off", choices=["off", "review", "review+fallback"])
    parser.add_argument("--llm-provider", default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-low-confidence-threshold", type=float, default=0.45)
    parser.add_argument("--llm-high-risk-sparse-threshold", type=int, default=1)
    parser.add_argument("--llm-fallback-max-categories", type=int, default=0)
    parser.add_argument("--llm-timeout-seconds", type=int, default=30)
    parser.add_argument("--llm-fail-open", action="store_true")
    parser.add_argument("--llm-fail-closed", action="store_true")
    parser.add_argument("--emit-review-audit", action="store_true")
    parser.add_argument("--goldset-path", default=None)
    return parser


def load_skill_record(db_path: Path, skill_id: str) -> SkillRecord:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT skill_id, source, source_url FROM skills WHERE skill_id = ? LIMIT 1",
            (skill_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ResolutionError(
            "skill_id_not_found",
            f"skill_id not found in DB: {skill_id}",
            skill_id=skill_id,
            repo=None,
            repo_root=None,
            source=None,
            source_url=None,
        )
    return SkillRecord(skill_id=row["skill_id"], source=row["source"], source_url=row["source_url"])


def load_skill_records(db_path: Path, limit: int | None = None) -> list[SkillRecord]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        query = "SELECT skill_id, source, source_url FROM skills ORDER BY id ASC"
        if limit is not None:
            rows = conn.execute(f"{query} LIMIT ?", (limit,)).fetchall()
        else:
            rows = conn.execute(query).fetchall()
    finally:
        conn.close()
    return [SkillRecord(skill_id=row["skill_id"], source=row["source"], source_url=row["source_url"]) for row in rows]


class ResolutionError(RuntimeError):
    def __init__(
        self,
        error_type: str,
        message: str,
        *,
        skill_id: str,
        repo: str | None,
        repo_root: Path | None,
        source: str | None,
        source_url: str | None,
        candidates: list[Path] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.skill_id = skill_id
        self.repo = repo
        self.repo_root = repo_root
        self.source = source
        self.source_url = source_url
        self.candidates = candidates or []


def resolve_skill(record: SkillRecord, repos_root: Path, include_hidden: bool = False) -> ResolvedSkill:
    repo = extract_github_repo(record.source, record.source_url)
    if repo is None:
        raise ResolutionError(
            "repo_unparseable",
            f"Unable to parse repo from source fields for {record.skill_id}",
            skill_id=record.skill_id,
            repo=None,
            repo_root=None,
            source=record.source,
            source_url=record.source_url,
        )

    repo_root = repos_root / repo.replace("/", "__")
    if not repo_root.is_dir():
        raise ResolutionError(
            "repo_not_found",
            f"Local repo directory not found: {repo_root}",
            skill_id=record.skill_id,
            repo=repo,
            repo_root=repo_root,
            source=record.source,
            source_url=record.source_url,
        )

    slug = record.skill_id.rsplit("/", 1)[-1]
    candidates = find_skill_candidates(repo_root, slug, include_hidden=include_hidden)

    if not candidates and _repo_level_skill_matches(record, repo, repo_root):
        candidates = [repo_root]

    if not candidates:
        raise ResolutionError(
            "skill_not_found",
            f"Could not resolve skill path for {record.skill_id}",
            skill_id=record.skill_id,
            repo=repo,
            repo_root=repo_root,
            source=record.source,
            source_url=record.source_url,
        )

    ranked = rank_skill_candidates(candidates, repo_root, slug)
    top_rank = candidate_rank(ranked[0], repo_root, slug)
    tied = [path for path in ranked if candidate_rank(path, repo_root, slug) == top_rank]
    if len(tied) > 1:
        raise ResolutionError(
            "ambiguous_skill_path",
            f"Multiple equally-ranked skill paths found for {record.skill_id}",
            skill_id=record.skill_id,
            repo=repo,
            repo_root=repo_root,
            source=record.source,
            source_url=record.source_url,
            candidates=tied,
        )

    return ResolvedSkill(skill_dir=ranked[0], repo=repo, repo_root=repo_root, slug=slug)


def find_skill_candidates(repo_root: Path, slug: str, include_hidden: bool = False) -> list[Path]:
    candidates: list[Path] = []

    for candidate in [
        repo_root / "skills" / slug,
        repo_root / slug,
    ]:
        if (candidate / "SKILL.md").is_file():
            candidates.append(candidate)

    glob_patterns = [f"**/skills/{slug}/SKILL.md", f"**/{slug}/SKILL.md"]
    for pattern in glob_patterns:
        for skill_md in repo_root.glob(pattern):
            skill_dir = skill_md.parent
            if skill_dir in candidates:
                continue
            if not include_hidden and path_has_ignored_part(skill_dir.relative_to(repo_root)):
                continue
            candidates.append(skill_dir)

    return candidates


def path_has_ignored_part(relative_path: Path) -> bool:
    return any(part in IGNORED_DIR_NAMES for part in relative_path.parts)


def candidate_rank(path: Path, repo_root: Path, slug: str) -> tuple[int, int, int]:
    relative = path.relative_to(repo_root)
    parts = relative.parts
    has_skills_slug = len(parts) >= 2 and parts[-2] == "skills" and parts[-1] == slug
    return (0 if has_skills_slug else 1, len(parts), 0)


def rank_skill_candidates(candidates: list[Path], repo_root: Path, slug: str) -> list[Path]:
    return sorted(candidates, key=lambda path: (candidate_rank(path, repo_root, slug), str(path)))


def _repo_level_skill_matches(record: SkillRecord, repo: str, repo_root: Path) -> bool:
    return record.skill_id.lower() == repo.lower() and (repo_root / "SKILL.md").is_file()


def build_main_command(args: argparse.Namespace, resolved: ResolvedSkill) -> list[str]:
    command = [
        args.python_bin,
        "main.py",
        "--skills-dir",
        str(resolved.skill_dir),
        "--output-dir",
        args.output_dir,
        "--format",
        args.format,
        "--case-study-skill",
        args.case_study_skill or resolved.slug,
        "--matrix-path",
        args.matrix_path,
        "--llm-review-mode",
        args.llm_review_mode,
        "--llm-low-confidence-threshold",
        str(args.llm_low_confidence_threshold),
        "--llm-high-risk-sparse-threshold",
        str(args.llm_high_risk_sparse_threshold),
        "--llm-fallback-max-categories",
        str(args.llm_fallback_max_categories),
        "--llm-timeout-seconds",
        str(args.llm_timeout_seconds),
    ]
    if args.limit is not None:
        command.extend(["--limit", str(args.limit)])
    if args.include_hidden:
        command.append("--include-hidden")
    if args.fail_on_unknown_matrix:
        command.append("--fail-on-unknown-matrix")
    if args.llm_provider:
        command.extend(["--llm-provider", args.llm_provider])
    if args.llm_model:
        command.extend(["--llm-model", args.llm_model])
    if args.llm_fail_open:
        command.append("--llm-fail-open")
    if args.llm_fail_closed:
        command.append("--llm-fail-closed")
    if args.emit_review_audit:
        command.append("--emit-review-audit")
    if args.goldset_path:
        command.extend(["--goldset-path", args.goldset_path])
    return command


def run_batch_analysis(args: argparse.Namespace, records: list[SkillRecord]) -> int:
    load_environment()
    requested_formats = [value.strip() for value in args.format.split(",") if value.strip()]
    matrix_categories = parse_matrix_file(Path(args.matrix_path))
    matrix_by_id = {category.category_id: category for category in matrix_categories}
    provider_registry = _build_provider_registry()
    failure_policy = "fail_closed" if args.llm_fail_closed else "fail_open"
    repos_root = Path(args.repos_root)

    run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_dir = Path(args.output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    results = []
    skill_errors: list[dict[str, str]] = []
    for record in records:
        try:
            resolved = resolve_skill(record, repos_root, include_hidden=args.include_hidden)
            artifact = discover_skills(resolved.skill_dir, include_hidden=args.include_hidden, limit=1)[0]
            artifact.skill_id = record.skill_id
            result = _analyze_skill(artifact, matrix_by_id, args, provider_registry, failure_policy)
        except ResolutionError as exc:
            skill_errors.append(
                {
                    "skill_id": record.skill_id,
                    "error_type": exc.error_type,
                    "error": str(exc),
                    "repo": exc.repo or "",
                    "repo_root": str(exc.repo_root) if exc.repo_root else "",
                }
            )
            continue
        except Exception as exc:  # pragma: no cover - defensive batch isolation
            skill_errors.append({"skill_id": record.skill_id, "error_type": "analysis_error", "error": str(exc)})
            continue
        results.append(result)

    summary = RunSummary(
        run_id=run_id,
        output_dir=str(run_dir),
        analyzed_skills=len(results),
        skipped_skills=len(skill_errors),
        errored_skills=len(skill_errors),
        config=RunConfig(
            skills_dir=args.repos_root,
            output_dir=args.output_dir,
            requested_formats=requested_formats,
            limit=args.limit,
            case_study_skill=args.case_study_skill,
            include_hidden=args.include_hidden,
            fail_on_unknown_matrix=args.fail_on_unknown_matrix,
            llm_review_mode=args.llm_review_mode,
            llm_provider=args.llm_provider,
            llm_model=args.llm_model,
            llm_low_confidence_threshold=args.llm_low_confidence_threshold,
            llm_high_risk_sparse_threshold=args.llm_high_risk_sparse_threshold,
            llm_fallback_max_categories=args.llm_fallback_max_categories,
            llm_timeout_seconds=args.llm_timeout_seconds,
            llm_failure_policy=failure_policy,
            emit_review_audit=args.emit_review_audit,
            goldset_path=args.goldset_path,
        ),
        skill_errors=skill_errors,
    )

    if "json" in requested_formats:
        export_json_files(run_dir, results, summary)
    if "csv" in requested_formats:
        export_csv_files(run_dir, results)

    print(f"Run complete: {summary.run_id}")
    print(f"Output directory: {summary.output_dir}")
    print(f"Analyzed skills: {summary.analyzed_skills}")
    print(f"Errored skills: {summary.errored_skills}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.skill_id is None:
        records = load_skill_records(Path(args.db), limit=args.limit)
        return run_batch_analysis(args, records)

    record = load_skill_record(Path(args.db), args.skill_id)
    try:
        resolved = resolve_skill(record, Path(args.repos_root), include_hidden=args.include_hidden)
    except ResolutionError as exc:
        print_resolution_error(exc)
        return 1

    command = build_main_command(args, resolved)
    print(f"Resolved skill path: {resolved.skill_dir}", flush=True)
    print("Executing command:", subprocess.list2cmdline(command), flush=True)
    completed = subprocess.run(command, check=False)
    return completed.returncode


def print_resolution_error(exc: ResolutionError) -> None:
    print(f"[{exc.error_type}] {exc}")
    print(f"skill_id: {exc.skill_id}")
    print(f"source: {exc.source or ''}")
    print(f"source_url: {exc.source_url or ''}")
    print(f"repo: {exc.repo or ''}")
    print(f"repo_root: {exc.repo_root or ''}")
    if exc.candidates:
        print("candidates:")
        for path in exc.candidates:
            print(f"  - {path}")


if __name__ == "__main__":
    raise SystemExit(main())
