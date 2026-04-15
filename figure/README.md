# Figure：论文配图脚本（权限映射 / 平台统计）

本目录可整体拷贝到 GitHub 总仓库的任意子路径（如 `analysis/figure/`），**在 `figure` 目录内**按下面步骤运行即可。

---

## 如何运行（按顺序做）

### 1. 环境要求

- 已安装 **Python 3.10 或更高**（终端里执行 `python --version` 能看到版本号）。
- Windows / macOS / Linux 均可。

### 2. 进入本目录

所有命令都在 **`figure` 文件夹**下执行（该目录里应有 `requirements.txt`、`plot_fig1.py` 等）。

```bash
cd figure
```

若仓库里路径是 `paper/figure/`，则：

```bash
cd paper/figure
```

### 3. 安装依赖（只需做一次）

```bash
python -m pip install -r requirements.txt
```

若系统里 `python` 不可用，可改用 `py -3` 或 `python3`：

```bash
py -3 -m pip install -r requirements.txt
```

### 4. 运行脚本生成图片

**输出位置**：默认写到当前目录下的 **`output/`**（若不存在会自动创建）。图是 **PNG 文件**，不会弹窗，请到 `output` 里查看。

---

#### 方式 A：一次生成全部图 + 导出 CSV（推荐先跑通）

使用内置演示数据（不读外部 CSV）：

```bash
python plot_all_figures.py
```

使用 `sample_data` 里的示例 CSV（与真实数据格式相同）：

```bash
python plot_all_figures.py --data-dir sample_data
```

指定输出到别的文件夹：

```bash
python plot_all_figures.py --data-dir sample_data --output-dir my_output
```

---

#### 方式 B：只生成某一张图

不加大参数 = 用脚本内置演示数据：

```bash
python plot_fig1.py
python plot_fig1b.py
python plot_fig2.py
python plot_fig3.py
```

使用 `sample_data`：

```bash
python plot_fig1.py --data-dir sample_data
python plot_fig1b.py --data-dir sample_data
python plot_fig2.py --data-dir sample_data
python plot_fig3.py --data-dir sample_data
```

---

#### 方式 C：从仓库根目录运行（不先 `cd figure`）

把下面路径改成你仓库里 `figure` 的实际路径：

```bash
python figure/plot_all_figures.py --data-dir figure/sample_data --output-dir figure/output
```

---

### 5. 使用你自己的数据

1. 新建一个文件夹（例如 `my_data`），放入 **两个必需文件**（文件名必须一致）：
   - `heatmap_overprivilege_rate.csv`
   - `heatmap_presence_by_platform.csv`
2. 运行：

```bash
python plot_all_figures.py --data-dir my_data
```

可选文件与 CSV 格式说明见下文 **「数据文件说明」**。

---

### 6. PyCharm / VS Code

- 将 **`figure`** 作为工作目录打开，或使用「在包含 `plot_fig1.py` 的文件夹中打开终端」。
- 运行配置里 **工作目录** 设为 `figure`，脚本选 `plot_all_figures.py` 或 `plot_fig1.py` 等。
- 需要参数时，在运行配置里填写 **形参**：例如 `--data-dir sample_data`。

---

### 7. 常见问题

| 现象 | 处理 |
|------|------|
| 提示找不到 `python` | 改用 `py`、`python3`，或先配置好 PATH。 |
| 写 CSV 报错「权限被拒绝」 | 关闭 Excel 中打开的 `output` 里同名文件。 |
| 没有弹窗 | 正常；打开 **`output`** 文件夹里的 `.png`。 |
| Windows 下自动弹出资源管理器 | 设置环境变量 `OPEN_OUTPUT_FOLDER=0` 可关闭（仅 `plot_all_figures.py` 会尝试打开文件夹）。 |

---

## 数据文件说明（`--data-dir`）

**必需**（文件名固定）：

- `heatmap_overprivilege_rate.csv` — 行：统一权限类型；列：平台；单元格：0～1 小数。
- `heatmap_presence_by_platform.csv` — 同上；行/列可与前者不完全一致，程序按前者对齐，缺失填 0。

**可选**：

- `permission_frequency_stats.csv` — 列：`unified_category`, `occurrences`, `skills_covered`, `coverage_rate`
- `data_meta.json` — 例如 `{"total_skills": 100000}`
- `powerlaw.csv` — Fig.2（列名见 `figures_common.py` 中 `load_user_data_from_directory` 的文档字符串）
- `toxic_combos.csv` — Fig.3（列名见同上）

CSV 建议 UTF-8；Excel 可另存为「CSV UTF-8」。

---

## 文件一览

| 文件 | 作用 |
|------|------|
| `figures_common.py` | 共享逻辑与数据加载。**不要**当作主程序直接运行。 |
| `plot_fig1.py` | Fig.1 过度授权率热图 → `fig1_heatmap_overprivilege.png` |
| `plot_fig1b.py` | Fig.1b 出现占比热图 → `fig1b_heatmap_presence_by_platform.png` |
| `plot_fig2.py` | Fig.2 幂律曲线 → `fig2_powerlaw_redundancy.png` |
| `plot_fig3.py` | Fig.3 毒性组合条形图 → `fig3_toxic_combos.png` |
| `plot_all_figures.py` | 一次导出表 + 全部单图 + `dashboard_all_figures.png` |
| `sample_data/` | 示例 CSV |
| `requirements.txt` | 依赖列表 |

---

## 图与期刊风格

热图：Blues、白格线、正方形单元格；条形图：中性灰；折线图：深蓝 + 浅蓝带。字体 Arial/Helvetica。默认导出 DPI 300（可在 `figures_common.py` 中修改 `FIGURE_DPI`）。

---

## 许可证

与所在总仓库一致；若未指定，由项目维护者补充。
