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
| 主数据 | `--v4-csv` | Fig1 / Fig3 / Fig4A（含下载量漏斗）；Fig2 默认同文件 |
| Top10 毒性组合 | `--combo-stats-csv` | 推荐；自动统计 top10 原子组合 |
| Top10（预聚合） | `--top10-csv` | 与上表二选一 |
| Fig4B 自定义矩阵 | `--reg-conflict-csv` | 可选；覆盖内置默认矩阵 |

### v4.csv 必需列

**Fig1 / Fig3 / Fig4A（skill 漏斗）：** `domain`, `declaration_atomic_ids`, `pdei_score`, `delta_t1`–`delta_t4`, `path_A`–`path_E`

**Fig4A（download 漏斗）额外：** `estimated_download_count`, `pdei_score`（与 Fig2 相同列）

**Fig2 额外：** `pdei_score`, `estimated_download_count`, `developer`, `developer_is_org`, `developer_github_stars`

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

### 常用选项

| 命令 | 作用 |
|------|------|
| `--fig2-only` | 只生成 Fig2A / Fig2B |
| `--fig4b-only` | 只生成 Fig4B（无需 v4 CSV） |
| `--skip-fig2` | 跳过 Fig2 |
| `--skip-fig4b` | 跳过 Fig4B |
| `--funnel-l1 N` | 手动指定 Fig4A 漏斗 L1 总量 |
| `--pdf` | 同时输出 PDF |

未指定 `--funnel-l1` 时，L1 取 combo stats 行数与 v4 行数的较大值。

## 输出

| 图 | 主要 PNG |
|----|----------|
| Fig1 | `fig1_heatmap.png` |
| Fig2A | `fig2a_pdei_powerlaw_ccdf_outside.png` |
| Fig2B | `fig2b_developer_stars_vs_avg_pdei_*.png` 等变体 |
| Fig3A | `fig3a_cooccurrence.png` |
| Fig3B | `fig3b_avg_pdei_by_domain.png` |
| Fig3C | `fig3c_path_density_by_domain.png` |
| Fig4A | `fig4a_funnel.png`（skill 数量漏斗） |
| Fig4A | `fig4a_download_funnel.png`（下载量漏斗） |
| Fig4B | `fig4b_reg_conflict.png` |

每张图还附带：

- `*_caption.txt` — 论文图注草稿（复制到稿件）；Fig3 另有 `fig3_combined_caption.txt`
- `*_stats.txt` / `*_meta.json` — 统计与元数据（Fig2 / Fig3 / Fig4；Fig3b 见 `fig3b_domain_summary.csv`；下载量漏斗见 `fig4a_download_funnel_stats.txt`）

Fig2 会生成多个 2B 变体（散点、分箱、优化散点），投稿时保留实际使用的那一张即可。

## Fig3 三 panel

一键生成时会输出 Fig3 的三个独立 panel（图内无标题；合并图注见 `fig3_combined_caption.txt`）：

| 输出文件 | 含义 |
|----------|------|
| `fig3a_cooccurrence.png` | Top10 毒性原子组合共现矩阵；红框标注 Path A–E |
| `fig3b_avg_pdei_by_domain.png` | 各 skill domain 平均 PDEI（按均值降序） |
| `fig3c_path_density_by_domain.png` | 各 domain 的 path_A–path_E 激活率热图（Y 轴顺序与 3b 一致） |

附带文件：`fig3a_cooccurrence_meta.json`、`fig3b_avg_pdei_by_domain_stats.txt`、`fig3b_domain_summary.csv`。

Fig3b/3c 由全量 v4 按 `domain` 聚合；path 密度定义为该 domain 内 `path_X > 0` 的 skill 占比。

若只需快速重出 Fig3（跳过耗时的 Fig2 bootstrap），可加 `--skip-fig2 --skip-fig4b`。

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
