#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 SQLite DB 与 CSV 按 Skill 键进行合并，输出一个新的 CSV。

合并规则：
1) 以 DB 为主表。
2) 只从 CSV 中提取 declaration / implementation 两列。
3) 其他重复字段一律以 DB 为准。
4) 默认使用 inner join，只保留 DB 和 CSV 都存在的 Skill。
5) 可选按 source_plat 一起作为联合键；若开启但当前文件缺失该列，可自动回退为仅按 skill 键合并。

当前默认适配：
- DB 表: skills
- DB 中 skill 键列: name
- CSV 中 skill 键列: skill_id
- CSV 中补充列: declaration_atomic_ids, implementation_atomic_ids
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List

import pandas as pd


CONFIG = {
    # 输入
    "db_path": "../RawData/skill_test.db",
    "db_table": "skills",
    "csv_path": "classifications_deduped.csv",

    # 输出
    "output_csv": "skills_merged_with_decl_impl.csv",

    # 键列映射
    "db_skill_key": "name",
    "csv_skill_key": "skill_id",

    # 可选联合键：source_plat
    "use_source_plat": True,
    "db_source_plat_col": "source_plat",
    "csv_source_plat_col": "source_plat",
    # 若开启了 source_plat，但当前 DB/CSV 缺该列，是否自动回退到仅 skill 键
    "fallback_without_source_plat": True,

    # 从 CSV 中仅提取这两列补到 DB 中
    "csv_declaration_col": "declaration_atomic_ids",
    "csv_implementation_col": "implementation_atomic_ids",

    # CSV 若在键上仍有重复，保留哪一条
    "csv_keep": "first",   # first / last

    # 合并方式：inner 最符合“去除 DB 中多余条目”的要求
    "merge_how": "inner",  # inner / left

    # 编码
    "encoding": "utf-8",
}


def load_db_table(db_path: str, table_name: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
    finally:
        conn.close()
    return df


def load_csv(csv_path: str) -> pd.DataFrame:
    return pd.read_csv(csv_path)


def ensure_column_exists(df: pd.DataFrame, col: str, df_name: str) -> None:
    if col not in df.columns:
        raise KeyError(f"{df_name} 中缺少必需字段: {col}")


def resolve_join_keys(db_df: pd.DataFrame, csv_df: pd.DataFrame) -> tuple[list[str], list[str], bool]:
    """
    返回 (db_join_keys, csv_join_keys, source_plat_enabled)
    """
    db_skill = CONFIG["db_skill_key"]
    csv_skill = CONFIG["csv_skill_key"]
    ensure_column_exists(db_df, db_skill, "DB")
    ensure_column_exists(csv_df, csv_skill, "CSV")

    db_join_keys = [db_skill]
    csv_join_keys = [csv_skill]
    source_plat_enabled = False

    if CONFIG["use_source_plat"]:
        db_sp = CONFIG["db_source_plat_col"]
        csv_sp = CONFIG["csv_source_plat_col"]
        db_has = db_sp in db_df.columns
        csv_has = csv_sp in csv_df.columns
        if db_has and csv_has:
            db_join_keys.append(db_sp)
            csv_join_keys.append(csv_sp)
            source_plat_enabled = True
        elif not CONFIG["fallback_without_source_plat"]:
            missing = []
            if not db_has:
                missing.append(f"DB.{db_sp}")
            if not csv_has:
                missing.append(f"CSV.{csv_sp}")
            raise KeyError("开启了 source_plat 联合键，但缺少字段: " + ", ".join(missing))

    return db_join_keys, csv_join_keys, source_plat_enabled


def build_csv_subset(csv_df: pd.DataFrame, csv_join_keys: List[str]) -> pd.DataFrame:
    decl_col = CONFIG["csv_declaration_col"]
    impl_col = CONFIG["csv_implementation_col"]
    ensure_column_exists(csv_df, decl_col, "CSV")
    ensure_column_exists(csv_df, impl_col, "CSV")

    subset_cols = list(dict.fromkeys(csv_join_keys + [decl_col, impl_col]))
    subset = csv_df[subset_cols].copy()

    keep = CONFIG["csv_keep"]
    if keep not in {"first", "last"}:
        raise ValueError("CONFIG['csv_keep'] 只能是 'first' 或 'last'")

    subset = subset.drop_duplicates(subset=csv_join_keys, keep=keep)
    return subset


def normalize_key_columns(db_df: pd.DataFrame, csv_subset: pd.DataFrame, db_join_keys: List[str], csv_join_keys: List[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """把连接键统一转成字符串，避免数值/字符串混型导致 join 失败。"""
    db_df = db_df.copy()
    csv_subset = csv_subset.copy()

    for col in db_join_keys:
        db_df[col] = db_df[col].astype(str)
    for col in csv_join_keys:
        csv_subset[col] = csv_subset[col].astype(str)

    return db_df, csv_subset


def merge_db_with_csv_subset(db_df: pd.DataFrame, csv_subset: pd.DataFrame, db_join_keys: List[str], csv_join_keys: List[str]) -> pd.DataFrame:
    merged = db_df.merge(
        csv_subset,
        how=CONFIG["merge_how"],
        left_on=db_join_keys,
        right_on=csv_join_keys,
        suffixes=("", "_csv"),
    )

    # 如果左右键列名不同，删掉来自 CSV 的键列；若同名则不会重复生成
    extra_csv_key_cols = [k for k in csv_join_keys if k not in db_join_keys and k in merged.columns]
    if extra_csv_key_cols:
        merged = merged.drop(columns=extra_csv_key_cols)

    return merged


def reorder_output_columns(merged_df: pd.DataFrame, original_db_columns: List[str]) -> pd.DataFrame:
    decl_col = CONFIG["csv_declaration_col"]
    impl_col = CONFIG["csv_implementation_col"]

    final_cols = [c for c in original_db_columns if c in merged_df.columns]
    for col in [decl_col, impl_col]:
        if col in merged_df.columns:
            final_cols.append(col)

    # 防御性处理：若还有意外列，附到末尾，避免信息丢失
    tail_cols = [c for c in merged_df.columns if c not in final_cols]
    final_cols.extend(tail_cols)
    return merged_df[final_cols]


def save_csv(df: pd.DataFrame, output_csv: str) -> None:
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False, encoding=CONFIG["encoding"])


def main() -> None:
    db_df = load_db_table(CONFIG["db_path"], CONFIG["db_table"])
    csv_df = load_csv(CONFIG["csv_path"])
    original_db_columns = db_df.columns.tolist()

    db_join_keys, csv_join_keys, source_plat_enabled = resolve_join_keys(db_df, csv_df)
    csv_subset = build_csv_subset(csv_df, csv_join_keys)
    db_df, csv_subset = normalize_key_columns(db_df, csv_subset, db_join_keys, csv_join_keys)
    merged_df = merge_db_with_csv_subset(db_df, csv_subset, db_join_keys, csv_join_keys)
    merged_df = reorder_output_columns(merged_df, original_db_columns)
    save_csv(merged_df, CONFIG["output_csv"])

    print("=== Merge finished ===")
    print(f"DB rows: {len(db_df)}")
    print(f"CSV rows: {len(csv_df)}")
    print(f"CSV rows after dedupe on keys: {len(csv_subset)}")
    print(f"Join keys (DB): {db_join_keys}")
    print(f"Join keys (CSV): {csv_join_keys}")
    print(f"source_plat enabled: {source_plat_enabled}")
    print(f"Merge how: {CONFIG['merge_how']}")
    print(f"Output rows: {len(merged_df)}")
    print(f"Output file: {CONFIG['output_csv']}")


if __name__ == "__main__":
    main()
