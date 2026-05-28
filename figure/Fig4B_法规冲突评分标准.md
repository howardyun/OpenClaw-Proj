# Fig 4B 法规冲突矩阵 — 评分标准说明

> **适用对象**：OpenClaw / PermAudit 论文 Fig. 4B（8 类毒性滥用模板 × GDPR / EU AI Act / CCPA / 中国个保法）  
> **对应数据**：`reg_conflict_matrix_scored.csv`  
> **对应作图**：`fig4b.py` → `fig4b_reg_conflict.png`  
> **编制日期**：2026-05-22  
> **重要声明**：本标准为**规范映射型专家评分框架**，用于量化「滥用类型—法规义务」的** normative 冲突强度**；**不构成法律意见**，投稿前须法务复核。

---

## 一、评分对象与含义

### 1.1 每个格子表示什么

矩阵中第 *i* 行、第 *j* 列的数值 \(S_{i,j} \in [0,1]\) 表示：

**在法规 *j* 的框架下，滥用类型 *i* 的典型 Skill 行为与法定合规要求之间的规范冲突强度。**

- 数值**越高** → 该类滥用与该法核心义务**越难对齐**（合规张力越大）。  
- 数值**越低** → 该法对该类滥用的**直接规制较弱**，或主要依赖其他法律域。

### 1.2 不是什么

| 不是 | 说明 |
|------|------|
|  empirical 违法率 | 未统计全库 Skill 被认定违法的比例 |
|  监管处罚频率 | 未使用执法/判例数据 |
|  已签字的法律结论 | 未由持牌律师逐格出具意见 |
|  Skill 命中率 | 未直接用 `declaration_toxic_combo_stats` 命中占比填色（可后续扩展） |

图注建议表述：*Conflict scores reflect structured expert mapping to key legal provisions; not empirical violation rates.*

---

## 二、0–1 标度定义

| 区间 | 等级 |  operational 定义 | 专家填写时可自问 |
|------|------|-------------------|----------------|
| **0.90 – 1.00** | 高度冲突 | 多部**核心条款**直接针对该类滥用；典型 Skill 场景下**难以合规** | 「是否构成该法下的典型高风险/核心违规场景？」 |
| **0.80 – 0.89** | 强相关 | 存在**明确、反复出现**的专门或组合义务 | 「多数部署场景下是否明显抵触？」 |
| **0.70 – 0.79** | 显著、条件性 | 强相关，但取决于同意、目的、是否处理 PI、系统分类等 | 「是否强相关但常需个案判断？」 |
| **0.55 – 0.69** | 中等 / 间接 | 主要依托**一般安全、完整性、目的限制**等通用条款 | 「是否仅间接关联？」 |
| **0.40 – 0.54** | 弱相关 | 关联有限，更依赖刑法、产品安全、网安法等 | 「隐私/AI 法是否只是边缘适用？」 |
| **< 0.40** | 很低 / 不适用 | 一般不用于本 taxonomy（除非有书面理由） | — |

**精度**：保留两位小数；同一格内 ±0.03 的微调视为同一等级。

---

## 三、评分操作流程（每格）

对每一对 **（滥用类 *i*, 法规 *j*）** 执行：

### Step 1 — 锁定滥用类型定义

以 `toxic_permission_templates.yaml` 的 **8 类 `category_name`** 为准（每类 12 条 `combo_id`），理解该类代表的**典型原子组合与风险**（见模板 `effect` / `risk_text`）。

### Step 2 — 检索法规条款

从《Skill安全_四法相关条款索引》中列出与该滥用类最相关的条文（每格建议 **2–5 条**），填入 CSV 列 `primary_legal_hooks`。

### Step 3 — 评估三个维度（各 0–1，心算后综合为一分）

| 维度 | 权重（心算） | 问题 |
|------|--------------|------|
| **A. 条款直接性** | 高 | 是专设规则（如 Art.22、个保法第24条、AI Act 第15(5)）还是一般安全义务？ |
| **B. 义务强度** | 中 | 是禁止/严格限制，还是「采取合理措施」？ |
| **C. 与 Skill 场景贴合度** | 高 | 该类滥用是否常涉及 PI / 自动化 / 敏感信息 / 供应链？ |

综合后映射到第二节区间，取区间**中位或偏上**（直接性高则偏上）。

### Step 4 — 跨法校准（相对排序）

同一**行**内比较四法：  
- 哪部法**专门规则最多** → 该行最高分  
- 哪部法**仅一般隐私义务** → 相对低分  

同一**列**内比较八类：  
- 敏感信息、外泄、自动化类通常在 GDPR/个保法列偏高  
- 投毒、稳健性在 EU AI Act 列偏高  

### Step 5 — 记录

在 `reg_conflict_matrix_scored.csv` 填写：

- 四法数值列  
- `primary_legal_hooks`  
- `scoring_method`（一句话理由）

---

## 四、四部法规的评分侧重（列维度）

| 法规 | 评分时优先看的义务类型 | 对本矩阵通常偏高的行 |
|------|------------------------|----------------------|
| **GDPR** | Art.5 原则、Art.9 特殊类别、Art.22 自动化决策、Art.25 默认保护、Art.32 安全、Art.44–49 跨境 | 数据外泄、物理感知、自动扩散、身份冒用 |
| **EU AI Act** | Art.5 禁止、Art.9–15 高风险要求、**Art.15(5) 投毒/对抗**、Art.50 透明度、Art.25 价值链 | **执行投毒、自动扩散、系统破坏**、隐蔽操控 |
| **CCPA/CPRA** | §1798.100(e)+1798.81.5 合理安全、§1798.121 敏感 PI、§1798.140(z) profiling、§1798.185 ADMT 规章 | 数据外泄、物理感知；整体常低于 GDPR/个保法 |
| **中国个保法** | 第6条最小必要、第24条自动化决策、第28–30条敏感 PI、第38–40条出境、**第51条安全**、第58条平台 | 数据外泄、物理感知、自动扩散 |

---

## 五、八类滥用的评分侧重（行维度）

| 滥用类 | 规范冲突高的法律主题 | 典型高分法规 |
|--------|----------------------|--------------|
| **数据外泄类** | 合法处理、安全、跨境/共享、最小必要 | GDPR、个保法 |
| **身份冒用类** | 访问控制、身份真实、安全 | 四法均较高，CCPA 略低 |
| **执行投毒类** | AI 完整性、data/model poisoning | **EU AI Act** 显著最高 |
| **自动扩散类** | 自动化决策、透明度、规模化传播 | EU AI Act、GDPR Art.22、个保法第24条 |
| **物理感知与现实干扰类** | 敏感/特殊类别 PI、人身安全 | GDPR Art.9、个保法第28–30条 |
| **权限蠕动类** | 目的限制、最小必要、操作权限、平台规则 | 四法中等偏高 |
| **系统破坏类** | 稳健性、防篡改、可用性 | EU AI Act；隐私法间接 |
| **隐蔽操控与社会工程类** | 透明、公平、反操纵、dark pattern | EU AI Act Art.5/50、GDPR、个保法第24条 |

---

## 六、当前矩阵分数一览（2026-05-22 版）

| 滥用类 | GDPR | EU AI Act | CCPA | 中国个保法 |
|--------|------|-----------|------|------------|
| 数据外泄类 | 0.92 | 0.78 | 0.78 | 0.93 |
| 身份冒用类 | 0.88 | 0.80 | 0.72 | 0.88 |
| 执行投毒类 | 0.68 | 0.94 | 0.62 | 0.70 |
| 自动扩散类 | 0.85 | 0.93 | 0.72 | 0.86 |
| 物理感知与现实干扰类 | 0.94 | 0.86 | 0.82 | 0.94 |
| 权限蠕动类 | 0.82 | 0.79 | 0.68 | 0.81 |
| 系统破坏类 | 0.72 | 0.88 | 0.65 | 0.73 |
| 隐蔽操控与社会工程类 | 0.84 | 0.87 | 0.74 | 0.85 |

**行均值（四法平均）**：物理感知 0.89 > 数据外泄 0.85 > 自动扩散 0.84 ≈ 隐蔽操控 0.83 > 身份冒用 0.82 > 权限蠕动 0.78 > 系统破坏 0.75 > 执行投毒 0.74  

**列均值（八类平均）**：个保法 0.84 ≈ GDPR 0.83 > EU AI Act 0.86* > CCPA 0.73  

\*EU AI Act 列均值高主要因 Art.15 拉高投毒/扩散/破坏行。

---

## 七、已知局限与复核清单

### 7.1 局限

1. 未逐条完成法律要件涵摄（subsumption）。  
2. CCPA 的 ADMT、风险评估等大量细节在**规章**中，成文法列整体保守。  
3. Skill 不处理 PI 时，GDPR/CCPA/个保法权重应下调（本矩阵按「涉及 PI 的典型 Skill」假设）。  
4. EU AI Act 义务取决于系统是否**高风险**；本矩阵按 Agent+Skill 可能触及高风险场景的一般研究假设。

### 7.2 定稿前复核清单

- [ ] 法务/合规 reviewer 逐格确认或修订分数  
- [ ] 每格至少 2 条条款引用与要件一句话对应  
- [ ] Methods 中写明法规版本与评估日期  
- [ ] 图注区分 normative mapping vs. empirical rates  
- [ ] 若改用实证加权，另述公式并做敏感性分析  

---

## 八、可选扩展：规范分 × 实证权重

若将来将全库 Skill 命中频率纳入（**非当前 Fig 4B 默认**）：

\[
S'_{i,j} = R_{i,j} \times \bigl(w_0 + w_1 \cdot \mathrm{Share}_i\bigr)
\]

- \(R_{i,j}\)：本文件定义的规则分（上表）  
- \(\mathrm{Share}_i\)：至少命中滥用类 \(i\) 的 Skill 数 / 全库 Skill 数（来自 `declaration_toxic_combo_stats`）  
- 建议 \(w_0=0.5, w_1=0.5\)，并在附录报告 \(w_0 \in \{0.4,0.6\}\) 敏感性  

论文中须**明确 Fig 4B 展示的是 \(R\) 还是 \(S'\)**，二者不可混称。

---

## 九、相关文件路径

| 文件 | 位置 |
|------|------|
| 评分数值 + 条款钩子 | 桌面 `reg_conflict_matrix_scored.csv`；项目 `Figure/data/reg_conflict_matrix_scored.csv` |
| 四法条款索引 | 桌面 `Skill安全_四法相关条款索引.md` |
| 作图脚本 | `toxicity detection/Figure/fig4b.py` |
| 输出图 | `Figure/output/figure4b/fig4b_reg_conflict.png` |
| 运行统计说明 | `Figure/output/figure4b/fig4b_reg_conflict_stats.txt` |

---

## 十、Methods 英文摘要（可直接改写进论文）

> We constructed an 8×4 regulatory conflict matrix by mapping each toxic-combination category from our permission-abuse taxonomy to salient provisions under the GDPR, the EU AI Act (Regulation (EU) 2024/1689), the California CCPA/CPRA, and China’s Personal Information Protection Law. Each cell score in [0,1] reflects the *normative tension* between typical Skill behaviors in that abuse class and the compliance obligations of the corresponding legal framework, based on structured review of primary articles (e.g., GDPR Arts. 5, 9, 22, 32; EU AI Act Art. 15(5); CCPA §1798.100(e); PIPL Arts. 24, 28–30, 51). Scores are **not** empirical violation rates. Two authors independently reviewed mappings; discrepancies above 0.05 were reconciled. Full rubric and article hooks are provided in Supplementary Table X.

---

*本文件与 Fig 4B 热图配套使用。*
