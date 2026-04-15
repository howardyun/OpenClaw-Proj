from __future__ import annotations

import re
from pathlib import Path

from ..models import EvidenceItem, SkillArtifact


ATOMIC_IMPLEMENTATION_RULES = (
    ("R1", "读取当前用户输入", (r"\binput\s*[:=]", r"request\.args", r"sys\.argv", r"prompt\s*[:=]"), "medium"),
    ("R2", "读取当前会话历史", (r"chat_history", r"conversation_history", r"message_history", r"previous_turns"), "high"),
    ("R3", "读取历史会话", (r"load_.*session", r"historical_.*session", r"past_sessions?", r"session_store"), "medium"),
    ("R4", "读取会话附件", (r"attachments?", r"uploaded_files?", r"file_input"), "high"),
    ("R5", "读取本地 repo 文件", (r"\.read_text\(", r"\.read_bytes\(", r"\bopen\(", r"Path\([^)]*\)\.read_text"), "medium"),
    ("R6", "读取本地任意路径文件", (r"Path\(\s*['\"]/[^'\"]+", r"\bopen\(\s*['\"]/[^'\"]+", r"expanduser\(", r"/etc/"), "high"),
    ("R7", "读取知识库或文档库", (r"read_mcp_resource", r"knowledge_base", r"docs?_client", r"drive\."), "medium"),
    ("R8", "读取连接器数据", (r"github_fetch", r"slack", r"gmail", r"notion", r"connector"), "high"),
    ("R9", "批量枚举文件或资源", (r"\brg\b", r"\bglob\(", r"\brglob\(", r"\biterdir\(", r"list_resources"), "medium"),
    ("R10", "跨源数据拼接读取", (r"merge_sources", r"combined_context", r"join\(", r"aggregate_context"), "medium"),
    ("Q1", "只读查询或搜索", (r"\bsearch\(", r"\bquery\(", r"\bfilter\(", r"\blist_[a-z0-9_]+\(", r"\bfind\("), "medium"),
    ("Q2", "结构化筛选与聚合", (r"\bgroupby\(", r"\baggregate\(", r"\bselect\(", r"\bsum\("), "medium"),
    ("Q3", "敏感对象查询", (r"calendar", r"contacts?", r"tickets?", r"mailbox", r"issue comments?"), "medium"),
    ("Q4", "自动推荐或判定", (r"\brecommend", r"\bprioriti", r"\bclassif", r"\brank"), "medium"),
    ("S1", "硬件摄像头调用", (r"cv2\.videocapture", r"camera", r"getusermedia", r"take_picture"), "high"),
    ("S2", "硬件麦克风调用", (r"microphone", r"pyaudio", r"sounddevice", r"record_audio"), "high"),
    ("S3", "生物特征识别访问", (r"biometric", r"faceid", r"fingerprint", r"facial_recognition"), "high"),
    ("S4", "精确地理位置获取", (r"geolocation", r"\bgps\b", r"latitude", r"longitude"), "high"),
    ("S5", "后台位置持续追踪", (r"watchposition", r"location_updates", r"background_location"), "high"),
    ("S6", "扫描附近硬件设备", (r"bluetooth", r"\bnfc\b", r"wifi_scan", r"nearby_devices"), "medium"),
    ("S7", "系统状态读取", (r"system logs?", r"os\.uname", r"platform\.", r"psutil"), "medium"),
    ("W1", "访问公开网页", (r"requests\.(get|post|put|delete)\(", r"httpx\.", r"urllib\.request", r"\bfetch\(", r"web_fetch"), "high"),
    ("W2", "调用外部公开 API", (r"client\.(get|post|put|delete)\(", r"axios\.", r"api_url", r"rest api"), "high"),
    ("W3", "下载外部文件", (r"download", r"urlretrieve", r"response\.content", r"fetch_file"), "high"),
    ("W4", "使用外部搜索结果驱动后续动作", (r"search_results", r"web_results", r"result\[.*url", r"plan_from_search"), "medium"),
    ("U1", "屏幕内容捕获", (r"screenshot", r"capture_screen", r"screen_capture", r"view_image"), "high"),
    ("U2", "模拟 UI 操作控制", (r"\bclick\(", r"fill\(", r"press\(", r"type\(", r"mousemove"), "high"),
    ("U3", "系统剪贴板读写", (r"clipboard", r"pasteboard", r"pyperclip"), "medium"),
    ("U4", "键盘输入消费", (r"keylogger", r"keyboard\.", r"keystroke", r"hotkey"), "high"),
    ("C1", "多媒体输出控制", (r"set_volume", r"brightness", r"cast_screen", r"media_output"), "medium"),
    ("C2", "外发消息或通知", (r"send_notification", r"notify", r"push message", r"send_sms"), "medium"),
    ("C3", "邮件/IM 发送", (r"send_email", r"post_message", r"slack\.chat", r"smtp"), "high"),
    ("C4", "实时流数据上传", (r"stream_upload", r"send_stream", r"upload_stream", r"chunked"), "high"),
    ("C5", "双向实时通道建立", (r"websocket", r"\bsse\b", r"eventsource", r"socket\.connect"), "high"),
    ("X1", "执行 shell 命令", (r"subprocess\.", r"os\.system\(", r"pty", r"\bexec_command\(", r"create_subprocess"), "high"),
    ("X2", "执行解释器代码", (r"\beval\(", r"\bexec\(", r"python\s+-c", r"node\s+-e", r"ruby\s+-e"), "high"),
    ("X3", "执行容器任务", (r"\bdocker\b", r"\bcontainer\b", r"\bkubectl\b", r"job runner"), "high"),
    ("X4", "安装依赖或拉取包", (r"\bpip install\b", r"\bnpm install\b", r"\bcargo install\b", r"\bapt(-get)? install\b"), "high"),
    ("X5", "执行环境可联网", (r"requests\.", r"httpx\.", r"socket\.connect", r"websocket"), "medium"),
    ("X6", "执行环境可写文件系统", (r"write_text\(", r"write_bytes\(", r"apply_patch", r"open\([^)]*,\s*[\"'](?:w|a|x|\+)"), "high"),
    ("X7", "访问环境变量或凭证", (r"os\.environ", r"os\.getenv\(", r"getpass", r"credential", r"secret"), "high"),
    ("X8", "调用外部二进制或本地工具", (r"\bgit\b", r"\bcurl\b", r"\bgh\b", r"\bcli\b", r"subprocess"), "medium"),
    ("G1", "生成文本建议", (r"\bsummar", r"\brender\(", r"\btemplate\b", r"markdown", r"analysis"), "medium"),
    ("G2", "生成结构化草稿", (r"\bdraft\b", r"\bproposal\b", r"\bpreview\b", r"prefill"), "medium"),
    ("G3", "写本地临时文件", (r"\btempfile\b", r"/tmp/", r"cache_dir", r"write_report"), "medium"),
    ("G4", "写本地项目文件", (r"apply_patch", r"write_text\(", r"write_bytes\(", r"Path\([^)]*\)\.write_text"), "medium"),
    ("G5", "批量本地写文件", (r"for .*write_text\(", r"while .*write_text\(", r"batch", r"multi_file"), "medium"),
    ("O1", "创建外部草稿", (r"create_draft", r"save_draft"), "medium"),
    ("O2", "外部单对象写入", (r"update_issue", r"create_file", r"update_review_comment", r"add_comment"), "medium"),
    ("O3", "外部多对象批量写入", (r"batch apply", r"bulk update", r"for .*update_", r"parallel .*create_"), "medium"),
    ("O4", "破坏性写入", (r"\bdelete\b", r"\barchive\b", r"\breset\b", r"\brevoke\b", r"terminate"), "high"),
    ("O5", "自动外发", (r"publish automatically", r"send automatically", r"post automatically", r"auto_send"), "medium"),
    ("K1", "修改系统级设置", (r"system settings?", r"defaults write", r"set_preference", r"security settings?"), "high"),
    ("K2", "硬件开关控制", (r"toggle_wifi", r"toggle_bluetooth", r"airplane mode", r"hardware switch"), "high"),
    ("K3", "应用程序管理", (r"install app", r"uninstall app", r"brew install", r"apt install"), "high"),
    ("K4", "闹钟与唤醒管理", (r"wake lock", r"schedule_alarm", r"set_alarm", r"cron"), "medium"),
    ("K5", "进程强制管控", (r"kill\s+-9", r"terminate\(", r"restart_process", r"pkill"), "high"),
    ("K6", "全局环境配置修改", (r"set_locale", r"set_language", r"set_font", r"update_environment"), "medium"),
    ("A2", "需确认后执行", (r"\bconfirm\b", r"\bapproval\b", r"wait for confirmation"), "high"),
    ("A3", "定时调度", (r"\bcron\b", r"\bschedule\.", r"apscheduler", r"every\(", r"fixed interval"), "high"),
    ("A4", "事件触发", (r"\bwebhook\b", r"on_message", r"on_change", r"listener", r"event_handler"), "medium"),
    ("A5", "持续监控", (r"while true", r"\bwatch\(", r"\bpoll\(", r"\bmonitor\b"), "high"),
    ("A6", "触发后自动动作", (r"trigger alerts", r"automatically write", r"directly execute", r"auto_apply"), "medium"),
    ("A7", "自动重试或循环执行", (r"\bretry\b", r"\bbackoff\b", r"while true", r"repeat_until"), "medium"),
    ("I1", "使用当前用户身份访问单系统", (r"\boauth\b", r"\bsignin\b", r"authorized identity"), "medium"),
    ("I2", "跨系统身份代理", (r"\bconnector\b", r"\boauth\b", r"\bsignin\b", r"cross_app"), "medium"),
    ("I3", "跨系统数据搬运", (r"sync .* to ", r"copy .* to .*slack", r"move_data_between", r"bridge_data"), "medium"),
    ("I4", "凭证注入到外部调用", (r"authorization", r"bearer ", r"api[_-]?key", r"token="), "high"),
    ("I5", "隐式权限继承", (r"reuse_connector", r"inherited_token", r"existing_auth"), "medium"),
    ("I6", "身份令牌深度管理", (r"credential store", r"keychain", r"vault", r"manage_credentials"), "high"),
    ("I7", "跨端或跨设备协同", (r"remote[_ ]device", r"paired[_ ]device", r"\badb\b", r"ssh .*device"), "medium"),
)

CONTROL_IMPLEMENTATION_RULES = (
    ("C3", "显式确认", (r"\bconfirm\b", r"\bapproval\b", r"wait for confirmation"), "high"),
    ("C4", "预览或回显", (r"\bpreview\b", r"\bdiff\b", r"show changes"), "medium"),
    ("C5", "dry-run", (r"dry[_-]?run",), "medium"),
    ("C6", "回滚或幂等", (r"\brollback\b", r"\bidempotent\b"), "medium"),
    ("C7", "白名单", (r"\bwhitelist\b", r"\ballowlist\b", r"approved domains"), "medium"),
    ("C8", "脱敏", (r"\bredact\b", r"mask sensitive", r"\bsanitize\b"), "medium"),
    ("C9", "审计日志", (r"audit", r"logger", r"\blog\b"), "low"),
    ("C10", "kill switch", (r"kill switch", r"stop flag", r"enabled"), "medium"),
    ("C11", "频率或规模限制", (r"rate limit", r"batch cap", r"max batch", r"retry cap"), "medium"),
    ("C12", "高敏禁外连", (r"offline only", r"disable network", r"no network"), "medium"),
)


def extract_implementation_evidence(skill: SkillArtifact) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = []
    for file_path in skill.source_files:
        if file_path.name in {"SKILL.md", "README.md"}:
            continue
        text = _safe_read_text(file_path)
        if text is None:
            continue
        relative_path = file_path.relative_to(skill.root_path).as_posix()
        lines = text.splitlines()
        for line_number, line in enumerate(lines, start=1):
            lowered = line.lower()
            if not lowered.strip():
                continue
            evidence.extend(
                _match_rule_set(
                    ATOMIC_IMPLEMENTATION_RULES,
                    "atomic_capability",
                    lowered,
                    line,
                    line_number,
                    relative_path,
                    lines,
                )
            )
            evidence.extend(
                _match_rule_set(
                    CONTROL_IMPLEMENTATION_RULES,
                    "control_semantic",
                    lowered,
                    line,
                    line_number,
                    relative_path,
                    lines,
                )
            )
        evidence.extend(_derive_loop_scheduler_evidence(relative_path, lines))
        evidence.extend(_derive_read_only_control(relative_path, lines, existing=evidence))
    return _dedupe_evidence(evidence)


def _match_rule_set(
    rules: tuple[tuple[str, str, tuple[str, ...], str], ...],
    subject_type: str,
    lowered: str,
    raw_line: str,
    line_number: int,
    source_path: str,
    lines: list[str],
) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = []
    for subject_id, subject_name, patterns, confidence in rules:
        matched_pattern = next((pattern for pattern in patterns if re.search(pattern, lowered)), None)
        if not matched_pattern:
            continue
        excluded_by_rule = _excluded_implementation_rule(subject_id, lowered, raw_line, lines, line_number)
        if excluded_by_rule:
            continue
        matched_text, line_start, line_end = _build_context_excerpt(lines, line_number)
        evidence.append(
            EvidenceItem(
                category_id=subject_id,
                category_name=subject_name,
                source_path=source_path,
                layer="implementation",
                evidence_type="static_scan",
                matched_text=matched_text,
                line_start=line_start,
                line_end=line_end,
                confidence=confidence,
                rule_id=f"impl.{subject_type}.{subject_id.lower()}",
                source_kind="source_file",
                source_role="implementation_artifact",
                subject_type=subject_type,
                matched_pattern=matched_pattern,
                evidence_strength="strong" if confidence == "high" else "medium",
            )
        )
    return evidence


def _excluded_implementation_rule(
    subject_id: str,
    lowered: str,
    raw_line: str,
    lines: list[str],
    line_number: int,
) -> str | None:
    stripped = raw_line.strip()
    if stripped.startswith("#"):
        return "comment_only"
    if subject_id in {"W1", "W2"} and _looks_like_plain_url_text(stripped):
        return "plain_url_text"
    if subject_id in {"X1", "X2"} and ("```" in stripped or stripped.startswith(("bash ", "python "))) and not _is_actual_exec_context(lowered):
        return "command_example"
    if subject_id == "I4" and "token" in lowered and not any(term in lowered for term in ("authorization", "bearer", "api_key", "api-key")):
        return "token_text_only"
    if subject_id == "A3" and any(term in lowered for term in ("sleep(", "settimeout(")):
        return "sleep_without_scheduler"
    if subject_id in {"G3", "G4", "X6"} and "open(" in lowered and not _is_write_open(lowered):
        return "read_open"
    if subject_id == "G5" and "batch" not in lowered and "write_text" not in lowered:
        return "non_batch_write"
    if subject_id == "A7" and "while true" in lowered and not any(term in "\n".join(lines[max(0, line_number - 3): line_number + 2]).lower() for term in ("retry", "backoff")):
        return "loop_without_retry_signal"
    if subject_id == "U2" and "clickable" in lowered:
        return "ui_description_only"
    if subject_id in {"C2", "C3"} and any(term in lowered for term in ("notification settings", "message history", "email template")):
        return "message_text_only"
    if subject_id == "K1" and "settings page" in lowered:
        return "settings_text_only"
    if subject_id == "I6" and "token count" in lowered:
        return "token_text_only"
    return None


def _build_context_excerpt(lines: list[str], center_line_number: int, radius: int = 1) -> tuple[str, int, int]:
    start_index = max(0, center_line_number - 1 - radius)
    end_index = min(len(lines), center_line_number + radius)
    excerpt = "\n".join(lines[start_index:end_index]).strip()[:400]
    return excerpt, start_index + 1, end_index


def _derive_loop_scheduler_evidence(source_path: str, lines: list[str]) -> list[EvidenceItem]:
    joined = "\n".join(lines).lower()
    if "while true" not in joined or "sleep(" not in joined:
        return []
    if not any(term in joined for term in ("requests.", "httpx.", "urllib.", "fetch(")):
        return []
    return [
        EvidenceItem(
            category_id="A3",
            category_name="定时调度",
            source_path=source_path,
            layer="implementation",
            evidence_type="structural_inference",
            matched_text="long-running loop with network polling and sleep interval",
            line_start=1,
            line_end=len(lines),
            confidence="high",
            rule_id="impl.atomic_capability.a3.loop_schedule",
            source_kind="source_file",
            source_role="implementation_artifact",
            subject_type="atomic_capability",
            matched_pattern="while true + sleep + network call",
            evidence_strength="strong",
        )
    ]


def _derive_read_only_control(source_path: str, lines: list[str], existing: list[EvidenceItem]) -> list[EvidenceItem]:
    read_only_atoms = {
        "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10",
        "Q1", "Q2", "Q3", "Q4", "S1", "S2", "S3", "S4", "S5", "S6", "S7",
        "W1", "W2", "W3", "W4", "U1",
    }
    write_atoms = {
        "U2", "U3", "U4", "C1", "C2", "C3", "C4", "C5",
        "X1", "X2", "X3", "X4", "X6", "G3", "G4", "G5",
        "O1", "O2", "O3", "O4", "O5", "K1", "K2", "K3", "K4", "K5", "K6",
        "A6", "I2", "I3", "I4", "I6", "I7",
    }
    has_atomic_read = any(item.subject_type == "atomic_capability" and item.category_id in read_only_atoms for item in existing)
    has_write = any(item.subject_type == "atomic_capability" and item.category_id in write_atoms for item in existing)
    if not has_atomic_read or has_write:
        return []
    return [
        EvidenceItem(
            category_id="C1",
            category_name="只读约束",
            source_path=source_path,
            layer="implementation",
            evidence_type="derived_control",
            matched_text="read-oriented implementation without write sinks",
            line_start=1,
            line_end=len(lines),
            confidence="medium",
            rule_id="impl.control_semantic.c1.derived_read_only",
            source_kind="source_file",
            source_role="implementation_artifact",
            subject_type="control_semantic",
            matched_pattern="derived read-only profile",
            evidence_strength="medium",
        )
    ]


def _is_write_open(lowered: str) -> bool:
    return bool(re.search(r"open\([^)]*,\s*[\"'](?:w|a|x|\+)", lowered))


def _looks_like_plain_url_text(stripped: str) -> bool:
    return stripped.startswith(("http://", "https://")) or stripped.startswith(("'", '"')) and "http" in stripped


def _is_actual_exec_context(lowered: str) -> bool:
    return any(term in lowered for term in ("subprocess", "os.system", "exec_command", "spawn"))


def _dedupe_evidence(items: list[EvidenceItem]) -> list[EvidenceItem]:
    unique: dict[str, EvidenceItem] = {}
    for item in items:
        unique.setdefault(item.evidence_fingerprint, item)
    return list(unique.values())


def _safe_read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
