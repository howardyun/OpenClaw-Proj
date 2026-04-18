from __future__ import annotations

import re
from pathlib import Path

from ..models import EvidenceItem, SkillArtifact
from ..skill_structure import FRONTMATTER_RE, extract_frontmatter_and_body, parse_frontmatter


REFERENCE_PATTERN = re.compile(
    r"`(?P<code>[^`]+)`|\[(?P<label>[^\]]+)\]\((?P<link>[^)]+)\)"
)

FENCE_PATTERN = re.compile(r"^\s*```")


ATOMIC_DECLARATION_RULES = (
    ("R1", "读取当前用户输入", (r"\binput\b", r"\bprompt\b", r"user input"), "medium"),
    ("R2", "读取当前会话历史", (r"chat history", r"conversation history", r"message history", r"previous turns"), "high"),
    ("R3", "读取历史会话", (r"historical sessions?", r"past sessions?", r"cross-session", r"history records?"), "medium"),
    ("R4", "读取会话附件", (r"\battachments?\b", r"uploaded files?", r"file input"), "high"),
    ("R5", "读取本地 repo 文件", (r"read (?:project|repo|workspace) files", r"local references", r"project files"), "high"),
    ("R6", "读取本地任意路径文件", (r"absolute path", r"outside the repo", r"system files?", r"arbitrary local path"), "high"),
    ("R7", "读取知识库或文档库", (r"knowledge base", r"internal docs", r"document library", r"\breferences\b", r"\bdocs\b"), "medium"),
    ("R8", "读取连接器数据", (r"\bconnectors?\b", r"gmail", r"slack", r"github", r"notion"), "high"),
    ("R9", "批量枚举文件或资源", (r"list files", r"enumerate", r"scan all", r"bulk export", r"search files"), "medium"),
    ("R10", "跨源数据拼接读取", (r"combine .*?(?:files|connectors?|web|attachments?)", r"cross-source", r"merge .*?data"), "medium"),
    ("Q1", "只读查询或搜索", (r"\bsearch\b", r"\bquery\b", r"\bfilter\b", r"\blist\b", r"read-only query"), "medium"),
    ("Q2", "结构化筛选与聚合", (r"\baggregate\b", r"\bgroup\b", r"\bselect\b", r"structured filter"), "medium"),
    ("Q3", "敏感对象查询", (r"calendar", r"contacts?", r"tickets?", r"emails?", r"mailbox"), "medium"),
    ("Q4", "自动推荐或判定", (r"\brecommend\b", r"\bsuggest\b", r"\bclassif", r"\bprioriti", r"\brank\b"), "medium"),
    ("S1", "硬件摄像头调用", (r"camera", r"take photos?", r"record video", r"live video"), "high"),
    ("S2", "硬件麦克风调用", (r"microphone", r"record audio", r"voice input", r"environment audio"), "high"),
    ("S3", "生物特征识别访问", (r"fingerprint", r"face id", r"biometric", r"facial recognition"), "high"),
    ("S4", "精确地理位置获取", (r"\bgps\b", r"latitude", r"longitude", r"geolocation", r"current location"), "high"),
    ("S5", "后台位置持续追踪", (r"background location", r"track location", r"location updates", r"location monitoring"), "high"),
    ("S6", "扫描附近硬件设备", (r"\bbluetooth\b", r"\bnfc\b", r"nearby devices", r"wifi scan"), "medium"),
    ("S7", "系统状态读取", (r"system logs?", r"runtime parameters?", r"system properties", r"system status"), "medium"),
    ("W1", "访问公开网页", (r"browse public webpages", r"public web", r"browse the web", r"webpages?"), "high"),
    ("W2", "调用外部公开 API", (r"public api", r"rest api", r"sdk api", r"remote endpoint"), "high"),
    ("W3", "下载外部文件", (r"download files?", r"fetch file", r"remote file", r"external file"), "high"),
    ("W4", "使用外部搜索结果驱动后续动作", (r"search results? .*?(?:plan|action)", r"web results? .*?(?:plan|execute)", r"drive actions? from search"), "medium"),
    ("U1", "屏幕内容捕获", (r"screenshot", r"screen capture", r"record screen", r"capture ui"), "high"),
    ("U2", "模拟 UI 操作控制", (r"click buttons?", r"simulate clicks?", r"fill forms?", r"ui automation", r"simulate ui"), "high"),
    ("U3", "系统剪贴板读写", (r"clipboard", r"copy/paste", r"pasteboard"), "medium"),
    ("U4", "键盘输入消费", (r"keyboard input", r"keystrokes?", r"hotkeys?", r"key events?"), "high"),
    ("C1", "多媒体输出控制", (r"screen brightness", r"volume control", r"cast screen", r"media output"), "medium"),
    ("C2", "外发消息或通知", (r"push notifications?", r"send notifications?", r"\bsms\b", r"in-app message"), "medium"),
    ("C3", "邮件/IM 发送", (r"send email", r"send slack", r"wechat", r"instant message", r"\bim\b"), "high"),
    ("C4", "实时流数据上传", (r"stream upload", r"real-time upload", r"push stream", r"live data"), "high"),
    ("C5", "双向实时通道建立", (r"websocket", r"\bsse\b", r"persistent connection", r"real-time channel"), "high"),
    ("X1", "执行 shell 命令", (r"\bbash\b", r"\bsh\b", r"\bexec\b", r"\bspawn\b", r"shell command"), "high"),
    ("X2", "执行解释器代码", (r"run python", r"run node", r"execute code", r"interpreter"), "high"),
    ("X3", "执行容器任务", (r"docker", r"container", r"job runner", r"kubectl"), "high"),
    ("X4", "安装依赖或拉取包", (r"pip install", r"npm install", r"apt install", r"cargo install"), "high"),
    ("X5", "执行环境可联网", (r"network access", r"internet access", r"联网执行", r"code .*?network"), "medium"),
    ("X6", "执行环境可写文件系统", (r"write filesystem", r"modify local files", r"writable filesystem", r"write files"), "medium"),
    ("X7", "访问环境变量或凭证", (r"environment variables?", r"\bsecrets?\b", r"\btokens?\b", r"credential store"), "high"),
    ("X8", "调用外部二进制或本地工具", (r"\bgit\b", r"\bcurl\b", r"\bdocker\b", r"\bcli\b", r"local tool"), "medium"),
    ("G1", "生成文本建议", (r"generate .*?summary", r"analysis", r"recommendations?", r"source-backed answers"), "medium"),
    ("G2", "生成结构化草稿", (r"\bdraft\b", r"pre-fill", r"prefill", r"pr description", r"form draft"), "high"),
    ("G3", "写本地临时文件", (r"temp file", r"cache file", r"report file", r"output file"), "medium"),
    ("G4", "写本地项目文件", (r"edit repo", r"modify files", r"update project files", r"workspace files"), "high"),
    ("G5", "批量本地写文件", (r"batch update", r"bulk edit", r"multi-file", r"multiple files"), "medium"),
    ("O1", "创建外部草稿", (r"create draft", r"save draft", r"external draft"), "medium"),
    ("O2", "外部单对象写入", (r"update one", r"single write", r"update one object", r"create one object"), "medium"),
    ("O3", "外部多对象批量写入", (r"\bbatch\b", r"\bbulk\b", r"auto-apply", r"many objects"), "medium"),
    ("O4", "破坏性写入", (r"\bdelete\b", r"\barchive\b", r"\breset\b", r"\brevoke\b"), "high"),
    ("O5", "自动外发", (r"send automatically", r"publish automatically", r"post automatically", r"without second confirmation"), "medium"),
    ("K1", "修改系统级设置", (r"system settings?", r"global settings?", r"security settings?"), "high"),
    ("K2", "硬件开关控制", (r"wifi switch", r"bluetooth switch", r"infrared", r"hardware switch"), "high"),
    ("K3", "应用程序管理", (r"install apps?", r"uninstall apps?", r"application management"), "high"),
    ("K4", "闹钟与唤醒管理", (r"alarms?", r"wake lock", r"wake-up", r"schedule wake"), "medium"),
    ("K5", "进程强制管控", (r"kill process", r"restart process", r"terminate process"), "high"),
    ("K6", "全局环境配置修改", (r"system language", r"system font", r"global environment", r"locale settings"), "medium"),
    ("A1", "用户显式单次触发", (r"single user request", r"only when explicitly requested", r"current instruction"), "medium"),
    ("A2", "需确认后执行", (r"after user confirmation", r"after approval", r"wait for confirmation", r"approve before"), "high"),
    ("A3", "定时调度", (r"every hour", r"daily", r"scheduled", r"\bcron\b", r"scheduler"), "high"),
    ("A4", "事件触发", (r"on change", r"webhook", r"on event", r"on message", r"triggered by"), "medium"),
    ("A5", "持续监控", (r"\bmonitor\b", r"\bwatch\b", r"\bpoll\b", r"long-running"), "high"),
    ("A6", "触发后自动动作", (r"trigger alerts", r"automatically write", r"directly execute", r"auto-run action"), "medium"),
    ("A7", "自动重试或循环执行", (r"\bretry\b", r"\bbackoff\b", r"repeated attempts", r"loop execution"), "medium"),
    ("I1", "使用当前用户身份访问单系统", (r"user identity", r"authorized identity", r"single system", r"connector access"), "medium"),
    ("I2", "跨系统身份代理", (r"multiple systems?", r"cross-system", r"\bconnector\b", r"desktop app integration"), "medium"),
    ("I3", "跨系统数据搬运", (r"from .*? to .*?", r"copy data between", r"sync across systems?"), "medium"),
    ("I4", "凭证注入到外部调用", (r"bearer token", r"api key", r"authorization header", r"token="), "high"),
    ("I5", "隐式权限继承", (r"existing connector", r"inherited permissions?", r"implicit permissions?"), "medium"),
    ("I6", "身份令牌深度管理", (r"credential management", r"manage credentials?", r"long-lived (?:token|credentials?)", r"system credential"), "high"),
    ("I7", "跨端或跨设备协同", (r"other device", r"cross-device", r"another terminal", r"paired device", r"another device"), "medium"),
)

CONTROL_DECLARATION_RULES = (
    ("C1", "只读约束", (r"\breadonly\b", r"read only", r"gather public information only"), "high"),
    ("C2", "范围限制", (r"local references", r"project files only", r"public webpages"), "medium"),
    ("C3", "显式确认", (r"after user confirmation", r"after approval", r"wait for confirmation"), "high"),
    ("C4", "预览或回显", (r"\bpreview\b", r"\bdiff\b", r"show changes"), "medium"),
    ("C5", "dry-run", (r"dry-run", r"dry run"), "medium"),
    ("C6", "回滚或幂等", (r"\brollback\b", r"\bidempotent\b"), "medium"),
    ("C7", "白名单", (r"\bwhitelist\b", r"\ballowlist\b", r"approved domains"), "medium"),
    ("C8", "脱敏", (r"\bredact\b", r"mask sensitive", r"\bdesensiti"), "medium"),
    ("C9", "审计日志", (r"audit log", r"access log", r"retain logs"), "medium"),
    ("C10", "kill switch", (r"kill switch", r"pause automation", r"stop switch"), "medium"),
    ("C11", "频率或规模限制", (r"rate limit", r"batch cap", r"retry cap"), "medium"),
    ("C12", "高敏禁外连", (r"no network", r"disable network", r"offline only"), "medium"),
)

NEGATIVE_DECLARATION_RULES = {
    "R2": (r"story about one session", r"one-off project context"),
    "W2": (r"api urls", r"json api", r"ledger api", r"admin api"),
    "X1": (r"```bash", r"\bbash example\b"),
    "X2": (r"```python", r"```node"),
    "I2": (r"--token", r"\btoken\b"),
    "U2": (r"clickable", r"button click copy", r"click the link"),
    "C2": (r"notification settings", r"message history"),
    "C3": (r"email template", r"slack thread history"),
    "C5": (r"eventsource example", r"websocket url"),
    "K1": (r"settings page", r"configuration docs"),
    "I6": (r"token count", r"token budget"),
    "I7": (r"device type", r"cross-device responsive"),
}


def extract_declaration_evidence(skill: SkillArtifact) -> list[EvidenceItem]:
    skill_md = skill.root_path / "SKILL.md"
    skill_root_resolved = skill.root_path.resolve()
    if not skill_md.exists():
        return []
    skill_text = _safe_read_text(skill_md)
    if skill_text is None:
        return []

    frontmatter, body = extract_frontmatter_and_body(skill_text)
    body_start_line = _body_start_line_number(skill_text)
    frontmatter_map = parse_frontmatter(frontmatter) if frontmatter else {}
    evidence: list[EvidenceItem] = []

    for key, value in frontmatter_map.items():
        evidence.extend(
            _scan_text_for_declaration(
                text=f"{key}: {value}",
                source_path=skill_md.relative_to(skill.root_path).as_posix(),
                source_kind="skill_md_frontmatter",
                source_role="primary_declaration",
                support_reference_mode="direct",
            )
        )
    evidence.extend(
        _scan_text_for_declaration(
            text=body,
            source_path=skill_md.relative_to(skill.root_path).as_posix(),
            source_kind="skill_md_body",
            source_role="primary_declaration",
            support_reference_mode="direct",
            base_line_number=body_start_line,
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
                source_role="referenced_supporting_material",
                support_reference_mode="referenced_by_skill_md",
            )
        )
    return evidence


def _extract_referenced_support_files(skill_root: Path, body: str) -> list[Path]:
    resolved_root = skill_root.resolve()
    files: set[Path] = set()
    body_without_fences = _strip_fenced_code_blocks(body)
    for match in REFERENCE_PATTERN.finditer(body_without_fences):
        reference = (match.group("code") or match.group("link") or "").strip()
        if not _is_supported_relative_reference(reference):
            continue
        try:
            candidate = (resolved_root / reference).resolve()
            candidate.relative_to(resolved_root)
            if candidate.is_file():
                files.add(candidate)
        except (OSError, ValueError):
            continue
    return sorted(files)


def _strip_fenced_code_blocks(text: str) -> str:
    lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append(line)
    return "\n".join(lines)


def _is_supported_relative_reference(reference: str) -> bool:
    if not reference:
        return False
    if "\n" in reference or "\r" in reference:
        return False
    if len(reference) > 240:
        return False
    if reference.startswith(("http://", "https://", "#", "/")):
        return False
    if reference.endswith("/"):
        return False
    return "/" in reference or "." in Path(reference).name


def _scan_text_for_declaration(
    text: str,
    source_path: str,
    source_kind: str,
    source_role: str,
    support_reference_mode: str,
    base_line_number: int = 1,
) -> list[EvidenceItem]:
    lines = text.splitlines() or [text]
    evidence: list[EvidenceItem] = []
    in_fence = False
    for index, line in enumerate(lines, start=1):
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
            continue
        lowered = line.lower()
        if not line.strip():
            continue
        evidence.extend(
            _match_rule_set(
                ATOMIC_DECLARATION_RULES,
                "atomic_capability",
                lowered,
                base_line_number + index - 1,
                lines,
                base_line_number,
                source_path,
                source_kind,
                source_role,
                support_reference_mode,
                in_fence=in_fence,
            )
        )
        evidence.extend(
            _match_rule_set(
                CONTROL_DECLARATION_RULES,
                "control_semantic",
                lowered,
                base_line_number + index - 1,
                lines,
                base_line_number,
                source_path,
                source_kind,
                source_role,
                support_reference_mode,
                in_fence=in_fence,
            )
        )
    return evidence


def _match_rule_set(
    rules: tuple[tuple[str, str, tuple[str, ...], str], ...],
    subject_type: str,
    lowered: str,
    line_number: int,
    lines: list[str],
    base_line_number: int,
    source_path: str,
    source_kind: str,
    source_role: str,
    support_reference_mode: str,
    *,
    in_fence: bool,
) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = []
    for subject_id, subject_name, patterns, confidence in rules:
        matched_pattern = next((pattern for pattern in patterns if re.search(pattern, lowered)), None)
        if not matched_pattern:
            continue
        excluded_by_rule = _excluded_declaration_rule(subject_id, lowered, in_fence=in_fence)
        if excluded_by_rule:
            continue
        matched_text, line_start, line_end = _build_context_excerpt(lines, line_number, base_line_number=base_line_number)
        evidence.append(
            EvidenceItem(
                category_id=subject_id,
                category_name=subject_name,
                source_path=source_path,
                layer="declaration",
                evidence_type="text_match",
                matched_text=matched_text,
                line_start=line_start,
                line_end=line_end,
                confidence=confidence,
                rule_id=f"decl.{subject_type}.{subject_id.lower()}",
                source_kind=source_kind,
                source_role=source_role,
                support_reference_mode=support_reference_mode,
                subject_type=subject_type,
                matched_pattern=matched_pattern,
                evidence_strength="strong" if confidence == "high" else "medium",
            )
        )
    return evidence


def _build_context_excerpt(
    lines: list[str],
    center_line_number: int,
    radius: int = 1,
    *,
    base_line_number: int = 1,
) -> tuple[str, int, int]:
    relative_center = center_line_number - base_line_number + 1
    start_index = max(0, relative_center - 1 - radius)
    end_index = min(len(lines), relative_center + radius)
    excerpt = "\n".join(lines[start_index:end_index]).strip()[:400]
    return excerpt, base_line_number + start_index, base_line_number + end_index - 1


def _excluded_declaration_rule(subject_id: str, lowered: str, *, in_fence: bool) -> str | None:
    if in_fence and subject_id in {"X1", "X2"}:
        return "fenced_code_block"
    for pattern in NEGATIVE_DECLARATION_RULES.get(subject_id, ()):
        if re.search(pattern, lowered):
            return "negative_text_guard"
    return None


def _safe_read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _body_start_line_number(skill_text: str) -> int:
    match = FRONTMATTER_RE.search(skill_text)
    if not match:
        return 1
    return skill_text[: match.end()].count("\n") + 1
