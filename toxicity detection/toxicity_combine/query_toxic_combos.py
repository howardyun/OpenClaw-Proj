#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给定一组权限，匹配全部命中的毒性权限组合。

默认使用 /mnt/data/toxic_permission_templates_flat.json 作为模板库。

用法示例：
1) 直接传 JSON 数组：
   python query_toxic_combos.py '["R8", "I3", "O5", "A3"]'

2) 传带中文说明的字符串：
   python query_toxic_combos.py 'R8（读取连接器数据） + I3（跨系统数据搬运） + O5（自动外发）'

3) 传 JSON 对象（支持从 minimum_permission_set 中抽取）：
   python query_toxic_combos.py '{"minimum_permission_set": ["R8", "I3", "O5"]}'

4) 从文件读取：
   python query_toxic_combos.py --input-file permissions.json

5) 同时输出接近命中（只差 1 个权限）：
   python query_toxic_combos.py '["R8", "I3"]' --include-near --near-threshold 1
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple

DEFAULT_TEMPLATE_PATH = Path('./toxic_permission_templates_flat.json')
OP_CODE_RE = re.compile(r'\b([A-Z]\d+)\b', re.IGNORECASE)


def load_templates(template_path: Path) -> List[Dict[str, Any]]:
    with template_path.open('r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f'模板文件格式不正确，期望 list，实际为 {type(data).__name__}')
    return data


def normalize_codes_from_any(obj: Any) -> Set[str]:
    """从任意输入中尽量提取权限码集合，如 R8 / I3 / O5。"""
    codes: Set[str] = set()

    def visit(x: Any) -> None:
        if x is None:
            return
        if isinstance(x, str):
            for code in OP_CODE_RE.findall(x.upper()):
                codes.add(code.upper())
            return
        if isinstance(x, dict):
            # 优先尝试常见字段
            preferred_keys = [
                'minimum_permission_set', 'permissions', 'permission_set',
                'atomic_op_codes', 'ops', 'codes'
            ]
            for key in preferred_keys:
                if key in x:
                    visit(x[key])
            # 再兜底扫所有 value
            for v in x.values():
                visit(v)
            return
        if isinstance(x, (list, tuple, set)):
            for item in x:
                visit(item)
            return
        # 其他类型转字符串兜底
        visit(str(x))

    visit(obj)
    return codes


def parse_user_input(raw_text: str) -> Set[str]:
    raw_text = raw_text.strip()
    if not raw_text:
        return set()

    # 先尝试按 JSON 解析
    try:
        obj = json.loads(raw_text)
        return normalize_codes_from_any(obj)
    except json.JSONDecodeError:
        pass

    # 再按普通文本处理
    return normalize_codes_from_any(raw_text)


def match_templates(
    user_codes: Set[str],
    templates: List[Dict[str, Any]],
    include_near: bool = False,
    near_threshold: int = 1,
) -> Dict[str, Any]:
    exact_hits: List[Dict[str, Any]] = []
    near_hits: List[Dict[str, Any]] = []

    for tpl in templates:
        required_codes = {str(x).upper() for x in tpl.get('atomic_op_codes', [])}
        if not required_codes:
            continue

        matched = sorted(required_codes & user_codes)
        missing = sorted(required_codes - user_codes)
        extra = sorted(user_codes - required_codes)

        item = {
            'combo_id': tpl.get('combo_id'),
            'category_name': tpl.get('category_name'),
            'tier_combo': tpl.get('tier_combo', []),
            'tier_combo_text': tpl.get('tier_combo_text'),
            'atomic_ops_text': tpl.get('atomic_ops_text'),
            'atomic_op_codes': sorted(required_codes),
            'effect': tpl.get('effect'),
            'risk': tpl.get('risk', []),
            'risk_text': tpl.get('risk_text'),
            'explanation': tpl.get('explanation'),
            'matched_op_codes': matched,
            'missing_op_codes': missing,
            'extra_input_codes': extra,
            'match_ratio': round(len(matched) / len(required_codes), 4),
        }

        if required_codes.issubset(user_codes):
            exact_hits.append(item)
        elif include_near and len(missing) <= near_threshold:
            near_hits.append(item)

    exact_hits.sort(key=lambda x: (x['category_name'] or '', x['combo_id'] or ''))
    near_hits.sort(key=lambda x: (len(x['missing_op_codes']), -(x['match_ratio']), x['combo_id'] or ''))

    return {
        'input_codes': sorted(user_codes),
        'exact_hit_count': len(exact_hits),
        'exact_hits': exact_hits,
        'near_hit_count': len(near_hits),
        'near_hits': near_hits,
    }


def build_summary(result: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"输入权限码: {', '.join(result['input_codes']) if result['input_codes'] else '(空)'}")
    lines.append(f"精确命中: {result['exact_hit_count']}")

    if result['exact_hits']:
        lines.append('--- 精确命中列表 ---')
        for hit in result['exact_hits']:
            lines.append(
                f"[{hit['combo_id']}] {hit['category_name']} | 需要: {', '.join(hit['atomic_op_codes'])} | 风险: {hit.get('risk_text', '')}"
            )

    if result['near_hits']:
        lines.append(f"接近命中: {result['near_hit_count']}")
        lines.append('--- 接近命中列表 ---')
        for hit in result['near_hits']:
            lines.append(
                f"[{hit['combo_id']}] {hit['category_name']} | 已命中: {', '.join(hit['matched_op_codes'])} | 缺少: {', '.join(hit['missing_op_codes'])}"
            )

    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description='查询毒性权限组合')
    parser.add_argument('permissions', nargs='?', help='权限输入，支持 JSON 或普通字符串')
    parser.add_argument('--input-file', type=str, help='从文件中读取权限输入')
    parser.add_argument('--template-file', type=str, default=str(DEFAULT_TEMPLATE_PATH), help='模板文件路径')
    parser.add_argument('--include-near', action='store_true', help='输出接近命中的组合')
    parser.add_argument('--near-threshold', type=int, default=1, help='接近命中阈值（缺少几个权限以内）')
    parser.add_argument('--output-file', type=str, help='将结果 JSON 写入文件')
    parser.add_argument('--pretty', action='store_true', help='额外打印简洁摘要')
    args = parser.parse_args()

    if not args.permissions and not args.input_file:
        parser.error('必须提供 permissions 或 --input-file')

    if args.input_file:
        raw_text = Path(args.input_file).read_text(encoding='utf-8')
    else:
        raw_text = args.permissions or ''

    user_codes = parse_user_input(raw_text)
    templates = load_templates(Path(args.template_file))
    result = match_templates(
        user_codes=user_codes,
        templates=templates,
        include_near=args.include_near,
        near_threshold=args.near_threshold,
    )

    if args.output_file:
        Path(args.output_file).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.pretty:
        print('\n' + build_summary(result))




if __name__ == '__main__':
    main()
