# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

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


def resolve_funnel_l1(*, funnel_l1: int | None, combo_stats_csv: Path | None, v4_rows: int) -> int:
    if funnel_l1 is not None:
        return int(funnel_l1)
    if combo_stats_csv is not None:
        n = sum(len(c) for c in pd.read_csv(combo_stats_csv.resolve(), encoding="utf-8-sig", usecols=["name"], chunksize=100_000))
        return max(n, v4_rows)
    return 516_370


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

# PDEI v3 毒性路径：两条 Tier 同时冗余（Γ 因子）；Fig3 按 Tier 交叉子矩阵标注
PATH_TIER_RULES: dict[str, tuple[str, str]] = {
    "A": ("T1", "T2"),
    "B": ("T1", "T3"),
    "C": ("T2", "T3"),
    "D": ("T4", "T2"),
    "E": ("T4", "T3"),
}
PATH_EDGE_COLOR = "#d62728"


def _path_letter_for_tiers(ta: str, tb: str) -> str | None:
    pair = {ta, tb}
    for letter, (t1, t2) in PATH_TIER_RULES.items():
        if pair == {t1, t2}:
            return letter
    return None


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
        fig.savefig(out_pdf, bbox_inches="tight", pad_inches=pad_inches)
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
        "Complementary cumulative distribution function (CCDF) of PDEI scores with a power-law tail fit."
    ),
    "fig2b": (
        "Fig. 2b | Developer reputation does not guarantee permission safety. "
        "Relationship between developer GitHub stars and average PDEI per developer."
    ),
    "fig3": (
        "Fig. 3 | Toxic-combo co-occurrence matrix. "
        "Pairwise co-occurrence counts among top toxic atomic-permission combinations; "
        "red boxes mark Path A–E tier-crossing pairs."
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
    "fig4b": (
        "Fig. 4b | Regulatory conflict matrix. "
        "Normative conflict scores (0–1) between abuse categories and "
        "GDPR, EU AI Act, CCPA, and PIPL."
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


def build_fig3(v4: pd.DataFrame, top_pairs: set[tuple[str, str]], out_dir: Path, pdf: bool) -> None:
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

    save_fig(fig, out_dir / "fig3_cooccurrence.png", out_dir / "fig3_cooccurrence.pdf" if pdf else None)
    save_figure_caption(out_dir, "fig3_cooccurrence", FIGURE_CAPTIONS["fig3"])

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
    (out_dir / "fig3_cooccurrence_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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


def _fig4a_half_widths(levels: list[float]) -> list[float]:
    """各层半宽与 Skill 数量成正比，形成漏斗收窄。"""
    max_v = max(levels) if levels else 1.0
    return [FIG4A_HW_BASE * (v / max_v) for v in levels]


def _fig4a_hw_at_mid(i: int, half_w: list[float], n: int) -> float:
    if i < n - 1:
        return (half_w[i] + half_w[i + 1]) / 2
    return half_w[-1]


def build_fig4a(v4: pd.DataFrame, out_dir: Path, pdf: bool, *, raw_total: int = 516_370) -> None:
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
    half_w = _fig4a_half_widths(levels)

    fig, ax = plt.subplots(figsize=FIG4A_FIGSIZE)
    fig.patch.set_facecolor(FIG4A_BG)
    ax.set_facecolor(FIG4A_BG)

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

    for i, ((tag, title, color), val, _hw) in enumerate(zip(stages, levels, half_w)):
        y_mid = y_top - i * seg_h - seg_h / 2 + (neck / 2 if i < n - 1 else neck * 0.32)
        hw_mid = _fig4a_hw_at_mid(i, half_w, n)
        center_color = "#1a202c" if i < 2 else "#ffffff"

        ax.text(
            FIG4A_LEFT_TAG_X, y_mid, tag, va="center", ha="left",
            fontsize=13.5, fontweight="bold", color=color, zorder=30,
            clip_on=False,
        )

        center_lines = [title, f"{int(round(val)):,}"]
        if l2 and i >= 2:
            center_lines.append(f"({100.0 * val / l2:.1f}% of L2)")
        ax.text(
            cx, y_mid, "\n".join(center_lines), va="center", ha="center",
            fontsize=10.8 if i < 2 else 10.2, fontweight="bold", color=center_color,
            linespacing=1.18, zorder=22, clip_on=False,
        )

        line_x = FIG4A_ANNOT_X
        line_start = min(cx + hw_mid + 0.012, line_x - 0.02)
        ax.plot([line_start, line_x], [y_mid, y_mid], color="#cbd5e0", linewidth=1.0, solid_capstyle="round", zorder=18)
        ax.plot(line_x, y_mid, "o", color="#94a3b8", markersize=3.8, zorder=19)
        ax.text(
            line_x + 0.02, y_mid + 0.11, title, va="center", ha="left",
            fontsize=10.5, fontweight="bold", color=color, zorder=30, clip_on=False,
        )
        ax.text(
            line_x + 0.02, y_mid - 0.15, _stage_note(i), va="center", ha="left",
            fontsize=8.4, color="#4a5568", zorder=30, clip_on=False,
        )

    ax.set_xlim(0.02, 1.06)
    ax.set_ylim(-0.05, y_top + 0.12)
    ax.set_aspect("auto")
    fig.subplots_adjust(left=0.10, right=0.98, top=0.98, bottom=0.04)
    add_panel_label(ax, "a")
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)

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


# ---------------------------------------------------------------------------
# Fig2: PDEI distribution & developer reputation
# ---------------------------------------------------------------------------

PDEI_COL = "pdei_score"
DOWNLOAD_COL = "estimated_download_count"
DEVELOPER_COL = "developer"
IS_ORG_COL = "developer_is_org"
STAR_COL = "developer_github_stars"
FIG2A_TOP_PERCENT = 1.0
FIG2A_MIN_TAIL_N = 30
FIG2A_MAX_QUANTILE_FOR_XMIN = 0.90

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


def _fig2_fit_powerlaw_tail(
    values: pd.Series | np.ndarray,
    *,
    min_tail_n: int = FIG2A_MIN_TAIL_N,
    max_quantile: float = FIG2A_MAX_QUANTILE_FOR_XMIN,
) -> Dict[str, float]:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x) & (x > 0)]
    if len(x) < min_tail_n:
        raise ValueError(f"Not enough positive observations for tail fitting: {len(x)} < {min_tail_n}.")
    candidates = np.unique(np.quantile(x, np.linspace(0, max_quantile, 181)))
    best = None
    for xmin in candidates:
        tail = x[x >= xmin]
        n_tail = len(tail)
        if n_tail < min_tail_n:
            continue
        denom = np.sum(np.log(tail / xmin))
        if denom <= 0:
            continue
        alpha = 1.0 + n_tail / denom
        ks_d, ks_p = sp_stats.kstest(tail, "pareto", args=(alpha - 1.0, 0, xmin))
        if best is None or ks_d < best["ks_D"]:
            best = {
                "xmin": float(xmin),
                "alpha": float(alpha),
                "n_tail": int(n_tail),
                "tail_fraction": float(n_tail / len(x)),
                "ks_D": float(ks_d),
                "ks_p_approx": float(ks_p),
            }
    if best is None:
        raise ValueError("No valid tail fit found for Fig2A power-law tail.")
    return best


def build_fig2a(pdei_csv: Path, out_dir: Path, *, pdf: bool = False, stats_box: str = "outside") -> None:
    df = pd.read_csv(pdei_csv.resolve(), encoding="utf-8-sig")
    for col in [PDEI_COL, DOWNLOAD_COL]:
        if col not in df.columns:
            raise ValueError(f"Fig2A missing column {col!r}. Have: {list(df.columns)}")
    df[PDEI_COL] = pd.to_numeric(df[PDEI_COL], errors="coerce").fillna(0).clip(lower=0)
    df[DOWNLOAD_COL] = pd.to_numeric(df[DOWNLOAD_COL], errors="coerce").fillna(0).clip(lower=0)
    df["downstream_exposure"] = df[PDEI_COL] * df[DOWNLOAD_COL]

    positive_pdei = df.loc[df[PDEI_COL] > 0, PDEI_COL]
    fit = _fig2_fit_powerlaw_tail(positive_pdei)
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

    ax.scatter(x, ccdf, s=18, alpha=0.62, color="#4A9FD4", edgecolors="none", label="Empirical CCDF")
    x_fit = np.logspace(np.log10(fit["xmin"]), np.log10(x.max()), 200)
    y_fit = fit["tail_fraction"] * (x_fit / fit["xmin"]) ** (1.0 - fit["alpha"])
    ax.plot(x_fit, y_fit, linewidth=2.2, linestyle="--", label="Power-law fit")
    ax.axvline(fit["xmin"], linewidth=1.2, linestyle=":", label=f"xmin={fit['xmin']:.1f}")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("PDEI score")
    ax.set_ylabel("Pr(PDEI >= x)")
    ax.grid(True, which="both", linestyle=":", linewidth=0.7, alpha=0.45)
    ax.legend(loc="lower right", frameon=False, fontsize=8.5)
    fig.subplots_adjust(left=0.16, top=0.96)
    add_panel_label(ax, "a")

    if stats_box in ("outside", "inside"):
        annotation = (
            f"n = {len(df):,}; positive = {len(positive_pdei):,}\n"
            f"alpha = {fit['alpha']:.2f}; xmin = {fit['xmin']:.1f}\n"
            f"KS D = {fit['ks_D']:.3f}; p ~ {fit['ks_p_approx']:.3f}\n"
            f"Top {FIG2A_TOP_PERCENT:g}%: k = {k_top:,}\n"
            f"PDEI share = {top_pdei_share:.1%}\n"
            f"Exposure share = {top_exposure_share:.1%}"
        )
        ax.text(
            0.04, 0.04, annotation, transform=ax.transAxes, fontsize=8.6, va="bottom", ha="left",
            bbox=dict(boxstyle="round,pad=0.40", facecolor="white", alpha=0.92, linewidth=0.6),
        )

    box_tag = stats_box
    png_path = out_dir / f"fig2a_pdei_powerlaw_ccdf_{box_tag}.png"
    pdf_path = out_dir / f"fig2a_pdei_powerlaw_ccdf_{box_tag}.pdf" if pdf else None
    save_fig(fig, png_path, pdf_path, pad_inches=0.10, use_tight_layout=False)

    stats_path = out_dir / f"fig2a_stats_{box_tag}.txt"
    stats_path.write_text(
        f"""Input file: {pdei_csv}
Number of skills: {len(df)}
Positive PDEI skills: {len(positive_pdei)}
Zero-PDEI skills: {int((df[PDEI_COL] == 0).sum())}

Power-law tail fit:
  alpha = {fit['alpha']:.4f}
  xmin = {fit['xmin']:.4f}
  tail_n = {fit['n_tail']}
  tail_fraction = {fit['tail_fraction']:.4f}
  KS_D = {fit['ks_D']:.4f}
  KS_p_approx = {fit['ks_p_approx']:.4f}

Concentration (top 1%):
  top_pct = {FIG2A_TOP_PERCENT:.4f}%
  top_count = {k_top}
  top_PDEI_share = {top_pdei_share:.4%}
  top_downstream_exposure_share_among_top_PDEI_skills = {top_exposure_share:.4%}
  top_downstream_exposure_share_if_ranked_by_exposure = {top_exposure_share_by_exposure:.4%}
  Gini_PDEI = {gini(df[PDEI_COL]):.4f}
  Gini_downstream_exposure = {gini(df['downstream_exposure']):.4f}
""".strip(),
        encoding="utf-8",
    )
    save_figure_caption(out_dir, f"fig2a_pdei_powerlaw_ccdf_{box_tag}", FIGURE_CAPTIONS["fig2a"])
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
    add_panel_label(ax, "b")
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
    add_panel_label(ax, "b")

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
    fig.subplots_adjust(right=0.74)
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
    fig.subplots_adjust(left=0.14, top=0.96, right=0.74)
    add_panel_label(ax, "b")
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.00), frameon=False, fontsize=8.8)
    p_text = "p<0.001" if pval < 0.001 else f"p={pval:.3f}"
    annotation = (
        f"Spearman rho={rho:.2f}, {p_text}\n"
        f"developers={len(agg_full):,} (stats)\n"
        f"plotted n={len(plot_df):,}\n"
        f"Gini(avg PDEI)={gini(agg_full['avg_pdei']):.2f}"
    )
    fig.text(
        0.76, 0.22, annotation, fontsize=8.4, va="bottom", ha="left",
        bbox=dict(boxstyle="round,pad=0.40", facecolor="white", alpha=0.92, linewidth=0.5),
    )
    base = "fig2b_scatter_opt_starsgt0_thin_sub6000_outsidelegend_outsidestats"
    png_path = out_dir / f"{base}.png"
    pdf_path = out_dir / f"{base}.pdf" if pdf else None
    save_fig(fig, png_path, pdf_path, pad_inches=0.10, use_tight_layout=False)
    save_figure_caption(out_dir, base, FIGURE_CAPTIONS["fig2b"])
    print(f"Saved: {png_path}")


def run_fig2_suite(pdei_csv: Path, out_dir: Path, *, pdf: bool = False) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    build_fig2a(pdei_csv, out_dir, pdf=pdf)
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
    add_panel_label_above_ylabel(ax, "b")

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
        run_fig2_suite(pdei_csv.resolve(), out_dir, pdf=args.pdf)
        print("DONE (Fig2 only):", out_dir)
        return

    if args.v4_csv is None:
        raise ValueError("生成 Fig1/3/4 需要 --v4-csv")

    if not args.skip_fig2:
        if pdei_csv is None:
            pdei_csv = args.v4_csv
        run_fig2_suite(pdei_csv.resolve(), out_dir, pdf=args.pdf)

    v4 = pd.read_csv(args.v4_csv.resolve(), encoding="utf-8-sig")
    required = {
        "domain",
        "declaration_atomic_ids",
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
    build_fig3(v4, top_pairs, out_dir, args.pdf)
    build_fig4a(v4, out_dir, args.pdf, raw_total=funnel_l1)

    if not args.skip_fig4b:
        build_fig4b(out_dir, args.reg_conflict_csv, pdf=args.pdf)
        save_figure_caption(out_dir, "fig4_combined", FIGURE_CAPTIONS["fig4"])

    print("DONE:", out_dir)
    print(f"funnel L1={funnel_l1:,}, v4 rows (L2)={len(v4):,}, top pairs={len(top_pairs)}")


if __name__ == "__main__":
    main()

