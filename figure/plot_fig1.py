# -*- coding: utf-8 -*-
"""仅生成 Fig1：过度授权率热图 → fig1_heatmap_overprivilege.png"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt

import figures_common as fc


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, default=None, help="数据目录（与总脚本相同要求）")
    p.add_argument("--output-dir", type=Path, default=None, help="输出目录，默认本目录下 output/")
    return p.parse_args()


def main() -> None:
    args = _parse()
    fc.init_plot_style()
    if args.data_dir is not None:
        fc.load_user_data_from_directory(Path(args.data_dir))

    out_dir = Path(args.output_dir).resolve() if args.output_dir else Path(__file__).resolve().parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=fc.HEATMAP_SINGLE_FIGSIZE_INCHES)
    fc.plot_fig1_heatmap(ax, include_footnote=True)
    fc._layout_single_heatmap_figure(fig, has_footnote=True)
    path = out_dir / "fig1_heatmap_overprivilege.png"
    fig.savefig(path, dpi=fc.FIGURE_DPI, bbox_inches=None)
    plt.close(fig)
    print(f"已保存: {path}")


if __name__ == "__main__":
    main()
