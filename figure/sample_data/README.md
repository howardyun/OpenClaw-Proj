本文件夹为「静态模拟真实数据」，与 figures_common.load_user_data_from_directory 约定格式一致。

在 figure 目录下执行（一次出全图 + 导出表）：

  python plot_all_figures.py --data-dir sample_data

或指定输出目录：

  python plot_all_figures.py --data-dir sample_data --output-dir output_sample

若只要单张图：

  python plot_fig1.py --data-dir sample_data
  python plot_fig1b.py --data-dir sample_data
  python plot_fig2.py --data-dir sample_data
  python plot_fig3.py --data-dir sample_data

文件说明：
  heatmap_overprivilege_rate.csv   → Fig1 热图（过权率，0~1）
  heatmap_presence_by_platform.csv → Fig1b 热图（出现占比，0~1）
  permission_frequency_stats.csv   → 频率统计（可选）
  data_meta.json                   → total_skills = 100000
  powerlaw.csv                     → Fig2（可选）
  toxic_combos.csv                 → Fig3（可选）

可自行改表格里的数字，保存后再运行同一命令即可重新出图。
