from __future__ import annotations

import csv
import re
from pathlib import Path

from .models import MatrixCategory


CATEGORY_ID_MAP = {
    "会话与上下文访问": "session_context_access",
    "文件与知识库访问": "file_knowledge_access",
    "外部信息访问": "external_information_access",
    "检索与查询执行": "retrieval_query_execution",
    "代码与计算执行": "code_computation_execution",
    "内容生成与文件处理": "content_generation_file_processing",
    "草稿与建议写入": "draft_suggestion_write",
    "受确认的单次写入": "confirmed_single_write",
    "自动或批量写入": "automatic_batch_write",
    "跨应用身份代理": "cross_app_identity_proxy",
    "定时与周期自动化": "scheduled_periodic_automation",
    "条件触发与监控自动化": "conditional_trigger_monitoring_automation",
}


def parse_matrix_file(matrix_path: Path) -> list[MatrixCategory]:
    text = matrix_path.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.strip()]
    reader = csv.reader(lines, delimiter="\t")
    rows = list(reader)
    if not rows:
        raise ValueError(f"Matrix file is empty: {matrix_path}")
    header = rows[0]
    expected_header = ["大类", "小类", "安全定义", "数据等级", "主要风险", "控制要求"]
    if header != expected_header:
        raise ValueError(f"Unexpected matrix header in {matrix_path}: {header}")

    categories: list[MatrixCategory] = []
    current_major = ""
    for row in rows[1:]:
        normalized = [cell.strip() for cell in row]
        if len(normalized) == 1:
            current_major = normalized[0]
            continue
        if len(normalized) == 6:
            _, subcategory, definition, data_level, risks, controls = normalized
        elif len(normalized) == 5:
            subcategory, definition, data_level, risks, controls = normalized
        else:
            raise ValueError(f"Unexpected matrix row shape in {matrix_path}: {row}")
        if not subcategory:
            continue
        category_id = CATEGORY_ID_MAP.get(subcategory)
        if not category_id:
            raise ValueError(f"Unknown matrix category: {subcategory}")
        categories.append(
            MatrixCategory(
                category_id=category_id,
                major_category=current_major,
                subcategory=subcategory,
                security_definition=definition,
                data_level=data_level,
                primary_risks=_split_values(risks),
                control_requirements=_split_controls(controls),
            )
        )
    return categories


def _split_values(value: str) -> list[str]:
    cleaned = value.replace("（", "(").replace("）", ")")
    parts = re.split(r"[、,，]", cleaned)
    return [part.strip() for part in parts if part.strip()]


def _split_controls(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[；;]", value) if part.strip()]
