# -*- coding: utf-8 -*-
"""
Fig. 3A: Tier-level redundant permission co-occurrence heatmap
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

# =========================
# Config
# =========================
CSV_PATH = r"./pdei_scores_full_v4_download_proxy.csv"
OUT_DIR = Path("./output/fig3a")
OUT_DIR.mkdir(parents=True, exist_ok=True)

FIG3A_VALUE_MODE = "percent"   # "percent" or "count"

TIER_ORDER = ["T1", "T2", "T3", "T4"]

TIER_LABELS = {
    "T1": "T1\nResource\nSensing",
    "T2": "T2\nInteraction\nCommunication",
    "T3": "T3\nEnvironment\nControl",
    "T4": "T4\nAgentic\nDelegation",
}

PATH_INFO = {
    "A": {"tiers": ("T1", "T2"), "full": "Data Exfiltration"},
    "B": {"tiers": ("T1", "T3"), "full": "Persistent Backdoor"},
    "C": {"tiers": ("T2", "T3"), "full": "Remote Command"},
    "D": {"tiers": ("T4", "T2"), "full": "Identity-mediated Exfiltration"},
    "E": {"tiers": ("T4", "T3"), "full": "Autonomous Privilege Drift"},
}


# =========================
# Helpers
# =========================
def has_extra_permission(value) -> int:
    if pd.isna(value):
        return 0
    s = str(value).strip()
    if s == "" or s.lower() in {"nan", "none", "null", "[]", "{}"}:
        return 0
    return 1


def build_tier_flags(df: pd.DataFrame) -> pd.DataFrame:
    tier_flags = pd.DataFrame(index=df.index)
    for i in range(1, 5):
        col = f"extra_t{i}"
        tier = f"T{i}"
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
        tier_flags[tier] = df[col].apply(has_extra_permission)
    return tier_flags


# =========================
# Main plotting function
# =========================
def plot_fig3a_heatmap(df: pd.DataFrame, tier_flags: pd.DataFrame):
    n = len(df)
    mat = np.zeros((len(TIER_ORDER), len(TIER_ORDER)), dtype=float)

    for i, ti in enumerate(TIER_ORDER):
        for j, tj in enumerate(TIER_ORDER):
            count = ((tier_flags[ti] == 1) & (tier_flags[tj] == 1)).sum()
            if FIG3A_VALUE_MODE == "count":
                mat[i, j] = count
            else:
                mat[i, j] = count / n * 100.0

    fig, ax = plt.subplots(figsize=(7.2, 6.2))
    im = ax.imshow(mat, cmap="Blues")

    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    if FIG3A_VALUE_MODE == "count":
        cbar.set_label("Number of skills", fontsize=11)
    else:
        cbar.set_label("Co-occurrence frequency (%)", fontsize=11)

    ax.set_xticks(range(len(TIER_ORDER)))
    ax.set_yticks(range(len(TIER_ORDER)))
    ax.set_xticklabels([TIER_LABELS[t] for t in TIER_ORDER], fontsize=10)
    ax.set_yticklabels([TIER_LABELS[t] for t in TIER_ORDER], fontsize=10)

    ax.set_xlabel("Redundant permission tier", fontsize=12)
    ax.set_ylabel("Redundant permission tier", fontsize=12)
    ax.set_title(
        "Fig. 3A. Co-occurrence Matrix of Redundant Permission Tiers",
        fontsize=13,
        pad=14,
    )

    # 用来标注 Path A-E
    path_cell_labels = {}
    for path_name, info in PATH_INFO.items():
        ta, tb = info["tiers"]
        i = TIER_ORDER.index(ta)
        j = TIER_ORDER.index(tb)
        path_cell_labels[(i, j)] = f"Path {path_name}"
        path_cell_labels[(j, i)] = f"Path {path_name}"

    max_val = mat.max() if mat.max() > 0 else 1

    for i in range(len(TIER_ORDER)):
        for j in range(len(TIER_ORDER)):
            if FIG3A_VALUE_MODE == "count":
                value_text = f"{int(mat[i, j])}"
            else:
                value_text = f"{mat[i, j]:.1f}%"

            path_text = path_cell_labels.get((i, j), "")
            text = f"{value_text}\n{path_text}" if path_text else value_text
            text_color = "white" if mat[i, j] > 0.55 * max_val else "black"

            ax.text(
                j, i, text,
                ha="center", va="center",
                fontsize=9,
                color=text_color,
                fontweight="bold" if path_text else "normal"
            )

    # 给 Path 对应的格子加边框
    for path_name, info in PATH_INFO.items():
        ta, tb = info["tiers"]
        i = TIER_ORDER.index(ta)
        j = TIER_ORDER.index(tb)

        for row, col in [(i, j), (j, i)]:
            ax.add_patch(
                Rectangle(
                    (col - 0.5, row - 0.5),
                    1, 1,
                    fill=False,
                    edgecolor="black",
                    linewidth=2.0
                )
            )

    ax.set_xticks(np.arange(-0.5, len(TIER_ORDER), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(TIER_ORDER), 1), minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=1.5)
    ax.tick_params(which="minor", bottom=False, left=False)

    plt.tight_layout()

    png_path = OUT_DIR / "fig3A_permission_cooccurrence_heatmap.png"
    pdf_path = OUT_DIR / "fig3A_permission_cooccurrence_heatmap.pdf"
    plt.savefig(png_path, dpi=300, bbox_inches="tight")
    plt.savefig(pdf_path, bbox_inches="tight")
    plt.close()

    print(f"[Saved] {png_path}")
    print(f"[Saved] {pdf_path}")


# =========================
# Run
# =========================
def main():
    df = pd.read_csv(CSV_PATH)
    tier_flags = build_tier_flags(df)
    plot_fig3a_heatmap(df, tier_flags)


if __name__ == "__main__":
    main()