from __future__ import annotations

from pathlib import Path

from ..models import EvidenceItem, SkillArtifact


IMPLEMENTATION_RULES = [
    (
        "external_information_access",
        "外部信息访问",
        ["requests.", "urllib", "fetch(", "axios", "curl ", "http://", "https://", "browser", "webfetch"],
        "high",
        "impl.external.info",
    ),
    (
        "file_knowledge_access",
        "文件与知识库访问",
        ["open(", "read_text(", "read_bytes(", "cat ", "rg ", "glob(", "pathlib.path", "knowledge"],
        "medium",
        "impl.file.knowledge",
    ),
    (
        "retrieval_query_execution",
        "检索与查询执行",
        ["search", "query", "select ", "grep", "ripgrep", "list_", "filter("],
        "medium",
        "impl.retrieval.query",
    ),
    (
        "code_computation_execution",
        "代码与计算执行",
        ["subprocess", "exec(", "eval(", "bash", "python ", "node ", "tmux", "docker", "shell"],
        "high",
        "impl.code.execution",
    ),
    (
        "content_generation_file_processing",
        "内容生成与文件处理",
        ["render", "template", "markdown", "generate", "transform", "summar", "format("],
        "medium",
        "impl.content.generation",
    ),
    (
        "draft_suggestion_write",
        "草稿与建议写入",
        ["draft", "suggest", "proposal", "preview", "recommend"],
        "medium",
        "impl.draft.write",
    ),
    (
        "confirmed_single_write",
        "受确认的单次写入",
        ["confirm", "approval", "approved", "are you sure", "single write"],
        "medium",
        "impl.confirmed.write",
    ),
    (
        "automatic_batch_write",
        "自动或批量写入",
        ["write_text(", "write(", "append(", "commit(", "bulk", "batch", "for ", "while "],
        "medium",
        "impl.batch.write",
    ),
    (
        "cross_app_identity_proxy",
        "跨应用身份代理",
        ["oauth", "token", "signin", "account", "credential", "connector", "op://"],
        "medium",
        "impl.cross.app.proxy",
    ),
    (
        "scheduled_periodic_automation",
        "定时与周期自动化",
        ["cron", "schedule", "interval", "every(", "sleep(", "poll", "timer"],
        "medium",
        "impl.scheduled.automation",
    ),
    (
        "conditional_trigger_monitoring_automation",
        "条件触发与监控自动化",
        ["watch", "monitor", "webhook", "trigger", "notify", "event", "listener"],
        "medium",
        "impl.trigger.monitoring",
    ),
    (
        "session_context_access",
        "会话与上下文访问",
        ["history", "context", "conversation", "messages", "attachment", "transcript"],
        "medium",
        "impl.session.context",
    ),
]


def extract_implementation_evidence(skill: SkillArtifact) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = []
    for file_path in skill.source_files:
        if file_path.name == "SKILL.md":
            continue
        if file_path.name == "README.md":
            continue
        text = _safe_read_text(file_path)
        if text is None:
            continue
        relative_path = file_path.relative_to(skill.root_path).as_posix()
        for line_number, line in enumerate(text.splitlines(), start=1):
            lowered = line.lower()
            if not lowered.strip():
                continue
            for category_id, category_name, patterns, confidence, rule_id in IMPLEMENTATION_RULES:
                matched_pattern = next((pattern for pattern in patterns if pattern in lowered), None)
                if not matched_pattern:
                    continue
                evidence.append(
                    EvidenceItem(
                        category_id=category_id,
                        category_name=category_name,
                        source_path=relative_path,
                        layer="implementation",
                        evidence_type="static_scan",
                        matched_text=line.strip()[:400],
                        line_start=line_number,
                        line_end=line_number,
                        confidence=confidence,
                        rule_id=rule_id,
                        source_kind="source_file",
                        source_role="implementation_artifact",
                    )
                )
    return evidence


def _safe_read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
