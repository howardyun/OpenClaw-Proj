#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
根据 CSV 中的 domain 字段，调用 query_domain.py 里的 get_domains_mini_privilege，
为每条 skill 增加一列最小权限集合，并输出为新的 CSV。

说明：
1. 只新增一列，不改动原有列。
2. 输出列默认名为 minimum_permission_set。
3. 为了保留列表结构，写入 CSV 时默认保存为 JSON 字符串，例如：
   ["R1", "R2", "Q1"]
4. 脚本会按 domain 做缓存，同一个 domain 只查询一次。
5. query_domain.py 依赖的 domains.yaml 路径需要你在 CONFIG 中填写正确。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
from typing import Any, Callable, Dict, List

import pandas as pd


# =========================
# 配置区：只改这里
# =========================
CONFIG = {
    "input_csv": "../Data/ProcessData/skills_merged_with_decl_impl.csv",
    "output_csv": "../Data/Result/skills_with_minimum_permission_set.csv",
    "query_domain_py": "query_domain.py",
    "yaml_path": "domains.yaml",   # 改成你的实际路径
    "domain_column": "domain",
    "output_column": "minimum_permission_set",
    "save_as": "json",   # 可选: "json" / "comma"
    "encoding": "utf-8",
}


# =========================
# 工具函数
# =========================
def load_python_module_from_file(file_path: str, module_name: str = "query_domain_dynamic"):
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"未找到 Python 文件: {path}")

    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"无法从文件加载模块: {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_domain_query_function(query_domain_py: str) -> Callable[..., List[str]]:
    module = load_python_module_from_file(query_domain_py)
    if not hasattr(module, "get_domains_mini_privilege"):
        raise AttributeError(
            f"{query_domain_py} 中未找到 get_domains_mini_privilege 函数"
        )
    return module.get_domains_mini_privilege


def safe_query_minimum_permissions(
    query_func: Callable[..., Any],
    domain: str,
    yaml_path: str,
) -> List[str]:
    """
    调用 query_domain.py 里的函数，并抑制它内部的 print 输出。
    返回最小权限原子列表；失败时返回空列表。
    """
    if domain is None or str(domain).strip() == "":
        return []

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            result = query_func(domain, yaml=yaml_path)
    except Exception as e:
        print(f"[WARN] 查询 domain={domain} 失败: {e}")
        return []

    if result is None:
        return []

    if isinstance(result, list):
        return [str(x).strip() for x in result if str(x).strip()]

    if isinstance(result, (tuple, set)):
        return [str(x).strip() for x in result if str(x).strip()]

    if isinstance(result, str):
        text = result.strip()
        if not text:
            return []
        return [text]

    return [str(result).strip()]


def format_permission_list(values: List[str], save_as: str = "json") -> str:
    values = [str(v).strip() for v in values if str(v).strip()]
    if save_as == "comma":
        return ",".join(values)
    return json.dumps(values, ensure_ascii=False)


def build_domain_to_permission_map(
    domains: List[str],
    query_func: Callable[..., Any],
    yaml_path: str,
) -> Dict[str, List[str]]:
    cache: Dict[str, List[str]] = {}
    for domain in domains:
        cache[domain] = safe_query_minimum_permissions(query_func, domain, yaml_path)
    return cache


def add_minimum_permission_column(
    df: pd.DataFrame,
    domain_col: str,
    output_col: str,
    domain_cache: Dict[str, List[str]],
    save_as: str = "json",
) -> pd.DataFrame:
    out = df.copy()
    out[output_col] = out[domain_col].map(
        lambda x: format_permission_list(domain_cache.get(x, []), save_as=save_as)
    )
    return out


def main() -> None:
    input_csv = CONFIG["input_csv"]
    output_csv = CONFIG["output_csv"]
    query_domain_py = CONFIG["query_domain_py"]
    yaml_path = CONFIG["yaml_path"]
    domain_col = CONFIG["domain_column"]
    output_col = CONFIG["output_column"]
    save_as = CONFIG["save_as"]
    encoding = CONFIG["encoding"]

    df = pd.read_csv(input_csv, encoding=encoding)

    if domain_col not in df.columns:
        raise KeyError(f"输入 CSV 中未找到 domain 列: {domain_col}")

    query_func = get_domain_query_function(query_domain_py)

    unique_domains = sorted(df[domain_col].dropna().astype(str).unique().tolist())
    domain_cache = build_domain_to_permission_map(unique_domains, query_func, yaml_path)

    out = add_minimum_permission_column(
        df=df,
        domain_col=domain_col,
        output_col=output_col,
        domain_cache=domain_cache,
        save_as=save_as,
    )

    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_csv, index=False, encoding=encoding)

    unresolved = [d for d, perms in domain_cache.items() if not perms]

    print(f"输入文件: {input_csv}")
    print(f"输出文件: {output_csv}")
    print(f"总记录数: {len(df)}")
    print(f"唯一 domain 数: {len(unique_domains)}")
    print(f"新增列: {output_col}")
    if unresolved:
        print(f"[WARN] 以下 domain 未解析到最小权限，共 {len(unresolved)} 个: {unresolved}")
    else:
        print("所有 domain 都已成功解析最小权限。")


if __name__ == "__main__":
    main()
