# -*- coding: utf-8 -*-
"""
Fig. 3B: Bubble plot of five toxic pathways
x-axis: trigger frequency
y-axis: PDEI amplification
bubble size: affected users
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# =========================
# Config
# =========================
CSV_PATH = r"./pdei_scores_full_v4_download_proxy.csv"
OUT_DIR = Path("./output/fig3b")
OUT_DIR.mkdir(parents=True, exist_ok=True)

PATH_INFO = {
    "A": {
        "col": "path_A",
        "tiers": ("T1", "T2"),
        "full": "Data Exfiltration",
    },
    "B": {
        "col": "path_B",
        "tiers": ("T1", "T3"),
        "full": "Persistent Backdoor",
    },
    "C": {
        "col": "path_C",
        "tiers": ("T2", "T3"),
        "full": "Remote Command",
    },
    "D": {
        "col": "path_D",
        "tiers": ("T4", "T2"),
        "full": "Identity-mediated Exfiltration",
    },
    "E": {
        "col": "path_E",
        "tiers": ("T4", "T3"),
        "full": "Autonomous Privilege Drift",
    },
}


# =========================
# Helpers
# =========================
def to_binary_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return (series.fillna(0).astype(float) > 0).astype(int)

    s = series.astype(str).str.strip().str.lower()
    return s.isin({"1", "true", "yes", "y", "path", "triggered"}).astype(int)


def choose_exposure_column(df: pd.DataFrame) -> str:
    candidates = [
        "estimated_download_count",
        "n_eff",
        "skill_download_count",
        "skill_install_count",
    ]
    for col in candidates:
        if col in df.columns:
            return col
    raise ValueError(
        "No exposure column found. Please provide one of: "
        "estimated_download_count, n_eff, skill_download_count, skill_install_count."
    )


def scale_bubble_sizes(values, min_size=350, max_size=2600):
    values = np.asarray(values, dtype=float)
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)

    if values.max() <= 0:
        return np.full_like(values, min_size, dtype=float)

    scaled = np.sqrt(values / values.max())
    return min_size + scaled * (max_size - min_size)


# =========================
# Main plotting function
# =========================
def plot_fig3b_bubble(df: pd.DataFrame):
    n = len(df)

    if "pdei_score" not in df.columns:
        raise ValueError("Missing required column: pdei_score")

    exposure_col = choose_exposure_column(df)

    df = df.copy()
    df["pdei_score"] = pd.to_numeric(df["pdei_score"], errors="coerce").fillna(0)
    df[exposure_col] = pd.to_numeric(df[exposure_col], errors="coerce").fillna(0)

    baseline_pdei = df["pdei_score"].mean()
    if baseline_pdei <= 0:
        raise ValueError("Mean pdei_score is zero or invalid; cannot compute amplification.")

    rows = []
    for path_name, info in PATH_INFO.items():
        col = info["col"]
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

        flag = to_binary_series(df[col]) == 1
        sub = df.loc[flag]

        trigger_count = int(flag.sum())
        trigger_freq = trigger_count / n * 100.0
        mean_pdei = sub["pdei_score"].mean() if trigger_count > 0 else 0
        pdei_amp = mean_pdei / baseline_pdei if trigger_count > 0 else 0
        exposure_sum = sub[exposure_col].sum() if trigger_count > 0 else 0

        rows.append(
            {
                "Path": f"Path {path_name}",
                "PathKey": path_name,
                "Combination": " ∧ ".join(info["tiers"]),
                "Meaning": info["full"],
                "TriggerCount": trigger_count,
                "TriggerFrequencyPercent": trigger_freq,
                "MeanPDEI": mean_pdei,
                "PDEIAmplification": pdei_amp,
                "AffectedUsersProxy": exposure_sum,
            }
        )

    stats = pd.DataFrame(rows)

    # 保存统计表，正文里可直接用
    stats_path = OUT_DIR / "fig3B_path_statistics.csv"
    stats.to_csv(stats_path, index=False, encoding="utf-8-sig")
    print(f"[Saved] {stats_path}")

    sizes = scale_bubble_sizes(stats["AffectedUsersProxy"].values)

    fig, ax = plt.subplots(figsize=(8.2, 5.8))

    for idx, row in stats.iterrows():
        path_key = row["PathKey"]

        if path_key in {"D", "E"}:
            alpha = 0.85
            linewidth = 1.8
        else:
            alpha = 0.65
            linewidth = 1.0

        ax.scatter(
            row["TriggerFrequencyPercent"],
            row["PDEIAmplification"],
            s=sizes[idx],
            alpha=alpha,
            edgecolors="black",
            linewidths=linewidth,
        )

    offsets = {
        "A": (10, -18),
        "B": (-58, 6),
        "C": (10, 8),
        "D": (10, 14),
        "E": (10, 8),
    }

    for _, row in stats.iterrows():
        path_key = row["PathKey"]
        dx, dy = offsets.get(path_key, (8, 8))

        label = f"{row['Path']}\n{row['Meaning']}"
        ax.annotate(
            label,
            xy=(row["TriggerFrequencyPercent"], row["PDEIAmplification"]),
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=9,
            ha="left" if dx >= 0 else "right",
            va="center",
        )

    ax.axhline(
        y=1.0,
        linestyle="--",
        linewidth=1.0,
        color="gray",
        alpha=0.8,
    )
    ax.text(
        0.5,
        1.03,
        "Ecosystem average PDEI",
        fontsize=9,
        color="gray",
        va="bottom",
    )

    ax.set_xlabel("Trigger frequency among skills (%)", fontsize=12)
    ax.set_ylabel("PDEI amplification over ecosystem average", fontsize=12)
    ax.set_title(
        "Fig. 3B. Trigger Frequency and Risk Amplification of Toxic Pathways",
        fontsize=13,
        pad=14,
    )

    # bubble legend
    exposure_values = stats["AffectedUsersProxy"].values
    legend_values = np.percentile(exposure_values, [25, 50, 100])
    legend_values = np.unique(np.round(legend_values, 0))

    for val in legend_values:
        if val <= 0:
            continue
        legend_size = scale_bubble_sizes([val], min_size=350, max_size=2600)[0]

        if val >= 1_000_000:
            label = f"{val / 1_000_000:.1f}M users"
        elif val >= 1_000:
            label = f"{val / 1_000:.1f}K users"
        else:
            label = f"{int(val)} users"

        ax.scatter(
            [],
            [],
            s=legend_size,
            alpha=0.45,
            edgecolors="black",
            linewidths=0.8,
            label=label,
        )

    ax.legend(
        title=f"Exposure proxy\n({exposure_col})",
        loc="upper right",
        frameon=True,
        fontsize=8,
        title_fontsize=9,
    )

    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.45)

    x_max = max(stats["TriggerFrequencyPercent"].max() * 1.18, 5)
    y_max = max(stats["PDEIAmplification"].max() * 1.22, 1.5)

    ax.set_xlim(0, x_max)
    ax.set_ylim(0, y_max)

    plt.tight_layout()

    png_path = OUT_DIR / "fig3B_path_bubble_plot.png"
    pdf_path = OUT_DIR / "fig3B_path_bubble_plot.pdf"
    plt.savefig(png_path, dpi=300, bbox_inches="tight")
    plt.savefig(pdf_path, bbox_inches="tight")
    plt.close()

    print(f"[Saved] {png_path}")
    print(f"[Saved] {pdf_path}")

    print("\n=== Path statistics ===")
    print(
        stats[
            [
                "Path",
                "Combination",
                "Meaning",
                "TriggerCount",
                "TriggerFrequencyPercent",
                "PDEIAmplification",
                "AffectedUsersProxy",
            ]
        ].to_string(index=False)
    )


# =========================
# Run
# =========================
def main():
    df = pd.read_csv(CSV_PATH)
    plot_fig3b_bubble(df)


if __name__ == "__main__":
    main()