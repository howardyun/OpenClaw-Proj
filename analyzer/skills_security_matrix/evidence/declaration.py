from __future__ import annotations

import re
from pathlib import Path

from ..models import EvidenceItem, SkillArtifact
from ..skill_structure import extract_frontmatter_and_body, parse_frontmatter


REFERENCE_PATTERN = re.compile(
    r"`(?P<code>(?:references|docs|assets|templates)/[^`]+)`|\[(?P<label>[^\]]+)\]\((?P<link>[^)]+)\)"
)


def extract_declaration_evidence(skill: SkillArtifact) -> list[EvidenceItem]:
    skill_md = skill.root_path / "SKILL.md"
    skill_root_resolved = skill.root_path.resolve()
    if not skill_md.exists():
        return []
    skill_text = _safe_read_text(skill_md)
    if skill_text is None:
        return []

    frontmatter, body = extract_frontmatter_and_body(skill_text)
    frontmatter_map = parse_frontmatter(frontmatter) if frontmatter else {}
    evidence: list[EvidenceItem] = []

    for key, value in frontmatter_map.items():
        evidence.extend(
            _scan_text_for_declaration(
                text=f"{key}: {value}",
                source_path=skill_md.relative_to(skill.root_path).as_posix(),
                source_kind="skill_md_frontmatter",
                support_reference_mode="direct",
            )
        )
    evidence.extend(
        _scan_text_for_declaration(
            text=body,
            source_path=skill_md.relative_to(skill.root_path).as_posix(),
            source_kind="skill_md_body",
            support_reference_mode="direct",
        )
    )

    referenced_files = _extract_referenced_support_files(skill.root_path, body)
    for support_file in referenced_files:
        support_text = _safe_read_text(support_file)
        if support_text is None:
            continue
        evidence.extend(
            _scan_text_for_declaration(
                text=support_text,
                source_path=support_file.relative_to(skill_root_resolved).as_posix(),
                source_kind="support_file",
                support_reference_mode="referenced_by_skill_md",
            )
        )
    return evidence


def _extract_referenced_support_files(skill_root: Path, body: str) -> list[Path]:
    resolved_root = skill_root.resolve()
    files: set[Path] = set()
    for match in REFERENCE_PATTERN.finditer(body):
        reference = match.group("code") or match.group("link") or ""
        if reference.startswith(("http://", "https://", "#")):
            continue
        candidate = (resolved_root / reference).resolve()
        try:
            candidate.relative_to(resolved_root)
        except ValueError:
            continue
        if candidate.is_file():
            files.add(candidate)
    return sorted(files)


def _scan_text_for_declaration(
    text: str,
    source_path: str,
    source_kind: str,
    support_reference_mode: str,
) -> list[EvidenceItem]:
    lines = text.splitlines() or [text]
    evidence: list[EvidenceItem] = []
    for index, line in enumerate(lines, start=1):
        lowered = line.lower()
        if not line.strip():
            continue
        for category_id, category_name, patterns, confidence, rule_id in DECLARATION_RULES:
            matched_pattern = next((pattern for pattern in patterns if pattern in lowered), None)
            if not matched_pattern:
                continue
            evidence.append(
                EvidenceItem(
                    category_id=category_id,
                    category_name=category_name,
                    source_path=source_path,
                    layer="declaration",
                    evidence_type="text_match",
                    matched_text=line.strip()[:400],
                    line_start=index,
                    line_end=index,
                    confidence=confidence,
                    rule_id=rule_id,
                    source_kind=source_kind,
                    support_reference_mode=support_reference_mode,
                )
            )
    return evidence


def _safe_read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


DECLARATION_RULES = [
    (
        "session_context_access",
        "会话与上下文访问",
        ["history", "context", "conversation", "session", "chat transcript", "attachment"],
        "medium",
        "decl.session.context",
    ),
    (
        "file_knowledge_access",
        "文件与知识库访问",
        ["read file", "knowledge base", "document", "references/", "reference", "docs/", "search files"],
        "medium",
        "decl.file.knowledge",
    ),
    (
        "external_information_access",
        "外部信息访问",
        ["http://", "https://", "api", "web", "browser", "internet", "fetch"],
        "high",
        "decl.external.info",
    ),
    (
        "retrieval_query_execution",
        "检索与查询执行",
        ["search", "query", "grep", "rg ", "find", "list "],
        "medium",
        "decl.retrieval.query",
    ),
    (
        "code_computation_execution",
        "代码与计算执行",
        ["run ", "execute", "script", "bash", "python", "node", "shell"],
        "high",
        "decl.code.execution",
    ),
    (
        "content_generation_file_processing",
        "内容生成与文件处理",
        ["generate", "transform", "format", "summarize", "create content", "template"],
        "medium",
        "decl.content.generation",
    ),
    (
        "draft_suggestion_write",
        "草稿与建议写入",
        ["draft", "suggest", "proposal", "pre-fill", "prefill"],
        "medium",
        "decl.draft.write",
    ),
    (
        "confirmed_single_write",
        "受确认的单次写入",
        ["confirm", "approval", "explicit approval", "after confirmation"],
        "medium",
        "decl.confirmed.write",
    ),
    (
        "automatic_batch_write",
        "自动或批量写入",
        ["batch", "bulk", "auto-apply", "automatically write"],
        "medium",
        "decl.batch.write",
    ),
    (
        "cross_app_identity_proxy",
        "跨应用身份代理",
        ["sign in", "account", "oauth", "connector", "desktop app integration", "authorized identity"],
        "medium",
        "decl.cross.app.proxy",
    ),
    (
        "scheduled_periodic_automation",
        "定时与周期自动化",
        ["cron", "schedule", "every hour", "daily", "periodic", "polling"],
        "medium",
        "decl.scheduled.automation",
    ),
    (
        "conditional_trigger_monitoring_automation",
        "条件触发与监控自动化",
        ["monitor", "watch", "trigger", "alert", "notify when", "on change"],
        "medium",
        "decl.trigger.monitoring",
    ),
]
