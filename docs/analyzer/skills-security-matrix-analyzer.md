# Skills Security Matrix Analyzer

`skills_security_matrix` 是一个面向研究的本地离线分析器，用来扫描 `skills/` 语料目录，并把每个 skill 的声明层与实现层能力映射到仓库里的安全矩阵。

## Inputs

- `--skills-dir`：技能仓库顶层目录
- `--output-dir`：输出根目录，实际运行会创建 `run-<timestamp>` 子目录
- `--limit`：只分析前 N 个 skill
- `--format`：`json`、`csv` 或两者组合
- `--case-study-skill`：在运行摘要中标记一个重点复核对象
- `--fail-on-unknown-matrix`：为后续矩阵演进保留的严格模式开关
- `--include-hidden`：是否包含隐藏目录

## Outputs

每次运行都会产出：

- `skills.json` / `skills.csv`：skill 结构画像与基础元数据
- `classifications.json` / `classifications.csv`：声明层、实现层分类与证据
- `discrepancies.json` / `discrepancies.csv`：层间能力漂移与风险映射
- `run_manifest.json`：运行参数、计数和逐 skill 错误摘要
- `cases/<skill-id>.json`：适合论文 case study 的单 skill 全量证据视图

## Evidence Semantics

- 声明层只读取 `SKILL.md`、frontmatter，以及 `SKILL.md` 明确引用的支持材料。
- 实现层扫描代码、脚本和配置文件的静态信号，不把 `SKILL.md` 本体当作实现证据。
- 每条证据都保留 `source_path`、`layer`、`rule_id`、`line_start`、`matched_text` 等字段，方便手工抽查。
- 当声明或实现证据不足时，输出会保留 `insufficient_*` 状态，而不是强行对齐。

## Rule Writing Notes

- 规则按矩阵 category id 归一化，这样声明层和实现层可以直接比较。
- 优先增加高精度硬证据，再补低强度支持证据。
- 新规则应尽量返回可复核的文本片段，不要只返回抽象标签。
- 如果后续要提高语言感知精度，可以在当前模块边界内替换为 Tree-sitter 或 Semgrep 风格的规则引擎，而无需改 CLI 和导出层。

## Example

```bash
python main.py \
  --skills-dir skills \
  --output-dir outputs/skills_security_matrix \
  --format json,csv \
  --case-study-skill readonly-skill
```
