# -*- coding: utf-8 -*-
"""仅生成 Fig2：幂律分布曲线 → fig2_powerlaw_redundancy.png"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt

import figures_common as fc


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, default=None, help="数据目录；若含 powerlaw.csv 会覆盖内置曲线")
    p.add_argument("--output-dir", type=Path, default=None, help="输出目录，默认本目录下 output/")
    return p.parse_args()


def main() -> None:
    args = _parse()
    fc.init_plot_style()
    if args.data_dir is not None:
        fc.load_user_data_from_directory(Path(args.data_dir))

    out_dir = Path(args.output_dir).resolve() if args.output_dir else Path(__file__).resolve().parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(9, 6))
    fc.plot_fig2_powerlaw(ax)
    fig.text(
        0.5,
        0.02,
        "Power-law distribution of redundancy",
        ha="center",
        fontsize=9,
        style="italic",
        color="#333333",
    )
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    path = out_dir / "fig2_powerlaw_redundancy.png"
    fig.savefig(path, dpi=fc.FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"已保存: {path}")


if __name__ == "__main__":
    main()
