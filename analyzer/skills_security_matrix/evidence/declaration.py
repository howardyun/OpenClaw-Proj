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
    ("R1", "读取当前用户输入", (r"\buser\s+(?:input|prompt)\b", r"\bcurrent\s+(?:input|prompt)\b", r"\binput\s+(?:from|provided by)\s+(?:the\s+)?user\b"), "medium"),
    ("R2", "读取当前会话历史", (r"\bchat history\b", r"\bconversation history\b", r"\bmessage history\b", r"\bprevious turns?\b", r"\bprior messages?\b"), "high"),
    ("R3", "读取历史会话", (r"\bhistorical sessions?\b", r"\bpast sessions?\b", r"\bcross-session\b", r"\bhistory records?\b", r"\bsaved sessions?\b"), "medium"),
    ("R4", "读取会话附件", (r"\battachments?\b", r"\buploaded files?\b", r"\bfile input\b", r"\buser-provided files?\b"), "high"),
    ("R5", "读取本地 repo 文件", (r"\bread (?:project|repo|repository|workspace) files\b", r"\blocal references\b", r"\bproject files\b", r"\bworkspace files\b"), "high"),
    ("R6", "读取本地任意路径文件", (r"\babsolute paths?\b", r"\boutside the repo\b", r"\bsystem files?\b", r"\barbitrary local paths?\b", r"\bany local files?\b"), "high"),
    ("R7", "读取知识库或文档库", (r"\bknowledge base\b", r"\binternal docs\b", r"\bdocument library\b", r"\breference library\b", r"\b(?:query|read|search|use|consult) (?:the )?(?:docs|documentation|references)\b"), "medium"),
    ("R8", "读取连接器数据", (r"\bconnectors?\b", r"\b(?:read|query|search|fetch|access) (?:gmail|slack|github|notion)\b", r"\b(?:gmail|slack|github|notion) (?:connector|data|workspace|repository|repo|issues?|prs?|messages?)\b"), "high"),
    ("R9", "批量枚举文件或资源", (r"\blist (?:files|resources|connectors?|repositories|repos|issues?|documents?)\b", r"\benumerate\b", r"\bscan all\b", r"\bbulk export\b", r"\bsearch files\b"), "medium"),
    ("R10", "跨源数据拼接读取", (r"\bcombine .*?(?:files|connectors?|web|attachments?)\b", r"\bcross-source\b", r"\bmerge .*?data\b", r"\bjoin .*?(?:sources|datasets?)\b"), "medium"),
    ("Q1", "只读查询或搜索", (r"\bsearch\b", r"\bquery\b", r"\bfilter\b", r"\blist (?:results?|items?|records?|resources?|files?)\b", r"\bread-only query\b"), "medium"),
    ("Q2", "结构化筛选与聚合", (r"\baggregate\b", r"\bgroup by\b", r"\bselect (?:fields?|columns?|records?|items?)\b", r"\bstructured filter\b", r"\bfacet(?:ed)? search\b"), "medium"),
    ("Q3", "敏感对象查询", (r"\bcalendar\b", r"\bcontacts?\b", r"\btickets?\b", r"\bemails?\b", r"\bmailbox\b"), "medium"),
    ("Q4", "自动推荐或判定", (r"\brecommend(?:ation|ations|ed|s)?\b", r"\bsuggest(?:ion|ions|ed|s)?\b", r"\bclassif(?:y|ies|ication|ications)\b", r"\bprioriti(?:ze|zes|zed|zation|se|ses|sed|sation)\b", r"\brank(?:ing|ed|s)?\b"), "medium"),
    ("S1", "硬件摄像头调用", (r"\bcamera\b", r"\btake photos?\b", r"\brecord video\b", r"\blive video\b"), "high"),
    ("S2", "硬件麦克风调用", (r"\bmicrophone\b", r"\brecord audio\b", r"\bvoice input\b", r"\benvironment audio\b"), "high"),
    ("S3", "生物特征识别访问", (r"\bfingerprint\b", r"\bface id\b", r"\bbiometric\b", r"\bfacial recognition\b"), "high"),
    ("S4", "精确地理位置获取", (r"\bgps\b", r"\blatitude\b", r"\blongitude\b", r"\bgeolocation\b", r"\bcurrent location\b"), "high"),
    ("S5", "后台位置持续追踪", (r"\bbackground location\b", r"\btrack location\b", r"\blocation updates\b", r"\blocation monitoring\b"), "high"),
    ("S6", "扫描附近硬件设备", (r"\bbluetooth\b", r"\bnfc\b", r"\bnearby devices\b", r"\bwifi scan\b"), "medium"),
    ("S7", "系统状态读取", (r"\bsystem logs?\b", r"\bruntime parameters?\b", r"\bsystem properties\b", r"\bsystem status\b"), "medium"),
    ("W1", "访问公开网页", (r"\bbrowse public webpages?\b", r"\bpublic web\b", r"\bbrowse the web\b", r"\bwebpages?\b", r"\bweb pages?\b"), "high"),
    ("W2", "调用外部公开 API", (r"\bpublic api\b", r"\brest api\b", r"\bsdk api\b", r"\bremote endpoints?\b", r"\bapi endpoints?\b"), "high"),
    ("W3", "下载外部文件", (r"\bdownload files?\b", r"\bfetch files?\b", r"\bremote files?\b", r"\bexternal files?\b"), "high"),
    ("W4", "使用外部搜索结果驱动后续动作", (r"\bsearch results? .*?(?:plan|action|execute)\b", r"\bweb results? .*?(?:plan|execute|action)\b", r"\bdrive actions? from search\b"), "medium"),
    ("U1", "屏幕内容捕获", (r"\bscreenshots?\b", r"\bscreen capture\b", r"\brecord screen\b", r"\bcapture ui\b"), "high"),
    ("U2", "模拟 UI 操作控制", (r"\bclick buttons?\b", r"\bsimulate clicks?\b", r"\bfill forms?\b", r"\bui automation\b", r"\bsimulate ui\b"), "high"),
    ("U3", "系统剪贴板读写", (r"\bclipboard\b", r"\bcopy/paste\b", r"\bpasteboard\b"), "medium"),
    ("U4", "键盘输入消费", (r"\bkeyboard input\b", r"\bkeystrokes?\b", r"\bhotkeys?\b", r"\bkey events?\b"), "high"),
    ("C1", "多媒体输出控制", (r"\bscreen brightness\b", r"\bvolume control\b", r"\bcast screen\b", r"\bmedia output\b"), "medium"),
    ("C2", "外发消息或通知", (r"\bpush notifications?\b", r"\bsend notifications?\b", r"\bsms\b", r"\bin-app messages?\b"), "medium"),
    ("C3", "邮件/IM 发送", (r"\bsend emails?\b", r"\bsend slack\b", r"\bwechat\b", r"\binstant messages?\b", r"\bim\b"), "high"),
    ("C4", "实时流数据上传", (r"\bstream upload\b", r"\breal-time upload\b", r"\bpush stream\b", r"\blive data\b"), "high"),
    ("C5", "双向实时通道建立", (r"\bwebsockets?\b", r"\bsse\b", r"\bpersistent connection\b", r"\breal-time channel\b"), "high"),
    ("X1", "执行 shell 命令", (r"\bbash\b", r"\bsh\b", r"\bexec\b", r"\bspawn\b", r"\bshell commands?\b"), "high"),
    ("X2", "执行解释器代码", (r"\brun python\b", r"\brun node\b", r"\bexecute code\b", r"\binterpreter code\b", r"\bevaluate code\b"), "high"),
    ("X3", "执行容器任务", (r"\bdocker\b", r"\bcontainers?\b", r"\bjob runner\b", r"\bkubectl\b"), "high"),
    ("X4", "安装依赖或拉取包", (r"\bpip install\b", r"\bnpm install\b", r"\bapt(?:-get)? install\b", r"\bcargo install\b"), "high"),
    ("X5", "执行环境可联网", (r"\bnetwork access\b", r"\binternet access\b", r"联网执行", r"\bcode .*?network\b"), "medium"),
    ("X6", "执行环境可写文件系统", (r"\bwrite filesystem\b", r"\bmodify local files\b", r"\bwritable filesystem\b", r"\bwrite files\b"), "medium"),
    ("X7", "访问环境变量或凭证", (r"\benvironment variables?\b", r"\bsecrets?\b", r"\b(?:access|auth|api|bearer) tokens?\b", r"\bcredential store\b", r"\bcredentials?\b"), "high"),
    ("X8", "调用外部二进制或本地工具", (r"\bgit\b", r"\bcurl\b", r"\bdocker\b", r"\bcli\b", r"\blocal tools?\b"), "medium"),
    ("G1", "生成文本建议", (r"\bgenerate .*?summary\b", r"\banalysis\b", r"\brecommendations?\b", r"\bsource-backed answers\b"), "medium"),
    ("G2", "生成结构化草稿", (r"\bdrafts?\b", r"\bpre-fill\b", r"\bprefill\b", r"\bpr description\b", r"\bform drafts?\b"), "high"),
    ("G3", "写本地临时文件", (r"\btemp files?\b", r"\btemporary files?\b", r"\bcache files?\b", r"\breport files?\b", r"\boutput files?\b"), "medium"),
    ("G4", "写本地项目文件", (r"\bedit repo\b", r"\bmodify files\b", r"\bupdate project files\b", r"\bworkspace files\b"), "high"),
    ("G5", "批量本地写文件", (r"\bbatch update\b", r"\bbulk edit\b", r"\bmulti-file\b", r"\bmultiple files\b"), "medium"),
    ("O1", "创建外部草稿", (r"\bcreate drafts?\b", r"\bsave drafts?\b", r"\bexternal drafts?\b"), "medium"),
    ("O2", "外部单对象写入", (r"\bupdate one\b", r"\bsingle write\b", r"\bupdate one object\b", r"\bcreate one object\b"), "medium"),
    ("O3", "外部多对象批量写入", (r"\bbatch\b", r"\bbulk\b", r"\bauto-apply\b", r"\bmany objects\b"), "medium"),
    ("O4", "破坏性写入", (r"\bdelete\b", r"\barchive\b", r"\breset\b", r"\brevoke\b"), "high"),
    ("O5", "自动外发", (r"\bsend automatically\b", r"\bpublish automatically\b", r"\bpost automatically\b", r"\bwithout second confirmation\b"), "medium"),
    ("K1", "修改系统级设置", (r"\bsystem settings?\b", r"\bglobal settings?\b", r"\bsecurity settings?\b"), "high"),
    ("K2", "硬件开关控制", (r"\bwifi switch\b", r"\bbluetooth switch\b", r"\binfrared\b", r"\bhardware switch\b"), "high"),
    ("K3", "应用程序管理", (r"\binstall apps?\b", r"\buninstall apps?\b", r"\bapplication management\b"), "high"),
    ("K4", "闹钟与唤醒管理", (r"\balarms?\b", r"\bwake lock\b", r"\bwake-up\b", r"\bschedule wake\b"), "medium"),
    ("K5", "进程强制管控", (r"\bkill process\b", r"\brestart process\b", r"\bterminate process\b"), "high"),
    ("K6", "全局环境配置修改", (r"\bsystem language\b", r"\bsystem font\b", r"\bglobal environment\b", r"\blocale settings\b"), "medium"),
    ("A1", "用户显式单次触发", (r"\bsingle user request\b", r"\bonly when explicitly requested\b", r"\bcurrent instruction\b"), "medium"),
    ("A2", "需确认后执行", (r"\bafter user confirmation\b", r"\bafter approval\b", r"\bwait for confirmation\b", r"\bapprove before\b"), "high"),
    ("A3", "定时调度", (r"\bevery hour\b", r"\bdaily\b", r"\bscheduled\b", r"\bcron\b", r"\bscheduler\b"), "high"),
    ("A4", "事件触发", (r"\bon change\b", r"\bwebhook\b", r"\bon event\b", r"\bon message\b", r"\btriggered by\b"), "medium"),
    ("A5", "持续监控", (r"\bmonitor\b", r"\bwatch\b", r"\bpoll\b", r"\blong-running\b"), "high"),
    ("A6", "触发后自动动作", (r"\btrigger alerts\b", r"\bautomatically write\b", r"\bdirectly execute\b", r"\bauto-run action\b"), "medium"),
    ("A7", "自动重试或循环执行", (r"\bretry\b", r"\bbackoff\b", r"\brepeated attempts\b", r"\bloop execution\b"), "medium"),
    ("I1", "使用当前用户身份访问单系统", (r"\buser identity\b", r"\bauthorized identity\b", r"\bsingle system\b", r"\bconnector access\b"), "medium"),
    ("I2", "跨系统身份代理", (r"\bmultiple systems?\b", r"\bcross-system\b", r"\bconnectors?\b", r"\bdesktop app integration\b"), "medium"),
    ("I3", "跨系统数据搬运", (r"\b(?:copy|sync|move|transfer) data between\b", r"\bsync across systems?\b", r"\b(?:copy|sync|move|transfer) .*? from .*? to\b", r"\bfrom .*? to .*? (?:copy|sync|move|transfer)\b"), "medium"),
    ("I4", "凭证注入到外部调用", (r"\bbearer token\b", r"\bapi key\b", r"\bauthorization header\b", r"\btoken\s*="), "high"),
    ("I5", "隐式权限继承", (r"\bexisting connector\b", r"\binherited permissions?\b", r"\bimplicit permissions?\b"), "medium"),
    ("I6", "身份令牌深度管理", (r"\bcredential management\b", r"\bmanage credentials?\b", r"\blong-lived (?:tokens?|credentials?)\b", r"\bsystem credential\b"), "high"),
    ("I7", "跨端或跨设备协同", (r"\bother devices?\b", r"\bcross-device\b", r"\banother terminal\b", r"\bpaired devices?\b", r"\banother devices?\b"), "medium"),
)

CONTROL_DECLARATION_RULES = (
    ("C1", "只读约束", (r"\bread[- ]only\b", r"\breadonly\b", r"\bgather public information only\b"), "high"),
    ("C2", "范围限制", (r"\blocal references\b", r"\bproject files only\b", r"\bpublic webpages?\b", r"\bapproved domains only\b"), "medium"),
    ("C3", "显式确认", (r"\bafter user confirmation\b", r"\bafter approval\b", r"\bwait for confirmation\b", r"\brequires? confirmation\b"), "high"),
    ("C4", "预览或回显", (r"\bpreview\b", r"\bdiff\b", r"\bshow changes\b", r"\breview changes\b"), "medium"),
    ("C5", "dry-run", (r"\bdry[-_ ]run\b",), "medium"),
    ("C6", "回滚或幂等", (r"\brollback\b", r"\bidempotent\b"), "medium"),
    ("C7", "白名单", (r"\bwhitelist\b", r"\ballowlist\b", r"\bapproved domains\b"), "medium"),
    ("C8", "脱敏", (r"\bredact\b", r"\bmask sensitive\b", r"\bdesensiti", r"\bsanitize sensitive\b"), "medium"),
    ("C9", "审计日志", (r"\baudit logs?\b", r"\baccess logs?\b", r"\bretain logs\b"), "medium"),
    ("C10", "kill switch", (r"\bkill switch\b", r"\bpause automation\b", r"\bstop switch\b"), "medium"),
    ("C11", "频率或规模限制", (r"\brate limits?\b", r"\bbatch caps?\b", r"\bretry caps?\b"), "medium"),
    ("C12", "高敏禁外连", (r"\bno network\b", r"\bdisable network\b", r"\boffline only\b"), "medium"),
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
