from __future__ import annotations

from pathlib import Path

from .models import SkillArtifact
from .skill_structure import detect_structure


SOURCE_SUFFIXES = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".sh",
    ".bash",
    ".zsh",
    ".rb",
    ".go",
    ".rs",
    ".java",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".md",
}


def discover_skills(skills_dir: Path, include_hidden: bool = False, limit: int | None = None) -> list[SkillArtifact]:
    candidates = sorted(path for path in skills_dir.iterdir() if path.is_dir())
    artifacts: list[SkillArtifact] = []
    for path in candidates:
        if not include_hidden and path.name.startswith("."):
            continue
        file_paths = sorted(file_path for file_path in path.rglob("*") if file_path.is_file())
        source_files = [file_path for file_path in file_paths if file_path.suffix.lower() in SOURCE_SUFFIXES]
        artifacts.append(
            SkillArtifact(
                skill_id=path.name,
                root_path=path,
                structure=detect_structure(path),
                file_paths=file_paths,
                source_files=source_files,
            )
        )
        if limit is not None and len(artifacts) >= limit:
            break
    return artifacts
