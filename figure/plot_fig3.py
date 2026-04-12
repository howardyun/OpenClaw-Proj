# -*- coding: utf-8 -*-
"""仅生成 Fig3：毒性权限组合条形图 → fig3_toxic_combos.png"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt

import figures_common as fc


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, default=None, help="数据目录；若含 toxic_combos.csv 会覆盖内置数据")
    p.add_argument("--output-dir", type=Path, default=None, help="输出目录，默认本目录下 output/")
    return p.parse_args()


def main() -> None:
    args = _parse()
    fc.init_plot_style()
    if args.data_dir is not None:
        fc.load_user_data_from_directory(Path(args.data_dir))

    out_dir = Path(args.output_dir).resolve() if args.output_dir else Path(__file__).resolve().parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(9, 5.2))
    fc.plot_fig3_toxic_bars(ax)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    fig.tight_layout()
    path = out_dir / "fig3_toxic_combos.png"
    fig.savefig(path, dpi=fc.FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"已保存: {path}")


if __name__ == "__main__":
    main()
