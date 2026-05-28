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
| 主数据 | `--v4-csv` | Fig1 / Fig3 / Fig4A；Fig2 默认同文件 |
| Top10 毒性组合 | `--combo-stats-csv` | 推荐；自动统计 top10 原子组合 |
| Top10（预聚合） | `--top10-csv` | 与上表二选一 |
| Fig4B 自定义矩阵 | `--reg-conflict-csv` | 可选；覆盖内置默认矩阵 |

### v4.csv 必需列

**Fig1 / Fig3 / Fig4：** `domain`, `declaration_atomic_ids`, `delta_t1`–`delta_t4`, `path_A`–`path_E`

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
| Fig3 | `fig3_cooccurrence.png` |
| Fig4A | `fig4a_funnel.png` |
| Fig4B | `fig4b_reg_conflict.png` |

每张图还附带：

- `*_caption.txt` — 论文图注草稿（复制到稿件）
- `*_stats.txt` / `*_meta.json` — 统计与元数据（Fig2 / Fig3 / Fig4）

Fig2 会生成多个 2B 变体（散点、分箱、优化散点），投稿时保留实际使用的那一张即可。

## Fig4B 内置矩阵

默认 8 类 abuse category × 4 部法规（GDPR、EU AI Act、CCPA、PIPL），分数定义见脚本内 `DEFAULT_REG_CONFLICT_SCORES`。

如需自定义，传入 CSV（列：`abuse_category`, `GDPR`, `EU AI Act`, `CCPA`, `PIPL`）：

```bash
python generate_figures.py --fig4b-only --reg-conflict-csv "./my_matrix.csv" --out-dir "./output"
```
