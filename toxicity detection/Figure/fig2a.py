"""
Fig. 2A: PDEI heavy-tailed distribution with a power-law tail fit.

This version fixes label/annotation overlap by moving the statistics box
outside the plotting area and making the Top X% concentration ratio configurable.

Usage examples:
  python fig2a_pdei_powerlaw_ccdf_v2.py
  python fig2a_pdei_powerlaw_ccdf_v2.py --top-pct 1
  python fig2a_pdei_powerlaw_ccdf_v2.py --top-pct 10 --input-csv your_full_dataset.csv
  python fig2a_pdei_powerlaw_ccdf_v2.py --stats-box inside
  python fig2a_pdei_powerlaw_ccdf_v2.py --stats-box none
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Dict, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats


# =============================
# Default configurable settings
# =============================
INPUT_CSV = Path("pdei_scores_full_v4_download_proxy.csv")
OUT_DIR = Path("output/figure2a")
PDEI_COL = "pdei_score"
DOWNLOAD_COL = "estimated_download_count"
TOP_PERCENT = 1.0  # Change this to 10.0 for top 10%, 5.0 for top 5%, etc.
MIN_TAIL_N = 30
MAX_QUANTILE_FOR_XMIN_SEARCH = 0.90

# Safer default font for Greek letters and minus signs in matplotlib.
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.unicode_minus": False,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot Fig. 2A: PDEI power-law CCDF.")
    parser.add_argument("--input-csv", type=Path, default=INPUT_CSV)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--pdei-col", type=str, default=PDEI_COL)
    parser.add_argument("--download-col", type=str, default=DOWNLOAD_COL)
    parser.add_argument(
        "--top-pct",
        type=float,
        default=TOP_PERCENT,
        help="Top percentage used for concentration statistics. Example: 1 means top 1%%.",
    )
    parser.add_argument("--min-tail-n", type=int, default=MIN_TAIL_N)
    parser.add_argument(
        "--stats-box",
        choices=["outside", "inside", "none"],
        default="outside",
        help="Where to place the statistics box. 'outside' avoids overlap and is recommended.",
    )
    return parser.parse_args()


def gini(values: pd.Series | np.ndarray) -> float:
    """Calculate the Gini coefficient of a non-negative vector."""
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


def top_share(values: pd.Series, top_pct: float) -> Tuple[int, float, pd.Index]:
    """Return count, mass share, and row index of the top top_pct observations."""
    if top_pct <= 0 or top_pct > 100:
        raise ValueError("top_pct must be in the range (0, 100].")
    x = pd.to_numeric(values, errors="coerce").fillna(0).astype(float)
    k = max(1, int(math.ceil(len(x) * top_pct / 100.0)))
    top_idx = x.nlargest(k).index
    total = float(x.sum())
    share = float(x.loc[top_idx].sum() / total) if total > 0 else float("nan")
    return k, share, top_idx


def fit_powerlaw_tail(
    values: pd.Series | np.ndarray,
    min_tail_n: int = MIN_TAIL_N,
    max_quantile: float = MAX_QUANTILE_FOR_XMIN_SEARCH,
) -> Dict[str, float]:
    """
    Fit a continuous power-law tail using a Clauset-style MLE search.

    PDF:  p(x) = (alpha - 1) / xmin * (x / xmin)^(-alpha), x >= xmin
    CCDF: P(X >= x) = (x / xmin)^(1 - alpha)

    The KS p-value reported here is approximate because xmin and alpha are
    estimated from the same data. For a final paper, a bootstrap p-value is more rigorous.
    """
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
        ks_d, ks_p = stats.kstest(tail, "pareto", args=(alpha - 1.0, 0, xmin))
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
        raise ValueError("No valid tail fit found. Try lowering --min-tail-n.")
    return best


def make_annotation(
    n_total: int,
    n_positive: int,
    fit: Dict[str, float],
    top_pct: float,
    k_top: int,
    top_pdei_share: float,
    top_exposure_share_by_pdei: float,
) -> str:
    """Build a compact annotation to reduce text overlap."""
    return (
        f"n = {n_total:,}; positive = {n_positive:,}\n"
        f"alpha = {fit['alpha']:.2f}; xmin = {fit['xmin']:.1f}\n"
        f"KS D = {fit['ks_D']:.3f}; p ~ {fit['ks_p_approx']:.3f}\n"
        f"Top {top_pct:g}%: k = {k_top:,}\n"
        f"PDEI share = {top_pdei_share:.1%}\n"
        f"Exposure share = {top_exposure_share_by_pdei:.1%}"
    )


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.input_csv)
    missing = [c for c in [args.pdei_col, args.download_col] if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}. Available columns: {list(df.columns)}")

    df[args.pdei_col] = pd.to_numeric(df[args.pdei_col], errors="coerce").fillna(0).clip(lower=0)
    df[args.download_col] = pd.to_numeric(df[args.download_col], errors="coerce").fillna(0).clip(lower=0)
    df["downstream_exposure"] = df[args.pdei_col] * df[args.download_col]

    positive_pdei = df.loc[df[args.pdei_col] > 0, args.pdei_col]
    fit = fit_powerlaw_tail(positive_pdei, min_tail_n=args.min_tail_n)

    # Concentration based on top-PDEI Skills.
    k_top, top_pdei_share, top_pdei_idx = top_share(df[args.pdei_col], args.top_pct)
    total_exposure = float(df["downstream_exposure"].sum())
    top_exposure_share_by_pdei = (
        float(df.loc[top_pdei_idx, "downstream_exposure"].sum() / total_exposure)
        if total_exposure > 0 else float("nan")
    )

    # Optional comparison: top exposure share if ranked directly by exposure.
    _, top_exposure_share_by_exposure, _ = top_share(df["downstream_exposure"], args.top_pct)

    # Empirical CCDF.
    x = np.sort(positive_pdei.to_numpy(dtype=float))
    ccdf = np.arange(len(x), 0, -1) / len(x)

    if args.stats_box == "outside":
        fig, ax = plt.subplots(figsize=(8.2, 4.8))
        fig.subplots_adjust(right=0.70)
    else:
        fig, ax = plt.subplots(figsize=(6.6, 4.8))

    ax.scatter(x, ccdf, s=18, alpha=0.62, edgecolors="none", label="Empirical CCDF")

    x_fit = np.logspace(np.log10(fit["xmin"]), np.log10(x.max()), 200)
    y_fit = fit["tail_fraction"] * (x_fit / fit["xmin"]) ** (1.0 - fit["alpha"])
    ax.plot(x_fit, y_fit, linewidth=2.2, linestyle="--", label=f"Power-law fit (alpha={fit['alpha']:.2f})")
    ax.axvline(fit["xmin"], linewidth=1.2, linestyle=":", label=f"xmin={fit['xmin']:.1f}")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("PDEI score")
    ax.set_ylabel("Pr(PDEI >= x)")
    ax.set_title("Fig. 2A. Heavy-tailed distribution of permission abuse")
    ax.grid(True, which="both", linestyle=":", linewidth=0.7, alpha=0.45)
    ax.legend(loc="upper right", frameon=False, fontsize=8.5)

    annotation = make_annotation(
        n_total=len(df),
        n_positive=len(positive_pdei),
        fit=fit,
        top_pct=args.top_pct,
        k_top=k_top,
        top_pdei_share=top_pdei_share,
        top_exposure_share_by_pdei=top_exposure_share_by_pdei,
    )

    if args.stats_box == "outside":
        # Put the box in figure coordinates, outside the plotting axes.
        fig.text(
            0.725,
            0.52,
            annotation,
            fontsize=8.6,
            va="center",
            ha="left",
            bbox=dict(boxstyle="round,pad=0.40", facecolor="white", alpha=0.92, linewidth=0.6),
        )
    elif args.stats_box == "inside":
        # Upper-left is usually cleaner than lower-left for a CCDF curve.
        ax.text(
            0.04,
            0.96,
            annotation,
            transform=ax.transAxes,
            fontsize=8.0,
            va="top",
            bbox=dict(boxstyle="round,pad=0.35", facecolor="white", alpha=0.88, linewidth=0.5),
        )

    pct_tag = str(args.top_pct).replace(".", "p")
    box_tag = args.stats_box
    png_path = args.out_dir / f"fig2a_pdei_powerlaw_ccdf_top{pct_tag}pct_{box_tag}.png"
    pdf_path = args.out_dir / f"fig2a_pdei_powerlaw_ccdf_top{pct_tag}pct_{box_tag}.pdf"
    stats_path = args.out_dir / f"fig2a_stats_top{pct_tag}pct_{box_tag}.txt"

    if args.stats_box == "outside":
        fig.savefig(png_path, dpi=300, bbox_inches="tight")
        fig.savefig(pdf_path, bbox_inches="tight")
    else:
        fig.tight_layout()
        fig.savefig(png_path, dpi=300)
        fig.savefig(pdf_path)
    plt.close(fig)

    stats_text = f"""
Input file: {args.input_csv}
Number of skills: {len(df)}
Positive PDEI skills: {len(positive_pdei)}
Zero-PDEI skills: {int((df[args.pdei_col] == 0).sum())}

Power-law tail fit:
  alpha = {fit['alpha']:.4f}
  xmin = {fit['xmin']:.4f}
  tail_n = {fit['n_tail']}
  tail_fraction = {fit['tail_fraction']:.4f}
  KS_D = {fit['ks_D']:.4f}
  KS_p_approx = {fit['ks_p_approx']:.4f}

Concentration with configurable top percentage:
  top_pct = {args.top_pct:.4f}%
  top_count = {k_top}
  top_PDEI_share = {top_pdei_share:.4%}
  top_downstream_exposure_share_among_top_PDEI_skills = {top_exposure_share_by_pdei:.4%}
  top_downstream_exposure_share_if_ranked_by_exposure = {top_exposure_share_by_exposure:.4%}
  Gini_PDEI = {gini(df[args.pdei_col]):.4f}
  Gini_downstream_exposure = {gini(df['downstream_exposure']):.4f}
""".strip()
    stats_path.write_text(stats_text, encoding="utf-8")

    print(stats_text)
    print(f"\nSaved: {png_path}")
    print(f"Saved: {pdf_path}")
    print(f"Saved: {stats_path}")


if __name__ == "__main__":
    main()
