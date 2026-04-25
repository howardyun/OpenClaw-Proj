#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扫描 CSV 中每个 Skill 的 declaration 原子权限，统计命中的毒性组合数量。

前提：
1. 当前目录或同目录下存在 toxic_combo_matcher.py
2. 需要准备 toxic_permission_templates_flat.json，并在 CONFIG 中配置路径

输入：
- 一个 CSV，每行代表一个 Skill（建议已经完成去重）
- 默认读取 declaration_atomic_ids 列；如果你的列名不同，改 CONFIG 即可

输出：
- 一个新的 CSV，记录每个 skill 命中的毒性组合数量及摘要信息
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from toxic_combo_matcher import get_toxity_combo


CONFIG = {
    # 输入 CSV：每个 skill 一条记录
    "input_csv": "../Data/ProcessData/skills_merged_with_decl_impl.csv",

    # 输出结果 CSV：记录每个 skill 的毒性组合统计
    "output_csv": "../Data/Result/declaration_toxic_combo_stats.csv",

    # 毒性模板 JSON 路径（必须提供）
    "template_file": "toxic_permission_templates_flat.json",

    # 用哪个列做扫描；你当前 CSV 对应的是 declaration_atomic_ids
    "declaration_column": "declaration_atomic_ids",

    # skill 唯一标识列
    "skill_id_column": "name",

    # 额外保留到结果里的原始列
    "keep_columns": ["name", "domain"],

    # 是否输出接近命中的组合
    "include_near": False,
    "near_threshold": 1,

    # 是否在结果里保留详细 JSON（方便后续人工分析）
    "include_detail_json": True,
}


def validate_config(config: Dict[str, Any]) -> None:
    input_csv = Path(config["input_csv"])
    if not input_csv.exists():
        raise FileNotFoundError(f"找不到输入 CSV：{input_csv}")

    template_file = Path(config["template_file"])
    if not template_file.exists():
        raise FileNotFoundError(
            f"找不到毒性模板文件：{template_file}\n"
            f"请把 toxic_permission_templates_flat.json 放到该路径，或修改 CONFIG['template_file']"
        )


def load_input_csv(input_csv: str) -> pd.DataFrame:
    return pd.read_csv(input_csv)


def validate_required_columns(
    df: pd.DataFrame,
    skill_id_column: str,
    declaration_column: str,
    keep_columns: List[str],
) -> None:
    required = {skill_id_column, declaration_column, *keep_columns}
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"CSV 缺少必要列：{missing}\n当前列为：{list(df.columns)}")


def safe_str(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def compact_hits(hit_items: List[Dict[str, Any]]) -> Dict[str, str]:
    combo_ids = [str(item.get("combo_id", "")) for item in hit_items if item.get("combo_id")]
    combo_names = [str(item.get("category_name", "")) for item in hit_items if item.get("category_name")]
    atomic_codes = [
        "+".join(item.get("atomic_op_codes", []))
        for item in hit_items
        if item.get("atomic_op_codes")
    ]
    return {
        "combo_ids": "|".join(combo_ids),
        "combo_names": "|".join(combo_names),
        "combo_atomic_codes": "|".join(atomic_codes),
    }


def scan_one_skill(
    declaration_value: Any,
    template_file: str,
    include_near: bool,
    near_threshold: int,
) -> Dict[str, Any]:
    result = get_toxity_combo(
        permissions=declaration_value,
        template_file=template_file,
        include_near=include_near,
        near_threshold=near_threshold,
    )

    exact_summary = compact_hits(result.get("exact_hits", []))
    near_summary = compact_hits(result.get("near_hits", []))

    return {
        "parsed_input_codes": ",".join(result.get("input_codes", [])),
        "toxic_combo_count": int(result.get("exact_hit_count", 0)),
        "toxic_combo_ids": exact_summary["combo_ids"],
        "toxic_combo_names": exact_summary["combo_names"],
        "toxic_combo_atomic_codes": exact_summary["combo_atomic_codes"],
        "near_hit_count": int(result.get("near_hit_count", 0)),
        "near_hit_ids": near_summary["combo_ids"],
        "near_hit_names": near_summary["combo_names"],
        "detail_json": json.dumps(result, ensure_ascii=False),
    }


def build_output_dataframe(df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    skill_id_column = config["skill_id_column"]
    declaration_column = config["declaration_column"]
    keep_columns = config["keep_columns"]

    for _, row in df.iterrows():
        declaration_value = row.get(declaration_column)
        scan_result = scan_one_skill(
            declaration_value=declaration_value,
            template_file=config["template_file"],
            include_near=config["include_near"],
            near_threshold=config["near_threshold"],
        )

        out_row: Dict[str, Any] = {}
        for col in keep_columns:
            out_row[col] = row.get(col)

        out_row[declaration_column] = safe_str(declaration_value)
        out_row.update(scan_result)

        if not config.get("include_detail_json", True):
            out_row.pop("detail_json", None)

        rows.append(out_row)

    out_df = pd.DataFrame(rows)

    # 为了看起来更直观，按命中数量降序、skill_id 升序排列
    sort_cols = ["toxic_combo_count"]
    ascending = [False]
    if skill_id_column in out_df.columns:
        sort_cols.append(skill_id_column)
        ascending.append(True)

    out_df = out_df.sort_values(sort_cols, ascending=ascending).reset_index(drop=True)
    return out_df


def save_output_csv(df: pd.DataFrame, output_csv: str) -> None:
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")


def print_summary(result_df: pd.DataFrame) -> None:
    total = len(result_df)
    positive = int((result_df["toxic_combo_count"] > 0).sum()) if total > 0 else 0
    avg_count = float(result_df["toxic_combo_count"].mean()) if total > 0 else 0.0
    max_count = int(result_df["toxic_combo_count"].max()) if total > 0 else 0

    print(f"总 Skill 数：{total}")
    print(f"命中至少一个毒性组合的 Skill 数：{positive}")
    print(f"命中比例：{positive / total:.2%}" if total else "命中比例：0.00%")
    print(f"平均每个 Skill 命中的毒性组合数：{avg_count:.4f}")
    print(f"单个 Skill 最大命中毒性组合数：{max_count}")


def main() -> None:
    validate_config(CONFIG)
    df = load_input_csv(CONFIG["input_csv"])
    validate_required_columns(
        df=df,
        skill_id_column=CONFIG["skill_id_column"],
        declaration_column=CONFIG["declaration_column"],
        keep_columns=CONFIG["keep_columns"],
    )

    result_df = build_output_dataframe(df, CONFIG)
    save_output_csv(result_df, CONFIG["output_csv"])
    print_summary(result_df)
    print(f"\n结果已保存到：{CONFIG['output_csv']}")


if __name__ == "__main__":
    main()
