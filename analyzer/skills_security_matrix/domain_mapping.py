from __future__ import annotations

from dataclasses import dataclass


APPROXIMATE_MATCH_THRESHOLD = 0.4


@dataclass(frozen=True, slots=True)
class DomainDefinition:
    domain_id: str
    domain_name: str
    typical_examples: str
    minimum_permission_set: frozenset[str]


# Keep this list in sync with analyzer/功能映射表.md.
DOMAIN_DEFINITIONS: tuple[DomainDefinition, ...] = (
    DomainDefinition("Dom-1", "纯计算/逻辑类", "数学计算、单位换算、规则判断", frozenset({"R1", "G1"})),
    DomainDefinition("Dom-2", "会话写作/改写类", "润色、翻译、摘要改写、标题生成", frozenset({"R1", "R2", "G1"})),
    DomainDefinition("Dom-3", "在线信息检索类", "天气预报、股票查询、搜文章", frozenset({"R1", "W1", "W2", "Q1", "G1"})),
    DomainDefinition("Dom-4", "外部内容采集类", "下载公开 PDF、抓取网页内容、拉 API 数据", frozenset({"R1", "W2", "W3", "Q1"})),
    DomainDefinition("Dom-5", "私有知识读取/问答类", "读附件答题、读知识库、读连接器内容后总结", frozenset({"R1", "R4", "R7", "R8", "Q1", "G1"})),
    DomainDefinition("Dom-6", "资源搜索/导航类", "找文件、找邮件、找某份文档、找某条记录", frozenset({"R1", "R4", "R7", "R8", "R9", "Q1", "G1"})),
    DomainDefinition("Dom-7", "只读分析/报表类", "BI 查询、聚合统计、筛选报表、只读数据分析", frozenset({"R1", "R7", "R8", "Q2", "G1"})),
    DomainDefinition("Dom-8", "环境感知类", "拍照识别、语音记录理解、定位感知、系统状态读取", frozenset({"R1", "S1", "S2", "S4", "S7", "G1"})),
    DomainDefinition("Dom-9", "个人助理/处理类", "简历润色、邮件草拟、日程建议、纪要整理", frozenset({"R1", "R4", "R7", "R8", "Q3", "G2", "O1"})),
    DomainDefinition("Dom-10", "通信/通知类", "发邮件、发 IM、发短信、推送通知、创建草稿", frozenset({"R1", "G2", "C2", "C3", "O1"})),
    DomainDefinition("Dom-11", "UI 代操作类", "代填表、代点按钮、网页前台辅助操作", frozenset({"R1", "U2"})),
    DomainDefinition("Dom-12", "受限文档/工件编辑类", "Word/PDF/PPT 编辑、表格格式化、图片裁剪", frozenset({"R1", "R4", "R5", "G3", "G4"})),
    DomainDefinition("Dom-13", "系统/开发工具类", "代码解释器、脚本执行、批量重命名、repo 改写", frozenset({"R1", "R5", "X1", "X2", "X6", "X8"})),
    DomainDefinition("Dom-14", "外部业务对象写入类", "改日历事件、写 CRM、更新工单、创建 SaaS 记录", frozenset({"R1", "R8", "Q3", "G2", "O2"})),
    DomainDefinition("Dom-15", "系统/设备管理类", "修改系统设置、安装/卸载应用、控制 WiFi/蓝牙、杀进程", frozenset({"R1", "K1", "K2", "K3", "K5"})),
    DomainDefinition("Dom-16", "自动化流程类", "定时任务、事件触发、持续监控后自动处理", frozenset({"R1", "G1", "A3", "A4", "A5"})),
    DomainDefinition("Dom-17", "跨系统身份代理类", "代表用户跨多系统联动、A 系统读 B 系统写", frozenset({"R1", "R8", "Q3", "G2", "O2", "C3", "U2", "I2", "I3"})),
    DomainDefinition("Dom-18", "主动安全测试类", "红队测试、渗透测试、SMTP 安全测试、端口探测、漏洞验证、授权扫描、攻击面验证", frozenset({"R1", "W1", "W2", "Q1", "G1", "X1", "X8"})),
    DomainDefinition("Dom-19", "外部设备/物理设备控制类", "实验室机器人控制、摄像头云台控制、车牌识别设备、IoT 设备控制、机械臂操作、外部传感器读取、硬件开关控制", frozenset({"R1", "S1", "S6", "S7", "K2", "K5", "G1"})),
)


def allowed_domain_ids() -> list[str]:
    return [definition.domain_id for definition in DOMAIN_DEFINITIONS]


def allowed_domain_definitions() -> list[dict[str, str]]:
    return [
        {
            "domain_id": definition.domain_id,
            "domain_name": definition.domain_name,
            "typical_examples": definition.typical_examples,
        }
        for definition in DOMAIN_DEFINITIONS
    ]


def resolve_domain_from_atomic_ids(atomic_ids: list[str]) -> str:
    normalized_atoms = frozenset(atomic_ids)
    if not normalized_atoms:
        return ""

    scored_matches: list[tuple[float, int, DomainDefinition]] = []
    for definition in DOMAIN_DEFINITIONS:
        overlap_count = len(definition.minimum_permission_set & normalized_atoms)
        if overlap_count == 0:
            continue
        score = overlap_count / len(definition.minimum_permission_set)
        if score < APPROXIMATE_MATCH_THRESHOLD:
            continue
        scored_matches.append((score, overlap_count, definition))

    if not scored_matches:
        return ""

    _, _, best_match = max(scored_matches, key=_domain_sort_key)
    return best_match.domain_id


def _domain_sort_key(item: tuple[float, int, DomainDefinition]) -> tuple[float, int, int, int]:
    score, overlap_count, definition = item
    return (
        score,
        overlap_count,
        len(definition.minimum_permission_set),
        -_domain_number(definition.domain_id),
    )


def _domain_number(domain_id: str) -> int:
    return int(domain_id.split("-", 1)[1])
