# -*- coding: utf-8 -*-
"""
共享模块：数据矩阵、加载 CSV、绘图函数、总控 run_all_figures（一次出全图 + 导出表）。
单张图请运行同目录下 plot_fig1.py / plot_fig1b.py / plot_fig2.py / plot_fig3.py；一次全图用 plot_all_figures.py。
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import ticker
import numpy as np
import pandas as pd
import seaborn as sns

# 期刊级导出分辨率（可按需改为 600 用于印刷）
FIGURE_DPI = 300

# Fig1 / Fig1b 单张热图：相同英寸画布 + 相同边距，savefig 不用 tight 以保证 PNG 像素宽高一致
HEATMAP_SINGLE_FIGSIZE_INCHES = (10.0, 6.2)

# ---------------------------------------------------------------------------
def _layout_single_heatmap_figure(fig: plt.Figure, *, has_footnote: bool) -> None:
    """两张单页热图共用边距；Fig1 带底部脚注时略加大下边距。"""
    bottom = 0.36 if has_footnote else 0.30
    fig.subplots_adjust(left=0.19, right=0.86, bottom=bottom, top=0.88)


def _setup_matplotlib_style() -> None:
    """Arial / Helvetica 无衬线；论文图表常用字号与线宽。"""
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Arial", "Helvetica", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.size"] = 10
    plt.rcParams["axes.titlesize"] = 11
    plt.rcParams["axes.labelsize"] = 10
    plt.rcParams["xtick.labelsize"] = 9
    plt.rcParams["ytick.labelsize"] = 9
    plt.rcParams["axes.linewidth"] = 0.8
    plt.rcParams["xtick.major.width"] = 0.6
    plt.rcParams["ytick.major.width"] = 0.6
    plt.rcParams["figure.facecolor"] = "white"
    plt.rcParams["axes.facecolor"] = "white"


def _heatmap_cmap_nc():
    """Nature Communications 热图常用：单色相 Blues（浅→深海军蓝）。"""
    return plt.get_cmap("Blues")


def _style_heatmap_cell_labels(ax: plt.Axes, data: np.ndarray, vmin: float, vmax: float) -> None:
    """Blues 深格用白字、浅格用黑字（与 NC 示例一致）。"""
    lo, hi = float(vmin), float(vmax)
    span = hi - lo if hi > lo else 1.0
    thr = lo + span * 0.48
    for text, val in zip(ax.texts, np.asarray(data, dtype=float).ravel()):
        text.set_color("#ffffff" if val > thr else "#1a1a1a")
        text.set_fontsize(8)


def _rotate_heatmap_axis_labels(ax: plt.Axes) -> None:
    """NC 版式：横纵轴刻度标签 45°，避免重叠。"""
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")
    plt.setp(ax.get_yticklabels(), rotation=45, ha="right", rotation_mode="anchor")


def _nc_axes_frame(ax: plt.Axes) -> None:
    """细黑全框线（参考 NC 条形图外框）。"""
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.8)
        spine.set_edgecolor("#000000")


def _panel_letter(ax: plt.Axes, letter: str) -> None:
    """子图外沿左上角粗体小写面板标签 a、b、c、d（NC 多面板排版）。"""
    ax.text(
        -0.18,
        1.02,
        letter,
        transform=ax.transAxes,
        fontsize=12,
        fontweight="bold",
        va="bottom",
        ha="left",
        color="#000000",
    )


# 兼容旧名（若外部引用）
def _heatmap_cmap():
    return _heatmap_cmap_nc()


# ---------------------------------------------------------------------------
# 统一分类（与 Fig1 Y 轴一致，可按业务增删）
# 图一纵轴
UNIFIED_CATEGORIES = [
    "File Access",
    "Network Send",
    "Databases",
    "Email/Contacts",
    "Browser",
    "System Commands",
]

# 图一横轴
PLATFORMS = ["OpenAI", "Microsoft", "Coze", "Dify", "Lark", "Other OS"]

# Fig1：过权率矩阵（0~1），来自参考图示例
HEATMAP_OVERPRIV_RATE = np.array(
    [
        [0.720, 0.199, 0.333, 0.128, 0.440, 0.089],
        [0.408, 0.142, 0.650, 0.301, 0.435, 0.068],
        [0.286, 0.219, 0.108, 0.283, 0.106, 0.261],
        [0.133, 0.580, 0.211, 0.312, 0.123, 0.244],
        [0.163, 0.147, 0.294, 0.162, 0.149, 0.227],
        [0.080, 0.166, 0.248, 0.036, 0.150, 0.169],
    ]
)

# 第二张热图：示例「各平台下该权限类型在 Skill 中的出现占比」0~1（初版占位，可换为覆盖率等）
HEATMAP_PRESENCE_RATE = np.array(
    [
        [0.62, 0.41, 0.35, 0.28, 0.33, 0.12],
        [0.45, 0.22, 0.58, 0.31, 0.40, 0.09],
        [0.25, 0.18, 0.12, 0.22, 0.11, 0.19],
        [0.10, 0.48, 0.15, 0.24, 0.09, 0.17],
        [0.14, 0.12, 0.21, 0.13, 0.12, 0.16],
        [0.07, 0.11, 0.18, 0.04, 0.10, 0.11],
    ]
)

# Fig2：幂律曲线（不必要权限数 vs Skill 数）
POWER_LAW_X = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 15], dtype=float)
POWER_LAW_Y = np.array(
    [100_000, 20_000, 9_000, 5_000, 3_000, 2_000, 1_500, 1_300, 700, 600, 400, 200, 350],
    dtype=float,
)

# Fig3：毒性权限组合
TOXIC_COMBOS = [
    "File Read + Net Send",
    "Email Read + Net Send",
    "Contacts + SMS",
    "Database + File Write",
    "Search + System Cmd",
]
TOXIC_COUNTS = np.array([8420, 5210, 3105, 2040, 980])

# Fig2：与 Blues 热图同系的深蓝主色 + 浅蓝带（NC 医学图常见搭配）
COLOR_LINE = "#1f4e79"
COLOR_CI_FILL = "#c6d9f0"

# Fig3：NC 柱状图式中性灰条（勿用高饱和红绿）
NC_BAR_GREY_GRADIENT = ["#9a9a9a", "#909090", "#868686", "#7c7c7c", "#727272"]

# 权限频率表示例：总 Skill 数占位
TOTAL_SKILLS_SAMPLE = 100_000

# 若从 CSV 读入频率表，则不再用演示公式生成（由 load_user_data_from_directory 设置）
_FREQ_FROM_USER: pd.DataFrame | None = None


def _auto_heatmap_vmax(data: np.ndarray, *, ceiling: float = 1.0) -> float:
    """色条上限：随数据略留余量，不超过 ceiling（比例型指标一般为 1.0）。"""
    m = float(np.nanmax(np.asarray(data, dtype=float)))
    if not np.isfinite(m) or m <= 0:
        return min(0.75, ceiling)
    m = min(ceiling, m * 1.02)
    return float(min(ceiling, max(np.ceil(m * 100) / 100, 0.05)))


def load_user_data_from_directory(data_dir: Path) -> None:
    """
    从「数据文件夹」里读 CSV，替换脚本里的矩阵和名称，供后面画图、导出使用。
    调用本函数后，照常执行 main() 即可（命令行加 --data-dir 时会自动调用）。

    ---------- 你必须准备的两个文件（缺一不可）----------

    两个文件都是「Excel 可打开的表格」，编码用 UTF-8（Excel 另存时选「CSV UTF-8」最省事）。

    ① heatmap_overprivilege_rate.csv  —— 对应图 Fig 1（过度授权率）
       · 最左边一列：每一行是一种「统一后的权限类型」名称（不要用数字当行名）。
       · 最上面一行：每一列是一个「平台」名称。
       · 中间每个格子：一个小数，表示比例，一般在 0～1 之间（例如 0.72 表示 72%）。

       示意（第一列在 CSV 里没有列名，pandas 会当作行索引读入）：

            ,OpenAI,Microsoft,...
            File Access,0.72,0.20,...
            Network Send,0.41,0.14,...

    ② heatmap_presence_by_platform.csv  —— 对应图 Fig 1b（出现占比等第二张热图）
       · 格式与上面完全相同：左权限类型、上平台名、中间小数 0～1。
       · 若行名或列名和 ① 不完全一致：程序会以 ① 为准排序；② 里缺的格子会自动当成 0，
         并在屏幕上打一行提示。

    ---------- 你可以额外放的文件（没有也行）----------

    · permission_frequency_stats.csv
        每一行一种权限类型，需包含这四列（列名要一致）：
        unified_category, occurrences, skills_covered, coverage_rate
        若放了：导出「权限频率统计」时就用这份表，不再用脚本里的演示公式瞎算。

    · data_meta.json
        一行 JSON 即可，例如：{"total_skills": 100000}
        用来写进 export_meta.json，表示你一共统计了多少个 Skill。

    · powerlaw.csv
        两列数字：一列「横轴」（例如每人多申请了几次权限），一列「纵轴」（例如有多少个 Skill）。
        列名可以用下面任意一组（英文字母大小写无所谓）：
        - x 和 y
        - n_unnecessary 和 n_skills
        - n_redundant 和 skill_count

    · toxic_combos.csv
        一列写组合名称，一列写出现次数。列名可以是：
        - combo 和 count，或 label 和 n，或 name 和 occurrences
    """
    global HEATMAP_OVERPRIV_RATE, HEATMAP_PRESENCE_RATE, UNIFIED_CATEGORIES, PLATFORMS
    global POWER_LAW_X, POWER_LAW_Y, TOXIC_COMBOS, TOXIC_COUNTS
    global TOTAL_SKILLS_SAMPLE, _FREQ_FROM_USER

    data_dir = data_dir.resolve()
    p1 = data_dir / "heatmap_overprivilege_rate.csv"
    p2 = data_dir / "heatmap_presence_by_platform.csv"
    if not p1.is_file():
        raise FileNotFoundError(f"缺少必需文件: {p1}")
    if not p2.is_file():
        raise FileNotFoundError(f"缺少必需文件: {p2}")

    df1 = pd.read_csv(p1, index_col=0, encoding="utf-8-sig")
    df2 = pd.read_csv(p2, index_col=0, encoding="utf-8-sig")
    df1.index = df1.index.astype(str)
    df1.columns = df1.columns.astype(str)
    df2.index = df2.index.astype(str)
    df2.columns = df2.columns.astype(str)
    df2 = df2.reindex(index=df1.index, columns=df1.columns)
    if df2.isna().any().any():
        n_missing = int(df2.isna().sum().sum())
        df2 = df2.fillna(0.0)
        print(f"提示: heatmap_presence 相对 heatmap_overpriv 缺失 {n_missing} 个格点，已填 0。")

    UNIFIED_CATEGORIES = df1.index.tolist()
    PLATFORMS = df1.columns.tolist()
    HEATMAP_OVERPRIV_RATE = df1.to_numpy(dtype=float)
    HEATMAP_PRESENCE_RATE = df2.to_numpy(dtype=float)

    meta_path = data_dir / "data_meta.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if "total_skills" in meta:
            TOTAL_SKILLS_SAMPLE = int(meta["total_skills"])

    fp = data_dir / "permission_frequency_stats.csv"
    if fp.is_file():
        _FREQ_FROM_USER = pd.read_csv(fp, encoding="utf-8-sig")
    else:
        _FREQ_FROM_USER = None

    plp = data_dir / "powerlaw.csv"
    if plp.is_file():
        pl = pd.read_csv(plp, encoding="utf-8-sig")
        cmap = {c.lower(): c for c in pl.columns}
        xc = cmap.get("x") or cmap.get("n_unnecessary") or cmap.get("n_redundant")
        yc = cmap.get("y") or cmap.get("n_skills") or cmap.get("skill_count")
        if not xc or not yc:
            raise ValueError(
                "powerlaw.csv 里找不到需要的两列。请使用：x 与 y，"
                "或 n_unnecessary 与 n_skills，或 n_redundant 与 skill_count（列名不区分大小写）。"
            )
        POWER_LAW_X = pl[xc].to_numpy(dtype=float)
        POWER_LAW_Y = pl[yc].to_numpy(dtype=float)

    txp = data_dir / "toxic_combos.csv"
    if txp.is_file():
        tx = pd.read_csv(txp, encoding="utf-8-sig")
        cmap = {c.lower(): c for c in tx.columns}
        lc = cmap.get("combo") or cmap.get("label") or cmap.get("name")
        cc = cmap.get("count") or cmap.get("n") or cmap.get("occurrences")
        if not lc or not cc:
            raise ValueError(
                "toxic_combos.csv 里需要两列：组合名称 + 次数。"
                "列名可用 combo/count，或 label/n，或 name/occurrences（不区分大小写）。"
            )
        TOXIC_COMBOS = tx[lc].astype(str).tolist()
        TOXIC_COUNTS = tx[cc].to_numpy(dtype=float).astype(int)

    print(f"已读入真实数据，目录为：{data_dir}")


def build_demo_frequency_table() -> pd.DataFrame:
    """每种统一分类下的出现次数与覆盖 Skill 数；若已传入 permission_frequency_stats.csv 则直接返回该表。"""
    if _FREQ_FROM_USER is not None:
        return _FREQ_FROM_USER.copy()
    rows = []
    for i, cat in enumerate(UNIFIED_CATEGORIES):
        # 用热图行均值构造可自洽的演示频率
        mean_p = float(HEATMAP_PRESENCE_RATE[i].mean())
        covered = int(TOTAL_SKILLS_SAMPLE * mean_p)
        occurrences = int(covered * (1.2 + 0.1 * i))  # 演示：单次 Skill 可映射多权限
        rows.append(
            {
                "unified_category": cat,
                "occurrences": occurrences,
                "skills_covered": covered,
                "coverage_rate": covered / TOTAL_SKILLS_SAMPLE,
            }
        )
    return pd.DataFrame(rows)


def _write_csv_resilient(df: pd.DataFrame, path: Path, **kwargs) -> Path:
    """写入 CSV；若 PermissionError（常见于文件被 Excel 占用），则写入带时间戳的备用文件。"""
    try:
        df.to_csv(path, **kwargs)
        return path
    except PermissionError:
        ts = time.strftime("%Y%m%d_%H%M%S")
        alt = path.with_name(f"{path.stem}_{ts}{path.suffix}")
        df.to_csv(alt, **kwargs)
        print(
            f"警告: 无法写入 {path}（可能被 Excel 或其他程序占用），已改为: {alt.name}"
        )
        return alt


def _write_text_resilient(content: str, path: Path, *, encoding: str = "utf-8") -> Path:
    try:
        path.write_text(content, encoding=encoding)
        return path
    except PermissionError:
        ts = time.strftime("%Y%m%d_%H%M%S")
        alt = path.with_name(f"{path.stem}_{ts}{path.suffix}")
        alt.write_text(content, encoding=encoding)
        print(f"警告: 无法写入 {path}，已改为: {alt.name}")
        return alt


def export_outputs(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    freq = build_demo_frequency_table()
    _write_csv_resilient(freq, out_dir / "permission_frequency_stats.csv", index=False, encoding="utf-8-sig")

    h1 = pd.DataFrame(HEATMAP_OVERPRIV_RATE, index=UNIFIED_CATEGORIES, columns=PLATFORMS)
    _write_csv_resilient(h1, out_dir / "heatmap_overprivilege_rate.csv", encoding="utf-8-sig")

    h2 = pd.DataFrame(HEATMAP_PRESENCE_RATE, index=UNIFIED_CATEGORIES, columns=PLATFORMS)
    _write_csv_resilient(h2, out_dir / "heatmap_presence_by_platform.csv", encoding="utf-8-sig")

    meta = {
        "total_skills": TOTAL_SKILLS_SAMPLE,
        "unified_categories": UNIFIED_CATEGORIES,
        "platforms": PLATFORMS,
        "heatmap_1_name": "overprivilege_rate (platform × category)",
        "heatmap_2_name": "presence_rate demo (platform × category)",
    }
    _write_text_resilient(json.dumps(meta, ensure_ascii=False, indent=2), out_dir / "export_meta.json")


def plot_fig1_heatmap(ax: plt.Axes, *, include_footnote: bool = True) -> None:
    data = HEATMAP_OVERPRIV_RATE
    vmin, vmax = 0.0, _auto_heatmap_vmax(data, ceiling=1.0)
    annot = np.array([[f"{v:.2f}" for v in row] for row in data])
    cbar_ticks = np.linspace(vmin, vmax, 5)
    sns.heatmap(
        data,
        ax=ax,
        cmap=_heatmap_cmap_nc(),
        vmin=vmin,
        vmax=vmax,
        annot=annot,
        fmt="",
        linewidths=0.5,
        linecolor="white",
        square=True,
        cbar_kws={
            "label": "Over-privilege rate",
            "shrink": 0.82,
            "ticks": cbar_ticks,
        },
        xticklabels=PLATFORMS,
        yticklabels=UNIFIED_CATEGORIES,
    )
    _style_heatmap_cell_labels(ax, data, vmin, vmax)
    _rotate_heatmap_axis_labels(ax)
    _nc_axes_frame(ax)
    ax.set_title(
        "Global over-privilege rate by platform and capability",
        pad=14,
        fontweight="bold",
    )
    ax.set_xlabel("AI agent platforms")
    ax.set_ylabel("Risk categories (unified taxonomy)")
    if include_footnote:
        ax.text(
            0.5,
            -0.32,
            "Global over-privilege heatmap",
            transform=ax.transAxes,
            ha="center",
            fontsize=9,
            color="#333333",
        )


def plot_fig2_powerlaw(ax: plt.Axes) -> None:
    x = POWER_LAW_X
    y = POWER_LAW_Y
    y_low = y * 0.88
    y_high = y * 1.12

    ax.fill_between(x, y_low, y_high, color=COLOR_CI_FILL, alpha=0.55, linewidth=0)
    ax.plot(
        x,
        y,
        color=COLOR_LINE,
        marker="o",
        markersize=5,
        markerfacecolor=COLOR_LINE,
        markeredgecolor="white",
        markeredgewidth=0.6,
        linewidth=1.6,
    )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Number of unnecessary permissions requested")
    ax.set_ylabel("Number of skills")
    ax.set_title("Power-law distribution of permission redundancy", pad=12, fontweight="bold")
    ax.grid(True, which="major", linestyle="--", color="#e5e5e5", alpha=0.95, linewidth=0.5)
    ax.set_axisbelow(True)
    _nc_axes_frame(ax)
    ax.text(
        0.62,
        0.72,
        "Top 1% Skills account for ~68% of all excessive permissions",
        transform=ax.transAxes,
        fontsize=9,
        verticalalignment="top",
        color="#333333",
    )


def plot_fig3_toxic_bars(ax: plt.Axes) -> None:
    order = np.argsort(TOXIC_COUNTS)[::-1]
    labels = [TOXIC_COMBOS[i] for i in order]
    vals = TOXIC_COUNTS[order]
    n = len(vals)
    colors = NC_BAR_GREY_GRADIENT[:n]

    y_pos = np.arange(len(labels))
    ax.barh(y_pos, vals, color=colors, height=0.62, edgecolor="white", linewidth=0.5)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Occurrences in 100,000 skills")
    ax.set_title("Prevalence of toxic permission combinations", pad=12, fontweight="bold")
    ax.set_xlim(0, max(vals) * 1.15)
    _nc_axes_frame(ax)
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"{x:,.0f}"))
    for i, v in enumerate(vals):
        ax.text(
            v + max(vals) * 0.015,
            i,
            f"{v:,}",
            va="center",
            fontsize=9,
            color="#1a1a1a",
        )
    ax.text(
        0.5,
        -0.12,
        "High-risk combos",
        transform=ax.transAxes,
        ha="center",
        fontsize=9,
        style="italic",
        color="#333333",
    )


def plot_second_heatmap_presence(out_path: Path) -> None:
    """第二张热图：平台 × 权限类型出现占比（示例）。"""
    fig, ax = plt.subplots(figsize=HEATMAP_SINGLE_FIGSIZE_INCHES)
    data = HEATMAP_PRESENCE_RATE
    vmin, vmax = 0.0, _auto_heatmap_vmax(data, ceiling=1.0)
    annot = np.array([[f"{v:.2f}" for v in row] for row in data])
    cbar_ticks = np.linspace(vmin, vmax, 5)
    sns.heatmap(
        data,
        ax=ax,
        cmap=_heatmap_cmap_nc(),
        vmin=vmin,
        vmax=vmax,
        annot=annot,
        fmt="",
        linewidths=0.5,
        linecolor="white",
        square=True,
        cbar_kws={
            "label": "Presence rate in skills (demo)",
            "shrink": 0.82,
            "ticks": cbar_ticks,
        },
        xticklabels=PLATFORMS,
        yticklabels=UNIFIED_CATEGORIES,
    )
    _style_heatmap_cell_labels(ax, data, vmin, vmax)
    _rotate_heatmap_axis_labels(ax)
    _nc_axes_frame(ax)
    ax.set_title(
        "Unified permission type presence by platform (draft)",
        pad=14,
        fontweight="bold",
    )
    ax.set_xlabel("AI agent platforms")
    ax.set_ylabel("Unified permission categories")
    _layout_single_heatmap_figure(fig, has_footnote=False)
    fig.savefig(out_path, dpi=FIGURE_DPI, bbox_inches=None)
    plt.close(fig)


def init_plot_style() -> None:
    sns.set_theme(style="white", font="sans-serif")
    _setup_matplotlib_style()


def run_all_figures(*, data_dir: Path | None = None, output_dir: Path | None = None) -> None:
    init_plot_style()

    if data_dir is not None:
        load_user_data_from_directory(Path(data_dir))

    out_dir = Path(output_dir).resolve() if output_dir else Path(__file__).resolve().parent / "output"
    export_outputs(out_dir)

    # 单图：Fig1（与 Fig1b 同画布英寸与导出方式，PNG 宽高像素一致）
    fig1, ax1 = plt.subplots(figsize=HEATMAP_SINGLE_FIGSIZE_INCHES)
    plot_fig1_heatmap(ax1)
    _layout_single_heatmap_figure(fig1, has_footnote=True)
    fig1.savefig(out_dir / "fig1_heatmap_overprivilege.png", dpi=FIGURE_DPI, bbox_inches=None)
    plt.close(fig1)

    plot_second_heatmap_presence(out_dir / "fig1b_heatmap_presence_by_platform.png")

    # 单图：Fig2
    fig2, ax2 = plt.subplots(figsize=(9, 6))
    plot_fig2_powerlaw(ax2)
    fig2.text(
        0.5,
        0.02,
        "Power-law distribution of redundancy",
        ha="center",
        fontsize=9,
        style="italic",
        color="#333333",
    )
    fig2.tight_layout(rect=(0, 0.06, 1, 1))
    fig2.savefig(out_dir / "fig2_powerlaw_redundancy.png", dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig2)

    # Fig3：NC 式细黑全框，无额外装饰框线
    fig3, ax3 = plt.subplots(figsize=(9, 5.2))
    plot_fig3_toxic_bars(ax3)
    fig3.patch.set_facecolor("white")
    ax3.set_facecolor("white")
    fig3.tight_layout()
    fig3.savefig(out_dir / "fig3_toxic_combos.png", dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig3)

    # 汇总一页（可选）：子图标注 a–d，风格与 NC 多面板图一致
    fig_all, axes = plt.subplots(2, 2, figsize=(14, 11))
    plot_fig1_heatmap(axes[0, 0], include_footnote=False)
    _panel_letter(axes[0, 0], "a")

    _ph_vmin, _ph_vmax = 0.0, _auto_heatmap_vmax(HEATMAP_PRESENCE_RATE, ceiling=1.0)
    _ph_ticks = np.linspace(_ph_vmin, _ph_vmax, 5)
    sns.heatmap(
        HEATMAP_PRESENCE_RATE,
        ax=axes[0, 1],
        cmap=_heatmap_cmap_nc(),
        vmin=_ph_vmin,
        vmax=_ph_vmax,
        annot=np.array([[f"{v:.2f}" for v in row] for row in HEATMAP_PRESENCE_RATE]),
        fmt="",
        linewidths=0.5,
        linecolor="white",
        square=True,
        cbar_kws={"label": "Presence (demo)", "shrink": 0.82, "ticks": _ph_ticks},
        xticklabels=PLATFORMS,
        yticklabels=UNIFIED_CATEGORIES,
    )
    _style_heatmap_cell_labels(axes[0, 1], HEATMAP_PRESENCE_RATE, _ph_vmin, _ph_vmax)
    _rotate_heatmap_axis_labels(axes[0, 1])
    _nc_axes_frame(axes[0, 1])
    axes[0, 1].set_title(
        "Presence by platform (demo)",
        fontweight="bold",
        pad=14,
    )
    _panel_letter(axes[0, 1], "b")

    plot_fig2_powerlaw(axes[1, 0])
    _panel_letter(axes[1, 0], "c")

    plot_fig3_toxic_bars(axes[1, 1])
    _panel_letter(axes[1, 1], "d")

    fig_all.suptitle(
        "Permission mapping — reference dashboard (mock data)",
        fontsize=12,
        fontweight="bold",
        y=1.01,
    )
    fig_all.tight_layout()
    fig_all.savefig(out_dir / "dashboard_all_figures.png", dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close(fig_all)

    out_abs = out_dir.resolve()
    print(f"\n全部结果已保存到文件夹：\n  {out_abs}\n")
    print("其中的文件分别是：")
    print("  · permission_frequency_stats.csv     —— 每种权限类型的次数、覆盖 Skill 数等")
    print("  · heatmap_overprivilege_rate.csv     —— Fig1 热图用的数字表")
    print("  · heatmap_presence_by_platform.csv   —— Fig1b 热图用的数字表")
    print("  · export_meta.json                   —— 总 Skill 数、分类名等说明")
    print("  · fig1_*.png / fig1b_*.png           —— 两张热图")
    print("  · fig2_*.png / fig3_*.png            —— 幂律曲线图、毒性组合条形图")
    print("  · dashboard_all_figures.png          —— 四张小图拼在一张里")
    print(
        "\n说明：图是存成 PNG 文件的，不会自动弹窗。"
        "请打开上面这个文件夹，或用 PyCharm 左侧项目树点开 .png 查看。"
    )
    if sys.platform == "win32" and os.environ.get("OPEN_OUTPUT_FOLDER", "1") not in ("0", "false", "no"):
        try:
            os.startfile(str(out_abs))
        except OSError:
            pass
