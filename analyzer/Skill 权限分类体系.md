## <font style="color:rgb(31, 31, 31);">1. 顶层分层框架 </font>
<font style="color:rgb(31, 31, 31);">按照“感知、交互、管控、代理”四个维度进行层级划分，确保涵盖 Agent 从基础信息读取到全自动身份代理的全生命周期风险。</font>

| **<font style="color:rgb(31, 31, 31);">风险层级 (Tier)</font>** | **<font style="color:rgb(31, 31, 31);">核心定义 (Nature)</font>** | **<font style="color:rgb(31, 31, 31);">包含的原子类</font>** | **<font style="color:rgb(31, 31, 31);">层级解释</font>** | **<font style="color:rgb(31, 31, 31);">通俗解释</font>** |
| --- | --- | --- | --- | --- |
| **<font style="color:rgb(31, 31, 31);">Tier 1: 资源感知层</font>** | **<font style="color:rgb(31, 31, 31);">“它能拿到什么？”</font>** | **<font style="color:rgb(31, 31, 31);">R, Q, S</font>** | **<font style="color:rgb(31, 31, 31);">本层是 Agent 能力的入口。它决定了 Agent 能够获取多少关于用户和环境的静态或实时信息。治理的核心在于“知情权”与“最小化”，防止 Agent 在用户无感的情况下过度采集隐私，或通过传感器进行侧信道监听。</font>** | <font style="color:rgb(31, 31, 31);">获取会话上下文、用户数据资产及硬件传感器数据。</font> |
| **<font style="color:rgb(31, 31, 31);">Tier 2: 交互通信层</font>** | **<font style="color:rgb(31, 31, 31);">“它能传往何处？”</font>** | **<font style="color:rgb(31, 31, 31);">W, U, C</font>** | **<font style="color:rgb(31, 31, 31);">本层是 Agent 数据的出口及与物理界面的交互。它决定了数据会传向何处，以及 Agent 是否能像真实用户一样操作界面。治理的核心在于“流向受控”与“视觉真实”，防止数据被非法外传，或 Agent 通过模拟点击进行隐蔽的转账、订购等违规行为。</font>** | <font style="color:rgb(31, 31, 31);">涉及数据出网、信息外发、以及通过 UI 进行模拟操作。</font> |
| **<font style="color:rgb(31, 31, 31);">Tier 3: 环境管控层</font>** | **<font style="color:rgb(31, 31, 31);">“它能做什么？”</font>** | **<font style="color:rgb(31, 31, 31);">X, G, O, K</font>** | **<font style="color:rgb(31, 31, 31);">本层代表了 Agent 对宿主系统及其逻辑的控制权力。它不仅能产生内容，还能修改系统结构、运行复杂逻辑。治理的核心在于“沙箱隔离”，确保 Agent 的代码执行在受限空间内，且对系统的任何持久化改动都必须是可追溯、可撤销的。</font>** | <font style="color:rgb(31, 31, 31);">执行代码/命令，生成内容，修改系统配置及应用管理。</font> |
| **<font style="color:rgb(31, 31, 31);">Tier 4: 代理协同层</font>** | **<font style="color:rgb(31, 31, 31);">“它代表谁？”</font>** | **<font style="color:rgb(31, 31, 31);">A, I</font>** | **<font style="color:rgb(31, 31, 31);">本层是 Agent 权限链的顶端，涉及主体责任和长期运行。它定义了 Agent 是否能自主决策、是否代表用户身份。治理的核心在于“身份穿透”，防止 Agent 在无人值守时产生规模化负面影响，或在多系统间进行权限蠕动。</font>** | <font style="color:rgb(31, 31, 31);">处理跨系统身份继承、自动化触发、全自动决策链。</font> |


## <font style="color:rgb(31, 31, 31);">2. 原子能力细化清单 </font>
### <font style="color:rgb(31, 31, 31);">Tier 1: 资源感知层 </font>
#### <font style="color:rgb(31, 31, 31);">3.1 读取类 R </font>
| **<font style="color:rgb(31, 31, 31);">原子ID</font>** | **<font style="color:rgb(31, 31, 31);">原子能力</font>** | **<font style="color:rgb(31, 31, 31);">通俗解释</font>** | **<font style="color:rgb(31, 31, 31);">关键风险</font>** | **<font style="color:rgb(31, 31, 31);">必要控制</font>** |
| --- | --- | --- | --- | --- |
| <font style="color:rgb(31, 31, 31);">R1</font> | <font style="color:rgb(31, 31, 31);">读取当前用户输入</font> | <font style="color:rgb(31, 31, 31);">读取当前 prompt / input</font> | <font style="color:rgb(31, 31, 31);">信息泄露、输入污染</font> | <font style="color:rgb(31, 31, 31);">最小化读取、脱敏</font> |
| <font style="color:rgb(31, 31, 31);">R2</font> | <font style="color:rgb(31, 31, 31);">读取当前会话历史</font> | <font style="color:rgb(31, 31, 31);">读取当前对话上下文</font> | <font style="color:rgb(31, 31, 31);">敏感上下文暴露、跨轮拼接</font> | <font style="color:rgb(31, 31, 31);">最小化读取、留痕</font> |
| <font style="color:rgb(31, 31, 31);">R3</font> | <font style="color:rgb(31, 31, 31);">读取历史会话</font> | <font style="color:rgb(31, 31, 31);">跨会话读取历史记录</font> | <font style="color:rgb(31, 31, 31);">长时记忆泄露、越权读取</font> | <font style="color:rgb(31, 31, 31);">按需授权、时间窗限制</font> |
| <font style="color:rgb(31, 31, 31);">R4</font> | <font style="color:rgb(31, 31, 31);">读取会话附件</font> | <font style="color:rgb(31, 31, 31);">读取当前会话上传文件</font> | <font style="color:rgb(31, 31, 31);">附件敏感信息泄露</font> | <font style="color:rgb(31, 31, 31);">附件范围限制、敏感扫描</font> |
| <font style="color:rgb(31, 31, 31);">R5</font> | <font style="color:rgb(31, 31, 31);">读取本地 repo 文件</font> | <font style="color:rgb(31, 31, 31);">读项目目录内文件</font> | <font style="color:rgb(31, 31, 31);">内部代码/配置暴露</font> | <font style="color:rgb(31, 31, 31);">路径范围限制</font> |
| <font style="color:rgb(31, 31, 31);">R6</font> | <font style="color:rgb(31, 31, 31);">读取本地任意路径文件</font> | <font style="color:rgb(31, 31, 31);">读 repo 外或绝对路径</font> | <font style="color:rgb(31, 31, 31);">越权读系统文件</font> | <font style="color:rgb(31, 31, 31);">目录白名单</font> |
| <font style="color:rgb(31, 31, 31);">R7</font> | <font style="color:rgb(31, 31, 31);">读取知识库或文档库</font> | <font style="color:rgb(31, 31, 31);">读 KB、Docs、Drive 等</font> | <font style="color:rgb(31, 31, 31);">内部资料越权读取</font> | <font style="color:rgb(31, 31, 31);">文档级授权、审计</font> |
| <font style="color:rgb(31, 31, 31);">R8</font> | <font style="color:rgb(31, 31, 31);">读取连接器数据</font> | <font style="color:rgb(31, 31, 31);">读 Gmail、Slack、GitHub 等</font> | <font style="color:rgb(31, 31, 31);">连接器越权</font> | <font style="color:rgb(31, 31, 31);">分系统授权</font> |
| <font style="color:rgb(31, 31, 31);">R9</font> | <font style="color:rgb(31, 31, 31);">批量枚举文件或资源</font> | <font style="color:rgb(31, 31, 31);">列举大量文件/对象</font> | <font style="color:rgb(31, 31, 31);">批量抽取、资源扫描</font> | <font style="color:rgb(31, 31, 31);">分页、条数上限</font> |
| <font style="color:rgb(31, 31, 31);">R10</font> | <font style="color:rgb(31, 31, 31);">跨源数据拼接读取</font> | <font style="color:rgb(31, 31, 31);">合并会话、文件、连接器、网页数据</font> | <font style="color:rgb(31, 31, 31);">拼接泄露、隐私扩展</font> | <font style="color:rgb(31, 31, 31);">跨源拼接告警</font> |


#### <font style="color:rgb(31, 31, 31);">3.2 查询类 Q </font>
| **<font style="color:rgb(31, 31, 31);">原子ID</font>** | **<font style="color:rgb(31, 31, 31);">原子能力</font>** | **<font style="color:rgb(31, 31, 31);">通俗解释</font>** | **<font style="color:rgb(31, 31, 31);">关键风险</font>** | **<font style="color:rgb(31, 31, 31);">必要控制</font>** |
| --- | --- | --- | --- | --- |
| <font style="color:rgb(31, 31, 31);">Q1</font> | <font style="color:rgb(31, 31, 31);">只读查询或搜索</font> | <font style="color:rgb(31, 31, 31);">search/query/filter/list</font> | <font style="color:rgb(31, 31, 31);">敏感信息暴露</font> | <font style="color:rgb(31, 31, 31);">只读约束、范围限制</font> |
| <font style="color:rgb(31, 31, 31);">Q2</font> | <font style="color:rgb(31, 31, 31);">结构化筛选与聚合</font> | <font style="color:rgb(31, 31, 31);">select/group/aggregate</font> | <font style="color:rgb(31, 31, 31);">结果过量暴露</font> | <font style="color:rgb(31, 31, 31);">最小化结果</font> |
| <font style="color:rgb(31, 31, 31);">Q3</font> | <font style="color:rgb(31, 31, 31);">敏感对象查询</font> | <font style="color:rgb(31, 31, 31);">查邮件、日历、联系人、工单</font> | <font style="color:rgb(31, 31, 31);">高敏对象信息暴露</font> | <font style="color:rgb(31, 31, 31);">字段遮蔽、按对象授权</font> |
| <font style="color:rgb(31, 31, 31);">Q4</font> | <font style="color:rgb(31, 31, 31);">自动推荐或判定</font> | <font style="color:rgb(31, 31, 31);">根据查询结果给建议、分类</font> | <font style="color:rgb(31, 31, 31);">错误推荐、错误决策</font> | <font style="color:rgb(31, 31, 31);">来源标注、人工复核</font> |


#### <font style="color:rgb(31, 31, 31);">3.3 系统感知类 S</font>
| **<font style="color:rgb(31, 31, 31);">原子ID</font>** | **<font style="color:rgb(31, 31, 31);">原子能力</font>** | **<font style="color:rgb(31, 31, 31);">通俗解释</font>** | **<font style="color:rgb(31, 31, 31);">关键风险</font>** | **<font style="color:rgb(31, 31, 31);">必要控制</font>** |
| --- | --- | --- | --- | --- |
| <font style="color:rgb(31, 31, 31);">S1</font> | <font style="color:rgb(31, 31, 31);">硬件摄像头调用</font> | <font style="color:rgb(31, 31, 31);">拍照或录制实时画面</font> | <font style="color:rgb(31, 31, 31);">隐私泄露、环境监控</font> | <font style="color:rgb(31, 31, 31);">运行时授权、状态提示</font> |
| <font style="color:rgb(31, 31, 31);">S2</font> | <font style="color:rgb(31, 31, 31);">硬件麦克风调用</font> | <font style="color:rgb(31, 31, 31);">录制实时语音或环境音</font> | <font style="color:rgb(31, 31, 31);">敏感谈话监听</font> | <font style="color:rgb(31, 31, 31);">运行时授权、录音标识</font> |
| <font style="color:rgb(31, 31, 31);">S3</font> | <font style="color:rgb(31, 31, 31);">生物特征识别访问</font> | <font style="color:rgb(31, 31, 31);">获取指纹/人脸识别校验结果</font> | <font style="color:rgb(31, 31, 31);">身份认证凭证滥用</font> | <font style="color:rgb(31, 31, 31);">仅限本地校验结果</font> |
| <font style="color:rgb(31, 31, 31);">S4</font> | <font style="color:rgb(31, 31, 31);">精确地理位置获取</font> | <font style="color:rgb(31, 31, 31);">获取当前 GPS/经纬度</font> | <font style="color:rgb(31, 31, 31);">轨迹跟踪、现实生活干扰</font> | <font style="color:rgb(31, 31, 31);">仅限当前位置、脱敏处理</font> |
| <font style="color:rgb(31, 31, 31);">S5</font> | <font style="color:rgb(31, 31, 31);">后台位置持续追踪</font> | <font style="color:rgb(31, 31, 31);">在非活跃状态下监听位置变化</font> | <font style="color:rgb(31, 31, 31);">长期轨迹泄露</font> | <font style="color:rgb(31, 31, 31);">强审计、通知提醒</font> |
| <font style="color:rgb(31, 31, 31);">S6</font> | <font style="color:rgb(31, 31, 31);">扫描附近硬件设备</font> | <font style="color:rgb(31, 31, 31);">扫描蓝牙、NFC、WiFi 设备</font> | <font style="color:rgb(31, 31, 31);">物理边界穿透、侧信道风险</font> | <font style="color:rgb(31, 31, 31);">范围限制、白名单</font> |
| <font style="color:rgb(31, 31, 31);">S7</font> | <font style="color:rgb(31, 31, 31);">系统状态读取</font> | <font style="color:rgb(31, 31, 31);">读系统日志、属性、运行参数</font> | <font style="color:rgb(31, 31, 31);">暴露系统脆弱性</font> | <font style="color:rgb(31, 31, 31);">权限受限读取</font> |


### <font style="color:rgb(31, 31, 31);">Tier 2: 交互通信层 </font>
#### <font style="color:rgb(31, 31, 31);">3.4 外部访问类 W </font>
| **<font style="color:rgb(31, 31, 31);">原子ID</font>** | **<font style="color:rgb(31, 31, 31);">原子能力</font>** | **<font style="color:rgb(31, 31, 31);">通俗解释</font>** | **<font style="color:rgb(31, 31, 31);">关键风险</font>** | **<font style="color:rgb(31, 31, 31);">必要控制</font>** |
| --- | --- | --- | --- | --- |
| <font style="color:rgb(31, 31, 31);">W1</font> | <font style="color:rgb(31, 31, 31);">访问公开网页</font> | <font style="color:rgb(31, 31, 31);">浏览网页、抓取网页内容</font> | <font style="color:rgb(31, 31, 31);">恶意内容、内容污染</font> | <font style="color:rgb(31, 31, 31);">域名白名单</font> |
| <font style="color:rgb(31, 31, 31);">W2</font> | <font style="color:rgb(31, 31, 31);">调用外部公开 API</font> | <font style="color:rgb(31, 31, 31);">调 REST/API/SDK</font> | <font style="color:rgb(31, 31, 31);">不可信返回、字段泄露</font> | <font style="color:rgb(31, 31, 31);">API 白名单</font> |
| <font style="color:rgb(31, 31, 31);">W3</font> | <font style="color:rgb(31, 31, 31);">下载外部文件</font> | <font style="color:rgb(31, 31, 31);">下载外部文件到本地</font> | <font style="color:rgb(31, 31, 31);">恶意文件、内容污染</font> | <font style="color:rgb(31, 31, 31);">类型限制、恶意扫描</font> |
| <font style="color:rgb(31, 31, 31);">W4</font> | <font style="color:rgb(31, 31, 31);">使用搜索驱动后续动作</font> | <font style="color:rgb(31, 31, 31);">根据网页结果直接计划动作</font> | <font style="color:rgb(31, 31, 31);">外部信息驱动高权限动作</font> | <font style="color:rgb(31, 31, 31);">人工复核</font> |


#### **3.5 UI 模拟交互类 U (New)**
| **原子ID** | **原子能力** | **通俗解释** | **关键风险** | **必要控制** |
| --- | --- | --- | --- | --- |
| U1 | 屏幕内容捕获 | 录屏或截取 UI 画面 | 界面数据泄露 | 视觉遮蔽 |
| U2 | 模拟 UI 操作控制 | 模拟点击、滑动、表单输入 | 自动执行高敏动作 | 前台回显 |
| U3 | 系统剪贴板读写 | 读写剪贴板内容 | 验证码/凭证截获 | 读前确认 |
| U4 | 键盘输入消费 | 拦截或监听按键 | 账户窃取 | 禁用高敏键 |


#### <font style="color:rgb(31, 31, 31);">3.6 实时通信类 C </font>
| 原子ID | 原子能力 | 通俗解释 | 关键风险 | 必要控制 |
| --- | --- | --- | --- | --- |
| **C1** | 多媒体输出控制 | 控制音量、屏幕亮度、投屏 | 物理干扰、数据投屏外泄 | 仅限当前活跃应用 |
| **C2** | 外发消息或通知 | 发 Push 通知、站内信、短信 | 骚扰/钓鱼扩散、资费损耗 | 发送前预览、频率限制 |
| **C3** | 邮件/IM 发送 | 代用户发 Email、Slack、微信 | 冒充用户身份、信誉受损 | 身份二次确认、脱敏校验 |
| **C4** | 实时流数据上传 | 将数据流持续推送外部端点 | 静默数据外传、隐私监控 | 流量异常检测、状态提示 |
| **C5** | 双向实时通道建立 | WebSocket/SSE 建立持久连接 | 被远程持续控制（肉鸡化） | 终端白名单、长连接超时 |


### <font style="color:rgb(31, 31, 31);">Tier 3: 环境管控层 </font>
#### <font style="color:rgb(31, 31, 31);">3.7 执行类 X </font>
| **<font style="color:rgb(31, 31, 31);">原子ID</font>** | **<font style="color:rgb(31, 31, 31);">原子能力</font>** | **<font style="color:rgb(31, 31, 31);">通俗解释</font>** | **<font style="color:rgb(31, 31, 31);">关键风险</font>** | **<font style="color:rgb(31, 31, 31);">必要控制</font>** |
| --- | --- | --- | --- | --- |
| <font style="color:rgb(31, 31, 31);">X1</font> | <font style="color:rgb(31, 31, 31);">执行 shell 命令</font> | <font style="color:rgb(31, 31, 31);">bash/sh/exec/spawn</font> | <font style="color:rgb(31, 31, 31);">命令滥用、越权执行</font> | <font style="color:rgb(31, 31, 31);">沙箱、命令白名单</font> |
| <font style="color:rgb(31, 31, 31);">X2</font> | <font style="color:rgb(31, 31, 31);">执行解释器代码</font> | <font style="color:rgb(31, 31, 31);">python/node 运行代码</font> | <font style="color:rgb(31, 31, 31);">数据泄露、资源滥用</font> | <font style="color:rgb(31, 31, 31);">沙箱、依赖限制</font> |
| <font style="color:rgb(31, 31, 31);">X3</font> | <font style="color:rgb(31, 31, 31);">执行容器任务</font> | <font style="color:rgb(31, 31, 31);">docker/container/job</font> | <font style="color:rgb(31, 31, 31);">扩大执行面</font> | <font style="color:rgb(31, 31, 31);">镜像白名单</font> |
| <font style="color:rgb(31, 31, 31);">X4</font> | <font style="color:rgb(31, 31, 31);">安装依赖或拉包</font> | <font style="color:rgb(31, 31, 31);">pip/npm/apt 等</font> | <font style="color:rgb(31, 31, 31);">恶意依赖包</font> | <font style="color:rgb(31, 31, 31);">源白名单、锁版本</font> |
| <font style="color:rgb(31, 31, 31);">X5</font> | <font style="color:rgb(31, 31, 31);">执行环境可联网</font> | <font style="color:rgb(31, 31, 31);">代码运行同时能上网</font> | <font style="color:rgb(31, 31, 31);">出网泄露</font> | <font style="color:rgb(31, 31, 31);">高敏任务禁网</font> |
| <font style="color:rgb(31, 31, 31);">X6</font> | <font style="color:rgb(31, 31, 31);">写文件系统</font> | <font style="color:rgb(31, 31, 31);">能修改本地文件</font> | <font style="color:rgb(31, 31, 31);">篡改、数据落地</font> | <font style="color:rgb(31, 31, 31);">路径白名单</font> |
| <font style="color:rgb(31, 31, 31);">X7</font> | <font style="color:rgb(31, 31, 31);">访问环境变量</font> | <font style="color:rgb(31, 31, 31);">读取 env/secret/token</font> | <font style="color:rgb(31, 31, 31);">凭证泄露</font> | <font style="color:rgb(31, 31, 31);">密钥隔离</font> |
| <font style="color:rgb(31, 31, 31);">X8</font> | <font style="color:rgb(31, 31, 31);">调用本地工具</font> | <font style="color:rgb(31, 31, 31);">git/docker/curl/CLI</font> | <font style="color:rgb(31, 31, 31);">工具滥用</font> | <font style="color:rgb(31, 31, 31);">工具白名单</font> |


#### <font style="color:rgb(31, 31, 31);">3.8 生成与写入类 G / O </font>
| **<font style="color:rgb(31, 31, 31);">原子ID</font>** | **<font style="color:rgb(31, 31, 31);">原子能力</font>** | **<font style="color:rgb(31, 31, 31);">通俗解释</font>** | **<font style="color:rgb(31, 31, 31);">关键风险</font>** | **<font style="color:rgb(31, 31, 31);">必要控制</font>** |
| --- | --- | --- | --- | --- |
| <font style="color:rgb(31, 31, 31);">G1</font> | <font style="color:rgb(31, 31, 31);">生成文本建议</font> | <font style="color:rgb(31, 31, 31);">只输出建议，不落地</font> | <font style="color:rgb(31, 31, 31);">误建议</font> | <font style="color:rgb(31, 31, 31);">来源标注</font> |
| <font style="color:rgb(31, 31, 31);">G2</font> | <font style="color:rgb(31, 31, 31);">生成结构化草稿</font> | <font style="color:rgb(31, 31, 31);">邮件/表单预填</font> | <font style="color:rgb(31, 31, 31);">带错对象</font> | <font style="color:rgb(31, 31, 31);">目标确认</font> |
| <font style="color:rgb(31, 31, 31);">G3</font> | <font style="color:rgb(31, 31, 31);">写本地临时文件</font> | <font style="color:rgb(31, 31, 31);">生成 report/cache</font> | <font style="color:rgb(31, 31, 31);">敏感数据落地</font> | <font style="color:rgb(31, 31, 31);">输出脱敏</font> |
| <font style="color:rgb(31, 31, 31);">G4</font> | <font style="color:rgb(31, 31, 31);">写本地项目文件</font> | <font style="color:rgb(31, 31, 31);">修改工作区文件</font> | <font style="color:rgb(31, 31, 31);">错改代码</font> | <font style="color:rgb(31, 31, 31);">diff 预览</font> |
| <font style="color:rgb(31, 31, 31);">G5</font> | <font style="color:rgb(31, 31, 31);">批量本地写文件</font> | <font style="color:rgb(31, 31, 31);">多文件批量修改</font> | <font style="color:rgb(31, 31, 31);">大范围破坏</font> | <font style="color:rgb(31, 31, 31);">数量上限</font> |
| <font style="color:rgb(31, 31, 31);">O1</font> | <font style="color:rgb(31, 31, 31);">创建外部草稿</font> | <font style="color:rgb(31, 31, 31);">在外部系统保存 draft</font> | <font style="color:rgb(31, 31, 31);">对象错误</font> | <font style="color:rgb(31, 31, 31);">仅草稿、回显</font> |
| <font style="color:rgb(31, 31, 31);">O2</font> | <font style="color:rgb(31, 31, 31);">外部单对象写入</font> | <font style="color:rgb(31, 31, 31);">创建/更新一个对象</font> | <font style="color:rgb(31, 31, 31);">误修改、不可逆影响</font> | <font style="color:rgb(31, 31, 31);">显式确认、预览</font> |
| <font style="color:rgb(31, 31, 31);">O3</font> | <font style="color:rgb(31, 31, 31);">外部多对象批量写入</font> | <font style="color:rgb(31, 31, 31);">批量更新多个对象</font> | <font style="color:rgb(31, 31, 31);">规模化错误</font> | <font style="color:rgb(31, 31, 31);">条数上限、dry-run</font> |
| <font style="color:rgb(31, 31, 31);">O4</font> | <font style="color:rgb(31, 31, 31);">破坏性写入</font> | <font style="color:rgb(31, 31, 31);">delete/archive/reset</font> | <font style="color:rgb(31, 31, 31);">彻底丢失数据</font> | <font style="color:rgb(31, 31, 31);">双确认、回滚</font> |
| <font style="color:rgb(31, 31, 31);">O5</font> | <font style="color:rgb(31, 31, 31);">自动外发</font> | <font style="color:rgb(31, 31, 31);">自动 send/publish/post</font> | <font style="color:rgb(31, 31, 31);">误发、敏感扩散</font> | <font style="color:rgb(31, 31, 31);">发送前确认</font> |


#### <font style="color:rgb(31, 31, 31);">3.9 系统底层管控类 K (new)</font>
| **<font style="color:rgb(31, 31, 31);">原子ID</font>** | **<font style="color:rgb(31, 31, 31);">原子能力</font>** | **<font style="color:rgb(31, 31, 31);">通俗解释</font>** | **<font style="color:rgb(31, 31, 31);">关键风险</font>** | **<font style="color:rgb(31, 31, 31);">必要控制</font>** |
| --- | --- | --- | --- | --- |
| <font style="color:rgb(31, 31, 31);">K1</font> | <font style="color:rgb(31, 31, 31);">修改系统级设置</font> | <font style="color:rgb(31, 31, 31);">修改安全、全局设置</font> | <font style="color:rgb(31, 31, 31);">环境劫持、安全性降低</font> | <font style="color:rgb(31, 31, 31);">权限隔离、变更确认</font> |
| <font style="color:rgb(31, 31, 31);">K2</font> | <font style="color:rgb(31, 31, 31);">硬件开关控制</font> | <font style="color:rgb(31, 31, 31);">控制 WiFi/蓝牙/红外开关</font> | <font style="color:rgb(31, 31, 31);">物理链路风险、非授权扫描</font> | <font style="color:rgb(31, 31, 31);">状态回显、开关锁</font> |
| <font style="color:rgb(31, 31, 31);">K3</font> | <font style="color:rgb(31, 31, 31);">应用程序管理</font> | <font style="color:rgb(31, 31, 31);">安装、卸载其他应用程序</font> | <font style="color:rgb(31, 31, 31);">预装恶意软件、破坏功能</font> | <font style="color:rgb(31, 31, 31);">用户强确认、安装源白名单</font> |
| <font style="color:rgb(31, 31, 31);">K4</font> | <font style="color:rgb(31, 31, 31);">闹钟与唤醒管理</font> | <font style="color:rgb(31, 31, 31);">设置闹钟、申请唤醒锁</font> | <font style="color:rgb(31, 31, 31);">资源滥用、隐蔽自动执行</font> | <font style="color:rgb(31, 31, 31);">频率限制、异常监控</font> |
| <font style="color:rgb(31, 31, 31);">K5</font> | <font style="color:rgb(31, 31, 31);">进程强制管控</font> | <font style="color:rgb(31, 31, 31);">终止或重启其他应用进程</font> | <font style="color:rgb(31, 31, 31);">业务中断、静默干扰</font> | <font style="color:rgb(31, 31, 31);">权限限制、进程白名单</font> |
| <font style="color:rgb(31, 31, 31);">K6</font> | <font style="color:rgb(31, 31, 31);">全局环境配置修改</font> | <font style="color:rgb(31, 31, 31);">修改系统语言、字体等</font> | <font style="color:rgb(31, 31, 31);">逻辑混淆、使用障碍</font> | <font style="color:rgb(31, 31, 31);">操作回显</font> |


### <font style="color:rgb(31, 31, 31);">Tier 4: 代理协同层 (身份与自主)</font>
#### <font style="color:rgb(31, 31, 31);">3.10 自动化与身份代理类 A / I </font>
| **<font style="color:rgb(31, 31, 31);">原子ID</font>** | **<font style="color:rgb(31, 31, 31);">原子能力</font>** | **<font style="color:rgb(31, 31, 31);">通俗解释</font>** | **<font style="color:rgb(31, 31, 31);">关键风险</font>** | **<font style="color:rgb(31, 31, 31);">必要控制</font>** |
| --- | --- | --- | --- | --- |
| <font style="color:rgb(31, 31, 31);">A1</font> | <font style="color:rgb(31, 31, 31);">用户显式单次触发</font> | <font style="color:rgb(31, 31, 31);">仅在当前指令下执行</font> | <font style="color:rgb(31, 31, 31);">单次误操作</font> | <font style="color:rgb(31, 31, 31);">默认模式</font> |
| <font style="color:rgb(31, 31, 31);">A2</font> | <font style="color:rgb(31, 31, 31);">需确认后执行</font> | <font style="color:rgb(31, 31, 31);">等用户 approve 再做</font> | <font style="color:rgb(31, 31, 31);">确认流程缺失</font> | <font style="color:rgb(31, 31, 31);">显式确认</font> |
| <font style="color:rgb(31, 31, 31);">A3</font> | <font style="color:rgb(31, 31, 31);">定时调度</font> | <font style="color:rgb(31, 31, 31);">cron / scheduler</font> | <font style="color:rgb(31, 31, 31);">长期无人值守</font> | <font style="color:rgb(31, 31, 31);">kill switch</font> |
| <font style="color:rgb(31, 31, 31);">A4</font> | <font style="color:rgb(31, 31, 31);">事件触发</font> | <font style="color:rgb(31, 31, 31);">webhook/on event</font> | <font style="color:rgb(31, 31, 31);">误触发、通知风暴</font> | <font style="color:rgb(31, 31, 31);">频率限制</font> |
| <font style="color:rgb(31, 31, 31);">A5</font> | <font style="color:rgb(31, 31, 31);">持续监控</font> | <font style="color:rgb(31, 31, 31);">watch/poll</font> | <font style="color:rgb(31, 31, 31);">资源消耗</font> | <font style="color:rgb(31, 31, 31);">暂停开关</font> |
| <font style="color:rgb(31, 31, 31);">A6</font> | <font style="color:rgb(31, 31, 31);">触发后自动动作</font> | <font style="color:rgb(31, 31, 31);">满足条件自动执行</font> | <font style="color:rgb(31, 31, 31);">自动化破坏性扩散</font> | <font style="color:rgb(31, 31, 31);">人工确认优先</font> |
| <font style="color:rgb(31, 31, 31);">A7</font> | <font style="color:rgb(31, 31, 31);">自动重试/循环</font> | <font style="color:rgb(31, 31, 31);">retry/repeat</font> | <font style="color:rgb(31, 31, 31);">错误放大</font> | <font style="color:rgb(31, 31, 31);">次数上限</font> |
| <font style="color:rgb(31, 31, 31);">I1</font> | <font style="color:rgb(31, 31, 31);">单系统身份访问</font> | <font style="color:rgb(31, 31, 31);">使用用户身份访问一处</font> | <font style="color:rgb(31, 31, 31);">系统越权</font> | <font style="color:rgb(31, 31, 31);">分系统授权</font> |
| <font style="color:rgb(31, 31, 31);">I2</font> | <font style="color:rgb(31, 31, 31);">跨系统身份代理</font> | <font style="color:rgb(31, 31, 31);">多系统联动操作</font> | <font style="color:rgb(31, 31, 31);">权限扩大、责任模糊</font> | <font style="color:rgb(31, 31, 31);">连接器白名单</font> |
| <font style="color:rgb(31, 31, 31);">I3</font> | <font style="color:rgb(31, 31, 31);">跨系统数据搬运</font> | <font style="color:rgb(31, 31, 31);">从 A 读写到 B</font> | <font style="color:rgb(31, 31, 31);">流向泄露</font> | <font style="color:rgb(31, 31, 31);">数据流约束</font> |
| <font style="color:rgb(31, 31, 31);">I4</font> | <font style="color:rgb(31, 31, 31);">凭证注入外部调用</font> | <font style="color:rgb(31, 31, 31);">凭证传给外部工具</font> | <font style="color:rgb(31, 31, 31);">凭证扩散</font> | <font style="color:rgb(31, 31, 31);">禁止明文传递</font> |
| <font style="color:rgb(31, 31, 31);">I5</font> | <font style="color:rgb(31, 31, 31);">隐式权限继承</font> | <font style="color:rgb(31, 31, 31);">沿用已有高权连接器</font> | <font style="color:rgb(31, 31, 31);">越权</font> | <font style="color:rgb(31, 31, 31);">显式授权</font> |
| <font style="color:rgb(31, 31, 31);">I6</font> | <font style="color:rgb(31, 31, 31);">身份令牌深度管理</font> | <font style="color:rgb(31, 31, 31);">新增：管理系统级 Credential</font> | <font style="color:rgb(31, 31, 31);">身份彻底接管风险</font> | <font style="color:rgb(31, 31, 31);">硬件级加密、严禁明文</font> |
| <font style="color:rgb(31, 31, 31);">I7</font> | <font style="color:rgb(31, 31, 31);">跨端/跨设备协同</font> | <font style="color:rgb(31, 31, 31);">新增：代表另一台设备操作</font> | <font style="color:rgb(31, 31, 31);">攻击面扩散</font> | <font style="color:rgb(31, 31, 31);">强认证配对、同步审计</font> |


## 
