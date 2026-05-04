from __future__ import annotations

import re
from pathlib import Path

from ..models import EvidenceItem, SkillArtifact


ATOMIC_IMPLEMENTATION_RULES = (
    ("R1", "读取当前用户输入", (r"\binput\s*[:=]", r"\binput\(", r"request\.(?:args|form|json|files)", r"sys\.argv", r"\bargparse\.", r"\bprompt\s*[:=]", r"\bprompt\("), "medium"),
    ("R2", "读取当前会话历史", (r"\bchat_history\b", r"\bconversation_history\b", r"\bmessage_history\b", r"\bprevious_turns\b", r"\bprior_messages\b"), "high"),
    ("R3", "读取历史会话", (r"\bload_[a-z0-9_]*session", r"\bhistorical_[a-z0-9_]*session", r"\bpast_sessions?\b", r"\bsession_store\b", r"\bsaved_sessions?\b"), "medium"),
    ("R4", "读取会话附件", (r"\battachments?\b", r"\buploaded_files?\b", r"\bfile_input\b", r"request\.files", r"\buser_files?\b"), "high"),
    ("R5", "读取本地 repo 文件", (r"\.read_text\(", r"\.read_bytes\(", r"\bopen\(", r"path\([^)]*\)\.read_text\(", r"path\([^)]*\)\.read_bytes\("), "medium"),
    ("R6", "读取本地任意路径文件", (r"path\(\s*['\"]/[^'\"]+", r"\bopen\(\s*['\"]/[^'\"]+", r"expanduser\(", r"\bos\.path\.expanduser\(", r"/etc/"), "high"),
    ("R7", "读取知识库或文档库", (r"\bread_mcp_resource\b", r"\bknowledge_base\b", r"\bdocs?_client\b", r"\bdocstore\b", r"\bvector_store\b", r"\bdrive\."), "medium"),
    ("R8", "读取连接器数据", (r"\bgithub_fetch\b", r"\bgithub_client\b", r"\bslack_sdk\b", r"\bslack\.", r"\bgmail\b", r"\bnotion_client\b", r"\bconnector(?:_client|\.|s?\[)"), "high"),
    ("R9", "批量枚举文件或资源", (r"\brg\b", r"\bglob\(", r"\brglob\(", r"\biterdir\(", r"\bos\.walk\(", r"\bos\.listdir\(", r"\blist_resources\b"), "medium"),
    ("R10", "跨源数据拼接读取", (r"\bmerge_sources\b", r"\bcombined_context\b", r"\baggregate_context\b", r"\bcombine_context\b", r"\bcontext_sources\b"), "medium"),
    ("Q1", "只读查询或搜索", (r"\bsearch\(", r"\bquery\(", r"\bfilter\(", r"\blist_[a-z0-9_]+\(", r"\bfind_[a-z0-9_]+\("), "medium"),
    ("Q2", "结构化筛选与聚合", (r"\bgroupby\(", r"\.groupby\(", r"\baggregate\(", r"\.aggregate\(", r"\bselect\(", r"\.select\(", r"\.sum\("), "medium"),
    ("Q3", "敏感对象查询", (r"\bcalendar\b", r"\bcontacts?\b", r"\btickets?\b", r"\bmailbox\b", r"\bissue_comments?\b", r"\bissue comments?\b"), "medium"),
    ("Q4", "自动推荐或判定", (r"\brecommend(?:_|[a-z])", r"\bprioriti(?:_|[a-z])", r"\bclassif(?:_|[a-z])", r"\brank(?:_|[a-z])"), "medium"),
    ("S1", "硬件摄像头调用", (r"cv2\.videocapture", r"\bcamera\b", r"\bgetusermedia\b", r"\btake_picture\b", r"\bmediadevices\.getusermedia\b"), "high"),
    ("S2", "硬件麦克风调用", (r"\bmicrophone\b", r"\bpyaudio\b", r"\bsounddevice\b", r"\brecord_audio\b", r"\baudioinput\b"), "high"),
    ("S3", "生物特征识别访问", (r"\bbiometric\b", r"\bfaceid\b", r"\bface_id\b", r"\bfingerprint\b", r"\bfacial_recognition\b"), "high"),
    ("S4", "精确地理位置获取", (r"\bgeolocation\b", r"\bgps\b", r"\blatitude\b", r"\blongitude\b", r"\bcoords\."), "high"),
    ("S5", "后台位置持续追踪", (r"\bwatchposition\b", r"\blocation_updates\b", r"\bbackground_location\b", r"\bwatch_position\b"), "high"),
    ("S6", "扫描附近硬件设备", (r"\bbluetooth\b", r"\bnfc\b", r"\bwifi_scan\b", r"\bnearby_devices\b", r"\brequestdevice\("), "medium"),
    ("S7", "系统状态读取", (r"\bsystem logs?\b", r"\bos\.uname\(", r"\bplatform\.", r"\bpsutil\b", r"\bsysctl\b"), "medium"),
    ("W1", "访问公开网页", (r"requests\.(?:get|post|put|delete|patch)\(", r"httpx\.", r"urllib\.request", r"\baiohttp\.", r"\bfetch\(", r"\bweb_fetch\b"), "high"),
    ("W2", "调用外部公开 API", (r"client\.(?:get|post|put|delete|patch)\(", r"\baxios\.", r"\bapi[_-]?url\b", r"\bapi_endpoint\b", r"\bbase_url\b", r"\brest api\b"), "high"),
    ("W3", "下载外部文件", (r"\bdownload(?:_file)?\b", r"\burlretrieve\(", r"\bresponse\.content\b", r"\biter_content\(", r"\bfetch_file\b"), "high"),
    ("W4", "使用外部搜索结果驱动后续动作", (r"\bsearch_results\b", r"\bweb_results\b", r"result\[.*url", r"\bplan_from_search\b", r"\baction_from_search\b"), "medium"),
    ("U1", "屏幕内容捕获", (r"\bscreenshot\b", r"\bcapture_screen\b", r"\bscreen_capture\b", r"\bview_image\b", r"\bpage\.screenshot\("), "high"),
    ("U2", "模拟 UI 操作控制", (r"\bclick\(", r"\bfill\(", r"\bpress\(", r"(?<![a-z0-9_])type\(", r"mousemove"), "high"),
    ("U3", "系统剪贴板读写", (r"\bclipboard\b", r"\bpasteboard\b", r"\bpyperclip\b", r"navigator\.clipboard"), "medium"),
    ("U4", "键盘输入消费", (r"\bkeylogger\b", r"\bkeyboard\.", r"\bkeystrokes?\b", r"\bhotkeys?\b", r"\bkey_events?\b"), "high"),
    ("C1", "多媒体输出控制", (r"\bset_volume\b", r"\bbrightness\b", r"\bcast_screen\b", r"\bmedia_output\b"), "medium"),
    ("C2", "外发消息或通知", (r"\bsend_notification\b", r"\bnotify\(", r"\bpush_message\b", r"\bpush message\b", r"\bsend_sms\b"), "medium"),
    ("C3", "邮件/IM 发送", (r"\bsend_email\b", r"\bsend_mail\b", r"\bpost_message\b", r"\bslack\.chat\b", r"\bsmtp\b"), "high"),
    ("C4", "实时流数据上传", (r"\bstream_upload\b", r"\bsend_stream\b", r"\bupload_stream\b", r"\bchunked\b"), "high"),
    ("C5", "双向实时通道建立", (r"\bwebsocket\b", r"\bsse\b", r"\beventsource\b", r"\bsocket\.connect\b", r"\bcreate_connection\("), "high"),
    ("X1", "执行 shell 命令", (r"\bsubprocess\.", r"\bos\.system\(", r"\bpty\b", r"\bexec_command\(", r"\bcreate_subprocess"), "high"),
    ("X2", "执行解释器代码", (r"\beval\(", r"\bexec\(", r"\bcompile\(", r"\bpython\s+-c\b", r"\bnode\s+-e\b", r"\bruby\s+-e\b"), "high"),
    ("X3", "执行容器任务", (r"\bdocker\b", r"\bkubectl\b", r"\bcontainer_run\b", r"\brun_container\b", r"\bjob_runner\b"), "high"),
    ("X4", "安装依赖或拉取包", (r"\bpip install\b", r"\bnpm install\b", r"\bcargo install\b", r"\bapt(?:-get)? install\b", r"\buv add\b"), "high"),
    ("X5", "执行环境可联网", (r"requests\.", r"httpx\.", r"\baiohttp\.", r"socket\.connect", r"\bwebsocket\b", r"urllib\.request"), "medium"),
    ("X6", "执行环境可写文件系统", (r"write_text\(", r"write_bytes\(", r"apply_patch", r"open\([^)]*,\s*[\"'](?:w|a|x|\+)"), "high"),
    ("X7", "访问环境变量或凭证", (r"\bos\.environ\b", r"\bos\.getenv\(", r"\bgetpass\b", r"\bcredentials?\b", r"\bsecrets?\b", r"\bapi[_-]?key\b"), "high"),
    ("X8", "调用外部二进制或本地工具", (r"\b(?:git|curl|gh)\b", r"\bcli\b", r"\bsubprocess\.", r"\bshutil\.which\("), "medium"),
    ("G1", "生成文本建议", (r"\bsummar(?:ize|ise|y)", r"\brender\(", r"\btemplate\b", r"\bmarkdown\b", r"\banalysis\b"), "medium"),
    ("G2", "生成结构化草稿", (r"\bdraft\b", r"\bdraft_", r"\bproposal\b", r"\bpreview\b", r"\bprefill\b", r"\bpre_fill\b"), "medium"),
    ("G3", "写本地临时文件", (r"\btempfile\b", r"/tmp/", r"\bcache_dir\b", r"\bwrite_report\b", r"\bnamedtemporaryfile\("), "medium"),
    ("G4", "写本地项目文件", (r"\bapply_patch\b", r"\bwrite_text\(", r"\bwrite_bytes\(", r"path\([^)]*\)\.write_text\(", r"path\([^)]*\)\.write_bytes\("), "medium"),
    ("G5", "批量本地写文件", (r"\bfor .*write_text\(", r"\bwhile .*write_text\(", r"\bbatch_[a-z0-9_]*write\b", r"\bbulk_[a-z0-9_]*write\b", r"\bmulti_file\b"), "medium"),
    ("O1", "创建外部草稿", (r"\bcreate_draft\b", r"\bsave_draft\b"), "medium"),
    ("O2", "外部单对象写入", (r"\bupdate_issue\b", r"\bcreate_file\b", r"\bupdate_review_comment\b", r"\badd_comment\b", r"\bcreate_pull_request\b"), "medium"),
    ("O3", "外部多对象批量写入", (r"\bbatch_apply\b", r"\bbatch apply\b", r"\bbulk_update\b", r"\bbulk update\b", r"\bfor .*update_", r"\bparallel .*create_"), "medium"),
    ("O4", "破坏性写入", (r"\bdelete\(", r"\bdelete_[a-z0-9_]+\(", r"\barchive\(", r"\breset\(", r"\brevoke\(", r"\bterminate\("), "high"),
    ("O5", "自动外发", (r"\bpublish_automatically\b", r"\bpublish automatically\b", r"\bsend_automatically\b", r"\bsend automatically\b", r"\bpost_automatically\b", r"\bauto_send\b"), "medium"),
    ("K1", "修改系统级设置", (r"\bsystem settings?\b", r"\bdefaults write\b", r"\bset_preference\b", r"\bsecurity settings?\b"), "high"),
    ("K2", "硬件开关控制", (r"\btoggle_wifi\b", r"\btoggle_bluetooth\b", r"\bairplane mode\b", r"\bhardware switch\b"), "high"),
    ("K3", "应用程序管理", (r"\binstall_app\b", r"\buninstall_app\b", r"\binstall app\b", r"\buninstall app\b", r"\bbrew install\b", r"\bapt install\b"), "high"),
    ("K4", "闹钟与唤醒管理", (r"\bwake_lock\b", r"\bwake lock\b", r"\bschedule_alarm\b", r"\bset_alarm\b", r"\bcron\b"), "medium"),
    ("K5", "进程强制管控", (r"\bkill\s+-9\b", r"\bterminate\(", r"\brestart_process\b", r"\bpkill\b", r"\bkill_process\b"), "high"),
    ("K6", "全局环境配置修改", (r"\bset_locale\b", r"\bset_language\b", r"\bset_font\b", r"\bupdate_environment\b"), "medium"),
    ("A2", "需确认后执行", (r"\bconfirm\(", r"\bapproval\b", r"\bwait_for_confirmation\b", r"\bwait for confirmation\b"), "high"),
    ("A3", "定时调度", (r"\bcron\b", r"\bschedule\.", r"\bapscheduler\b", r"\bevery\(", r"\bfixed interval\b"), "high"),
    ("A4", "事件触发", (r"\bwebhook\b", r"\bon_message\b", r"\bon_change\b", r"\blistener\b", r"\bevent_handler\b"), "medium"),
    ("A5", "持续监控", (r"while true", r"\bwatch\(", r"\bpoll\(", r"\bmonitor\b"), "high"),
    ("A6", "触发后自动动作", (r"\btrigger_alerts\b", r"\btrigger alerts\b", r"\bautomatically_write\b", r"\bautomatically write\b", r"\bdirectly_execute\b", r"\bdirectly execute\b", r"\bauto_apply\b"), "medium"),
    ("A7", "自动重试或循环执行", (r"\bretry\b", r"\bbackoff\b", r"while true", r"repeat_until"), "medium"),
    ("I1", "使用当前用户身份访问单系统", (r"\boauth\b", r"\bsignin\b", r"\bsign_in\b", r"\bauthorized_identity\b", r"\bauthorized identity\b"), "medium"),
    ("I2", "跨系统身份代理", (r"\bconnector(?:_client|\.|s?\[)", r"\boauth\b", r"\bsignin\b", r"\bsign_in\b", r"\bcross_app\b"), "medium"),
    ("I3", "跨系统数据搬运", (r"\bsync .* to ", r"\bcopy .* to .*slack", r"\bcopy_data_between\b", r"\bmove_data_between\b", r"\bbridge_data\b"), "medium"),
    ("I4", "凭证注入到外部调用", (r"\bauthorization\b", r"\bbearer ", r"\bapi[_-]?key\b", r"\btoken\s*="), "high"),
    ("I5", "隐式权限继承", (r"\breuse_connector\b", r"\binherited_token\b", r"\bexisting_auth\b", r"\binherited_permissions\b"), "medium"),
    ("I6", "身份令牌深度管理", (r"\bcredential_store\b", r"\bcredential store\b", r"\bkeychain\b", r"\bvault\b", r"\bmanage_credentials\b"), "high"),
    ("I7", "跨端或跨设备协同", (r"\bremote[_ ]device\b", r"\bpaired[_ ]device\b", r"\badb\b", r"\bssh .*device\b"), "medium"),
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
