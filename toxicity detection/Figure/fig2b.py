"""
Fig. 2B: Developer GitHub stars vs. average PDEI.
Improved layout to avoid overlap between legend and annotation.

Usage examples:
  python fig2b_developer_stars_vs_avg_pdei_v2.py
  python fig2b_developer_stars_vs_avg_pdei_v2.py --input-csv your_full_dataset.csv
  python fig2b_developer_stars_vs_avg_pdei_v2.py --legend-pos outside --stats-box inside

Required default columns:
  - developer
  - developer_is_org
  - developer_github_stars
  - pdei_score
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

INPUT_CSV = Path("pdei_scores_full_v4_download_proxy.csv")
OUT_DIR = Path("output/figure2b")
PDEI_COL = "pdei_score"
DEVELOPER_COL = "developer"
IS_ORG_COL = "developer_is_org"
STAR_COL = "developer_github_stars"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot Fig. 2B: developer reputation vs average PDEI.")
    parser.add_argument("--input-csv", type=Path, default=INPUT_CSV)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--pdei-col", type=str, default=PDEI_COL)
    parser.add_argument("--developer-col", type=str, default=DEVELOPER_COL)
    parser.add_argument("--is-org-col", type=str, default=IS_ORG_COL)
    parser.add_argument("--star-col", type=str, default=STAR_COL)
    parser.add_argument(
        "--min-skills-per-developer",
        type=int,
        default=1,
        help="Keep developers with at least this many Skills.",
    )
    parser.add_argument(
        "--legend-pos",
        choices=["inside", "outside", "none"],
        default="inside",
        help="Legend placement.",
    )
    parser.add_argument(
        "--stats-box",
        choices=["inside", "outside", "none"],
        default="inside",
        help="Statistics box placement.",
    )
    return parser.parse_args()


def normalize_bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .isin(["true", "1", "yes", "y", "org", "organization"])
    )


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


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.input_csv)
    required = [args.developer_col, args.is_org_col, args.star_col, args.pdei_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}. Available columns: {list(df.columns)}")

    df[args.pdei_col] = pd.to_numeric(df[args.pdei_col], errors="coerce").fillna(0).clip(lower=0)
    df[args.star_col] = pd.to_numeric(df[args.star_col], errors="coerce").fillna(0).clip(lower=0)
    df[args.is_org_col] = normalize_bool_series(df[args.is_org_col])
    df[args.developer_col] = df[args.developer_col].fillna("unknown_developer").astype(str)

    agg = (
        df.groupby([args.developer_col, args.is_org_col], as_index=False)
        .agg(
            avg_pdei=(args.pdei_col, "mean"),
            median_pdei=(args.pdei_col, "median"),
            max_pdei=(args.pdei_col, "max"),
            developer_github_stars=(args.star_col, "first"),
            n_skills=(args.pdei_col, "size"),
        )
    )
    agg = agg[agg["n_skills"] >= args.min_skills_per_developer].copy()

    if len(agg) < 3:
        raise ValueError("Too few developers after filtering; lower --min-skills-per-developer.")

    rho, pval = stats.spearmanr(agg["developer_github_stars"], agg["avg_pdei"])

    fig, ax = plt.subplots(figsize=(6.8, 4.8))

    for is_org, label, marker in [
        (False, "Individual developer", "o"),
        (True, "Organization", "s"),
    ]:
        sub = agg[agg[args.is_org_col] == is_org]
        if sub.empty:
            continue
        sizes = 24 + 12 * np.sqrt(sub["n_skills"].to_numpy())
        ax.scatter(
            np.log10(sub["developer_github_stars"] + 1),
            np.log10(sub["avg_pdei"] + 1),
            s=sizes,
            alpha=0.72,
            label=label,
            marker=marker,
            edgecolors="white",
            linewidths=0.5,
        )

    ax.set_xlabel("Developer GitHub stars, log10(stars + 1)")
    ax.set_ylabel("Average PDEI per developer, log10(PDEI + 1)")
    ax.set_title("Fig. 2B. Developer reputation does not guarantee permission safety")
    ax.grid(True, linestyle=":", linewidth=0.7, alpha=0.45)

    if args.legend_pos == "inside":
        ax.legend(loc="upper left", bbox_to_anchor=(0.02, 0.98), frameon=False, fontsize=8.8)
    elif args.legend_pos == "outside":
        fig.subplots_adjust(right=0.74)
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.00), frameon=False, fontsize=8.8)

    annotation = (
        f"Spearman rho={rho:.2f}, p={pval:.3f}\n"
        f"developers={len(agg):,}\n"
        f"Gini(avg PDEI)={gini(agg['avg_pdei']):.2f}"
    )

    if args.stats_box == "inside":
        ax.text(
            0.98,
            0.05,
            annotation,
            transform=ax.transAxes,
            fontsize=8.6,
            va="bottom",
            ha="right",
            bbox=dict(boxstyle="round,pad=0.35", facecolor="white", alpha=0.86, linewidth=0.5),
        )
    elif args.stats_box == "outside":
        fig.subplots_adjust(right=0.72)
        fig.text(
            0.745,
            0.25,
            annotation,
            fontsize=8.6,
            va="bottom",
            ha="left",
            bbox=dict(boxstyle="round,pad=0.35", facecolor="white", alpha=0.90, linewidth=0.5),
        )

    suffix = f"min{args.min_skills_per_developer}skills_{args.legend_pos}legend_{args.stats_box}stats"
    png_path = args.out_dir / f"fig2b_developer_stars_vs_avg_pdei_{suffix}.png"
    pdf_path = args.out_dir / f"fig2b_developer_stars_vs_avg_pdei_{suffix}.pdf"
    stats_path = args.out_dir / f"fig2b_stats_{suffix}.txt"

    fig.tight_layout()
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(pdf_path, bbox_inches="tight")
    plt.close(fig)

    stats_text = f"""
Input file: {args.input_csv}
Number of skills: {len(df)}
Number of developers after filtering: {len(agg)}
Minimum skills per developer: {args.min_skills_per_developer}

Developer reputation correlation:
  Spearman_rho = {rho:.4f}
  Spearman_p = {pval:.4f}

Developer-level PDEI summary:
  avg_PDEI_mean = {agg['avg_pdei'].mean():.4f}
  avg_PDEI_median = {agg['avg_pdei'].median():.4f}
  avg_PDEI_max = {agg['avg_pdei'].max():.4f}
  Gini_avg_PDEI = {gini(agg['avg_pdei']):.4f}

Developer type counts:
{agg[args.is_org_col].map({True: 'Organization', False: 'Individual'}).value_counts().to_string()}
""".strip()
    stats_path.write_text(stats_text, encoding="utf-8")

    print(stats_text)
    print(f"\nSaved: {png_path}")
    print(f"Saved: {pdf_path}")
    print(f"Saved: {stats_path}")


if __name__ == "__main__":
    main()
