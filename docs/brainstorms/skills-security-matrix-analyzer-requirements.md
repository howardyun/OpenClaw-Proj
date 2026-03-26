---
date: 2026-03-25
topic: skills-security-matrix-analyzer
---

# Skills Security Matrix Analyzer

## Problem Frame

现有 skill 生态中，skill 的公开描述、README、元数据所声明的能力，与其仓库代码实际实现的能力之间可能存在明显偏差。对于科研分析，这种偏差本身就是重要研究对象，因为它会影响用户对 skill 风险的理解、平台治理策略，以及后续安全审计的解释。

本项目要构建一个面向论文研究的分析器，对本地 `skills/` 文件夹中的 skill 进行批量分析，基于 `security matrix` 同时产出声明层分类、实现层分类，以及两者之间的偏差与风险映射结果。

## Requirements

- R1. 分析器必须以本地 skills 文件夹作为输入，不依赖 skills 的来源平台或 marketplace 信息才能运行。
- R2. 分析器必须对每个 skill 产出基于 `security matrix` 的声明层分类，优先依据 `SKILL.md` 的 YAML frontmatter 与正文，其次依据 skill 自带的 `references/` 等显式说明性材料进行判断。
- R3. 分析器必须对每个 skill 产出基于 `security matrix` 的实现层分类，依据仓库中的代码、脚本、配置、权限声明、工具调用痕迹和外部资源访问行为进行判断。
- R4. 分析器必须允许一个 skill 命中多个 `security matrix` 类别，而不是强制单标签归类。
- R5. 分析器必须为声明层和实现层的每个分类结果提供可解释证据，至少包括触发分类的文本、文件、代码模式或行为线索。
- R6. 分析器必须识别并输出声明层与实现层之间的偏差，至少覆盖“声明少于实现”“声明多于实现”“声明与实现基本一致”三类情况。
- R7. 分析器必须将分类结果映射到 `security matrix` 中对应的主要风险和控制要求，形成可用于论文分析的风险解释。
- R8. 分析器必须支持批量处理多个 skill，并输出适合后续统计分析的数据结果。
- R9. 分析器必须支持对单个 skill 导出案例级分析结果，以便论文中的 qualitative case study 使用。
- R10. 分析结果必须尽量可复查，支持研究者回溯每个结论所基于的证据来源。

## Success Criteria

- 可以对一个本地 skills 数据集稳定产出声明层分类、实现层分类、偏差标签和风险映射结果。
- 结果能够支持论文中的统计分析，例如不同能力类别分布、偏差比例、风险分布、控制要求覆盖情况。
- 结果能够支持论文中的案例分析，研究者可以快速查看某个 skill 被归类的原因和关键证据。
- 对同一 skill 的分析过程具备基本一致性和可复查性，不依赖人工记忆才能解释结果。

## Scope Boundaries

- 不要求第一版关注 skills 的来源站点、平台差异或 marketplace 去重逻辑。
- 不要求第一版直接做可视化 dashboard。
- 不要求第一版自动给出准入/封禁/放行等治理决策。
- 不要求第一版覆盖运行时动态执行或沙箱内真实行为观测；实现层可先基于静态仓库分析。
- 不要求第一版解决所有分类歧义；允许保留“不确定”或“需人工复核”的研究状态。

## Key Decisions

- 输入对象使用本地 skills 文件夹：避免绑定特定生态来源，更适合做统一研究分析。
- 采用双层分类：论文重点不是单纯归类，而是研究“声明能力”和“实现能力”的差异。
- 第一版做到风险映射但不做治理决策：这样既能支撑论文分析，也能避免项目范围过度膨胀。
- 分类框架以 `security matrix` 为主：确保研究结果能落到清晰的风险与控制语义上，而不是停留在通用功能标签。
- 支持多标签归类：skill 的能力和风险通常跨多个类别，单标签会损失研究信息。
- 声明层证据范围限定为 `SKILL.md`、其 YAML frontmatter 以及 skill 自带的 `references/` 等显式说明材料：避免把实现细节反向混入声明层判断。
- 第一版同时输出结构化表格数据和 JSON 结果：同时满足论文统计分析和案例级复查需求。

## Dependencies / Assumptions

- `analyzer/security matrix.md` 将作为当前分类框架的权威来源。
- skills 文件夹内通常包含足够的说明性材料与实现材料，足以支撑声明层和实现层分析。
- 后续规划阶段需要决定证据抽取、分类规则、输出格式和评估方法。

## Outstanding Questions

### Resolve Before Planning

- 无

### Deferred to Planning

- [Affects R3][Technical] 实现层分类应采用规则系统、启发式分析、LLM 辅助判定，还是组合式流程？
- [Affects R5][Needs research] 证据提取和引用粒度应如何设计，才能兼顾可解释性与批处理效率？
- [Affects R6][Needs research] 偏差标签是否需要更细粒度 taxonomy，例如“未声明高风险能力”“描述模糊导致低估”“实现残留能力”等？
- [Affects R7][Technical] 风险映射是直接继承 `security matrix` 的风险和控制要求，还是允许按证据强度做裁剪与加权？
- [Affects R8][Technical] 批处理结果的规范化 schema 应如何设计，便于统计分析和案例检索同时使用？
- [Affects R10][Needs research] 需要什么程度的人工标注或抽样复核，来验证分类器输出在论文中的可信度？

## Next Steps

→ /prompts:ce-plan for structured implementation planning
