from __future__ import annotations

import argparse
import csv
import json
import multiprocessing
import os
import re
import sqlite3
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path
from threading import Event, Lock

try:
    from tqdm.auto import tqdm
except ImportError:  # pragma: no cover - optional UX dependency
    tqdm = None

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analyzer.env import load_environment
from analyzer.skills_security_matrix.cli import (
    _analyze_skill,
    _build_provider_registry,
    analyze_skill_offline,
    apply_llm_review,
    skill_description_for_artifact,
)
from analyzer.skills_security_matrix.exporters.csv_exporter import (
    CLASSIFICATIONS_FIELDNAMES,
    DISCREPANCIES_FIELDNAMES,
    REVIEW_AUDIT_FIELDNAMES,
    RULE_CANDIDATES_FIELDNAMES,
    SKILLS_FIELDNAMES,
    candidate_rows_for_result,
    classification_rows_for_result,
    discrepancy_rows_for_result,
    review_audit_rows_for_result,
    skill_rows,
)
from analyzer.skills_security_matrix.exporters.json_exporter import (
    case_record,
    candidate_record,
    classification_record,
    discrepancy_record,
    review_audit_record,
    risk_mapping_record,
    skill_record,
)
from analyzer.skills_security_matrix.matrix_loader import load_matrix_definition, parse_matrix_file
from analyzer.skills_security_matrix.models import (
    AnalysisResult,
    AtomicEvidenceDecision,
    CategoryClassification,
    CategoryDiscrepancy,
    ControlDecision,
    DomainAdjudication,
    EvidenceItem,
    FinalCategoryDecision,
    ReviewAuditRecord,
    RuleCandidate,
    RunConfig,
    RunSummary,
    SkillArtifact,
    SkillRiskAdjudication,
    SkillStructureProfile,
    dataclass_to_dict,
)
from analyzer.skills_security_matrix.skill_discovery import discover_skills
from crawling.skills.skills_sh.download_skills import extract_github_repo


IGNORED_DIR_NAMES = {".git"}


@dataclass(frozen=True, slots=True)
class SkillRecord:
    skill_id: str
    source: str | None
    source_url: str | None


@dataclass(frozen=True, slots=True)
class ResolvedSkill:
    skill_dir: Path
    repo: str
    repo_root: Path
    slug: str


@dataclass(frozen=True, slots=True)
class AnalysisRecord:
    record: SkillRecord
    resolved: ResolvedSkill | None = None


@dataclass(frozen=True, slots=True)
class RepoSkillIndex:
    repo_root: Path
    include_hidden: bool
    repo_has_skill_md: bool
    candidate_dirs: tuple[Path, ...]
    candidate_dir_set: frozenset[Path]
    candidate_dirs_by_name: dict[str, tuple[Path, ...]]
    candidate_dirs_by_normalized_name: dict[str, tuple[Path, ...]]


class RepoSkillIndexCache:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, bool], RepoSkillIndex] = {}
        self._events: dict[tuple[str, bool], Event] = {}
        self._lock = Lock()

    def get(self, repo_root: Path, include_hidden: bool = False) -> RepoSkillIndex:
        key = (str(repo_root.resolve()), include_hidden)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                return cached

            event = self._events.get(key)
            should_build = event is None
            if should_build:
                event = Event()
                self._events[key] = event

        if should_build:
            try:
                index = build_repo_skill_index(repo_root, include_hidden=include_hidden)
            except Exception:
                with self._lock:
                    event = self._events.pop(key, None)
                    if event is not None:
                        event.set()
                raise

            with self._lock:
                self._cache[key] = index
                event = self._events.pop(key, None)
                if event is not None:
                    event.set()
            return index

        assert event is not None
        event.wait()
        with self._lock:
            cached = self._cache.get(key)
        if cached is None:
            return self.get(repo_root, include_hidden=include_hidden)
        return cached


class BatchResultWriter:
    def __init__(
        self,
        run_dir: Path,
        requested_formats: list[str],
        *,
        emit_category_discrepancies: bool = False,
        emit_risk_mappings: bool = False,
    ) -> None:
        self.run_dir = run_dir
        self.requested_formats = set(requested_formats)
        self.emit_category_discrepancies = emit_category_discrepancies
        self.emit_risk_mappings = emit_risk_mappings
        self.cases_dir = run_dir / "cases"
        self._jsonl_handles: dict[str, object] = {}
        self._csv_handles: list[object] = []
        self._csv_writers: dict[str, csv.DictWriter] = {}

        if "json" in self.requested_formats:
            self.cases_dir.mkdir(parents=True, exist_ok=True)
            for stem in (
                "skills",
                "rule_candidates",
                "classifications",
                "review_audit",
            ):
                path = run_dir / f"{stem}.jsonl"
                self._jsonl_handles[stem] = path.open("w", encoding="utf-8")
            if self.emit_category_discrepancies:
                self._jsonl_handles["discrepancies"] = (run_dir / "discrepancies.jsonl").open("w", encoding="utf-8")
            if self.emit_risk_mappings:
                self._jsonl_handles["risk_mappings"] = (run_dir / "risk_mappings.jsonl").open("w", encoding="utf-8")

        if "csv" in self.requested_formats:
            self._register_csv_writer("skills", SKILLS_FIELDNAMES)
            self._register_csv_writer("classifications", CLASSIFICATIONS_FIELDNAMES)
            self._register_csv_writer("rule_candidates", RULE_CANDIDATES_FIELDNAMES)
            self._register_csv_writer("review_audit", REVIEW_AUDIT_FIELDNAMES)
            if self.emit_category_discrepancies:
                self._register_csv_writer("discrepancies", DISCREPANCIES_FIELDNAMES)

    def _register_csv_writer(self, stem: str, fieldnames: list[str]) -> None:
        handle = (self.run_dir / f"{stem}.csv").open("w", encoding="utf-8", newline="")
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        handle.flush()
        self._csv_handles.append(handle)
        self._csv_writers[stem] = writer

    def write_result(self, result: AnalysisResult) -> None:
        if "json" in self.requested_formats:
            self._append_jsonl("skills", skill_record(result))
            self._append_jsonl("rule_candidates", candidate_record(result))
            self._append_jsonl(
                "classifications",
                classification_record(result, emit_risk_mappings=self.emit_risk_mappings),
            )
            if self.emit_category_discrepancies:
                self._append_jsonl("discrepancies", discrepancy_record(result))
            if self.emit_risk_mappings:
                self._append_jsonl("risk_mappings", risk_mapping_record(result))
            self._append_jsonl("review_audit", review_audit_record(result))
            (self.cases_dir / f"{_safe_filename(result.skill_id)}.json").write_text(
                json.dumps(
                    case_record(
                        result,
                        emit_category_discrepancies=self.emit_category_discrepancies,
                        emit_risk_mappings=self.emit_risk_mappings,
                    ),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        if "csv" in self.requested_formats:
            self._csv_writers["skills"].writerows(skill_rows(result))
            self._csv_writers["classifications"].writerows(classification_rows_for_result(result))
            self._csv_writers["rule_candidates"].writerows(candidate_rows_for_result(result))
            if self.emit_category_discrepancies:
                self._csv_writers["discrepancies"].writerows(discrepancy_rows_for_result(result))
            self._csv_writers["review_audit"].writerows(review_audit_rows_for_result(result))
            for handle in self._csv_handles:
                handle.flush()

    def _append_jsonl(self, stem: str, payload: dict[str, object]) -> None:
        handle = self._jsonl_handles[stem]
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")
        handle.flush()

    def close(self) -> None:
        for handle in self._jsonl_handles.values():
            handle.close()
        for handle in self._csv_handles:
            handle.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve skill paths from a skills.sh/all_skills SQLite DB and run the analyzer."
    )
    parser.add_argument(
        "--db",
        default=None,
        help=(
            "Optional path to the skills SQLite DB. Supports the legacy skills table and the "
            "new all_skills(name, repo_url, ...) table. Required only when resolving skills via DB metadata."
        ),
    )
    parser.add_argument("--repos-root", default="skills/skill_sh_test", help="Root directory of downloaded repos.")
    parser.add_argument(
        "--skill-id",
        default=None,
        help=(
            "Optional target identifier. With --db, this is a legacy skills.sh skill_id "
            "(e.g. aahl/skills/mcp-vods), a synthesized all_skills id "
            "(e.g. aahl/skills/mcp-vods), or an all_skills name when unambiguous. "
            "Without --db, this is a local skill slug matched against directories under --repos-root."
        ),
    )
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python interpreter used to invoke main.py. Defaults to the current interpreter.",
    )
    parser.add_argument("--output-dir", default="outputs/skills_security_matrix")
    parser.add_argument("--format", default="json,csv")
    parser.add_argument("--case-study-skill", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--pipeline-stage",
        default="full",
        choices=["full", "prepare", "review"],
        help=(
            "Batch pipeline stage. full preserves the existing end-to-end behavior; "
            "prepare writes offline intermediate results; review consumes them and runs LLM post-processing."
        ),
    )
    parser.add_argument(
        "--intermediate-dir",
        default=None,
        help="Directory for offline intermediate JSONL files. Defaults to <run-dir>/intermediate in prepare/full.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=min(32, (os.cpu_count() or 1) + 4),
        help="Number of concurrent workers used for batch analysis.",
    )
    parser.add_argument(
        "--scan-workers",
        type=int,
        default=None,
        help="Number of concurrent workers used for HDD-bound prepare scanning. Defaults to --workers.",
    )
    parser.add_argument(
        "--llm-workers",
        type=int,
        default=None,
        help="Number of concurrent workers used for review-stage LLM calls. Defaults to --workers.",
    )
    parser.add_argument(
        "--max-buffered-results",
        type=int,
        default=None,
        help=(
            "Maximum number of in-flight plus completed-but-not-yet-written batch results. "
            "Defaults to max(workers * 4, workers)."
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip indexes already present in the relevant intermediate JSONL file.",
    )
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
    parser.add_argument(
        "--skill-timeout-seconds",
        type=int,
        default=180,
        help="Per-skill timeout used only in batch mode.",
    )
    parser.add_argument("--llm-fail-open", action="store_true")
    parser.add_argument("--llm-fail-closed", action="store_true")
    parser.add_argument("--emit-review-audit", action="store_true")
    parser.add_argument("--emit-category-discrepancies", action="store_true")
    parser.add_argument("--emit-risk-mappings", action="store_true")
    parser.add_argument("--goldset-path", default=None)
    return parser


def _sqlite_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _db_table_kind(conn: sqlite3.Connection) -> str:
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "skills" in tables:
        columns = _sqlite_table_columns(conn, "skills")
        if {"skill_id", "source", "source_url"}.issubset(columns):
            return "legacy_skills"
    if "all_skills" in tables:
        columns = _sqlite_table_columns(conn, "all_skills")
        if {"name", "repo_url"}.issubset(columns):
            return "all_skills"
    raise ValueError(
        "Unsupported DB schema. Expected legacy table skills(skill_id, source, source_url) "
        "or new table all_skills(name, repo_url, ...)."
    )


def _record_from_all_skills_row(row: sqlite3.Row) -> SkillRecord:
    name = row["name"]
    repo_url = row["repo_url"]
    repo = extract_github_repo(None, repo_url)
    skill_id = f"{repo}/{name}" if repo else name
    return SkillRecord(skill_id=skill_id, source=repo, source_url=repo_url)


def _all_skills_match(row: sqlite3.Row, target_id: str) -> bool:
    record = _record_from_all_skills_row(row)
    return target_id in {
        record.skill_id,
        row["name"],
        f"{row['repo_url'].rstrip('/')}/{row['name']}" if row["repo_url"] else "",
    }


def load_skill_record(db_path: Path, skill_id: str) -> SkillRecord:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        table_kind = _db_table_kind(conn)
        if table_kind == "legacy_skills":
            row = conn.execute(
                "SELECT skill_id, source, source_url FROM skills WHERE skill_id = ? LIMIT 1",
                (skill_id,),
            ).fetchone()
            if row is not None:
                return SkillRecord(skill_id=row["skill_id"], source=row["source"], source_url=row["source_url"])

        else:
            rows = conn.execute(
                """
                SELECT rowid, name, repo_url
                FROM all_skills
                WHERE name = ?
                   OR (? LIKE '%' || '/' || name AND repo_url IS NOT NULL AND repo_url != '')
                   OR (repo_url IS NOT NULL AND repo_url != '' AND repo_url || '/' || name = ?)
                ORDER BY rowid ASC
                """,
                (skill_id, skill_id, skill_id),
            ).fetchall()
            matches = [row for row in rows if _all_skills_match(row, skill_id)]
            if len(matches) == 1:
                return _record_from_all_skills_row(matches[0])
            if len(matches) > 1:
                candidates = [_record_from_all_skills_row(row).skill_id for row in matches[:10]]
                raise ResolutionError(
                    "skill_ambiguous",
                    f"Multiple DB rows matched skill identifier: {skill_id}. "
                    f"Use a synthesized id such as one of: {', '.join(candidates)}",
                    skill_id=skill_id,
                    repo=None,
                    repo_root=None,
                    source=None,
                    source_url=None,
                )
            row = None
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


def load_skill_records(db_path: Path, limit: int | None = None) -> list[SkillRecord]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        table_kind = _db_table_kind(conn)
        if table_kind == "legacy_skills":
            query = "SELECT skill_id, source, source_url FROM skills ORDER BY id ASC"
            if limit is not None:
                rows = conn.execute(f"{query} LIMIT ?", (limit,)).fetchall()
            else:
                rows = conn.execute(query).fetchall()
            return [SkillRecord(skill_id=row["skill_id"], source=row["source"], source_url=row["source_url"]) for row in rows]

        query = """
            SELECT rowid, name, repo_url
            FROM all_skills
            WHERE name IS NOT NULL
              AND name != ''
              AND repo_url IS NOT NULL
              AND repo_url != ''
            ORDER BY rowid ASC
        """
        if limit is not None:
            rows = conn.execute(f"{query} LIMIT ?", (limit,)).fetchall()
        else:
            rows = conn.execute(query).fetchall()
        return [_record_from_all_skills_row(row) for row in rows]
    finally:
        conn.close()


def _iter_local_skill_dirs(repos_root: Path, include_hidden: bool = False) -> list[Path]:
    repos_root = repos_root.resolve()
    skill_dirs: list[Path] = []
    seen: set[Path] = set()

    for current_root, dir_names, file_names in os.walk(repos_root, topdown=True):
        if not include_hidden:
            dir_names[:] = [name for name in dir_names if name not in IGNORED_DIR_NAMES and not name.startswith(".")]
        else:
            dir_names[:] = [name for name in dir_names if name not in IGNORED_DIR_NAMES]

        if "SKILL.md" not in file_names:
            continue

        skill_dir = Path(current_root).resolve()
        if skill_dir in seen:
            continue
        skill_dirs.append(skill_dir)
        seen.add(skill_dir)

    return sorted(skill_dirs)


def _local_skill_id(skill_dir: Path, repos_root: Path) -> str:
    return skill_dir.resolve().relative_to(repos_root.resolve()).as_posix()


def _infer_local_repo_root(skill_dir: Path, repos_root: Path) -> Path:
    skill_dir = skill_dir.resolve()
    repos_root = repos_root.resolve()
    repo_root = skill_dir
    while repo_root.parent != repos_root and repo_root != repos_root:
        repo_root = repo_root.parent
    return repo_root


def scan_local_skill_records(repos_root: Path, include_hidden: bool = False) -> list[SkillRecord]:
    return [
        SkillRecord(
            skill_id=_local_skill_id(skill_dir, repos_root),
            source=None,
            source_url=None,
        )
        for skill_dir in _iter_local_skill_dirs(repos_root, include_hidden=include_hidden)
    ]


def resolve_local_skill_by_slug(skill_slug: str, repos_root: Path, include_hidden: bool = False) -> ResolvedSkill:
    normalized_slug = normalize_skill_dir_name(skill_slug)
    candidates = [
        skill_dir
        for skill_dir in _iter_local_skill_dirs(repos_root, include_hidden=include_hidden)
        if normalize_skill_dir_name(skill_dir.name) == normalized_slug
    ]

    if not candidates:
        raise ResolutionError(
            "skill_not_found",
            f"Could not resolve local skill path for slug: {skill_slug}",
            skill_id=skill_slug,
            repo=None,
            repo_root=repos_root,
            source=None,
            source_url=None,
        )

    if len(candidates) > 1:
        raise ResolutionError(
            "skill_ambiguous",
            f"Multiple local skill directories matched slug: {skill_slug}",
            skill_id=skill_slug,
            repo=None,
            repo_root=repos_root,
            source=None,
            source_url=None,
            candidates=candidates,
        )

    skill_dir = candidates[0]
    return ResolvedSkill(
        skill_dir=skill_dir,
        repo="",
        repo_root=_infer_local_repo_root(skill_dir, repos_root),
        slug=normalized_slug,
    )


def resolve_local_skill(record: SkillRecord, repos_root: Path, include_hidden: bool = False) -> ResolvedSkill:
    skill_dir = (repos_root / record.skill_id).resolve()
    if not (skill_dir / "SKILL.md").is_file():
        raise ResolutionError(
            "skill_not_found",
            f"Could not resolve local skill path for {record.skill_id}",
            skill_id=record.skill_id,
            repo=None,
            repo_root=repos_root,
            source=None,
            source_url=None,
        )

    return ResolvedSkill(
        skill_dir=skill_dir,
        repo="",
        repo_root=_infer_local_repo_root(skill_dir, repos_root),
        slug=normalize_skill_dir_name(skill_dir.name),
    )


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


def resolve_skill(
    record: SkillRecord,
    repos_root: Path,
    include_hidden: bool = False,
    repo_index_cache: RepoSkillIndexCache | None = None,
) -> ResolvedSkill:
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

    repo_root = (repos_root / repo.replace("/", "__")).resolve()
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

    return resolve_skill_in_repo(
        record,
        repo,
        repo_root,
        include_hidden=include_hidden,
        repo_index_cache=repo_index_cache,
    )


def resolve_skill_in_repo(
    record: SkillRecord,
    repo: str,
    repo_root: Path,
    include_hidden: bool = False,
    repo_index: RepoSkillIndex | None = None,
    repo_index_cache: RepoSkillIndexCache | None = None,
) -> ResolvedSkill:
    slug_variants = build_skill_slug_variants(record, repo)
    direct_candidate = find_direct_skill_candidate(repo_root, slug_variants, include_hidden=include_hidden)
    if direct_candidate is not None:
        return ResolvedSkill(
            skill_dir=direct_candidate,
            repo=repo,
            repo_root=repo_root,
            slug=slug_variants[0],
        )

    resolved_repo_index = repo_index or (
        repo_index_cache.get(repo_root, include_hidden=include_hidden)
        if repo_index_cache is not None
        else build_repo_skill_index(repo_root, include_hidden=include_hidden)
    )
    candidates = find_skill_candidates(resolved_repo_index, slug_variants)
    slug = slug_variants[0]

    if not candidates and _repo_level_skill_matches(
        record,
        repo,
        repo_root,
        repo_has_skill_md=resolved_repo_index.repo_has_skill_md,
    ):
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
    return ResolvedSkill(skill_dir=ranked[0], repo=repo, repo_root=repo_root, slug=slug)


def slugify_skill_name(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def normalize_skill_dir_name(value: str) -> str:
    return re.sub(r"[-_]+", "-", re.sub(r"\s+", "-", value.strip().lower())).strip("-")


def build_skill_slug_variants(record: SkillRecord, repo: str) -> list[str]:
    raw_tail = record.skill_id.rsplit("/", 1)[-1].strip()
    source_parts = [slugify_skill_name(part) for part in repo.split("/") if part]
    variants: list[str] = []

    def add_variant(value: str, *, slugify: bool = True) -> None:
        normalized = slugify_skill_name(value) if slugify else value.strip()
        if normalized and normalized not in variants:
            variants.append(normalized)

    add_variant(raw_tail)

    if " " in raw_tail:
        add_variant(raw_tail.replace(" ", "-"), slugify=False)
        add_variant(raw_tail.replace(" ", "_"), slugify=False)
        add_variant(raw_tail.lower().replace(" ", "-"), slugify=False)
        add_variant(raw_tail.lower().replace(" ", "_"), slugify=False)

    for prefix in source_parts:
        if variants and variants[0].startswith(f"{prefix}-"):
            add_variant(variants[0][len(prefix) + 1 :])

    if len(source_parts) >= 2 and variants:
        combined_prefix = "-".join(source_parts)
        if variants[0].startswith(f"{combined_prefix}-"):
            add_variant(variants[0][len(combined_prefix) + 1 :])

    return variants


def build_repo_skill_index(repo_root: Path, include_hidden: bool = False) -> RepoSkillIndex:
    repo_root = repo_root.resolve()
    repo_has_skill_md = (repo_root / "SKILL.md").is_file()
    candidate_dirs: list[Path] = []
    candidate_dir_set: set[Path] = set()
    candidate_dirs_by_name: dict[str, list[Path]] = defaultdict(list)
    candidate_dirs_by_normalized_name: dict[str, list[Path]] = defaultdict(list)

    for current_root, dir_names, file_names in os.walk(repo_root, topdown=True):
        if not include_hidden:
            dir_names[:] = [name for name in dir_names if name not in IGNORED_DIR_NAMES]

        if "SKILL.md" not in file_names:
            continue

        skill_dir = Path(current_root)
        if skill_dir == repo_root:
            continue

        relative_path = skill_dir.relative_to(repo_root)
        if not include_hidden and path_has_ignored_part(relative_path):
            continue
        if skill_dir in candidate_dir_set:
            continue

        candidate_dirs.append(skill_dir)
        candidate_dir_set.add(skill_dir)
        candidate_dirs_by_name[skill_dir.name].append(skill_dir)
        candidate_dirs_by_normalized_name[normalize_skill_dir_name(skill_dir.name)].append(skill_dir)

    return RepoSkillIndex(
        repo_root=repo_root,
        include_hidden=include_hidden,
        repo_has_skill_md=repo_has_skill_md,
        candidate_dirs=tuple(candidate_dirs),
        candidate_dir_set=frozenset(candidate_dir_set),
        candidate_dirs_by_name={name: tuple(paths) for name, paths in candidate_dirs_by_name.items()},
        candidate_dirs_by_normalized_name={
            name: tuple(paths) for name, paths in candidate_dirs_by_normalized_name.items()
        },
    )


def find_direct_skill_candidate(repo_root: Path, slugs: list[str], include_hidden: bool = False) -> Path | None:
    for slug in slugs:
        for candidate in (repo_root / "skills" / slug, repo_root / slug):
            if not include_hidden and path_has_ignored_part(candidate.relative_to(repo_root)):
                continue
            if (candidate / "SKILL.md").is_file():
                return candidate
    return None


def find_skill_candidates(repo_index: RepoSkillIndex, slugs: list[str]) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()

    def add_candidate(candidate: Path) -> None:
        if candidate in repo_index.candidate_dir_set and candidate not in seen:
            candidates.append(candidate)
            seen.add(candidate)

    for slug in slugs:
        add_candidate(repo_index.repo_root / "skills" / slug)
        add_candidate(repo_index.repo_root / slug)
        for candidate in repo_index.candidate_dirs_by_name.get(slug, ()):
            add_candidate(candidate)
        for candidate in repo_index.candidate_dirs_by_normalized_name.get(normalize_skill_dir_name(slug), ()):
            add_candidate(candidate)

    return candidates


def path_has_ignored_part(relative_path: Path) -> bool:
    return any(part in IGNORED_DIR_NAMES for part in relative_path.parts)


def _safe_filename(value: str) -> str:
    return value.replace("/", "__")


def _jsonl_path(intermediate_dir: Path, stem: str) -> Path:
    return intermediate_dir / f"{stem}.jsonl"


def _create_run_dir(output_dir: Path) -> tuple[str, Path]:
    base_run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    for suffix in range(1000):
        run_id = base_run_id if suffix == 0 else f"{base_run_id}-{suffix:03d}"
        run_dir = output_dir / run_id
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            return run_id, run_dir
        except FileExistsError:
            continue
    raise RuntimeError(f"Unable to create unique run directory under {output_dir}")


def _append_jsonl_record(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")
        handle.flush()


def _iter_jsonl_records(path: Path) -> list[dict[str, object]]:
    return list(_iter_jsonl_record_stream(path))


def _iter_jsonl_record_stream(path: Path):
    if not path.is_file():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _completed_indexes(path: Path) -> set[int]:
    completed: set[int] = set()
    for row in _iter_jsonl_records(path):
        index = row.get("index")
        if isinstance(index, int):
            completed.add(index)
    return completed


def _record_payload(record: SkillRecord) -> dict[str, object]:
    return dataclass_to_dict(record)


def _resolved_payload(resolved: ResolvedSkill | None) -> dict[str, object] | None:
    if resolved is None:
        return None
    return {
        "skill_dir": str(resolved.skill_dir),
        "repo": resolved.repo,
        "repo_root": str(resolved.repo_root),
        "slug": resolved.slug,
    }


def _hydrate_dataclass(cls, payload: dict[str, object]):
    if payload is None:
        return None
    field_names = {field.name for field in fields(cls)}
    return cls(**{name: payload[name] for name in field_names if name in payload})


def _hydrate_evidence_items(items: list[dict[str, object]]) -> list[EvidenceItem]:
    return [_hydrate_dataclass(EvidenceItem, item) for item in items]


def _hydrate_atomic_decisions(items: list[dict[str, object]]) -> list[AtomicEvidenceDecision]:
    decisions: list[AtomicEvidenceDecision] = []
    for item in items:
        payload = dict(item)
        payload["supporting_evidence"] = _hydrate_evidence_items(payload.get("supporting_evidence", []))
        payload["conflicting_evidence"] = _hydrate_evidence_items(payload.get("conflicting_evidence", []))
        decisions.append(_hydrate_dataclass(AtomicEvidenceDecision, payload))
    return decisions


def _hydrate_control_decisions(items: list[dict[str, object]]) -> list[ControlDecision]:
    decisions: list[ControlDecision] = []
    for item in items:
        payload = dict(item)
        payload["evidence"] = _hydrate_evidence_items(payload.get("evidence", []))
        decisions.append(_hydrate_dataclass(ControlDecision, payload))
    return decisions


def _hydrate_rule_candidates(items: list[dict[str, object]]) -> list[RuleCandidate]:
    candidates: list[RuleCandidate] = []
    for item in items:
        payload = dict(item)
        payload["supporting_evidence"] = _hydrate_evidence_items(payload.get("supporting_evidence", []))
        payload["conflicting_evidence"] = _hydrate_evidence_items(payload.get("conflicting_evidence", []))
        candidates.append(_hydrate_dataclass(RuleCandidate, payload))
    return candidates


def _hydrate_final_decisions(items: list[dict[str, object]]) -> list[FinalCategoryDecision]:
    decisions: list[FinalCategoryDecision] = []
    for item in items:
        payload = dict(item)
        payload["supporting_evidence"] = _hydrate_evidence_items(payload.get("supporting_evidence", []))
        payload["conflicting_evidence"] = _hydrate_evidence_items(payload.get("conflicting_evidence", []))
        decisions.append(_hydrate_dataclass(FinalCategoryDecision, payload))
    return decisions


def _hydrate_classifications(items: list[dict[str, object]]) -> list[CategoryClassification]:
    classifications: list[CategoryClassification] = []
    for item in items:
        payload = dict(item)
        payload["evidence"] = _hydrate_evidence_items(payload.get("evidence", []))
        classifications.append(_hydrate_dataclass(CategoryClassification, payload))
    return classifications


def _hydrate_analysis_result(payload: dict[str, object]) -> AnalysisResult:
    hydrated = dict(payload)
    hydrated["structure_profile"] = _hydrate_dataclass(SkillStructureProfile, hydrated["structure_profile"])
    hydrated["declaration_atomic_decisions"] = _hydrate_atomic_decisions(
        hydrated.get("declaration_atomic_decisions", [])
    )
    hydrated["implementation_atomic_decisions"] = _hydrate_atomic_decisions(
        hydrated.get("implementation_atomic_decisions", [])
    )
    hydrated["declaration_control_decisions"] = _hydrate_control_decisions(
        hydrated.get("declaration_control_decisions", [])
    )
    hydrated["implementation_control_decisions"] = _hydrate_control_decisions(
        hydrated.get("implementation_control_decisions", [])
    )
    hydrated["rule_candidates"] = _hydrate_rule_candidates(hydrated.get("rule_candidates", []))
    hydrated["final_decisions"] = _hydrate_final_decisions(hydrated.get("final_decisions", []))
    hydrated["declaration_classifications"] = _hydrate_classifications(
        hydrated.get("declaration_classifications", [])
    )
    hydrated["implementation_classifications"] = _hydrate_classifications(
        hydrated.get("implementation_classifications", [])
    )
    hydrated["category_discrepancies"] = [
        _hydrate_dataclass(CategoryDiscrepancy, item) for item in hydrated.get("category_discrepancies", [])
    ]
    hydrated["domain_adjudication"] = _hydrate_dataclass(DomainAdjudication, hydrated.get("domain_adjudication"))
    hydrated["skill_risk_adjudication"] = _hydrate_dataclass(
        SkillRiskAdjudication,
        hydrated.get("skill_risk_adjudication"),
    )
    hydrated["review_audit_records"] = [
        _hydrate_dataclass(ReviewAuditRecord, item) for item in hydrated.get("review_audit_records", [])
    ]
    field_names = {field.name for field in fields(AnalysisResult)}
    return AnalysisResult(**{name: hydrated[name] for name in field_names if name in hydrated})


def intermediate_success_payload(
    index: int,
    record: SkillRecord,
    resolved: ResolvedSkill | None,
    result: AnalysisResult,
    skill_description: str,
) -> dict[str, object]:
    return {
        "schema_version": "skills-security-matrix-offline-result-v1",
        "index": index,
        "record": _record_payload(record),
        "resolved": _resolved_payload(resolved),
        "skill_context": {"description": skill_description},
        "analysis_result": dataclass_to_dict(result),
    }


def candidate_rank(path: Path, repo_root: Path, slug: str) -> tuple[int, int, int]:
    relative = path.relative_to(repo_root)
    parts = relative.parts
    has_skills_slug = len(parts) >= 2 and parts[-2] == "skills" and parts[-1] == slug
    return (0 if has_skills_slug else 1, len(parts), 0)


def rank_skill_candidates(candidates: list[Path], repo_root: Path, slug: str) -> list[Path]:
    return sorted(candidates, key=lambda path: (candidate_rank(path, repo_root, slug), str(path)))


def _repo_level_skill_matches(
    record: SkillRecord,
    repo: str,
    repo_root: Path,
    *,
    repo_has_skill_md: bool | None = None,
) -> bool:
    if repo_has_skill_md is None:
        repo_has_skill_md = (repo_root / "SKILL.md").is_file()
    return record.skill_id.lower() == repo.lower() and repo_has_skill_md


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
    if args.emit_category_discrepancies:
        command.append("--emit-category-discrepancies")
    if args.emit_risk_mappings:
        command.append("--emit-risk-mappings")
    if args.goldset_path:
        command.extend(["--goldset-path", args.goldset_path])
    return command


def _error_payload(
    record: SkillRecord,
    *,
    error_type: str,
    error: str,
    repo: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, str]:
    resolved_repo = repo
    if resolved_repo is None and record.source and record.source_url:
        resolved_repo = extract_github_repo(record.source, record.source_url)
    return {
        "skill_id": record.skill_id,
        "error_type": error_type,
        "error": error,
        "repo": resolved_repo or "",
        "repo_root": str(repo_root) if repo_root else "",
    }


def _repo_root_for_record(record: SkillRecord, repos_root: Path) -> Path | None:
    if record.source and record.source_url:
        repo = extract_github_repo(record.source, record.source_url)
        if repo is not None:
            return repos_root / repo.replace("/", "__")
    skill_dir = repos_root / record.skill_id
    return _infer_local_repo_root(skill_dir, repos_root) if skill_dir.exists() else None


def pre_resolve_db_records(
    records: list[SkillRecord],
    repos_root: Path,
    include_hidden: bool = False,
) -> tuple[dict[int, AnalysisRecord], dict[int, tuple[str, dict[str, str]]]]:
    grouped_records: dict[tuple[str, Path], list[tuple[int, SkillRecord]]] = defaultdict(list)
    resolved_records: dict[int, AnalysisRecord] = {}
    errors: dict[int, tuple[str, dict[str, str]]] = {}

    for index, record in enumerate(records):
        repo = extract_github_repo(record.source, record.source_url)
        if repo is None:
            errors[index] = (
                "error",
                _error_payload(
                    record,
                    error_type="repo_unparseable",
                    error=f"Unable to parse repo from source fields for {record.skill_id}",
                    repo=None,
                    repo_root=None,
                ),
            )
            continue

        repo_root = (repos_root / repo.replace("/", "__")).resolve()
        if not repo_root.is_dir():
            errors[index] = (
                "error",
                _error_payload(
                    record,
                    error_type="repo_not_found",
                    error=f"Local repo directory not found: {repo_root}",
                    repo=repo,
                    repo_root=repo_root,
                ),
            )
            continue

        grouped_records[(repo, repo_root)].append((index, record))

    for (repo, repo_root), grouped in grouped_records.items():
        repo_index: RepoSkillIndex | None = None
        for index, record in grouped:
            try:
                slug_variants = build_skill_slug_variants(record, repo)
                direct_candidate = find_direct_skill_candidate(
                    repo_root,
                    slug_variants,
                    include_hidden=include_hidden,
                )
                if direct_candidate is not None:
                    resolved_records[index] = AnalysisRecord(
                        record=record,
                        resolved=ResolvedSkill(
                            skill_dir=direct_candidate,
                            repo=repo,
                            repo_root=repo_root,
                            slug=slug_variants[0],
                        ),
                    )
                    continue

                if repo_index is None:
                    repo_index = build_repo_skill_index(repo_root, include_hidden=include_hidden)
                resolved_records[index] = AnalysisRecord(
                    record=record,
                    resolved=resolve_skill_in_repo(
                        record,
                        repo,
                        repo_root,
                        include_hidden=include_hidden,
                        repo_index=repo_index,
                    ),
                )
            except ResolutionError as exc:
                errors[index] = (
                    "error",
                    _error_payload(
                        record,
                        error_type=exc.error_type,
                        error=str(exc),
                        repo=exc.repo,
                        repo_root=exc.repo_root,
                    ),
                )

    return resolved_records, errors


def _analyze_record_impl(
    record: SkillRecord,
    repos_root: Path,
    matrix_by_id,
    args: argparse.Namespace,
    provider_registry,
    failure_policy: str,
    repo_index_cache: RepoSkillIndexCache,
    resolved: ResolvedSkill | None = None,
    *,
    offline_only: bool = False,
):
    if resolved is None and args.db:
        resolved = resolve_skill(
            record,
            repos_root,
            include_hidden=args.include_hidden,
            repo_index_cache=repo_index_cache,
        )
    elif resolved is None:
        resolved = resolve_local_skill(record, repos_root, include_hidden=args.include_hidden)
    artifact = discover_skills(resolved.skill_dir, include_hidden=args.include_hidden, limit=1)[0]
    artifact.skill_id = record.skill_id
    matrix_definition = load_matrix_definition(Path(args.matrix_path))
    if offline_only:
        return (
            analyze_skill_offline(artifact, matrix_definition, matrix_by_id, args),
            skill_description_for_artifact(artifact),
            resolved,
        )
    return _analyze_skill(artifact, matrix_definition, matrix_by_id, args, provider_registry, failure_policy)


def _analyze_record_child(
    conn,
    record: SkillRecord,
    repos_root: Path,
    matrix_by_id,
    args: argparse.Namespace,
    failure_policy: str,
    resolved: ResolvedSkill | None = None,
    offline_only: bool = False,
) -> None:
    try:
        load_environment()
        provider_registry = _build_provider_registry()
        result = _analyze_record_impl(
            record,
            repos_root,
            matrix_by_id,
            args,
            provider_registry,
            failure_policy,
            RepoSkillIndexCache(),
            resolved,
            offline_only=offline_only,
        )
        if offline_only:
            result, skill_description, resolved_skill = result
            conn.send(("offline_result", result, skill_description, resolved_skill))
        else:
            conn.send(("result", result))
    except ResolutionError as exc:
        conn.send(
            (
                "error",
                _error_payload(
                    record,
                    error_type=exc.error_type,
                    error=str(exc),
                    repo=exc.repo,
                    repo_root=exc.repo_root,
                ),
            )
        )
    except Exception as exc:  # pragma: no cover - defensive batch isolation
        conn.send(("error", _error_payload(record, error_type="analysis_error", error=str(exc))))
    finally:
        conn.close()


def analyze_record(
    record: SkillRecord,
    repos_root: Path,
    matrix_by_id,
    args: argparse.Namespace,
    failure_policy: str,
    resolved: ResolvedSkill | None = None,
    *,
    offline_only: bool = False,
) -> tuple:
    safe_args = _to_namespace(args)
    skill_timeout_seconds = getattr(args, "skill_timeout_seconds", 600)
    start_method = "fork" if "fork" in multiprocessing.get_all_start_methods() else "spawn"
    context = multiprocessing.get_context(start_method)
    recv_conn, send_conn = context.Pipe(duplex=False)
    process = context.Process(
        target=_analyze_record_child,
        args=(
            send_conn,
            record,
            repos_root,
            matrix_by_id,
            safe_args,
            failure_policy,
            resolved,
            offline_only,
        ),
    )
    process.start()
    send_conn.close()

    try:
        deadline = skill_timeout_seconds
        while deadline > 0:
            if recv_conn.poll(min(0.5, deadline)):
                outcome = recv_conn.recv()
                process.join(timeout=1)
                return outcome
            if not process.is_alive():
                process.join(timeout=1)
                return (
                    "error",
                    _error_payload(
                        record,
                        error_type="analysis_error",
                        error=f"analysis subprocess exited unexpectedly with code {process.exitcode}",
                        repo_root=_repo_root_for_record(record, repos_root),
                    ),
                )
            deadline -= 0.5

        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join(timeout=5)
        return (
            "error",
            _error_payload(
                record,
                error_type="skill_timeout",
                error=f"skill exceeded {skill_timeout_seconds} seconds",
                repo_root=_repo_root_for_record(record, repos_root),
            ),
        )
    finally:
        recv_conn.close()
        if process.is_alive():
            process.kill()
            process.join(timeout=1)


def _to_namespace(args: argparse.Namespace) -> argparse.Namespace:
    values = {key: getattr(args, key) for key in dir(args) if not key.startswith("_") and not callable(getattr(args, key))}
    return argparse.Namespace(**values)


def review_intermediate_record(
    row: dict[str, object],
    matrix_definition,
    matrix_by_id,
    args: argparse.Namespace,
    provider_registry,
    failure_policy: str,
) -> AnalysisResult:
    result = _hydrate_analysis_result(row["analysis_result"])
    skill_context = row.get("skill_context") or {}
    description = skill_context.get("description", "") if isinstance(skill_context, dict) else ""
    skill = SkillArtifact(
        skill_id=result.skill_id,
        root_path=Path(result.root_path),
        structure=result.structure_profile,
        file_paths=[],
        source_files=[],
    )
    return apply_llm_review(
        result,
        skill,
        matrix_definition,
        matrix_by_id,
        args,
        provider_registry,
        failure_policy,
        skill_description=str(description or ""),
    )


def run_prepare_stage(args: argparse.Namespace, records: list[SkillRecord]) -> int:
    scan_workers_arg = getattr(args, "scan_workers", None)
    scan_workers = scan_workers_arg if scan_workers_arg is not None else args.workers
    if scan_workers < 1:
        print("[error] --scan-workers must be >= 1", file=sys.stderr)
        return 2
    skill_timeout_seconds = getattr(args, "skill_timeout_seconds", 600)
    if skill_timeout_seconds < 1:
        print("[error] --skill-timeout-seconds must be >= 1", file=sys.stderr)
        return 2

    matrix_categories = parse_matrix_file(Path(args.matrix_path))
    matrix_by_id = {category.category_id: category for category in matrix_categories}
    failure_policy = "fail_closed" if args.llm_fail_closed else "fail_open"
    repos_root = Path(args.repos_root)
    run_id, run_dir = _create_run_dir(Path(args.output_dir))
    intermediate_dir_arg = getattr(args, "intermediate_dir", None)
    intermediate_dir = Path(intermediate_dir_arg) if intermediate_dir_arg else run_dir / "intermediate"
    intermediate_dir.mkdir(parents=True, exist_ok=True)
    offline_results_path = _jsonl_path(intermediate_dir, "offline_results")
    offline_errors_path = _jsonl_path(intermediate_dir, "offline_errors")
    if not getattr(args, "resume", False):
        offline_results_path.write_text("", encoding="utf-8")
        offline_errors_path.write_text("", encoding="utf-8")

    completed = _completed_indexes(offline_results_path) | _completed_indexes(offline_errors_path)
    if args.db:
        analysis_records, pre_resolve_errors = pre_resolve_db_records(
            records,
            repos_root,
            include_hidden=args.include_hidden,
        )
        for index, (_outcome_type, payload) in sorted(pre_resolve_errors.items()):
            if index in completed:
                continue
            _append_jsonl_record(offline_errors_path, {"index": index, **payload})
            completed.add(index)
    else:
        analysis_records = {index: AnalysisRecord(record=record) for index, record in enumerate(records)}

    analysis_indices = [index for index in sorted(analysis_records) if index not in completed]
    progress = None
    if tqdm is not None:
        progress = tqdm(total=len(records), initial=len(completed), desc="Preparing skills", unit="skill")

    def submit_next(executor: ThreadPoolExecutor, in_flight: dict[Future, tuple[int, AnalysisRecord]], cursor: int) -> int:
        index = analysis_indices[cursor]
        analysis_record = analysis_records[index]
        future = executor.submit(
            analyze_record,
            analysis_record.record,
            repos_root,
            matrix_by_id,
            args,
            failure_policy,
            analysis_record.resolved,
            offline_only=True,
        )
        in_flight[future] = (index, analysis_record)
        return cursor + 1

    prepared = len(_completed_indexes(offline_results_path))
    errors = len(_completed_indexes(offline_errors_path))
    next_to_submit = 0
    try:
        with ThreadPoolExecutor(max_workers=scan_workers) as executor:
            in_flight: dict[Future, tuple[int, AnalysisRecord]] = {}
            while next_to_submit < len(analysis_indices) and len(in_flight) < scan_workers:
                next_to_submit = submit_next(executor, in_flight, next_to_submit)

            while in_flight:
                done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
                for future in done:
                    index, analysis_record = in_flight.pop(future)
                    try:
                        outcome = future.result()
                    except Exception as exc:  # pragma: no cover - defensive batch isolation
                        outcome = (
                            "error",
                            {
                                "skill_id": analysis_record.record.skill_id,
                                "error_type": "analysis_error",
                                "error": str(exc),
                            },
                        )

                    if outcome[0] == "offline_result":
                        _outcome_type, result, skill_description, resolved = outcome
                        _append_jsonl_record(
                            offline_results_path,
                            intermediate_success_payload(
                                index,
                                analysis_record.record,
                                resolved,
                                result,
                                skill_description,
                            ),
                        )
                        prepared += 1
                    else:
                        _outcome_type, payload = outcome
                        _append_jsonl_record(offline_errors_path, {"index": index, **payload})
                        errors += 1

                if progress is not None:
                    progress.update(len(done))
                    progress.set_postfix_str(f"prepared={prepared} err={errors} inflight={len(in_flight)}")

                while next_to_submit < len(analysis_indices) and len(in_flight) < scan_workers:
                    next_to_submit = submit_next(executor, in_flight, next_to_submit)
    finally:
        if progress is not None:
            progress.close()

    summary = {
        "run_id": run_id,
        "output_dir": str(run_dir),
        "intermediate_dir": str(intermediate_dir),
        "prepared_skills": prepared,
        "errored_skills": errors,
        "pipeline_stage": "prepare",
        "scan_workers": scan_workers,
    }
    (run_dir / "prepare_manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Prepare complete: {run_id}")
    print(f"Intermediate directory: {intermediate_dir}")
    print(f"Prepared skills: {prepared}")
    print(f"Errored skills: {errors}")
    return 0


def run_review_stage(args: argparse.Namespace) -> int:
    intermediate_dir_arg = getattr(args, "intermediate_dir", None)
    if not intermediate_dir_arg:
        print("[error] --intermediate-dir is required for --pipeline-stage review", file=sys.stderr)
        return 2
    llm_workers_arg = getattr(args, "llm_workers", None)
    llm_workers = llm_workers_arg if llm_workers_arg is not None else args.workers
    if llm_workers < 1:
        print("[error] --llm-workers must be >= 1", file=sys.stderr)
        return 2

    load_environment()
    requested_formats = [value.strip() for value in args.format.split(",") if value.strip()]
    matrix_definition = load_matrix_definition(Path(args.matrix_path))
    matrix_by_id = {category.category_id: category for category in matrix_definition.categories}
    provider_registry = _build_provider_registry()
    failure_policy = "fail_closed" if args.llm_fail_closed else "fail_open"
    intermediate_dir = Path(intermediate_dir_arg)
    offline_results_path = _jsonl_path(intermediate_dir, "offline_results")
    offline_errors_path = _jsonl_path(intermediate_dir, "offline_errors")
    reviewed_results_path = _jsonl_path(intermediate_dir, "reviewed_results")
    if not offline_results_path.is_file():
        print(f"[error] offline results not found: {offline_results_path}", file=sys.stderr)
        return 2
    if not getattr(args, "resume", False):
        reviewed_results_path.write_text("", encoding="utf-8")

    reviewed_rows = _completed_indexes(reviewed_results_path)
    skill_errors = [
        {key: str(value) for key, value in row.items() if key != "index"}
        for row in _iter_jsonl_records(offline_errors_path)
    ]
    total_offline_rows = sum(1 for _row in _iter_jsonl_record_stream(offline_results_path))

    run_id, run_dir = _create_run_dir(Path(args.output_dir))
    writer = BatchResultWriter(
        run_dir,
        requested_formats,
        emit_category_discrepancies=args.emit_category_discrepancies,
        emit_risk_mappings=args.emit_risk_mappings,
    )
    written_results = 0

    try:
        for row in _iter_jsonl_record_stream(reviewed_results_path):
            result = _hydrate_analysis_result(row["analysis_result"])
            writer.write_result(result)
            written_results += 1

        progress = None
        if tqdm is not None:
            progress = tqdm(
                total=total_offline_rows,
                initial=written_results,
                desc="Reviewing skills",
                unit="skill",
            )

        def review_row(row: dict[str, object]) -> tuple[int, AnalysisResult]:
            return (
                int(row["index"]),
                review_intermediate_record(
                    row,
                    matrix_definition,
                    matrix_by_id,
                    args,
                    provider_registry,
                    failure_policy,
                ),
            )

        pending_rows = (
            row
            for row in _iter_jsonl_record_stream(offline_results_path)
            if int(row["index"]) not in reviewed_rows
        )

        try:
            with ThreadPoolExecutor(max_workers=llm_workers) as executor:
                future_to_index: dict[Future, int] = {}
                max_in_flight = max(llm_workers * 4, llm_workers)
                pending_exhausted = False

                def submit_until_full() -> None:
                    nonlocal pending_exhausted
                    while not pending_exhausted and len(future_to_index) < max_in_flight:
                        try:
                            row = next(pending_rows)
                        except StopIteration:
                            pending_exhausted = True
                            return
                        future_to_index[executor.submit(review_row, row)] = int(row["index"])

                submit_until_full()
                while future_to_index:
                    done, _ = wait(future_to_index, return_when=FIRST_COMPLETED)
                    for future in done:
                        index = future_to_index.pop(future)
                        try:
                            reviewed_index, result = future.result()
                            row = {
                                "schema_version": "skills-security-matrix-reviewed-result-v1",
                                "index": reviewed_index,
                                "analysis_result": dataclass_to_dict(result),
                            }
                            _append_jsonl_record(reviewed_results_path, row)
                            reviewed_rows.add(reviewed_index)
                            writer.write_result(result)
                            written_results += 1
                        except Exception as exc:  # pragma: no cover - defensive batch isolation
                            skill_errors.append(
                                {
                                    "skill_id": str(index),
                                    "error_type": "review_error",
                                    "error": str(exc),
                                }
                            )
                        if progress is not None:
                            progress.update(1)
                            progress.set_postfix_str(f"reviewed={written_results} err={len(skill_errors)}")
                    submit_until_full()
        finally:
            if progress is not None:
                progress.close()
    finally:
        writer.close()

    summary = RunSummary(
        run_id=run_id,
        output_dir=str(run_dir),
        analyzed_skills=written_results,
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
            skill_timeout_seconds=getattr(args, "skill_timeout_seconds", 600),
            max_buffered_results=args.max_buffered_results,
            llm_failure_policy=failure_policy,
            emit_review_audit=args.emit_review_audit,
            emit_category_discrepancies=args.emit_category_discrepancies,
            emit_risk_mappings=args.emit_risk_mappings,
            goldset_path=args.goldset_path,
        ),
        skill_errors=skill_errors,
    )
    manifest = dataclass_to_dict(summary)
    manifest["pipeline_stage"] = "review"
    manifest["intermediate_dir"] = str(intermediate_dir)
    manifest["llm_workers"] = llm_workers
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Review complete: {run_id}")
    print(f"Output directory: {run_dir}")
    print(f"Analyzed skills: {written_results}")
    print(f"Errored skills: {len(skill_errors)}")
    return 0

def run_batch_analysis(args: argparse.Namespace, records: list[SkillRecord]) -> int:
    pipeline_stage = getattr(args, "pipeline_stage", "full")
    if pipeline_stage == "prepare":
        return run_prepare_stage(args, records)
    if pipeline_stage == "review":
        return run_review_stage(args)

    if args.workers < 1:
        print("[error] --workers must be >= 1", file=sys.stderr)
        return 2
    skill_timeout_seconds = getattr(args, "skill_timeout_seconds", 600)
    if skill_timeout_seconds < 1:
        print("[error] --skill-timeout-seconds must be >= 1", file=sys.stderr)
        return 2
    max_buffered_results = (
        args.max_buffered_results
        if args.max_buffered_results is not None
        else max(args.workers * 4, args.workers)
    )
    if max_buffered_results < args.workers:
        print("[error] --max-buffered-results must be >= --workers", file=sys.stderr)
        return 2

    load_environment()
    requested_formats = [value.strip() for value in args.format.split(",") if value.strip()]
    matrix_categories = parse_matrix_file(Path(args.matrix_path))
    matrix_by_id = {category.category_id: category for category in matrix_categories}
    failure_policy = "fail_closed" if args.llm_fail_closed else "fail_open"
    repos_root = Path(args.repos_root)
    run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_dir = Path(args.output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    writer = BatchResultWriter(
        run_dir,
        requested_formats,
        emit_category_discrepancies=args.emit_category_discrepancies,
        emit_risk_mappings=args.emit_risk_mappings,
    )

    skill_errors: list[dict[str, str]] = []
    written_results = 0
    next_item_to_submit = 0
    if args.db:
        analysis_records, pre_resolve_errors = pre_resolve_db_records(
            records,
            repos_root,
            include_hidden=args.include_hidden,
        )
        skill_errors.extend(payload for _outcome_type, payload in pre_resolve_errors.values())
    else:
        analysis_records = {
            index: AnalysisRecord(record=record)
            for index, record in enumerate(records)
        }
    analysis_indices = sorted(analysis_records)
    progress = None
    if tqdm is not None:
        progress = tqdm(total=len(records), desc="Analyzing skills", unit="skill")
        if skill_errors:
            progress.update(len(skill_errors))

    def submit_next(executor: ThreadPoolExecutor, in_flight: dict[Future, tuple[int, SkillRecord]]) -> None:
        nonlocal next_item_to_submit
        index = analysis_indices[next_item_to_submit]
        analysis_record = analysis_records[index]
        future = executor.submit(
            analyze_record,
            analysis_record.record,
            repos_root,
            matrix_by_id,
            args,
            failure_policy,
            analysis_record.resolved,
        )
        in_flight[future] = (index, analysis_record.record)
        next_item_to_submit += 1

    def handle_outcome(outcome: tuple[str, AnalysisResult | dict[str, str]]) -> None:
        nonlocal written_results
        outcome_type, payload = outcome
        if outcome_type == "result":
            writer.write_result(payload)
            written_results += 1
        else:
            skill_errors.append(payload)

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            in_flight: dict[Future, tuple[int, SkillRecord]] = {}

            while (
                next_item_to_submit < len(analysis_indices)
                and len(in_flight) < args.workers
            ):
                submit_next(executor, in_flight)

            while in_flight:
                completed, _ = wait(in_flight, return_when=FIRST_COMPLETED)

                for future in completed:
                    _index, record = in_flight.pop(future)
                    try:
                        handle_outcome(future.result())
                    except Exception as exc:  # pragma: no cover - defensive batch isolation
                        handle_outcome(
                            (
                                "error",
                                {"skill_id": record.skill_id, "error_type": "analysis_error", "error": str(exc)},
                            )
                        )

                if progress is not None:
                    progress.update(len(completed))
                    progress.set_postfix_str(
                        f"ok={written_results} err={len(skill_errors)} "
                        f"inflight={len(in_flight)}"
                    )

                while (
                    next_item_to_submit < len(analysis_indices)
                    and len(in_flight) < args.workers
                ):
                    submit_next(executor, in_flight)
    finally:
        if progress is not None:
            progress.close()
        writer.close()

    summary = RunSummary(
        run_id=run_id,
        output_dir=str(run_dir),
        analyzed_skills=written_results,
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
            skill_timeout_seconds=skill_timeout_seconds,
            max_buffered_results=max_buffered_results,
            llm_failure_policy=failure_policy,
            emit_review_audit=args.emit_review_audit,
            emit_category_discrepancies=args.emit_category_discrepancies,
            emit_risk_mappings=args.emit_risk_mappings,
            goldset_path=args.goldset_path,
        ),
        skill_errors=skill_errors,
    )

    (run_dir / "run_manifest.json").write_text(
        json.dumps(dataclass_to_dict(summary), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Run complete: {summary.run_id}")
    print(f"Output directory: {summary.output_dir}")
    print(f"Analyzed skills: {summary.analyzed_skills}")
    print(f"Errored skills: {summary.errored_skills}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    repos_root = Path(args.repos_root)

    if args.skill_id is None:
        if args.db:
            records = load_skill_records(Path(args.db), limit=args.limit)
        else:
            records = scan_local_skill_records(repos_root, include_hidden=args.include_hidden)
            if args.limit is not None:
                records = records[: args.limit]
        return run_batch_analysis(args, records)

    try:
        if args.db:
            record = load_skill_record(Path(args.db), args.skill_id)
            resolved = resolve_skill(record, repos_root, include_hidden=args.include_hidden)
        else:
            resolved = resolve_local_skill_by_slug(args.skill_id, repos_root, include_hidden=args.include_hidden)
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
