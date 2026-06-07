# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Windows / 常见环境的中文字体，避免热力图轴标签与标题缺字
plt.rcParams.setdefault("font.sans-serif", ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"])
plt.rcParams.setdefault("axes.unicode_minus", False)

from matplotlib import colors as mcolors
from matplotlib.patches import Polygon, Rectangle
import matplotlib.patheffects as pe
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats as sp_stats

_ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate Fig1/2/3/4 from v4 + top10 combo stats.")
    p.add_argument("--v4-csv", type=Path, default=None, help="v4 全量 CSV（Fig1/3/4 必需；Fig2 默认同文件）")
    p.add_argument(
        "--pdei-csv",
        type=Path,
        default=None,
        help="PDEI 全量 CSV，仅 Fig2；未指定时用 --v4-csv",
    )
    p.add_argument("--skip-fig2", action="store_true", help="跳过 Fig. 2A / 2B")
    p.add_argument("--fig2-only", action="store_true", help="只生成 Fig. 2A / 2B")
    p.add_argument("--skip-fig4b", action="store_true", help="跳过 Fig. 4B 法规冲突矩阵")
    p.add_argument("--fig4b-only", action="store_true", help="只生成 Fig. 4B")
    p.add_argument(
        "--reg-conflict-csv",
        type=Path,
        default=None,
        help="Fig4B 8×4 评分矩阵 CSV；未指定时使用脚本内置默认矩阵",
    )
    p.add_argument("--top10-csv", type=Path, default=None, help="预聚合 top10 组合 CSV（与 --combo-stats-csv 二选一）")
    p.add_argument(
        "--combo-stats-csv",
        type=Path,
        default=None,
        help="declaration_toxic_combo_stats_v2.csv；按 toxic_combo_atomic_codes 频数取 top10",
    )
    p.add_argument("--out-dir", type=Path, default=Path("./output"))
    p.add_argument("--top-k", type=int, default=15)
    p.add_argument("--pdf", action="store_true")
    p.add_argument(
        "--funnel-l1",
        type=int,
        default=None,
        help="Fig4 L1: raw AI Skills collected across platforms (pre-filter corpus size).",
    )
    p.add_argument(
        "--fig2a-run-bootstrap",
        action="store_true",
        help="在 fig2a_stats 中追加探索性幂律 bootstrap（默认不写入主图）",
    )
    p.add_argument(
        "--fig2a-run-vuong",
        action="store_true",
        help="在 fig2a_stats 中追加探索性 Vuong 模型比较（默认不写入主图）",
    )
    p.add_argument(
        "--fig2a-bootstrap-n",
        type=int,
        default=FIG2A_BOOTSTRAP_N,
        help=f"Fig2A bootstrap 重复次数（默认 {FIG2A_BOOTSTRAP_N}）",
    )
    p.add_argument(
        "--fig2a-bootstrap-seed",
        type=int,
        default=FIG2A_BOOTSTRAP_SEED,
        help=f"Fig2A bootstrap 随机种子（默认 {FIG2A_BOOTSTRAP_SEED}）",
    )
    p.add_argument(
        "--fig2a-bootstrap-size",
        choices=("tail", "full"),
        default=FIG2A_BOOTSTRAP_SIZE,
        help="Fig2A bootstrap 合成样本量：tail=与尾部同规模(默认,较快); full=全部正PDEI(慢,更接近CSN原文)",
    )
    return p.parse_args()


def split_codes(v: object) -> list[str]:
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return []
    return [x.strip().upper() for x in s.split(",") if x.strip()]


def parse_combo_text(v: object) -> list[tuple[str, ...]]:
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return []
    combos = []
    for seg in s.split("|"):
        atoms = sorted(set(x.strip().upper() for x in seg.split("+") if x.strip()))
        if len(atoms) >= 2:
            combos.append(tuple(atoms))
    return combos


def load_top_pairs(top10_df: pd.DataFrame) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    if "atom_a" in top10_df.columns and "atom_b" in top10_df.columns:
        for _, r in top10_df.iterrows():
            a = str(r["atom_a"]).strip().upper()
            b = str(r["atom_b"]).strip().upper()
            if a and b and a != "NAN" and b != "NAN" and a != b:
                pairs.add(tuple(sorted((a, b))))
        return pairs

    combo_col = "combo_atoms" if "combo_atoms" in top10_df.columns else None
    if combo_col is None and "toxic_combo_atomic_codes" in top10_df.columns:
        combo_col = "toxic_combo_atomic_codes"
    if combo_col is None and "atomic_operation_combo" in top10_df.columns:
        combo_col = "atomic_operation_combo"
    if combo_col is None:
        raise ValueError(
            "top10.csv 缺少可解析列：combo_atoms、toxic_combo_atomic_codes、atomic_operation_combo 或 atom_a+atom_b"
        )

    for v in top10_df[combo_col].fillna(""):
        if combo_col in ("combo_atoms", "atomic_operation_combo"):
            combos = parse_combo_text(str(v).replace(",", "|"))
        else:
            combos = parse_combo_text(v)
        for combo in combos:
            for a, b in combinations(combo, 2):
                pairs.add(tuple(sorted((a, b))))
    return pairs


def load_top_pairs_from_combo_stats(path: Path, *, top_k: int = 10) -> set[tuple[str, str]]:
    """从 declaration_toxic_combo_stats_v2 按 toxic_combo_atomic_codes 命中 skill 数取 top-k 组合。"""
    cnt: Counter[str] = Counter()
    for chunk in pd.read_csv(path.resolve(), encoding="utf-8-sig", usecols=["toxic_combo_atomic_codes"], chunksize=50_000):
        for v in chunk["toxic_combo_atomic_codes"].fillna(""):
            s = str(v).strip()
            if not s or s.lower() == "nan":
                continue
            for seg in s.split("|"):
                seg = seg.strip()
                if seg:
                    cnt[seg] += 1
    if not cnt:
        raise ValueError(f"{path} 未统计到任何 toxic_combo_atomic_codes。")
    top_combos = [combo for combo, _ in cnt.most_common(max(1, top_k))]
    pairs: set[tuple[str, str]] = set()
    for combo in top_combos:
        atoms = sorted(set(x.strip().upper() for x in combo.split("+") if x.strip()))
        if len(atoms) >= 2:
            for a, b in combinations(atoms, 2):
                pairs.add(tuple(sorted((a, b))))
    if not pairs:
        raise ValueError(f"{path} top{top_k} 组合未解析到有效原子对。")
    return pairs


def resolve_top_pairs(*, top10_csv: Path | None, combo_stats_csv: Path | None, top_k: int = 10) -> set[tuple[str, str]]:
    if combo_stats_csv is not None:
        return load_top_pairs_from_combo_stats(combo_stats_csv, top_k=top_k)
    if top10_csv is not None:
        df = pd.read_csv(top10_csv.resolve(), encoding="utf-8-sig")
        return load_top_pairs(df)
    raise ValueError("请提供 --combo-stats-csv 或 --top10-csv 之一。")


FIG4A_L1_DEFAULT = 516_370


def resolve_funnel_l1(*, funnel_l1: int | None, combo_stats_csv: Path | None, v4_rows: int) -> int:
    if funnel_l1 is not None:
        return int(funnel_l1)
    return FIG4A_L1_DEFAULT


# PDEI v3：原子 → Tier（见 PDEI(1).md 第六节 TIER_MAP）
_PDEI_TIER_ATOMS: dict[str, set[str]] = {
    "T1": {
        "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10",
        "Q1", "Q2", "Q3", "Q4",
        "S1", "S2", "S3", "S4", "S5", "S6", "S7",
    },
    "T2": {"W1", "W2", "W3", "W4", "U1", "U2", "U3", "U4", "C1", "C2", "C3", "C4", "C5"},
    "T3": {
        "X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8",
        "G1", "G2", "G3", "G4", "G5",
        "O1", "O2", "O3", "O4", "O5",
        "K1", "K2", "K3", "K4", "K5", "K6",
    },
    "T4": {"A1", "A2", "A3", "A4", "A5", "A6", "A7", "I1", "I2", "I3", "I4", "I5", "I6", "I7"},
}
TIER_BY_ATOM: dict[str, str] = {a: t for t, atoms in _PDEI_TIER_ATOMS.items() for a in atoms}

# PDEI v3 毒性路径：两条 Tier 同时冗余（Γ 因子）；Fig3a 按 Tier 交叉子矩阵标注
PATH_TIER_RULES: dict[str, tuple[str, str]] = {
    "A": ("T1", "T2"),
    "B": ("T1", "T3"),
    "C": ("T2", "T3"),
    "D": ("T4", "T2"),
    "E": ("T4", "T3"),
}
PATH_EDGE_COLOR = "#d62728"
PATH_COLS = ["path_A", "path_B", "path_C", "path_D", "path_E"]
PATH_RATE_COLS = [f"{p}_rate" for p in PATH_COLS]
FIG3B_BAR_COLOR = "#4a9fd4"
FIG5_NOT_OVER_COLOR = "#e8ecef"
DELTA_COLS = ["delta_t1", "delta_t2", "delta_t3", "delta_t4"]
PLATFORM_LABELS: dict[str, str] = {
    "lobehub": "LobeHub",
    "skillsmp": "SkillsMP",
    "skills_sh": "Skills.sh",
    "skillsdirectory": "Skills Directory",
    "clawhub": "ClawHub",
}


def _path_letter_for_tiers(ta: str, tb: str) -> str | None:
    pair = {ta, tb}
    for letter, (t1, t2) in PATH_TIER_RULES.items():
        if pair == {t1, t2}:
            return letter
    return None


def _savefig_safe(fig: plt.Figure, path: Path, **kwargs) -> Path:
    """Save figure; if path is locked, write to *_new.* sibling and return actual path."""
    try:
        fig.savefig(path, **kwargs)
        return path
    except PermissionError:
        alt = path.with_name(f"{path.stem}_new{path.suffix}")
        fig.savefig(alt, **kwargs)
        print(f"Warning: {path.name} is locked; saved to {alt.name}", flush=True)
        return alt


def save_fig(
    fig: plt.Figure,
    out_png: Path,
    out_pdf: Path | None = None,
    *,
    tight_pad: float | None = None,
    tight_rect: tuple[float, float, float, float] | None = None,
    pad_inches: float = 0.02,
    use_tight_layout: bool = True,
) -> None:
    if use_tight_layout:
        if tight_pad is not None or tight_rect is not None:
            fig.tight_layout(pad=tight_pad if tight_pad is not None else 1.0, rect=tight_rect)
        else:
            fig.tight_layout()
    fig.savefig(out_png, dpi=300, bbox_inches="tight", pad_inches=pad_inches)
    if out_pdf:
        _savefig_safe(fig, out_pdf, bbox_inches="tight", pad_inches=pad_inches)
    plt.close(fig)


# Nature Communications figure style: titles live in captions; multi-panel figures use a/b/c labels.
FIGURE_CAPTIONS: dict[str, str] = {
    "fig1": (
        "Fig. 1 | Panoramic over-privileging heatmap. "
        "Heatmap of atomic-permission hit rates within each skill domain."
    ),
    "fig2": (
        "Fig. 2 | Permission abuse concentration and developer reputation. "
        "a, Heavy-tailed distribution of permission abuse (PDEI CCDF). "
        "b, Developer GitHub stars versus average PDEI per developer."
    ),
    "fig2a": (
        "Fig. 2a | Heavy-tailed distribution of permission abuse. "
        "Empirical complementary cumulative distribution function (CCDF) of PDEI scores."
    ),
    "fig2b": (
        "Fig. 2b | Developer reputation does not guarantee permission safety. "
        "Relationship between developer GitHub stars and average PDEI per developer."
    ),
    "fig3": (
        "Fig. 3 | Toxic-combo structure and domain-level permission risk. "
        "a, Pairwise co-occurrence counts among top toxic atomic-permission combinations; "
        "red boxes mark Path A–E tier-crossing pairs. "
        "b, Average PDEI by skill domain (domains sorted by mean PDEI). "
        "c, Toxic-path density rates by skill domain (fraction of skills with each path active)."
    ),
    "fig3a": (
        "Fig. 3a | Toxic-combo co-occurrence matrix. "
        "Pairwise co-occurrence counts among top toxic atomic-permission combinations; "
        "red boxes mark Path A–E tier-crossing pairs."
    ),
    "fig3b": (
        "Fig. 3b | Average PDEI by skill domain. "
        "Mean PDEI score per functional domain across the analytical corpus; "
        "domains ordered by descending average PDEI."
    ),
    "fig3c": (
        "Fig. 3c | Toxic-path density by skill domain. "
        "Fraction of skills in each domain with Path A–E active; "
        "domains ordered by descending average PDEI (same order as panel b)."
    ),
    "fig4": (
        "Fig. 4 | Impact funnel and regulatory conflict. "
        "a, Impact funnel from raw corpus to high-risk skills. "
        "b, Normative regulatory conflict matrix across abuse categories and statutes."
    ),
    "fig4a": (
        "Fig. 4a | Impact funnel from raw corpus to high-risk skills. "
        "Sequential filtering from raw corpus through valid dataset, over-privileged skills, "
        "to toxic or high-risk skills."
    ),
    "fig4a_download": (
        "Fig. 4a (downloads) | Download-volume impact funnel. "
        "Estimated download counts aggregated from total corpus through over-privileged skills, "
        "toxic-combo skills, to the top 1% highest-PDEI toxic-combo skills."
    ),
    "fig4b": (
        "Fig. 4b | Regulatory conflict matrix. "
        "Normative conflict scores (0–1) between abuse categories and "
        "GDPR, EU AI Act, CCPA, and PIPL."
    ),
    "fig5": (
        "Fig. 5 | Over-privilege rate and corpus size by source platform. "
        "Stacked bars show total skills per platform (bar height) and the over-privileged "
        "subset (Σδ_t ≥ 1; blue); percentages and counts are annotated above each bar."
    ),
}


def add_panel_label(ax, label: str, *, figure_x: float | None = None) -> None:
    """Panel letter outside the top-left of the axes (Nature Communications style)."""
    pos = ax.get_position()
    if figure_x is not None:
        x_pos, ha = figure_x, "left"
    else:
        x_pos, ha = pos.x0 - 0.008, "right"
    ax.figure.text(
        x_pos,
        pos.y1 + 0.008,
        label,
        ha=ha,
        va="bottom",
        fontsize=12,
        fontweight="bold",
        color="#000000",
        zorder=100,
        clip_on=False,
    )


def add_panel_label_above_ylabel(ax, label: str) -> None:
    """Panel letter at the figure top, horizontally centered over the y-axis label."""
    fig = ax.figure
    fig.canvas.draw()
    bbox = ax.yaxis.get_label().get_window_extent(fig.canvas.get_renderer())
    bbox_fig = bbox.transformed(fig.transFigure.inverted())
    x = 0.5 * (bbox_fig.x0 + bbox_fig.x1)
    y = 1.0 - 0.004
    fig.text(
        x,
        y,
        label,
        ha="center",
        va="top",
        fontsize=12,
        fontweight="bold",
        color="#000000",
        zorder=100,
        clip_on=False,
    )


def save_figure_caption(out_dir: Path, stem: str, caption: str) -> None:
    (out_dir / f"{stem}_caption.txt").write_text(caption.strip() + "\n", encoding="utf-8")


def build_fig1(v4: pd.DataFrame, out_dir: Path, top_k: int, pdf: bool) -> None:
    d = v4.dropna(subset=["domain"]).copy()
    d["domain"] = d["domain"].astype(str).str.strip()
    d = d[d["domain"] != ""]
    d["atoms"] = d["declaration_atomic_ids"].map(split_codes)

    domain_total: Counter[str] = Counter()
    atom_global: Counter[str] = Counter()
    domain_atom_hits: dict[str, Counter[str]] = defaultdict(Counter)
    for _, row in d.iterrows():
        dm = row["domain"]
        atoms = row["atoms"]
        domain_total[dm] += 1
        for a in atoms:
            atom_global[a] += 1
            domain_atom_hits[dm][a] += 1

    top_atoms = [a for a, _ in atom_global.most_common(max(1, top_k))]
    domains = sorted(domain_total.keys())
    m = np.zeros((len(top_atoms), len(domains)), dtype=float)
    for i, a in enumerate(top_atoms):
        for j, dm in enumerate(domains):
            m[i, j] = domain_atom_hits[dm][a] / domain_total[dm] if domain_total[dm] > 0 else 0.0

    sns.set_theme(style="white")
    fig, ax = plt.subplots(figsize=(16, 7))
    annot = np.array([[f"{v:.2f}" for v in row] for row in m], dtype=object)
    sns.heatmap(
        m,
        ax=ax,
        cmap="Blues",
        vmin=0.0,
        vmax=max(0.05, float(np.nanmax(m)) if m.size else 0.05),
        annot=annot,
        fmt="",
        linewidths=0.5,
        linecolor="white",
        cbar_kws={"label": "Rate within domain"},
        xticklabels=domains,
        yticklabels=top_atoms,
        annot_kws={"fontsize": 8},
    )
    ax.set_xlabel("Domain")
    ax.set_ylabel("Atomic Permission ID")
    ax.tick_params(axis="x", rotation=0, labelsize=9)
    ax.tick_params(axis="y", rotation=0)
    save_fig(fig, out_dir / "fig1_heatmap.png", out_dir / "fig1_heatmap.pdf" if pdf else None)
    save_figure_caption(out_dir, "fig1_heatmap", FIGURE_CAPTIONS["fig1"])


def _positive_rate(series: pd.Series) -> float:
    return float((series > 0).mean())


def compute_domain_path_summary(v4: pd.DataFrame) -> pd.DataFrame:
    """按 domain 汇总平均 PDEI 与各 path 激活率；按 avg_pdei 降序排列。"""
    d = v4.dropna(subset=["domain"]).copy()
    d["domain"] = d["domain"].astype(str).str.strip()
    d = d[d["domain"] != ""]
    for col in [*PATH_COLS, "pdei_score"]:
        d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0.0)
    agg_spec: dict = {
        "skill_count": ("pdei_score", "size"),
        "avg_pdei": ("pdei_score", "mean"),
    }
    for path_col in PATH_COLS:
        agg_spec[f"{path_col}_rate"] = (path_col, _positive_rate)
    summary = d.groupby("domain", as_index=False).agg(**agg_spec)
    return summary.sort_values("avg_pdei", ascending=False).reset_index(drop=True)


def build_fig3a(v4: pd.DataFrame, top_pairs: set[tuple[str, str]], out_dir: Path, pdf: bool) -> None:
    """Top10 组合原子共现矩阵；Path A–E 按 PDEI Tier 交叉逐格红框（共现>0）。"""
    atoms = sorted({a for p in top_pairs for a in p})
    if not atoms:
        raise ValueError("top10 未解析到有效原子组合。")
    unknown = [a for a in atoms if a not in TIER_BY_ATOM]
    if unknown:
        raise ValueError(f"以下原子 ID 不在 PDEI TIER_MAP 中: {unknown[:8]}{'...' if len(unknown) > 8 else ''}")

    idx = {a: i for i, a in enumerate(atoms)}
    n = len(atoms)
    m = np.zeros((n, n), dtype=int)
    for v in v4["declaration_atomic_ids"].fillna(""):
        present = sorted({a for a in split_codes(v) if a in idx})
        for a, b in combinations(present, 2):
            i, j = idx[a], idx[b]
            m[i, j] += 1
            m[j, i] += 1
    np.fill_diagonal(m, 0)

    pair_letter: dict[tuple[str, str], str] = {}
    for i in range(n):
        for j in range(i + 1, n):
            if m[i, j] <= 0:
                continue
            ta, tb = TIER_BY_ATOM[atoms[i]], TIER_BY_ATOM[atoms[j]]
            if ta == tb:
                continue
            letter = _path_letter_for_tiers(ta, tb)
            if letter:
                pair_letter[tuple(sorted((atoms[i], atoms[j])))] = letter

    fig, ax = plt.subplots(figsize=(10.5, 9))
    annot = np.array([[f"{v:d}" for v in row] for row in m], dtype=object)
    sns.heatmap(
        m,
        ax=ax,
        cmap="Blues",
        annot=annot,
        fmt="",
        linewidths=0.55,
        linecolor="white",
        square=True,
        cbar_kws={"label": "Co-occurrence count"},
        xticklabels=atoms,
        yticklabels=atoms,
        annot_kws={"fontsize": 8},
    )
    ax.set_xlabel("Atomic permission ID")
    ax.set_ylabel("Atomic permission ID")
    ax.tick_params(axis="x", rotation=0)
    ax.tick_params(axis="y", rotation=0)

    stroke = [pe.withStroke(linewidth=2.2, foreground="white")]
    for (a, b), letter in pair_letter.items():
        i, j = idx[a], idx[b]
        if i >= j:
            i, j = j, i
        r, c = i, j
        ax.add_patch(
            Rectangle((c, r), 1, 1, fill=False, edgecolor=PATH_EDGE_COLOR, linewidth=1.6, zorder=15)
        )
        ann = ax.annotate(
            letter,
            xy=(c + 0.5, r + 0.5),
            xytext=(-11, 11),
            textcoords="offset points",
            ha="center",
            va="center",
            fontsize=9,
            fontweight="bold",
            color=PATH_EDGE_COLOR,
            zorder=20,
            clip_on=False,
        )
        ann.set_path_effects(stroke)

    save_fig(fig, out_dir / "fig3a_cooccurrence.png", out_dir / "fig3a_cooccurrence.pdf" if pdf else None)
    save_figure_caption(out_dir, "fig3a_cooccurrence", FIGURE_CAPTIONS["fig3a"])

    by_path: dict[str, int] = defaultdict(int)
    for letter in pair_letter.values():
        by_path[letter] += 1
    meta = {
        "atoms": atoms,
        "n_atoms": n,
        "n_path_pairs": len(pair_letter),
        "path_pair_counts": dict(by_path),
        "path_tier_rules": {k: list(v) for k, v in PATH_TIER_RULES.items()},
    }
    (out_dir / "fig3a_cooccurrence_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def build_fig3b(domain_summary: pd.DataFrame, out_dir: Path, pdf: bool) -> None:
    """各 domain 平均 PDEI 柱状图（按 avg_pdei 降序）。"""
    if domain_summary.empty:
        raise ValueError("domain 汇总为空，无法生成 Fig3b。")

    sns.set_theme(style="white")
    fig, ax = plt.subplots(figsize=(12.0, 5.0))
    x = np.arange(len(domain_summary))
    ax.bar(x, domain_summary["avg_pdei"], width=0.72, color=FIG3B_BAR_COLOR, edgecolor="none")
    ax.set_xticks(x)
    ax.set_xticklabels(domain_summary["domain"], rotation=0, fontsize=9)
    ax.set_xlabel("Domain")
    ax.set_ylabel("Average PDEI")
    ax.yaxis.grid(True, linestyle="-", linewidth=0.6, color="#e0e0e0", alpha=0.95)
    ax.set_axisbelow(True)
    sns.despine(ax=ax)

    save_fig(fig, out_dir / "fig3b_avg_pdei_by_domain.png", out_dir / "fig3b_avg_pdei_by_domain.pdf" if pdf else None)
    save_figure_caption(out_dir, "fig3b_avg_pdei_by_domain", FIGURE_CAPTIONS["fig3b"])

    stats_lines = [
        "Fig3b domain summary (sorted by avg_pdei descending):",
        domain_summary.to_string(index=False, float_format=lambda v: f"{v:.4f}"),
    ]
    (out_dir / "fig3b_avg_pdei_by_domain_stats.txt").write_text("\n".join(stats_lines), encoding="utf-8")
    domain_summary.round(4).to_csv(out_dir / "fig3b_domain_summary.csv", index=False, encoding="utf-8-sig")


def build_fig3c(domain_summary: pd.DataFrame, out_dir: Path, pdf: bool) -> None:
    """各 domain 的 path 激活率热图（Y 轴与 Fig3b 同序）。"""
    if domain_summary.empty:
        raise ValueError("domain 汇总为空，无法生成 Fig3c。")

    m = domain_summary[PATH_RATE_COLS].to_numpy(dtype=float)
    domains = domain_summary["domain"].tolist()
    vmax = max(0.7, float(np.nanmax(m)) if m.size else 0.7)

    sns.set_theme(style="white")
    fig, ax = plt.subplots(figsize=(7.8, 9.0))
    annot = np.array([[f"{v:.2f}" for v in row] for row in m], dtype=object)
    sns.heatmap(
        m,
        ax=ax,
        cmap="Blues",
        vmin=0.0,
        vmax=vmax,
        annot=annot,
        fmt="",
        linewidths=0.5,
        linecolor="white",
        cbar_kws={"label": "Path density"},
        xticklabels=PATH_RATE_COLS,
        yticklabels=domains,
        annot_kws={"fontsize": 8},
    )
    ax.set_xlabel("Path type")
    ax.set_ylabel("Domain")
    ax.tick_params(axis="x", rotation=0, labelsize=9)
    ax.tick_params(axis="y", rotation=0, labelsize=9)

    save_fig(fig, out_dir / "fig3c_path_density_by_domain.png", out_dir / "fig3c_path_density_by_domain.pdf" if pdf else None)
    save_figure_caption(out_dir, "fig3c_path_density_by_domain", FIGURE_CAPTIONS["fig3c"])


def build_fig3_suite(v4: pd.DataFrame, top_pairs: set[tuple[str, str]], out_dir: Path, pdf: bool) -> None:
    build_fig3a(v4, top_pairs, out_dir, pdf)
    domain_summary = compute_domain_path_summary(v4)
    build_fig3b(domain_summary, out_dir, pdf)
    build_fig3c(domain_summary, out_dir, pdf)
    save_figure_caption(out_dir, "fig3_combined", FIGURE_CAPTIONS["fig3"])


def compute_platform_overprivilege_summary(v4: pd.DataFrame) -> pd.DataFrame:
    """按 source_plat 汇总过度授权率（Σδ_t ≥ 1）；按 skill 总数降序。"""
    if "source_plat" not in v4.columns:
        raise ValueError("v4.csv 缺少 source_plat 列，无法生成平台过度授权率图。")
    d = v4.copy()
    d["source_plat"] = d["source_plat"].astype(str).str.strip()
    for col in DELTA_COLS:
        d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0.0)
    d["over_privileged"] = d[DELTA_COLS].sum(axis=1) >= 1
    summary = d.groupby("source_plat", as_index=False).agg(
        skill_count=("over_privileged", "size"),
        over_privileged_count=("over_privileged", "sum"),
    )
    summary["over_privilege_rate_pct"] = 100.0 * summary["over_privileged_count"] / summary["skill_count"]
    summary["platform_label"] = summary["source_plat"].map(lambda k: PLATFORM_LABELS.get(k, k))
    return summary.sort_values("skill_count", ascending=False).reset_index(drop=True)


def build_fig5_platform_overprivilege(v4: pd.DataFrame, out_dir: Path, pdf: bool) -> None:
    """五平台过度授权：堆叠柱高=skill 总数，蓝色=过度授权（Σδ_t ≥ 1）。"""
    summary = compute_platform_overprivilege_summary(v4)
    if summary.empty:
        raise ValueError("平台汇总为空，无法生成 Fig5。")

    sns.set_theme(style="white")
    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    x = np.arange(len(summary))
    over = summary["over_privileged_count"].to_numpy(dtype=float)
    not_over = summary["skill_count"].to_numpy(dtype=float) - over
    width = 0.68

    ax.bar(x, over, width=width, color=FIG3B_BAR_COLOR, label="Over-privileged", edgecolor="none")
    ax.bar(
        x, not_over, width=width, bottom=over, color=FIG5_NOT_OVER_COLOR,
        label="Not over-privileged", edgecolor="none",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(summary["platform_label"], rotation=0, fontsize=9)
    ax.set_xlabel("Platform")
    ax.set_ylabel("Number of skills")
    max_count = float(summary["skill_count"].max())
    ax.set_ylim(0, max_count * 1.14)
    ax.yaxis.grid(True, linestyle="-", linewidth=0.6, color="#e0e0e0", alpha=0.95)
    ax.set_axisbelow(True)
    sns.despine(ax=ax)
    ax.legend(frameon=False, loc="upper right", fontsize=8.5)

    for j, row in summary.iterrows():
        total = int(row["skill_count"])
        rate = float(row["over_privilege_rate_pct"])
        ax.text(
            j, total + max_count * 0.012,
            f"{rate:.2f}%\n(n={total:,})",
            ha="center", va="bottom", fontsize=8.2, linespacing=1.15,
        )

    save_fig(
        fig,
        out_dir / "fig5_platform_overprivilege_rate.png",
        out_dir / "fig5_platform_overprivilege_rate.pdf" if pdf else None,
    )
    save_figure_caption(out_dir, "fig5_platform_overprivilege_rate", FIGURE_CAPTIONS["fig5"])

    stats_lines = [
        "Fig5 platform over-privilege summary (over-privileged = sum(delta_t1..t4) >= 1):",
        summary.to_string(index=False, float_format=lambda v: f"{v:.4f}"),
        f"\nTotal skills: {int(summary['skill_count'].sum()):,}",
    ]
    (out_dir / "fig5_platform_overprivilege_rate_stats.txt").write_text(
        "\n".join(stats_lines), encoding="utf-8"
    )
    summary.round(4).to_csv(out_dir / "fig5_platform_overprivilege_rate.csv", index=False, encoding="utf-8-sig")


def compute_funnel_skill_levels(v4: pd.DataFrame, *, raw_total: int) -> dict[str, int | float]:
    d = v4.copy()
    for c in ["delta_t1", "delta_t2", "delta_t3", "delta_t4", "path_A", "path_B", "path_C", "path_D", "path_E"]:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)
    d["n_redundant"] = d["delta_t1"] + d["delta_t2"] + d["delta_t3"] + d["delta_t4"]
    d["toxic_any"] = (d[["path_A", "path_B", "path_C", "path_D", "path_E"]].sum(axis=1) > 0).astype(int)

    l2 = int(d.shape[0])
    l3 = int((d["n_redundant"] >= 1).sum())
    l4 = int((d["toxic_any"] == 1).sum())
    l1 = int(raw_total)
    filtered = max(l1 - l2, 0)
    return {
        "level1": l1,
        "level2": l2,
        "level3": l3,
        "level4": l4,
        "filtered_from_l1": filtered,
        "l3_pct_of_l2": round(100.0 * l3 / l2, 2) if l2 else 0.0,
        "l4_pct_of_l2": round(100.0 * l4 / l2, 2) if l2 else 0.0,
    }


def _hex_darken(hex_color: str, amount: float = 0.22) -> str:
    rgb = np.clip(np.array(mcolors.to_rgb(hex_color)) - amount, 0, 1)
    return mcolors.to_hex(rgb)


FIG4A_STAGE_COLORS = ["#7ec8e8", "#4a9fd4", "#3182ce", "#1e3a5f"]
FIG4A_BG = "#ffffff"
FIG4A_FIGSIZE = (10.2, 6.0)
FIG4A_CX = 0.44
FIG4A_HW_BASE = 0.30
FIG4A_LEFT_TAG_X = 0.10
FIG4A_ANNOT_X = 0.72


def _fig4a_layer_colors(base: str) -> tuple[str, str]:
    rgb = np.array(mcolors.to_rgb(base))
    top = np.clip(rgb + 0.10, 0, 1)
    return mcolors.to_hex(top), base


def _fig4a_half_widths(levels: list[float], *, min_last: float | None = None) -> list[float]:
    """各层半宽与 Skill 数量成正比，形成漏斗收窄。"""
    max_v = max(levels) if levels else 1.0
    widths = [FIG4A_HW_BASE * (v / max_v) for v in levels]
    if widths and min_last is not None:
        widths[-1] = max(widths[-1], min_last)
    return widths


def _fig4a_hw_at_mid(i: int, half_w: list[float], n: int) -> float:
    if i < n - 1:
        return (half_w[i] + half_w[i + 1]) / 2
    return half_w[-1]


def _render_fig4_funnel(
    ax,
    *,
    levels: list[float],
    stages: list[tuple[str, str, str]],
    stage_note: Callable[[int], str],
    center_extra_line: Callable[[int, float], str | None],
    side_titles: list[str] | None = None,
    center_text_colors: dict[int, str] | None = None,
    min_last_half_w: float | None = None,
) -> None:
    """Shared trapezoid funnel renderer for skill-count and download-volume variants."""
    half_w = _fig4a_half_widths(levels, min_last=min_last_half_w)
    cx = FIG4A_CX
    seg_h, neck, fold_h = 0.82, 0.08, 0.045
    n = len(levels)
    y_top = 3.55

    for i in range(n - 1):
        y0 = y_top - i * seg_h
        y1 = y_top - (i + 1) * seg_h + neck
        wt, wb = half_w[i], half_w[i + 1]
        top_c, body_c = _fig4a_layer_colors(stages[i][2])
        ax.add_patch(
            Polygon(
                [(cx - wt, y0), (cx + wt, y0), (cx + wb, y1), (cx - wb, y1)],
                closed=True, facecolor=body_c, edgecolor="#ffffff", linewidth=1.4,
                joinstyle="round", zorder=2 + i * 5,
            )
        )
        ax.add_patch(
            Polygon(
                [(cx - wt, y0), (cx + wt, y0), (cx + wt, y0 - 0.10), (cx - wt, y0 - 0.10)],
                closed=True, facecolor=top_c, edgecolor="none", zorder=3 + i * 5,
            )
        )
        fold_c = _hex_darken(body_c, 0.14)
        ax.add_patch(
            Polygon(
                [(cx - wb, y1), (cx + wb, y1), (cx + wb * 0.96, y1 - fold_h), (cx - wb * 0.96, y1 - fold_h)],
                closed=True, facecolor=fold_c, edgecolor="none", zorder=4 + i * 5,
            )
        )

    y0 = y_top - (n - 1) * seg_h
    y1 = y0 - seg_h + neck * 1.15
    wb = half_w[-1]
    top_c, body_c = _fig4a_layer_colors(stages[-1][2])
    ax.add_patch(
        Polygon(
            [(cx - wb, y0), (cx + wb, y0), (cx + wb, y1), (cx - wb, y1)],
            closed=True, facecolor=body_c, edgecolor="#ffffff", linewidth=1.4,
            joinstyle="round", zorder=2 + (n - 1) * 5,
        )
    )
    ax.add_patch(
        Polygon(
            [(cx - wb, y0), (cx + wb, y0), (cx + wb, y0 - 0.10), (cx - wb, y0 - 0.10)],
            closed=True, facecolor=top_c, edgecolor="none", zorder=3 + (n - 1) * 5,
        )
    )

    if side_titles is None:
        side_titles = [title for _, title, _ in stages]

    for i, ((tag, title, color), val, _hw) in enumerate(zip(stages, levels, half_w)):
        y_mid = y_top - i * seg_h - seg_h / 2 + (neck / 2 if i < n - 1 else neck * 0.32)
        hw_mid = _fig4a_hw_at_mid(i, half_w, n)
        center_color = (
            center_text_colors[i]
            if center_text_colors and i in center_text_colors
            else ("#1a202c" if i < 2 else "#ffffff")
        )
        center_fontsize = 10.2 if i == 3 and center_text_colors and 3 in center_text_colors else (10.8 if i < 2 else 10.2)

        ax.text(
            FIG4A_LEFT_TAG_X, y_mid, tag, va="center", ha="left",
            fontsize=13.5, fontweight="bold", color=color, zorder=30,
            clip_on=False,
        )

        center_lines = [title, f"{int(round(val)):,}"]
        extra = center_extra_line(i, val)
        if extra:
            center_lines.append(extra)
        ax.text(
            cx, y_mid, "\n".join(center_lines), va="center", ha="center",
            fontsize=center_fontsize, fontweight="bold", color=center_color,
            linespacing=1.18, zorder=22, clip_on=False,
        )

        line_x = FIG4A_ANNOT_X
        line_start = min(cx + hw_mid + 0.012, line_x - 0.02)
        ax.plot([line_start, line_x], [y_mid, y_mid], color="#cbd5e0", linewidth=1.0, solid_capstyle="round", zorder=18)
        ax.plot(line_x, y_mid, "o", color="#94a3b8", markersize=3.8, zorder=19)
        ax.text(
            line_x + 0.02, y_mid + 0.11, side_titles[i], va="center", ha="left",
            fontsize=10.5, fontweight="bold", color=color, zorder=30, clip_on=False,
        )
        ax.text(
            line_x + 0.02, y_mid - 0.15, stage_note(i), va="center", ha="left",
            fontsize=8.4, color="#4a5568", zorder=30, clip_on=False,
        )

    ax.set_xlim(0.02, 1.06)
    ax.set_ylim(-0.05, y_top + 0.12)
    ax.set_aspect("auto")
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)


def build_fig4a(v4: pd.DataFrame, out_dir: Path, pdf: bool, *, raw_total: int = FIG4A_L1_DEFAULT) -> None:
    """Fig4A：1:1 复刻参考图样式（固定布局/配色，仅数据随 CSV 变化）。"""
    stats = compute_funnel_skill_levels(v4, raw_total=raw_total)
    l1, l2, l3, l4 = stats["level1"], stats["level2"], stats["level3"], stats["level4"]
    filtered = stats["filtered_from_l1"]

    levels = [float(l1), float(l2), float(l3), float(l4)]
    stages = [
        ("L1", "Raw corpus", FIG4A_STAGE_COLORS[0]),
        ("L2", "Valid dataset", FIG4A_STAGE_COLORS[1]),
        ("L3", "Over-privileged", FIG4A_STAGE_COLORS[2]),
        ("L4", "Toxic / high-risk", FIG4A_STAGE_COLORS[3]),
    ]

    fig, ax = plt.subplots(figsize=FIG4A_FIGSIZE)
    fig.patch.set_facecolor(FIG4A_BG)
    ax.set_facecolor(FIG4A_BG)

    def _stage_note(i: int) -> str:
        if i == 0 and l1 > 0:
            return f"Retain {100.0 * l2 / l1:.1f}% after filtering ({filtered:,} removed)"
        if i == 1:
            return "Mapped to PermAudit framework"
        if i == 2 and l2 > 0:
            return f"{100.0 * l3 / l2:.1f}% of valid set are over-privileged"
        if i == 3 and l2 > 0:
            return f"{100.0 * l4 / l2:.1f}% of valid set are toxic / high-risk"
        return ""

    def _center_extra(i: int, val: float) -> str | None:
        if l2 and i >= 2:
            return f"({100.0 * val / l2:.1f}% of L2)"
        return None

    _render_fig4_funnel(
        ax, levels=levels, stages=stages, stage_note=_stage_note, center_extra_line=_center_extra,
    )
    fig.subplots_adjust(left=0.10, right=0.98, top=0.98, bottom=0.04)

    png_path = out_dir / "fig4a_funnel.png"
    pdf_path = out_dir / "fig4a_funnel.pdf" if pdf else None
    save_fig(fig, png_path, pdf_path, pad_inches=0.14, use_tight_layout=False)

    meta = {
        "level_values": {"level1": l1, "level2": l2, "level3": l3, "level4": l4},
        "filtered_from_l1": filtered,
        "stage_colors": FIG4A_STAGE_COLORS,
        "style": "fig4a_reference_v1",
        "l3_pct_of_l2": stats["l3_pct_of_l2"],
        "l4_pct_of_l2": stats["l4_pct_of_l2"],
    }
    (out_dir / "fig4a_funnel_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    save_figure_caption(out_dir, "fig4a_funnel", FIGURE_CAPTIONS["fig4a"])
    print(f"Saved: {png_path}")


FIG4A_DOWNLOAD_TOP_PCT = 1.0
FIG4A_DOWNLOAD_L4_CENTER_TEXT = "#ffffff"
FIG4A_DOWNLOAD_MIN_LAST_HALF_W = 0.105
_DOWNLOAD_FUNNEL_COLS = (
    "estimated_download_count", "pdei_score",
    "delta_t1", "delta_t2", "delta_t3", "delta_t4",
    "path_A", "path_B", "path_C", "path_D", "path_E",
)


def compute_funnel_download_levels(
    v4: pd.DataFrame,
    *,
    top_pct: float = FIG4A_DOWNLOAD_TOP_PCT,
) -> dict[str, int | float]:
    """Download-volume funnel: total → over-privileged → toxic-combo → top PDEI within toxic."""
    d = v4.copy()
    for c in _DOWNLOAD_FUNNEL_COLS:
        if c not in d.columns:
            raise ValueError(f"Download funnel missing column {c!r}. Have: {list(d.columns)}")
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)
    d["_dl"] = d["estimated_download_count"].clip(lower=0)
    d["n_redundant"] = d["delta_t1"] + d["delta_t2"] + d["delta_t3"] + d["delta_t4"]
    d["over_priv"] = d["n_redundant"] >= 1
    d["toxic_any"] = d[["path_A", "path_B", "path_C", "path_D", "path_E"]].sum(axis=1) > 0

    l1 = int(d["_dl"].sum())
    l2 = int(d.loc[d["over_priv"], "_dl"].sum())
    l3 = int(d.loc[d["toxic_any"], "_dl"].sum())

    toxic = d[d["toxic_any"]]
    k = max(1, int(math.ceil(top_pct / 100.0 * len(toxic))))
    top_idx = toxic.nlargest(k, "pdei_score").index
    l4 = int(d.loc[top_idx, "_dl"].sum())

    return {
        "level1": l1,
        "level2": l2,
        "level3": l3,
        "level4": l4,
        "top_toxic_skill_count": k,
        "toxic_skill_count": int(len(toxic)),
        "l2_pct_of_l1": round(100.0 * l2 / l1, 2) if l1 else 0.0,
        "l3_pct_of_l2": round(100.0 * l3 / l2, 2) if l2 else 0.0,
        "l4_pct_of_l3": round(100.0 * l4 / l3, 2) if l3 else 0.0,
        "l4_pct_of_l1": round(100.0 * l4 / l1, 2) if l1 else 0.0,
    }


def build_fig4a_download(
    v4: pd.DataFrame,
    out_dir: Path,
    pdf: bool,
    *,
    top_pct: float = FIG4A_DOWNLOAD_TOP_PCT,
) -> None:
    """Fig4A download variant: funnel of estimated download counts (same layout as skill funnel)."""
    stats = compute_funnel_download_levels(v4, top_pct=top_pct)
    l1, l2, l3, l4 = stats["level1"], stats["level2"], stats["level3"], stats["level4"]
    k_top = int(stats["top_toxic_skill_count"])

    levels = [float(l1), float(l2), float(l3), float(l4)]
    stages = [
        ("L1", "Total downloads", FIG4A_STAGE_COLORS[0]),
        ("L2", "Over-privileged", FIG4A_STAGE_COLORS[1]),
        ("L3", "Toxic-combo", FIG4A_STAGE_COLORS[2]),
        ("L4", f"Top {top_pct:g}% PDEI", FIG4A_STAGE_COLORS[3]),
    ]
    side_titles = [
        "Level 1: Skill total downloads",
        "Level 2: Users covered by over-privileged skills",
        "Level 3: High-risk users covered by toxic-combo skills",
        f"Level 4: User volume in Top {top_pct:g}% extreme PDEI skills (within toxic-combo)",
    ]

    fig, ax = plt.subplots(figsize=FIG4A_FIGSIZE)
    fig.patch.set_facecolor(FIG4A_BG)
    ax.set_facecolor(FIG4A_BG)

    def _stage_note(i: int) -> str:
        if i == 0 and l1 > 0:
            return f"{100.0 * l2 / l1:.1f}% of download volume from over-privileged skills"
        if i == 1 and l2 > 0:
            return f"{100.0 * l3 / l2:.1f}% of over-privileged volume is toxic-combo"
        if i == 2 and l3 > 0:
            return f"{100.0 * l4 / l3:.1f}% of toxic-combo volume in top {top_pct:g}% PDEI tail"
        if i == 3 and l1 > 0:
            return f"{100.0 * l4 / l1:.1f}% of total download volume in extreme tail"
        return ""

    prev_levels = [l1, l2, l3]

    def _center_extra(i: int, val: float) -> str | None:
        if i == 0:
            return None
        denom = prev_levels[i - 1]
        if denom > 0:
            return f"({100.0 * val / denom:.1f}% of L{i})"
        return None

    _render_fig4_funnel(
        ax,
        levels=levels,
        stages=stages,
        stage_note=_stage_note,
        center_extra_line=_center_extra,
        side_titles=side_titles,
        center_text_colors={3: FIG4A_DOWNLOAD_L4_CENTER_TEXT},
        min_last_half_w=FIG4A_DOWNLOAD_MIN_LAST_HALF_W,
    )
    fig.subplots_adjust(left=0.10, right=0.98, top=0.98, bottom=0.04)

    png_path = out_dir / "fig4a_download_funnel.png"
    pdf_path = out_dir / "fig4a_download_funnel.pdf" if pdf else None
    save_fig(fig, png_path, pdf_path, pad_inches=0.14, use_tight_layout=False)

    meta = {
        "level_values": {"level1": l1, "level2": l2, "level3": l3, "level4": l4},
        "top_pct_within_toxic": top_pct,
        "top_toxic_skill_count": k_top,
        "toxic_skill_count": stats["toxic_skill_count"],
        "stage_colors": FIG4A_STAGE_COLORS,
        "style": "fig4a_download_v1",
        "l2_pct_of_l1": stats["l2_pct_of_l1"],
        "l3_pct_of_l2": stats["l3_pct_of_l2"],
        "l4_pct_of_l3": stats["l4_pct_of_l3"],
        "l4_pct_of_l1": stats["l4_pct_of_l1"],
    }
    (out_dir / "fig4a_download_funnel_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    stats_path = out_dir / "fig4a_download_funnel_stats.txt"
    stats_path.write_text(
        "\n".join([
            "Download-volume impact funnel",
            f"  L1 total downloads = {l1:,}",
            f"  L2 over-privileged downloads = {l2:,} ({stats['l2_pct_of_l1']:.2f}% of L1)",
            f"  L3 toxic-combo downloads = {l3:,} ({stats['l3_pct_of_l2']:.2f}% of L2)",
            f"  L4 top {top_pct:g}% PDEI within toxic downloads = {l4:,} ({stats['l4_pct_of_l3']:.2f}% of L3)",
            f"  toxic skills = {stats['toxic_skill_count']:,}; top slice k = {k_top:,}",
        ]),
        encoding="utf-8",
    )
    save_figure_caption(out_dir, "fig4a_download_funnel", FIGURE_CAPTIONS["fig4a_download"])
    print(f"Saved: {png_path}")


# ---------------------------------------------------------------------------
# Fig2: PDEI distribution & developer reputation
# ---------------------------------------------------------------------------

PDEI_COL = "pdei_score"
N_EFF_COL = "n_eff"
PHI_COL = "phi"
GAMMA_COL = "gamma"
DOWNLOAD_COL = "estimated_download_count"
DEVELOPER_COL = "developer"
IS_ORG_COL = "developer_is_org"
STAR_COL = "developer_github_stars"
FIG2A_TOP_PERCENT = 1.0
FIG2A_MIN_TAIL_N = 30
FIG2A_MAX_QUANTILE_FOR_XMIN = 0.90
FIG2A_XMIN_QUANTILE_POINTS = 181
FIG2A_BOOTSTRAP_N = 100
FIG2A_BOOTSTRAP_SEED = 42
FIG2A_BOOTSTRAP_SIZE = "tail"
FIG2A_BOOTSTRAP_XMIN_QUANTILE_POINTS = 61
FIG2A_MAX_SCATTER_POINTS = 12_000


def _fig2_compute_downstream_exposure(df: pd.DataFrame) -> pd.Series:
    """E = N_eff × Φ × Γ (Methods §4.6 / M4); linear reach weight without double-counting Reach in PDEI."""
    for col in [N_EFF_COL, PHI_COL, GAMMA_COL]:
        if col not in df.columns:
            raise ValueError(f"Fig2A missing column {col!r} for downstream exposure. Have: {list(df.columns)}")
    n_eff = pd.to_numeric(df[N_EFF_COL], errors="coerce").fillna(0).clip(lower=0)
    phi = pd.to_numeric(df[PHI_COL], errors="coerce").fillna(0).clip(lower=0)
    gamma = pd.to_numeric(df[GAMMA_COL], errors="coerce").fillna(0).clip(lower=0)
    return n_eff * phi * gamma


def _fig2a_subsample_ccdf_for_display(
    x: np.ndarray,
    ccdf: np.ndarray,
    max_points: int = FIG2A_MAX_SCATTER_POINTS,
) -> tuple[np.ndarray, np.ndarray]:
    """Log-uniform downsampling for vector export; CCDF statistics still use full data."""
    n = len(x)
    if n <= max_points:
        return x, ccdf
    log_x = np.log10(np.maximum(x, np.finfo(float).tiny))
    targets = np.linspace(log_x[0], log_x[-1], max_points)
    idx = np.searchsorted(log_x, targets, side="left")
    idx = np.clip(idx, 0, n - 1)
    idx = np.unique(idx)
    if idx[0] != 0:
        idx = np.concatenate(([0], idx))
    if idx[-1] != n - 1:
        idx = np.concatenate((idx, [n - 1]))
    return x[idx], ccdf[idx]


def _fig2a_scatter_ccdf(ax, x: np.ndarray, ccdf: np.ndarray):
    return ax.scatter(
        x,
        ccdf,
        s=18,
        alpha=0.62,
        color="#4A9FD4",
        edgecolors="none",
        label="Empirical CCDF",
        zorder=1,
    )

STAR_BINS: Sequence[Tuple[str, float, float]] = (
    ("0", 0, 1),
    ("1–9", 1, 10),
    ("10–99", 10, 100),
    ("100–999", 100, 1000),
    ("1k–9.9k", 1000, 10000),
    ("10k+", 10000, float("inf")),
)

REG_CONFLICT_LAWS = ["GDPR", "EU AI Act", "CCPA", "PIPL"]
ABUSE_CATEGORIES_8 = [
    "Data exfiltration",
    "Identity impersonation",
    "Execution poisoning",
    "Autonomous propagation",
    "Physical sensing & real-world interference",
    "Privilege creep",
    "System disruption",
    "Covert manipulation & social engineering",
]
ABUSE_CATEGORY_ALIASES: dict[str, str] = {
    "数据外泄类": "Data exfiltration",
    "身份冒用类": "Identity impersonation",
    "执行投毒类": "Execution poisoning",
    "自动扩散类": "Autonomous propagation",
    "物理感知与现实干扰类": "Physical sensing & real-world interference",
    "权限蠕动类": "Privilege creep",
    "系统破坏类": "System disruption",
    "隐蔽操控与社会工程类": "Covert manipulation & social engineering",
}
REG_CONFLICT_LAW_ALIASES: dict[str, str] = {
    "中国个保法": "PIPL",
    "个保法": "PIPL",
    "china pipl": "PIPL",
    "china_pipl": "PIPL",
    "pipl": "PIPL",
}
ABUSE_CATEGORY_DISPLAY: dict[str, str] = {
    "Physical sensing & real-world interference": "Physical sensing &\nreal-world interference",
    "Covert manipulation & social engineering": "Covert manipulation &\nsocial engineering",
}
# Fig4B built-in normative conflict scores (8 abuse categories × 4 statutes).
DEFAULT_REG_CONFLICT_SCORES: dict[str, tuple[float, float, float, float]] = {
    "Data exfiltration": (0.92, 0.78, 0.78, 0.93),
    "Identity impersonation": (0.88, 0.80, 0.72, 0.88),
    "Execution poisoning": (0.68, 0.94, 0.62, 0.70),
    "Autonomous propagation": (0.85, 0.93, 0.72, 0.86),
    "Physical sensing & real-world interference": (0.94, 0.86, 0.82, 0.94),
    "Privilege creep": (0.82, 0.79, 0.68, 0.81),
    "System disruption": (0.72, 0.88, 0.65, 0.73),
    "Covert manipulation & social engineering": (0.84, 0.87, 0.74, 0.85),
}


def gini(values: pd.Series | np.ndarray) -> float:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return float("nan")
    if np.min(x) < 0:
        x = x - np.min(x)
    total = np.sum(x)
    if total == 0:
        return float("nan")
    x = np.sort(x)
    n = len(x)
    return float((2.0 * np.dot(np.arange(1, n + 1), x) / (n * total)) - (n + 1) / n)


def normalize_bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .isin(["true", "1", "yes", "y", "org", "organization"])
    )


def _fig2_top_share(values: pd.Series, top_pct: float) -> Tuple[int, float, pd.Index]:
    x = pd.to_numeric(values, errors="coerce").fillna(0).astype(float)
    k = max(1, int(math.ceil(len(x) * top_pct / 100.0)))
    top_idx = x.nlargest(k).index
    total = float(x.sum())
    share = float(x.loc[top_idx].sum() / total) if total > 0 else float("nan")
    return k, share, top_idx


def _fig2_xmin_candidates(x: np.ndarray, max_quantile: float, *, n_points: int) -> np.ndarray:
    return np.unique(np.quantile(x, np.linspace(0, max_quantile, n_points)))


def _pareto_tail_ks_D(tail: np.ndarray, xmin: float, alpha: float) -> float:
    tail = np.sort(np.asarray(tail, dtype=float))
    n = len(tail)
    if n == 0 or alpha <= 1.0:
        return float("inf")
    ecdf = np.arange(1, n + 1, dtype=float) / n
    theoretical = 1.0 - np.power(tail / xmin, 1.0 - alpha)
    return float(np.max(np.abs(ecdf - theoretical)))


def _sample_pareto_tail(n: int, xmin: float, alpha: float, rng: np.random.Generator) -> np.ndarray:
    if n <= 0:
        return np.empty(0, dtype=float)
    if alpha <= 1.0:
        raise ValueError(f"Pareto alpha must be > 1 for bootstrap sampling, got {alpha}.")
    u = rng.random(n)
    return xmin * np.power(1.0 - u, 1.0 / (1.0 - alpha))


def _fig2_fit_powerlaw_tail(
    values: pd.Series | np.ndarray,
    *,
    min_tail_n: int = FIG2A_MIN_TAIL_N,
    max_quantile: float = FIG2A_MAX_QUANTILE_FOR_XMIN,
    n_xmin_candidates: int = FIG2A_XMIN_QUANTILE_POINTS,
) -> Dict[str, float]:
    x = np.sort(np.asarray(values, dtype=float))
    x = x[np.isfinite(x) & (x > 0)]
    n = len(x)
    if n < min_tail_n:
        raise ValueError(f"Not enough positive observations for tail fitting: {n} < {min_tail_n}.")

    candidates = _fig2_xmin_candidates(x, max_quantile, n_points=n_xmin_candidates)
    best: Dict[str, float] | None = None
    for xmin in candidates:
        start = int(np.searchsorted(x, xmin, side="left"))
        tail = x[start:]
        n_tail = len(tail)
        if n_tail < min_tail_n:
            continue
        denom = float(np.sum(np.log(tail / xmin)))
        if denom <= 0:
            continue
        alpha = 1.0 + n_tail / denom
        if alpha <= 1.0:
            continue
        ks_d = _pareto_tail_ks_D(tail, xmin, alpha)
        if best is None or ks_d < best["ks_D"]:
            best = {
                "xmin": float(xmin),
                "alpha": float(alpha),
                "n_tail": int(n_tail),
                "tail_fraction": float(n_tail / n),
                "ks_D": float(ks_d),
            }

    if best is None:
        raise ValueError("No valid tail fit found for Fig2A power-law tail.")

    tail = x[x >= best["xmin"]]
    _, ks_p = sp_stats.kstest(tail, "pareto", args=(best["alpha"] - 1.0, 0, best["xmin"]))
    best["ks_p_approx"] = float(ks_p)
    return best


def _fig2_powerlaw_bootstrap_gof(
    values: pd.Series | np.ndarray,
    fit: Dict[str, float],
    *,
    n_bootstrap: int = FIG2A_BOOTSTRAP_N,
    seed: int = FIG2A_BOOTSTRAP_SEED,
    synthetic_size: str = FIG2A_BOOTSTRAP_SIZE,
    min_tail_n: int = FIG2A_MIN_TAIL_N,
    max_quantile: float = FIG2A_MAX_QUANTILE_FOR_XMIN,
) -> Dict[str, float | int | str]:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x) & (x > 0)]
    if n_bootstrap <= 0:
        raise ValueError("n_bootstrap must be positive.")
    if synthetic_size == "full":
        n_syn = len(x)
    elif synthetic_size == "tail":
        n_syn = int(fit["n_tail"])
    else:
        raise ValueError(f"Unknown synthetic_size {synthetic_size!r}; expected 'tail' or 'full'.")

    rng = np.random.default_rng(seed)
    d_obs = float(fit["ks_D"])
    d_sims: list[float] = []
    for _ in range(n_bootstrap):
        synthetic = _sample_pareto_tail(n_syn, fit["xmin"], fit["alpha"], rng)
        try:
            syn_fit = _fig2_fit_powerlaw_tail(
                synthetic,
                min_tail_n=min_tail_n,
                max_quantile=max_quantile,
                n_xmin_candidates=FIG2A_BOOTSTRAP_XMIN_QUANTILE_POINTS,
            )
        except ValueError:
            continue
        d_sims.append(float(syn_fit["ks_D"]))

    d_sims_arr = np.asarray(d_sims, dtype=float)
    if len(d_sims_arr) == 0:
        bootstrap_p = float("nan")
    else:
        bootstrap_p = float(np.mean(d_sims_arr >= d_obs))

    return {
        "bootstrap_p": bootstrap_p,
        "bootstrap_n_requested": int(n_bootstrap),
        "bootstrap_n_success": int(len(d_sims_arr)),
        "bootstrap_d_obs": d_obs,
        "bootstrap_d_sim_mean": float(np.mean(d_sims_arr)) if len(d_sims_arr) else float("nan"),
        "bootstrap_d_sim_median": float(np.median(d_sims_arr)) if len(d_sims_arr) else float("nan"),
        "bootstrap_synthetic_size_mode": synthetic_size,
        "bootstrap_synthetic_n": int(n_syn),
        "bootstrap_seed": int(seed),
    }


def _fig2_fit_lognormal_tail(tail: np.ndarray) -> Tuple[float, float]:
    logx = np.log(np.asarray(tail, dtype=float))
    mu = float(np.mean(logx))
    sigma = float(np.sqrt(np.mean((logx - mu) ** 2)))
    if sigma <= 0:
        sigma = float(np.finfo(float).tiny)
    return mu, sigma


def _fig2_fit_exponential_tail(tail: np.ndarray, xmin: float) -> float:
    shifted = np.asarray(tail, dtype=float) - xmin
    mean_shift = float(np.mean(shifted))
    if mean_shift <= 0:
        raise ValueError("Exponential tail fit requires positive mean(x - xmin).")
    return 1.0 / mean_shift


def _fig2_vuong_test(pointwise_ll_num: np.ndarray, pointwise_ll_den: np.ndarray) -> Dict[str, float]:
    m = np.asarray(pointwise_ll_num, dtype=float) - np.asarray(pointwise_ll_den, dtype=float)
    n = len(m)
    if n < 2:
        return {"vuong_z": float("nan"), "vuong_p": float("nan"), "mean_ll_ratio": float("nan")}
    mu = float(np.mean(m))
    sd = float(np.std(m, ddof=1))
    if sd <= 0:
        return {"vuong_z": float("nan"), "vuong_p": float("nan"), "mean_ll_ratio": mu}
    z = math.sqrt(n) * mu / sd
    p = float(2.0 * sp_stats.norm.sf(abs(z)))
    return {"vuong_z": z, "vuong_p": p, "mean_ll_ratio": mu}


def _fig2_powerlaw_vuong_comparisons(
    values: pd.Series | np.ndarray,
    fit: Dict[str, float],
) -> Dict[str, Dict[str, float]]:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x) & (x > 0)]
    tail = x[x >= fit["xmin"]]
    xmin = float(fit["xmin"])
    alpha = float(fit["alpha"])

    ll_pl = np.log(alpha - 1.0) - np.log(xmin) - alpha * np.log(tail / xmin)

    mu, sigma = _fig2_fit_lognormal_tail(tail)
    log_tail = np.log(tail)
    ll_ln = (
        -log_tail
        - np.log(sigma)
        - 0.5 * np.log(2.0 * np.pi)
        - (log_tail - mu) ** 2 / (2.0 * sigma**2)
    )

    lam = _fig2_fit_exponential_tail(tail, xmin)
    ll_exp = np.log(lam) - lam * (tail - xmin)

    vuong_ln = _fig2_vuong_test(ll_pl, ll_ln)
    vuong_exp = _fig2_vuong_test(ll_pl, ll_exp)
    return {
        "powerlaw": {
            "total_ll": float(np.sum(ll_pl)),
            "alpha": alpha,
            "xmin": xmin,
        },
        "lognormal": {
            **vuong_ln,
            "total_ll": float(np.sum(ll_ln)),
            "mu": mu,
            "sigma": sigma,
        },
        "exponential": {
            **vuong_exp,
            "total_ll": float(np.sum(ll_exp)),
            "lambda": lam,
        },
    }


def _fig2_vuong_winner_label(vuong_z: float, vuong_p: float, *, powerlaw_name: str, alt_name: str) -> str:
    if not np.isfinite(vuong_z) or not np.isfinite(vuong_p):
        return "undetermined"
    if vuong_p >= 0.05:
        return "no significant difference"
    if vuong_z > 0:
        return f"{powerlaw_name} preferred"
    if vuong_z < 0:
        return f"{alt_name} preferred"
    return "no significant difference"


def _fig2_format_bootstrap_stats(bootstrap: Dict[str, float | int | str]) -> str:
    return f"""Bootstrap goodness-of-fit (CSN-style parametric bootstrap):
  synthetic_size_mode = {bootstrap['bootstrap_synthetic_size_mode']}
  synthetic_n = {bootstrap['bootstrap_synthetic_n']}
  n_requested = {bootstrap['bootstrap_n_requested']}
  n_success = {bootstrap['bootstrap_n_success']}
  seed = {bootstrap['bootstrap_seed']}
  D_obs = {bootstrap['bootstrap_d_obs']:.4f}
  D_sim_mean = {bootstrap['bootstrap_d_sim_mean']:.4f}
  D_sim_median = {bootstrap['bootstrap_d_sim_median']:.4f}
  bootstrap_p = {bootstrap['bootstrap_p']:.4f}
  interpretation: p >= 0.05 -> tail consistent with fitted power law; p < 0.05 -> reject power-law tail"""


def _fig2_format_vuong_stats(vuong: Dict[str, Dict[str, float]]) -> str:
    ln = vuong["lognormal"]
    exp = vuong["exponential"]
    ln_winner = _fig2_vuong_winner_label(ln["vuong_z"], ln["vuong_p"], powerlaw_name="power law", alt_name="lognormal")
    exp_winner = _fig2_vuong_winner_label(exp["vuong_z"], exp["vuong_p"], powerlaw_name="power law", alt_name="exponential")
    return f"""Vuong tests on tail x >= xmin (pointwise log-likelihood ratios):
  powerlaw total log-likelihood = {vuong['powerlaw']['total_ll']:.2f}

  vs lognormal:
    mu = {ln['mu']:.4f}; sigma = {ln['sigma']:.4f}
    total log-likelihood = {ln['total_ll']:.2f}
    vuong_z = {ln['vuong_z']:.4f}; vuong_p = {ln['vuong_p']:.4f}
    result = {ln_winner}

  vs exponential:
    lambda = {exp['lambda']:.6f}
    total log-likelihood = {exp['total_ll']:.2f}
    vuong_z = {exp['vuong_z']:.4f}; vuong_p = {exp['vuong_p']:.4f}
    result = {exp_winner}

  interpretation: positive vuong_z favors power law; p < 0.05 indicates a significant preference"""


def build_fig2a(
    pdei_csv: Path,
    out_dir: Path,
    *,
    pdf: bool = False,
    stats_box: str = "outside",
    run_bootstrap: bool = False,
    run_vuong: bool = False,
    bootstrap_n: int = FIG2A_BOOTSTRAP_N,
    bootstrap_seed: int = FIG2A_BOOTSTRAP_SEED,
    bootstrap_size: str = FIG2A_BOOTSTRAP_SIZE,
) -> None:
    df = pd.read_csv(pdei_csv.resolve(), encoding="utf-8-sig")
    if PDEI_COL not in df.columns:
        raise ValueError(f"Fig2A missing column {PDEI_COL!r}. Have: {list(df.columns)}")
    df[PDEI_COL] = pd.to_numeric(df[PDEI_COL], errors="coerce").fillna(0).clip(lower=0)
    df["downstream_exposure"] = _fig2_compute_downstream_exposure(df)

    positive_mask = df[PDEI_COL] > 0
    positive_pdei = df.loc[positive_mask, PDEI_COL]
    gini_pdei = gini(df[PDEI_COL])
    gini_exposure = gini(df["downstream_exposure"])
    gini_pdei_positive = gini(positive_pdei)
    gini_exposure_positive = gini(df.loc[positive_mask, "downstream_exposure"])

    k_top, top_pdei_share, top_pdei_idx = _fig2_top_share(df[PDEI_COL], FIG2A_TOP_PERCENT)
    total_exposure = float(df["downstream_exposure"].sum())
    top_exposure_share = (
        float(df.loc[top_pdei_idx, "downstream_exposure"].sum() / total_exposure)
        if total_exposure > 0
        else float("nan")
    )
    _, top_exposure_share_by_exposure, _ = _fig2_top_share(df["downstream_exposure"], FIG2A_TOP_PERCENT)

    x = np.sort(positive_pdei.to_numpy(dtype=float))
    ccdf = np.arange(len(x), 0, -1) / len(x)
    fig, ax = plt.subplots(figsize=(6.8, 5.2))

    x_plot, ccdf_plot = (
        _fig2a_subsample_ccdf_for_display(x, ccdf)
        if pdf
        else (x, ccdf)
    )
    scatter = _fig2a_scatter_ccdf(ax, x_plot, ccdf_plot)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("PDEI score")
    ax.set_ylabel("Pr(PDEI >= x)")
    ax.grid(True, which="both", linestyle=":", linewidth=0.7, alpha=0.45)
    fig.subplots_adjust(left=0.16, top=0.96)

    if stats_box in ("outside", "inside"):
        annotation = (
            f"n = {len(df):,}; positive = {len(positive_pdei):,}\n"
            f"Gini(PDEI) = {gini_pdei:.2f}; Gini(E) = {gini_exposure:.2f}\n"
            f"Top {FIG2A_TOP_PERCENT:g}%: k = {k_top:,}\n"
            f"PDEI share = {top_pdei_share:.1%}\n"
            f"Exposure share = {top_exposure_share:.1%}"
        )
        ax.text(
            0.04, 0.04, annotation, transform=ax.transAxes, fontsize=8.6, va="bottom", ha="left",
            bbox=dict(boxstyle="round,pad=0.40", facecolor="white", alpha=0.92, linewidth=0.6),
        )

    box_tag = stats_box
    png_path = out_dir / f"fig2a_pdei_ccdf_{box_tag}.png"
    pdf_path = out_dir / f"fig2a_pdei_ccdf_{box_tag}.pdf" if pdf else None
    pad_inches = 0.10
    if pdf_path:
        _savefig_safe(fig, pdf_path, bbox_inches="tight", pad_inches=pad_inches)
        if len(x_plot) < len(x):
            scatter.remove()
            _fig2a_scatter_ccdf(ax, x, ccdf)
    fig.savefig(png_path, dpi=300, bbox_inches="tight", pad_inches=pad_inches)
    plt.close(fig)

    stats_path = out_dir / f"fig2a_stats_{box_tag}.txt"
    stats_lines = [
        f"Input file: {pdei_csv}",
        f"Number of skills: {len(df)}",
        f"Positive PDEI skills: {len(positive_pdei)}",
        f"Zero-PDEI skills: {int((df[PDEI_COL] == 0).sum())}",
        "",
        "Downstream exposure definition: E = n_eff * phi * gamma (Methods M4/M6)",
        "",
    ]
    if run_bootstrap or run_vuong:
        fit = _fig2_fit_powerlaw_tail(positive_pdei)
        stats_lines.extend(
            [
                "Exploratory power-law tail fit (not used in main figure):",
                f"  alpha = {fit['alpha']:.4f}",
                f"  xmin = {fit['xmin']:.4f}",
                f"  tail_n = {fit['n_tail']}",
                f"  tail_fraction = {fit['tail_fraction']:.4f}",
                f"  KS_D = {fit['ks_D']:.4f}",
                f"  KS_p_approx = {fit['ks_p_approx']:.4f}",
            ]
        )
        if run_bootstrap:
            bootstrap = _fig2_powerlaw_bootstrap_gof(
                positive_pdei,
                fit,
                n_bootstrap=bootstrap_n,
                seed=bootstrap_seed,
                synthetic_size=bootstrap_size,
            )
            stats_lines.extend(["", _fig2_format_bootstrap_stats(bootstrap)])
        if run_vuong:
            vuong = _fig2_powerlaw_vuong_comparisons(positive_pdei, fit)
            stats_lines.extend(["", _fig2_format_vuong_stats(vuong)])
    stats_lines.extend(
        [
            "",
            "Gini coefficients (corpus-level, all N; includes zero-PDEI skills):",
            f"  Gini_PDEI = {gini_pdei:.4f}",
            f"  Gini_downstream_exposure = {gini_exposure:.4f}",
            "",
            "Gini sensitivity (PDEI > 0 only, n+):",
            f"  Gini_PDEI = {gini_pdei_positive:.4f}",
            f"  Gini_downstream_exposure = {gini_exposure_positive:.4f}",
            "",
            "Concentration (top 1% by PDEI rank):",
            f"  top_pct = {FIG2A_TOP_PERCENT:.4f}%",
            f"  top_count = {k_top}",
            f"  top_PDEI_share = {top_pdei_share:.4%}",
            f"  top_downstream_exposure_share_among_top_PDEI_skills = {top_exposure_share:.4%}",
            f"  top_downstream_exposure_share_if_ranked_by_exposure = {top_exposure_share_by_exposure:.4%}",
        ]
    )
    stats_path.write_text("\n".join(stats_lines).strip(), encoding="utf-8")
    save_figure_caption(out_dir, f"fig2a_pdei_ccdf_{box_tag}", FIGURE_CAPTIONS["fig2a"])
    print(f"Saved: {png_path}")


def _fig2_aggregate_developers(df: pd.DataFrame, *, min_skills: int = 1) -> pd.DataFrame:
    agg = (
        df.groupby([DEVELOPER_COL, IS_ORG_COL], as_index=False)
        .agg(
            avg_pdei=(PDEI_COL, "mean"),
            median_pdei=(PDEI_COL, "median"),
            max_pdei=(PDEI_COL, "max"),
            developer_github_stars=(STAR_COL, "first"),
            n_skills=(PDEI_COL, "size"),
        )
    )
    agg = agg[agg["n_skills"] >= min_skills].copy()
    if len(agg) < 3:
        raise ValueError("Too few developers after filtering for Fig2B.")
    return agg


def build_fig2b(
    pdei_csv: Path,
    out_dir: Path,
    *,
    pdf: bool = False,
    min_skills_per_developer: int = 1,
    legend_pos: str = "inside",
    stats_box: str = "inside",
) -> None:
    df = pd.read_csv(pdei_csv.resolve(), encoding="utf-8-sig")
    for col in [DEVELOPER_COL, IS_ORG_COL, STAR_COL, PDEI_COL]:
        if col not in df.columns:
            raise ValueError(f"Fig2B missing column {col!r}. Have: {list(df.columns)}")
    df[PDEI_COL] = pd.to_numeric(df[PDEI_COL], errors="coerce").fillna(0).clip(lower=0)
    df[STAR_COL] = pd.to_numeric(df[STAR_COL], errors="coerce").fillna(0).clip(lower=0)
    df[IS_ORG_COL] = normalize_bool_series(df[IS_ORG_COL])
    df[DEVELOPER_COL] = df[DEVELOPER_COL].fillna("unknown_developer").astype(str)
    agg = _fig2_aggregate_developers(df, min_skills=min_skills_per_developer)
    rho, pval = sp_stats.spearmanr(agg["developer_github_stars"], agg["avg_pdei"])

    fig, ax = plt.subplots(figsize=(6.8, 4.8))
    for is_org, label, marker in [(False, "Individual developer", "o"), (True, "Organization", "s")]:
        sub = agg[agg[IS_ORG_COL] == is_org]
        if sub.empty:
            continue
        sizes = 24 + 12 * np.sqrt(sub["n_skills"].to_numpy())
        ax.scatter(
            np.log10(sub["developer_github_stars"] + 1),
            np.log10(sub["avg_pdei"] + 1),
            s=sizes, alpha=0.72, label=label, marker=marker, edgecolors="white", linewidths=0.5,
        )
    ax.set_xlabel("Developer GitHub stars, log10(stars + 1)")
    ax.set_ylabel("Average PDEI per developer, log10(PDEI + 1)")
    ax.grid(True, linestyle=":", linewidth=0.7, alpha=0.45)
    fig.subplots_adjust(left=0.14, top=0.96)
    if legend_pos == "inside":
        ax.legend(loc="upper left", bbox_to_anchor=(0.02, 0.98), frameon=False, fontsize=8.8)
    elif legend_pos == "outside":
        fig.subplots_adjust(right=0.74)
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.00), frameon=False, fontsize=8.8)

    annotation = f"Spearman rho={rho:.2f}, p={pval:.3f}\ndevelopers={len(agg):,}\nGini(avg PDEI)={gini(agg['avg_pdei']):.2f}"
    if stats_box == "inside":
        ax.text(
            0.98, 0.05, annotation, transform=ax.transAxes, fontsize=8.6, va="bottom", ha="right",
            bbox=dict(boxstyle="round,pad=0.35", facecolor="white", alpha=0.86, linewidth=0.5),
        )
    elif stats_box == "outside":
        fig.subplots_adjust(right=0.72)
        fig.text(
            0.745, 0.25, annotation, fontsize=8.6, va="bottom", ha="left",
            bbox=dict(boxstyle="round,pad=0.35", facecolor="white", alpha=0.90, linewidth=0.5),
        )

    suffix = f"min{min_skills_per_developer}skills_{legend_pos}legend_{stats_box}stats"
    png_path = out_dir / f"fig2b_developer_stars_vs_avg_pdei_{suffix}.png"
    pdf_path = out_dir / f"fig2b_developer_stars_vs_avg_pdei_{suffix}.pdf" if pdf else None
    save_fig(fig, png_path, pdf_path, pad_inches=0.10, use_tight_layout=False)

    stats_path = out_dir / f"fig2b_stats_{suffix}.txt"
    stats_path.write_text(
        f"""Input file: {pdei_csv}
Number of skills: {len(df)}
Number of developers after filtering: {len(agg)}
Minimum skills per developer: {min_skills_per_developer}

Developer reputation correlation:
  Spearman_rho = {rho:.4f}
  Spearman_p = {pval:.4f}

Developer-level PDEI summary:
  avg_PDEI_mean = {agg['avg_pdei'].mean():.4f}
  avg_PDEI_median = {agg['avg_pdei'].median():.4f}
  avg_PDEI_max = {agg['avg_pdei'].max():.4f}
  Gini_avg_PDEI = {gini(agg['avg_pdei']):.4f}

Developer type counts:
{agg[IS_ORG_COL].map({True: 'Organization', False: 'Individual'}).value_counts().to_string()}
""".strip(),
        encoding="utf-8",
    )
    save_figure_caption(out_dir, f"fig2b_developer_stars_vs_avg_pdei_{suffix}", FIGURE_CAPTIONS["fig2b"])
    print(f"Saved: {png_path}")


def _fig2_assign_star_bin(stars: float) -> str:
    for label, lo, hi in STAR_BINS:
        if lo <= stars < hi:
            return label
    return STAR_BINS[-1][0]


def build_fig2b_bins(
    pdei_csv: Path,
    out_dir: Path,
    *,
    pdf: bool = False,
    min_skills_per_developer: int = 1,
    plot_style: str = "both",
    log_y: bool = True,
    split_org: bool = True,
) -> None:
    df = pd.read_csv(pdei_csv.resolve(), encoding="utf-8-sig")
    for col in [DEVELOPER_COL, IS_ORG_COL, STAR_COL, PDEI_COL]:
        if col not in df.columns:
            raise ValueError(f"Fig2B bins missing column {col!r}. Have: {list(df.columns)}")
    df[PDEI_COL] = pd.to_numeric(df[PDEI_COL], errors="coerce").fillna(0).clip(lower=0)
    df[STAR_COL] = pd.to_numeric(df[STAR_COL], errors="coerce").fillna(0).clip(lower=0)
    df[IS_ORG_COL] = normalize_bool_series(df[IS_ORG_COL])
    df[DEVELOPER_COL] = df[DEVELOPER_COL].fillna("unknown_developer").astype(str)

    agg = _fig2_aggregate_developers(df, min_skills=min_skills_per_developer)
    agg["star_bin"] = agg["developer_github_stars"].map(_fig2_assign_star_bin)
    bin_labels = [b[0] for b in STAR_BINS]
    agg["star_bin"] = pd.Categorical(agg["star_bin"], categories=bin_labels, ordered=True)
    rho, pval = sp_stats.spearmanr(agg["developer_github_stars"], agg["avg_pdei"])

    y = np.log10(agg["avg_pdei"].to_numpy(dtype=float) + 1.0) if log_y else agg["avg_pdei"].to_numpy(dtype=float)
    agg = agg.assign(_y=y)
    n_bins = len(STAR_BINS)
    groups: List[np.ndarray] = []
    tick_labels: List[str] = []
    if split_org:
        width = 0.35
        positions: List[float] = []
        for i, label in enumerate(bin_labels):
            mask = agg["star_bin"] == label
            positions.extend([i - width / 2, i + width / 2])
            for is_org in (False, True):
                sub = agg.loc[mask & (agg[IS_ORG_COL] == is_org), "_y"]
                groups.append(sub.to_numpy(dtype=float))
            tick_labels.append(f"{label}\n(n={int(mask.sum()):,})")
    else:
        width = 0.65
        positions = list(range(n_bins))
        for label in bin_labels:
            sub = agg.loc[agg["star_bin"] == label, "_y"]
            groups.append(sub.to_numpy(dtype=float))
            tick_labels.append(f"{label}\n(n={len(sub):,})")

    fig_w = 9.6 if split_org else 8.0
    fig, ax = plt.subplots(figsize=(fig_w, 5.2))
    parts = None
    if plot_style in ("violin", "both"):
        parts = ax.violinplot(
            groups, positions=positions, widths=width * 0.95,
            showmeans=False, showmedians=True, showextrema=False,
        )
        for body in parts["bodies"]:
            body.set_alpha(0.35)
            body.set_edgecolor("none")
        if "cmedians" in parts:
            parts["cmedians"].set_color("0.25")
            parts["cmedians"].set_linewidth(1.2)
    if plot_style in ("box", "both"):
        bp = ax.boxplot(
            groups, positions=positions,
            widths=width * 0.55 if plot_style == "both" else width * 0.7,
            patch_artist=True, showfliers=False,
            medianprops=dict(color="black", linewidth=1.4),
            boxprops=dict(facecolor="white", alpha=0.85, linewidth=1.0),
        )
        colors = (["#4C72B0", "#DD8452"] * n_bins) if split_org else ["#4C72B0"] * n_bins
        for i, patch in enumerate(bp["boxes"]):
            patch.set_facecolor(colors[i])
            patch.set_alpha(0.55 if split_org else 0.45)
        if parts is not None:
            for i, body in enumerate(parts["bodies"]):
                body.set_facecolor(colors[i])

    ax.set_xticks(range(n_bins))
    ax.set_xticklabels(tick_labels, fontsize=9)
    if split_org:
        from matplotlib.patches import Patch
        ax.legend(
            handles=[
                Patch(facecolor="#4C72B0", alpha=0.7, label="Individual"),
                Patch(facecolor="#DD8452", alpha=0.7, label="Organization"),
            ],
            loc="upper left", bbox_to_anchor=(0.02, 0.98), frameon=False, fontsize=9,
        )
    ax.set_ylabel("Average PDEI per developer, log10(PDEI + 1)" if log_y else "Average PDEI per developer")
    ax.set_xlabel("Developer GitHub stars (binned)")
    ax.grid(True, axis="y", linestyle=":", linewidth=0.7, alpha=0.45)
    fig.subplots_adjust(left=0.14, top=0.96)

    p_text = "p<0.001" if pval < 0.001 else f"p={pval:.3f}"
    annotation = f"Spearman rho={rho:.2f}, {p_text}\ndevelopers={len(agg):,}\nGini(avg PDEI)={gini(agg['avg_pdei']):.2f}"
    ax.text(
        0.98, 0.04 if split_org else 0.97, annotation, transform=ax.transAxes,
        fontsize=8.6, va="bottom" if split_org else "top", ha="right",
        bbox=dict(boxstyle="round,pad=0.40", facecolor="white", alpha=0.92, linewidth=0.5), zorder=10,
    )

    style_tag = plot_style
    org_tag = "splitorg" if split_org else "all"
    y_tag = "logy" if log_y else "rawy"
    base = f"fig2b_star_bins_{style_tag}_{org_tag}_{y_tag}"
    png_path = out_dir / f"{base}.png"
    pdf_path = out_dir / f"{base}.pdf" if pdf else None
    save_fig(fig, png_path, pdf_path, pad_inches=0.10, use_tight_layout=False)
    save_figure_caption(out_dir, base, FIGURE_CAPTIONS["fig2b"])
    print(f"Saved: {png_path}")


def build_fig2b_scatter_opt(
    pdei_csv: Path,
    out_dir: Path,
    *,
    pdf: bool = False,
    min_skills_per_developer: int = 1,
    display_subsample: int = 6000,
    seed: int = 42,
) -> None:
    df = pd.read_csv(pdei_csv.resolve(), encoding="utf-8-sig")
    for col in [DEVELOPER_COL, IS_ORG_COL, STAR_COL, PDEI_COL]:
        if col not in df.columns:
            raise ValueError(f"Fig2B scatter_opt missing column {col!r}. Have: {list(df.columns)}")
    df[PDEI_COL] = pd.to_numeric(df[PDEI_COL], errors="coerce").fillna(0).clip(lower=0)
    df[STAR_COL] = pd.to_numeric(df[STAR_COL], errors="coerce").fillna(0).clip(lower=0)
    df[IS_ORG_COL] = normalize_bool_series(df[IS_ORG_COL])
    df[DEVELOPER_COL] = df[DEVELOPER_COL].fillna("unknown_developer").astype(str)
    agg_full = _fig2_aggregate_developers(df, min_skills=min_skills_per_developer)
    rho, pval = sp_stats.spearmanr(agg_full["developer_github_stars"], agg_full["avg_pdei"])

    plot_df = agg_full[agg_full[STAR_COL] > 0].copy()

    def _sample_band(mask: pd.Series, keep_fraction: float, band_id: int) -> pd.DataFrame:
        kept = []
        for is_org in (False, True):
            sub = plot_df[mask & (plot_df[IS_ORG_COL] == is_org)]
            if sub.empty:
                continue
            keep_n = max(1, min(len(sub), int(round(len(sub) * keep_fraction))))
            kept.append(sub.sample(n=keep_n, random_state=seed + band_id * 2 + int(is_org)))
        return pd.concat(kept, ignore_index=True) if kept else plot_df.iloc[0:0]

    stars = plot_df[STAR_COL]
    plot_df = pd.concat([
        _sample_band(stars <= 9, 0.20, 0),
        _sample_band((stars > 9) & (stars <= 99), 0.40, 1),
        _sample_band((stars > 99) & (stars <= 1000), 0.60, 2),
        plot_df[stars > 1000],
    ], ignore_index=True)
    if display_subsample > 0 and len(plot_df) > display_subsample:
        plot_df = plot_df.sample(n=display_subsample, random_state=seed)

    fig, ax = plt.subplots(figsize=(7.4, 4.9))
    for is_org, label, marker, color in [
        (False, "Individual developer", "o", "#4C72B0"),
        (True, "Organization", "s", "#DD8452"),
    ]:
        sub = plot_df[plot_df[IS_ORG_COL] == is_org]
        if sub.empty:
            continue
        n_sk = sub["n_skills"].to_numpy()
        sizes = np.full(len(n_sk), 16.0)
        sizes[n_sk <= 1] = 10.0
        sizes[n_sk >= 11] = 22.0
        ax.scatter(
            np.log10(sub["developer_github_stars"] + 1),
            np.log10(sub["avg_pdei"] + 1),
            s=sizes, alpha=0.24, label=label, marker=marker, color=color,
            edgecolors="none", rasterized=True, zorder=2 if is_org else 1,
        )
    ax.set_xlabel("Developer GitHub stars, log10(stars + 1)")
    ax.set_ylabel("Average PDEI per developer, log10(PDEI + 1)")
    ax.grid(True, linestyle=":", linewidth=0.7, alpha=0.45)
    fig.subplots_adjust(left=0.14, top=0.96)
    ax.legend(loc="upper left", bbox_to_anchor=(0.02, 0.98), frameon=False, fontsize=8.8)
    p_text = "p<0.001" if pval < 0.001 else f"p={pval:.3f}"
    annotation = (
        f"Spearman rho={rho:.2f}, {p_text}\n"
        f"developers={len(agg_full):,} (stats)\n"
        f"plotted n={len(plot_df):,}\n"
        f"Gini(avg PDEI)={gini(agg_full['avg_pdei']):.2f}"
    )
    ax.text(
        0.98, 0.05, annotation, transform=ax.transAxes, fontsize=8.4, va="bottom", ha="right",
        bbox=dict(boxstyle="round,pad=0.40", facecolor="white", alpha=0.92, linewidth=0.5), zorder=10,
    )
    base = "fig2b_scatter_opt_starsgt0_thin_sub6000_insidelegend_insidestats"
    png_path = out_dir / f"{base}.png"
    pdf_path = out_dir / f"{base}.pdf" if pdf else None
    save_fig(fig, png_path, pdf_path, pad_inches=0.10, use_tight_layout=False)
    save_figure_caption(out_dir, base, FIGURE_CAPTIONS["fig2b"])
    print(f"Saved: {png_path}")


def run_fig2_suite(
    pdei_csv: Path,
    out_dir: Path,
    *,
    pdf: bool = False,
    run_bootstrap: bool = False,
    run_vuong: bool = False,
    bootstrap_n: int = FIG2A_BOOTSTRAP_N,
    bootstrap_seed: int = FIG2A_BOOTSTRAP_SEED,
    bootstrap_size: str = FIG2A_BOOTSTRAP_SIZE,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    build_fig2a(
        pdei_csv,
        out_dir,
        pdf=pdf,
        run_bootstrap=run_bootstrap,
        run_vuong=run_vuong,
        bootstrap_n=bootstrap_n,
        bootstrap_seed=bootstrap_seed,
        bootstrap_size=bootstrap_size,
    )
    build_fig2b(pdei_csv, out_dir, pdf=pdf)
    build_fig2b_bins(pdei_csv, out_dir, pdf=pdf, split_org=True)
    build_fig2b_scatter_opt(pdei_csv, out_dir, pdf=pdf)
    save_figure_caption(out_dir, "fig2_combined", FIGURE_CAPTIONS["fig2"])
    print(f"Fig2 DONE: {out_dir}")


# ---------------------------------------------------------------------------
# Fig4B: regulatory conflict matrix
# ---------------------------------------------------------------------------

def _normalize_reg_conflict_columns(df: pd.DataFrame) -> pd.DataFrame:
    alias_to_canon = {
        "gdpr": "GDPR",
        "eu ai act": "EU AI Act",
        "eu_ai_act": "EU AI Act",
        "euaiact": "EU AI Act",
        "ccpa": "CCPA",
        **{k.lower(): v for k, v in REG_CONFLICT_LAW_ALIASES.items()},
    }
    rename: dict[str, str] = {}
    for c in df.columns:
        s = str(c).strip()
        s_low, s_under = s.lower(), s.lower().replace(" ", "_")
        if s in REG_CONFLICT_LAWS:
            rename[c] = s
        elif s in REG_CONFLICT_LAW_ALIASES:
            rename[c] = REG_CONFLICT_LAW_ALIASES[s]
        elif s_low in alias_to_canon:
            rename[c] = alias_to_canon[s_low]
        elif s_under in alias_to_canon:
            rename[c] = alias_to_canon[s_under]
    return df.rename(columns=rename)


def _normalize_abuse_category_index(index: pd.Index) -> pd.Index:
    return pd.Index([ABUSE_CATEGORY_ALIASES.get(str(v).strip(), str(v).strip()) for v in index])


def _finalize_conflict_matrix(body: pd.DataFrame) -> pd.DataFrame:
    body.index = _normalize_abuse_category_index(body.index)
    body = _normalize_reg_conflict_columns(body)
    missing_laws = [c for c in REG_CONFLICT_LAWS if c not in body.columns]
    if missing_laws:
        raise ValueError(f"Missing law columns: {missing_laws}. Have: {list(body.columns)}")
    mat = body[REG_CONFLICT_LAWS].apply(pd.to_numeric, errors="coerce")
    if mat.isna().all().all():
        raise ValueError("Could not parse numeric conflict scores.")
    mat = mat.fillna(0.0).clip(0.0, 1.0)
    order = [c for c in ABUSE_CATEGORIES_8 if c in mat.index]
    extra = [c for c in mat.index if c not in order]
    return mat.loc[order + extra]


def default_conflict_matrix() -> pd.DataFrame:
    """Built-in Fig4B matrix; no external CSV required."""
    missing = [c for c in ABUSE_CATEGORIES_8 if c not in DEFAULT_REG_CONFLICT_SCORES]
    if missing:
        raise ValueError(f"Built-in Fig4B matrix missing categories: {missing}")
    rows = [DEFAULT_REG_CONFLICT_SCORES[c] for c in ABUSE_CATEGORIES_8]
    return pd.DataFrame(rows, index=ABUSE_CATEGORIES_8, columns=REG_CONFLICT_LAWS, dtype=float)


def resolve_conflict_matrix(reg_conflict_csv: Path | None) -> tuple[pd.DataFrame, str]:
    if reg_conflict_csv is not None:
        path = Path(reg_conflict_csv).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Regulatory conflict matrix CSV not found: {path}")
        return load_conflict_matrix(path), str(path)
    return default_conflict_matrix(), "built-in default (generate_figures.py)"


def load_conflict_matrix(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path.resolve(), encoding="utf-8-sig")
    raw.columns = [str(c).strip() for c in raw.columns]
    if "abuse_category" not in raw.columns:
        raw = raw.rename(columns={raw.columns[0]: "abuse_category"})
    return _finalize_conflict_matrix(raw.set_index("abuse_category"))


def build_fig4b(
    out_dir: Path,
    reg_conflict_csv: Path | None = None,
    *,
    pdf: bool = False,
    caption: str | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    matrix, matrix_source = resolve_conflict_matrix(reg_conflict_csv)
    values = matrix.to_numpy(dtype=float)
    annot = np.array([[f"{v:.2f}" for v in row] for row in values], dtype=object)
    y_labels = [ABUSE_CATEGORY_DISPLAY.get(name, name) for name in matrix.index.tolist()]

    sns.set_theme(style="white")
    plt.rcParams["font.sans-serif"] = ["Arial", "Helvetica", "DejaVu Sans"]
    plt.rcParams["font.family"] = "sans-serif"
    fig_h = max(6.8, 0.62 * len(matrix) + 2.2)
    fig, ax = plt.subplots(figsize=(12.0, fig_h))
    sns.heatmap(
        values, ax=ax, cmap="Blues", vmin=0.0, vmax=1.0, annot=annot, fmt="",
        linewidths=0.5, linecolor="white", xticklabels=REG_CONFLICT_LAWS,
        yticklabels=y_labels, annot_kws={"fontsize": 8},
        cbar_kws={"label": "Conflict score (0–1)"},
    )
    ax.set_xlabel("Regulation", fontsize=10)
    ax.set_ylabel("Abuse category", fontsize=10)
    ax.tick_params(axis="x", rotation=0, labelsize=9)
    ax.tick_params(axis="y", rotation=0, labelsize=8.5)
    fig.subplots_adjust(left=0.38, right=0.92, top=0.98, bottom=0.08)

    png_path = out_dir / "fig4b_reg_conflict.png"
    pdf_path = out_dir / "fig4b_reg_conflict.pdf" if pdf else None
    save_fig(fig, png_path, pdf_path, pad_inches=0.12, use_tight_layout=False)

    stats_lines = [
        f"Input matrix: {matrix_source}",
        f"Rows (abuse categories): {len(matrix)}",
        f"Columns (laws): {', '.join(REG_CONFLICT_LAWS)}",
        "",
        "Scoring rubric (0–1 normative conflict, not empirical):",
        "  0.90–1.00  Multiple core provisions directly target the abuse pattern",
        "  0.80–0.89  Strong direct relevance",
        "  0.70–0.79  Significant, sometimes context-dependent",
        "  0.55–0.69  Moderate / indirect (e.g. security generality)",
        "  <0.55      Weak direct fit under privacy-focused statutes",
        "",
        "Matrix values:",
        matrix.round(2).to_string(),
        "",
        f"Row mean: {matrix.mean(axis=1).round(2).to_string()}",
        f"Column mean: {matrix.mean(axis=0).round(2).to_string()}",
    ]
    (out_dir / "fig4b_reg_conflict_stats.txt").write_text("\n".join(stats_lines), encoding="utf-8")
    matrix.round(3).to_csv(out_dir / "fig4b_reg_conflict_matrix.csv", encoding="utf-8-sig")
    save_figure_caption(out_dir, "fig4b_reg_conflict", caption or FIGURE_CAPTIONS["fig4b"])
    print(f"Saved: {png_path}")


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    pdei_csv = (args.pdei_csv or args.v4_csv)
    if args.fig4b_only:
        build_fig4b(out_dir, args.reg_conflict_csv, pdf=args.pdf)
        print("DONE (Fig4B only):", out_dir)
        return

    if args.fig2_only:
        if pdei_csv is None:
            raise ValueError("--fig2-only 需要 --pdei-csv 或 --v4-csv")
        run_fig2_suite(
            pdei_csv.resolve(),
            out_dir,
            pdf=args.pdf,
            run_bootstrap=args.fig2a_run_bootstrap,
            run_vuong=args.fig2a_run_vuong,
            bootstrap_n=args.fig2a_bootstrap_n,
            bootstrap_seed=args.fig2a_bootstrap_seed,
            bootstrap_size=args.fig2a_bootstrap_size,
        )
        print("DONE (Fig2 only):", out_dir)
        return

    if args.v4_csv is None:
        raise ValueError("生成 Fig1/3/4 需要 --v4-csv")

    if not args.skip_fig2:
        if pdei_csv is None:
            pdei_csv = args.v4_csv
        run_fig2_suite(
            pdei_csv.resolve(),
            out_dir,
            pdf=args.pdf,
            run_bootstrap=args.fig2a_run_bootstrap,
            run_vuong=args.fig2a_run_vuong,
            bootstrap_n=args.fig2a_bootstrap_n,
            bootstrap_seed=args.fig2a_bootstrap_seed,
            bootstrap_size=args.fig2a_bootstrap_size,
        )

    v4 = pd.read_csv(args.v4_csv.resolve(), encoding="utf-8-sig")
    required = {
        "domain",
        "source_plat",
        "declaration_atomic_ids",
        "pdei_score",
        "delta_t1",
        "delta_t2",
        "delta_t3",
        "delta_t4",
        "path_A",
        "path_B",
        "path_C",
        "path_D",
        "path_E",
    }
    miss = sorted(required - set(v4.columns))
    if miss:
        raise ValueError(f"v4.csv 缺少必要列: {miss}")

    top_pairs = resolve_top_pairs(top10_csv=args.top10_csv, combo_stats_csv=args.combo_stats_csv)
    funnel_l1 = resolve_funnel_l1(funnel_l1=args.funnel_l1, combo_stats_csv=args.combo_stats_csv, v4_rows=len(v4))

    build_fig1(v4, out_dir, args.top_k, args.pdf)
    build_fig3_suite(v4, top_pairs, out_dir, args.pdf)
    build_fig5_platform_overprivilege(v4, out_dir, args.pdf)
    build_fig4a(v4, out_dir, args.pdf, raw_total=funnel_l1)
    build_fig4a_download(v4, out_dir, args.pdf)

    if not args.skip_fig4b:
        build_fig4b(out_dir, args.reg_conflict_csv, pdf=args.pdf)
        save_figure_caption(out_dir, "fig4_combined", FIGURE_CAPTIONS["fig4"])

    print("DONE:", out_dir)
    print(f"funnel L1={funnel_l1:,}, v4 rows (L2)={len(v4):,}, top pairs={len(top_pairs)}")


if __name__ == "__main__":
    main()

