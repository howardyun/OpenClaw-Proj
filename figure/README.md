# figure

PermAudit 论文配图一键生成脚本，输出 **Nature Communications** 风格图（图内无标题、多 panel 图标注 a/b、图注写入 `*_caption.txt`）。

## 项目结构

```
figure/
├── generate_figures.py   # 唯一入口
├── requirements.txt
├── README.md
└── output/               # 运行后生成（可删可重建）
```

**不需要 `data/` 目录。** Fig4B 的 8×4 法规冲突评分矩阵已内置在 `generate_figures.py` 中。

## 安装

```bash
pip install -r requirements.txt
```

## 输入数据（项目外 CSV）

| 用途 | 参数 | 说明 |
|------|------|------|
| 主数据 | `--v4-csv` | Fig1 / Fig3 / Fig4A / Fig5（含下载量漏斗）；Fig2 默认同文件 |
| PDEI 全量（可选） | `--pdei-csv` | 仅 Fig2；未指定时使用 `--v4-csv` |
| Top10 毒性组合 | `--combo-stats-csv` | 推荐；自动统计 top10 原子组合 |
| Top10（预聚合） | `--top10-csv` | 与上表二选一 |
| Fig4B 自定义矩阵 | `--reg-conflict-csv` | 可选；覆盖内置默认矩阵 |

### v4.csv 必需列

**Fig1 / Fig3 / Fig4A / Fig5（skill 漏斗）：** `domain`, `source_plat`, `declaration_atomic_ids`, `pdei_score`, `delta_t1`–`delta_t4`, `path_A`–`path_E`

**Fig4A（download 漏斗）额外：** `estimated_download_count`, `pdei_score`

**Fig2 额外：**

| 列名 | 用途 |
|------|------|
| `pdei_score` | PDEI 分数 |
| `n_eff`, `phi`, `gamma` | 下游暴露 \(E = n_\mathrm{eff} \times \phi \times \gamma\)（与 Methods M6 一致） |
| `developer`, `developer_is_org`, `developer_github_stars` | Fig2B 开发者声誉散点 |

> Fig2A **不再**用 `estimated_download_count` 计算 exposure share；该列仍供 Fig4A 下载量漏斗使用。

## 运行

一键生成全部（推荐）：

```bash
python generate_figures.py \
  --v4-csv "/path/to/pdei_scores_full_v4.csv" \
  --combo-stats-csv "/path/to/declaration_toxic_combo_stats_v2.csv" \
  --out-dir "./output" --pdf
```

PowerShell 示例：

```powershell
python generate_figures.py `
  --v4-csv "C:\path\to\pdei_scores_full_v4.csv" `
  --combo-stats-csv "C:\path\to\declaration_toxic_combo_stats_v2.csv" `
  --out-dir "./output" --pdf
```

仅重出 Fig2（PDEI 与 v4 为同一文件时可只传一个 CSV）：

```powershell
python generate_figures.py `
  --fig2-only `
  --pdei-csv "C:\path\to\pdei_scores_full_v4.csv" `
  --out-dir "./output" --pdf
```

### 常用选项

| 命令 | 作用 |
|------|------|
| `--fig2-only` | 只生成 Fig2A / Fig2B |
| `--fig4b-only` | 只生成 Fig4B（无需 v4 CSV） |
| `--skip-fig2` | 跳过 Fig2 |
| `--skip-fig4b` | 跳过 Fig4B |
| `--funnel-l1 N` | 手动指定 Fig4A 漏斗 L1 总量 |
| `--pdf` | 同时输出 PDF（投稿 LaTeX 建议开启） |
| `--fig2a-run-bootstrap` | 在 `fig2a_stats_*.txt` 中追加**探索性**幂律 bootstrap（默认关闭，主图不含幂律拟合） |
| `--fig2a-run-vuong` | 同上，追加 Vuong 模型比较（默认关闭） |
| `--fig2a-bootstrap-n` / `--fig2a-bootstrap-seed` / `--fig2a-bootstrap-size` | 探索性 bootstrap 参数 |

未指定 `--funnel-l1` 时，L1 取 combo stats 行数与 v4 行数的较大值。

## 输出

| 图 | 主要 PNG / PDF |
|----|----------------|
| Fig1 | `fig1_heatmap.png` |
| Fig2A | `fig2a_pdei_ccdf_outside.png`（及 `.pdf`） |
| Fig2B | 见下文「Fig2」 |
| Fig3A | `fig3a_cooccurrence.png` |
| Fig3B | `fig3b_avg_pdei_by_domain.png` |
| Fig3C | `fig3c_path_density_by_domain.png` |
| Fig4A | `fig4a_funnel.png`（skill 数量漏斗） |
| Fig4A | `fig4a_download_funnel.png`（下载量漏斗） |
| Fig4B | `fig4b_reg_conflict.png` |
| Fig5 | `fig5_platform_overprivilege_rate.png` |

每张图还附带：

- `*_caption.txt` — 论文图注草稿（复制到稿件）；Fig2 / Fig3 另有 `fig2_combined_caption.txt`、`fig3_combined_caption.txt`
- `*_stats.txt` / `*_meta.json` — 统计与元数据（Fig2 / Fig3 / Fig4 / Fig5；Fig3b 见 `fig3b_domain_summary.csv`；Fig5 见 `fig5_platform_overprivilege_rate.csv`；下载量漏斗见 `fig4a_download_funnel_stats.txt`）

## Fig2（PDEI 分布 + 开发者声誉）

### Fig2A：经验 CCDF + 集中度（对齐 Methods M6）

主图**不含**幂律拟合曲线，仅绘制 PDEI>0 子集上的经验 CCDF（log-log）。图内 stats box 与 `fig2a_stats_outside.txt` 报告：

| 指标 | 说明 |
|------|------|
| CCDF | 分母为 \(n_+\)（PDEI>0）；全语料 \(N\) 见 stats 行首 |
| Gini(PDEI), Gini(E) | 全 \(N\) 计算（含 PDEI=0）；\(E = n_\mathrm{eff} \times \phi \times \gamma\) |
| Gini 敏感性 | 仅 PDEI>0 子集（`fig2a_stats_*.txt` 单独一节） |
| Top 1% | 按 PDEI 排序，\(k=\lceil 0.01N\rceil\)；报告 PDEI share 与 **同一 PDEI 排序**下的 exposure share |
| E-ranked Top 1% | 仅写入 stats 作对照（按 \(E\) 单独排序时的 exposure share），**不出现在主图** |

默认输出 `fig2a_pdei_ccdf_outside.*`（stats box 在图内左下）。`build_fig2a(..., stats_box="inside")` 可生成 inside 变体，但 `run_fig2_suite` 默认只跑 outside。

**LaTeX 更新：** 将 `output/fig2a_pdei_ccdf_outside.pdf` 复制到稿件 `fig/ysx/`，并在 `R3.tex` 中把 `\includegraphics` 路径改为 `fig/ysx/fig2a_pdei_ccdf_outside.pdf`（旧文件名 `fig2a_pdei_powerlaw_ccdf_outside.pdf` 已废弃）。

### Fig2B：多个变体

`run_fig2_suite` 会生成：

| 文件 | 说明 |
|------|------|
| `fig2b_developer_stars_vs_avg_pdei_min1skills_insidelegend_insidestats.*` | 全量散点 + stats |
| `fig2b_star_bins_*` | 按 star 分箱的小提琴/箱线图 |
| `fig2b_scatter_opt_starsgt0_thin_sub6000_insidelegend_insidestats.*` | **论文常用**：stars>0、分层抽样作图；Spearman 等统计仍基于全量 developer 聚合 |

Fig2B 附带 `fig2b_stats_min1skills_insidelegend_insidestats.txt`（Spearman、developer 数、Gini(avg PDEI) 等）。`scatter_opt` 变体图内标注与上述 stats 应对齐；投稿时保留实际使用的那一张即可。

## Fig3 三 panel

一键生成时会输出 Fig3 的三个独立 panel（图内无标题；合并图注见 `fig3_combined_caption.txt`）：

| 输出文件 | 含义 |
|----------|------|
| `fig3a_cooccurrence.png` | Top10 毒性原子组合共现矩阵；红框标注 Path A–E |
| `fig3b_avg_pdei_by_domain.png` | 各 skill domain 平均 PDEI（按均值降序） |
| `fig3c_path_density_by_domain.png` | 各 domain 的 path_A–path_E 激活率热图（Y 轴顺序与 3b 一致） |

附带文件：`fig3a_cooccurrence_meta.json`、`fig3b_avg_pdei_by_domain_stats.txt`、`fig3b_domain_summary.csv`。

Fig3b/3c 由全量 v4 按 `domain` 聚合；path 密度定义为该 domain 内 `path_X > 0` 的 skill 占比。

若只需快速重出 Fig3（跳过 Fig2），可加 `--skip-fig2 --skip-fig4b`。

## Fig5 平台过度授权（体量 + 比例）

按 `source_plat` 统计五平台 skill 总量与 **过度授权**（Σδ_t ≥ 1，与 Fig4A L3 定义一致）：

| 输出文件 | 含义 |
|----------|------|
| `fig5_platform_overprivilege_rate.png` | 堆叠柱状图：柱高 = skill 总数；蓝色 = 过度授权；浅灰 = 未过度授权 |
| `fig5_platform_overprivilege_rate.csv` | 各平台 skill 数、过度授权数、占比 |
| `fig5_platform_overprivilege_rate_stats.txt` | 汇总明细 |

平台按 corpus 规模降序排列；柱顶标注 `xx.xx%` 与 `(n=…)`。

## Fig4A 漏斗图

一键生成时会同时输出两张 Fig4A，布局与配色相同，仅聚合指标不同：

| 输出文件 | 含义 | L1 → L4 |
|----------|------|---------|
| `fig4a_funnel.png` | Skill 数量漏斗 | Raw corpus → Valid dataset → Over-privileged → Toxic / high-risk |
| `fig4a_download_funnel.png` | 下载量漏斗 | Total downloads → Over-privileged → Toxic-combo → Top 1% PDEI（toxic-combo 内） |

下载量漏斗按 `estimated_download_count` 加权；L4 取 toxic-combo 技能中 PDEI 最高的 top 1%（脚本常量 `FIG4A_DOWNLOAD_TOP_PCT = 1.0`）。

**L4 可读性：** 下载量漏斗的 L4 数值相对 L1 很小，若按真实比例绘制条带过窄，中心白字会落在白色画布上。脚本对 L4 条带设置了最小半宽（`FIG4A_DOWNLOAD_MIN_LAST_HALF_W = 0.105`），在可读性与比例感之间折中；如需更细/更宽，可在 `generate_figures.py` 中调整该常量。

两张漏斗均附带 `*_caption.txt`、`*_meta.json`；下载量变体另有 `fig4a_download_funnel_stats.txt`。

## Fig4B 内置矩阵

默认 8 类 abuse category × 4 部法规（GDPR、EU AI Act、CCPA、PIPL），分数定义见脚本内 `DEFAULT_REG_CONFLICT_SCORES`。

如需自定义，传入 CSV（列：`abuse_category`, `GDPR`, `EU AI Act`, `CCPA`, `PIPL`）：

```bash
python generate_figures.py --fig4b-only --reg-conflict-csv "./my_matrix.csv" --out-dir "./output"
```
