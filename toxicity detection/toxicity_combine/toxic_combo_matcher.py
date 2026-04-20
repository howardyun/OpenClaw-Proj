#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
可复用的毒性组合匹配模块。

核心接口：
    get_toxity_combo(permissions, ...)

用法示例：
    from toxic_combo_matcher import get_toxity_combo

    result = get_toxity_combo(["R8", "I3", "O5"])
    print(result["exact_hit_count"])
    print(result["exact_hits"])
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Set

DEFAULT_TEMPLATE_PATH = Path('toxic_permission_templates_flat.json')
OP_CODE_RE = re.compile(r'\b([A-Z]\d+)\b', re.IGNORECASE)


@lru_cache(maxsize=8)
def load_templates(template_path_str: str = str(DEFAULT_TEMPLATE_PATH)) -> List[Dict[str, Any]]:
    template_path = Path(template_path_str)
    with template_path.open('r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f'模板文件格式不正确，期望 list，实际为 {type(data).__name__}')
    return data


def normalize_codes_from_any(obj: Any) -> Set[str]:
    """从任意输入中提取权限码集合，如 R8 / I3 / O5。"""
    codes: Set[str] = set()

    def visit(x: Any) -> None:
        if x is None:
            return
        if isinstance(x, str):
            for code in OP_CODE_RE.findall(x.upper()):
                codes.add(code.upper())
            return
        if isinstance(x, dict):
            preferred_keys = [
                'minimum_permission_set', 'permissions', 'permission_set',
                'atomic_op_codes', 'ops', 'codes'
            ]
            for key in preferred_keys:
                if key in x:
                    visit(x[key])
            for v in x.values():
                visit(v)
            return
        if isinstance(x, (list, tuple, set)):
            for item in x:
                visit(item)
            return
        visit(str(x))

    visit(obj)
    return codes


def parse_permissions_input(permissions: Any) -> Set[str]:
    """
    支持三类输入：
    1) list/tuple/set，例如 ["R8", "I3", "O5"]
    2) str，例如 'R8（读取连接器数据） + I3（跨系统数据搬运） + O5（自动外发）'
    3) dict，例如 {"minimum_permission_set": ["R8", "I3", "O5"]}
    """
    if permissions is None:
        return set()

    if isinstance(permissions, str):
        text = permissions.strip()
        if not text:
            return set()
        try:
            obj = json.loads(text)
            return normalize_codes_from_any(obj)
        except json.JSONDecodeError:
            return normalize_codes_from_any(text)

    return normalize_codes_from_any(permissions)


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
            'atomic_ops': tpl.get('atomic_ops', []),
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


def get_toxity_combo(
    permissions: Any,
    template_file: str | Path = DEFAULT_TEMPLATE_PATH,
    include_near: bool = False,
    near_threshold: int = 1,
) -> Dict[str, Any]:
    """
    传入权限集合，返回命中的毒性组合信息。

    参数：
        permissions:
            - ["R8", "I3", "O5"]
            - "R8（读取连接器数据） + I3（跨系统数据搬运） + O5（自动外发）"
            - {"minimum_permission_set": ["R8", "I3", "O5"]}
        template_file:
            毒性模板文件路径，默认 /mnt/data/toxic_permission_templates_flat.json
        include_near:
            是否返回接近命中的组合
        near_threshold:
            接近命中允许缺少的权限数量

    返回：
        {
          "input_codes": [...],
          "exact_hit_count": 1,
          "exact_hits": [...],
          "near_hit_count": 0,
          "near_hits": [...]
        }
    """
    user_codes = parse_permissions_input(permissions)
    templates = load_templates(str(Path(template_file)))
    return match_templates(
        user_codes=user_codes,
        templates=templates,
        include_near=include_near,
        near_threshold=near_threshold,
    )


# 可选：给一个更标准的别名，避免后面改名麻烦
get_toxicity_combo = get_toxity_combo


if __name__ == '__main__':

    demo = get_toxity_combo(["R8", "I3", "O5", "A3", "W2","R6","X2"])
    print(json.dumps(demo, ensure_ascii=False, indent=2))
