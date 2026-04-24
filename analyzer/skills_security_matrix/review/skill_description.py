from __future__ import annotations

from ..models import SkillArtifact
from ..skill_structure import extract_frontmatter_and_body, parse_frontmatter


def extract_skill_description(skill: SkillArtifact) -> str:
    skill_md = skill.root_path / "SKILL.md"
    if not skill_md.exists():
        return ""
    try:
        text = skill_md.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""
    frontmatter, _body = extract_frontmatter_and_body(text)
    if not frontmatter:
        return ""
    return parse_frontmatter(frontmatter).get("description", "").strip()
