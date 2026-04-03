from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


IGNORED_DIR_NAMES = {".git"}
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
NAME_LINE_RE = re.compile(r"^name\s*:\s*(.+?)\s*$", re.IGNORECASE)


def normalize_skill_name(value: str) -> str:
    return re.sub(r"[-_]+", "-", re.sub(r"\s+", "-", value.strip().lower())).strip("-")


@dataclass(frozen=True, slots=True)
class SkillCandidate:
    name: str
    relative_path: str
    slug: str


def read_skill_name(skill_dir: Path) -> str:
    skill_file = skill_dir / "SKILL.md"
    try:
        content = skill_file.read_text(encoding="utf-8")
    except OSError:
        return skill_dir.name

    match = FRONTMATTER_RE.match(content)
    if not match:
        return skill_dir.name

    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name_match = NAME_LINE_RE.match(line)
        if not name_match:
            continue
        value = name_match.group(1).strip().strip("'\"")
        return value or skill_dir.name

    return skill_dir.name


def discover_skill_candidates(repo_root: Path, include_hidden: bool = False) -> list[SkillCandidate]:
    repo_root = repo_root.resolve()
    candidates: list[SkillCandidate] = []
    seen_paths: set[Path] = set()

    for current_root, dir_names, file_names in os.walk(repo_root, topdown=True):
        if not include_hidden:
            dir_names[:] = [name for name in dir_names if name not in IGNORED_DIR_NAMES and not name.startswith(".")]
        else:
            dir_names[:] = [name for name in dir_names if name not in IGNORED_DIR_NAMES]

        if "SKILL.md" not in file_names:
            continue

        skill_dir = Path(current_root).resolve()
        if skill_dir in seen_paths:
            continue
        seen_paths.add(skill_dir)

        relative_path = skill_dir.relative_to(repo_root).as_posix()
        skill_name = read_skill_name(skill_dir)
        candidates.append(
            SkillCandidate(
                name=skill_name,
                relative_path=relative_path,
                slug=normalize_skill_name(skill_name),
            )
        )

    return sorted(candidates, key=lambda item: item.relative_path)


def find_skill_matches(skill_name: str, candidates: list[SkillCandidate]) -> list[SkillCandidate]:
    target = normalize_skill_name(skill_name)
    if not target:
        return []
    return [candidate for candidate in candidates if candidate.slug == target]
