# -*- coding: utf-8 -*-
"""
一次运行：导出 CSV/JSON，生成全部 PNG（含四宫格 dashboard）。
单张图请用 plot_fig1.py、plot_fig1b.py、plot_fig2.py、plot_fig3.py。

用法（在 figure 目录下）:
  python plot_all_figures.py
  python plot_all_figures.py --data-dir sample_data [--output-dir 路径]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import figures_common as fc

main = fc.run_all_figures


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="一次生成全部图并导出表。单图请用 plot_fig*.py。",
    )
    p.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="真实数据目录（须含两张热图 CSV，详见 figures_common.load_user_data_from_directory）",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="输出目录，默认本目录下 output/",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    main(data_dir=args.data_dir, output_dir=args.output_dir)
