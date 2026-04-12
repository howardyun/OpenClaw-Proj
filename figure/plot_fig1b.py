# -*- coding: utf-8 -*-
"""仅生成 Fig1b：出现占比热图 → fig1b_heatmap_presence_by_platform.png"""

from __future__ import annotations

import argparse
from pathlib import Path

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

    path = out_dir / "fig1b_heatmap_presence_by_platform.png"
    fc.plot_second_heatmap_presence(path)
    print(f"已保存: {path}")


if __name__ == "__main__":
    main()
