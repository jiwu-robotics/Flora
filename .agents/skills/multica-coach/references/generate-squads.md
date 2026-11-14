# 从现有 Skills 生成 Bug Fix / Feature 编队

> 目的：当一个项目已经积累了大量 Skill 时，把这些能力整理成可运行、可裁剪、可验证的 Bug Fix 与 Feature Squad，而不是把所有 Skill 挂给一个“全能 Agent”。

本文是一套通用设计流程。它不假设具体技术栈、平台或现有角色名；输入是项目已有的 Skill 和工程约束，输出是可复制的 Agent / Squad / Issue 配置及验证证据。

## 一、先明确边界

编队设计处理五类问题：

1. **能力**：现有 Skill 分别能做什么。
2. **产物**：每一步产生什么可供下游消费的结果。
3. **责任**：谁生产、谁验证、谁评审、谁决定推进。
4. **编排**：步骤如何依赖、并行、汇合、返工和升级。
5. **强制**：哪些规则必须由 CI、权限系统或人类保证。

不要用 Squad 解决以下问题：

- Skill 本身未实现或无法运行；应先修 Skill。
- 项目没有明确的 Bug / Feature 输入契约；应先定义 Issue。
- 必须强制执行的安全或发布约束；应放进 CI、分支保护、审批和权限系统。

核心分层保持不变：

```text
Issue  = 这次做什么
Agent  = 谁对一类判断或产物负责
Skill  = 某类工作具体怎么做
Squad  = 谁在什么条件下调用什么 Skill
CI     = 什么必须真的通过
Human  = 谁在不可逆边界作最终决定
```

### 1.1 W1 先建立可追溯输入基线

W1 的第一部分必须固定并由人类接受：

- 能力样本项目、Skill 根目录和精确 commit 或确定性目录摘要；
- 需求来源、包含/排除范围、输出目录和文件所有权；
- Multica Issue 状态词汇的权威来源；
- 项目是否默认使用 worktree；
- 是否只生成本地模板，还是另有独立授权的 live provisioning/试跑请求。

能力样本项目可以是任意可读的本地项目根目录，可使用绝对路径或相对调用目录的
路径；不要求位于生成模板的当前仓库内。先解析项目根目录，再相对它解析 Skill
根目录；二者必须存在、可读且为目录，且解析符号链接后 Skill 根目录仍在项目根
目录内。能力样本仅可读取，不得写入。

能力样本只是提取可复用能力的证据源。最终模板不得包含它的绝对路径、
产品事实、账号、工作区 UUID、服务地址、runtime 名称或运行快照。

每个阶段输出都应记录阶段、输入 revision、决策状态、依赖输出、未决 blocker
和 supersedes。只允许消费状态为 `ACCEPTED` 且 revision 仍匹配的上游输出。
需求或上游产物改变时，从最早受影响阶段重新生成，不在过期设计上静默叠加。

`default_worktree` 必须是直接的人类决定，不能仅根据仓库配置推断。它决定
Feature checkout 的默认来源，不直接决定是否允许 Loop。若为 `true`，所有下游节点
都消费已接受的 worktree root；Loop 只有在合同支持 `isolation: none` 时才可继续作为
候选，并且不得创建嵌套 iteration worktree。若为 `false`，Loop 候选可使用经接受的
`none` 或 `worktree` isolation。两种情况下都只有在 Skill canonical、实现合同兼容、
共享状态和预算明确、独立 checker runtime/session 与真实 Human guard 有证据时，
才能设置 `loop_eligible: true`。每个 Feature 在修改源码前只选择 Core Implement 或
Loop 之一；不得让两条实现路径并行写同一 checkout。

## 二、最终要交付什么

一次完整的编队设计至少交付以下内容：

| 交付物 | 作用 |
| --- | --- |
| Skill 能力清单 | 统一描述所有现有 Skill 的输入、输出、副作用和依赖 |
| 产物与依赖矩阵 | 明确上游产物、下游消费者和稳定引用 |
| Feature 工作流图 | 定义需求、设计、实现、部署、测试、验收的阶段和门禁 |
| Bug Fix 工作流图 | 定义复现、根因、最小修复、回归、发布的快速路径 |
| Agent 责任矩阵 | 明确 Producer / Verifier / Reviewer / Leader 的边界 |
| Skill 挂载矩阵 | 规定每个角色只能看到和使用哪些 Skill |
| Squad Instructions | 可直接粘贴的路由、并行、门禁、失败和升级规则 |
| Issue 模板 | 为 Feature 与 Bug Fix 提供可判定的输入契约 |
| 验证报告 | W9 单独试跑时记录正常路径、失败路径和裁剪路径；W1–W8 模板生成不得伪造该证据 |

缺少其中任何一项，常见后果是：Skill 无人调用、多个角色重复调用、下游找不到产物，或者流程只能在理想路径运行。

## 三、工作一：建立 Skill 能力清单

### 3.1 不按目录名猜能力

逐个阅读 Skill 的真实说明、脚本入口和配置。每个 Skill 建一张能力卡：

| 字段 | 必须回答的问题 |
| --- | --- |
| `name` | 稳定 Skill 名是什么？ |
| `purpose` | 它只解决什么问题？ |
| `trigger` | 在什么条件下调用？ |
| `inputs` | 必需输入、格式和来源是什么？ |
| `outputs` | 产出什么内容、链接、文件或状态？ |
| `side_effects` | 是否写外部系统、改代码、触发部署或发送通知？ |
| `dependencies` | 依赖哪些其他 Skill、CLI、服务或凭据？ |
| `verification` | 如何客观判断调用成功？ |
| `failure_states` | 会返回 FAIL、BLOCKED、部分成功还是可重试错误？ |
| `runtime` | 可在哪些 OS / Runtime / Agent 能力下运行？ |
| `owner` | 谁维护这个 Skill？ |
| `status` | `canonical`、`candidate`、`legacy` 或 `retire`？ |

推荐先形成统一表格：

```markdown
| Skill | 类型 | 触发 | 输入 | 输出 | 副作用 | 依赖 | 成功证据 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| <skill-name> | 方法/编排/平台/门禁/评审 | <when> | <input> | <artifact> | <effect> | <deps> | <evidence> | canonical |
```

### 3.2 给 Skill 分类

分类不是为了美观，而是为了防止职责混用：

| 类型 | 作用 | 例子 |
| --- | --- | --- |
| 内容 / 方法 Skill | 生成或处理专业内容 | 需求分析、技术设计、实现、测试设计 |
| 产物编排 Skill | 发布产物并回传稳定引用 | 发布 PRD、API、设计或测试报告 |
| 平台 Skill | 连接具体系统 | Wiki、Issue、CI、测试平台 |
| 验证 Skill | 客观检查验收标准和证据 | 构建、测试、差异检查 |
| 评审 Skill | 提供专业判断 | 架构、前端、后端、测试评审 |
| 运维 / 管理 Skill | 管理环境或元数据 | 查询、统计、配置同步 |

### 3.3 清理重叠与失效能力

对于多个 Skill 做同一件事的情况：

1. 选择一个 `canonical` 实现。
2. 明确其他 Skill 是特定场景候选还是应退出。
3. Squad 只引用 canonical 名称。
4. 不在 Squad 里临时决定“这次用哪个相似 Skill”。

每个 Skill 最终必须被标记为：

- 被某条工作流使用；
- 可选能力，有明确启用条件；
- 与 Bug / Feature 无关；
- 待替换或待退役。

这样可以发现孤儿 Skill 和隐藏依赖，但不要求为了“利用率”把所有 Skill 强塞进编队。

### 3.4 单独盘点平台状态词汇

Issue 状态属于平台执行生命周期，不是编队 Gate 结论。盘点
`multica-triage` 等平台 Skill 时，必须逐项记录状态 display name、精确 key、
category、语义和授权边界，并以实际 Skill 合同或已验证 workspace mapping
为证据。不得复用旧 key、按名称猜 category，或创建重复 metadata 状态。

当前维护的 `multica-triage` 基线为：

| 语义 | Key | Category |
| --- | --- | --- |
| 等待维护者评估 | `needs_triage` | `backlog` |
| 等待可执行信息 | `needs_information` | `blocked` |
| 已完整描述、等待显式派发 | `ready_for_agent` | `backlog` |
| 已明确的人类实现或决定 | `ready_for_human` | `todo` |
| 明确拒绝 | `wontfix` | `cancelled` |

`ready_for_agent` 不是已开始执行；`ready_for_human` 不是例行 PR review。
编队内部仍使用 `APPROVED / APPROVED_NA / REJECTED / BLOCKED` 记录 Gate，
不得把这四值写成 Issue status。权威 Skill 与 workspace mapping 冲突时，
依赖的模板生成必须 `BLOCKED`，不能静默归一化。

## 四、工作二：建立产物与依赖矩阵

工作流应由**产物依赖**驱动，而不是由 Agent 名称串联。

为每类产物记录：

| 产物 | Producer | 必需输入 | 下游消费者 | 稳定引用 | 客观检查 |
| --- | --- | --- | --- | --- | --- |
| 需求契约 | 产品/需求责任人 | Issue、业务资料 | 设计、实现、测试 | 链接或路径 | 范围与 AC 可判定 |
| 技术方案 | 架构责任人 | 需求、现有代码 | 实现、测试 | 链接或路径 | 覆盖 AC、改动可执行 |
| API 契约 | 后端责任人 | 需求、技术方案 | 前端、接口测试 | 接口链接 | Schema、错误码完整 |
| 实现 | 前端/后端责任人 | 设计、契约 | 测试、部署 | 仓库引用 | Test/Lint/Build |
| 测试报告 | 测试责任人 | AC、实现、环境 | Leader、Human | 报告链接 | 每条 AC 有证据 |

产物契约至少规定：

- 稳定标题和固定字段；
- 可追踪编号，如 `FR-`、`BR-`、`AC-`、`RISK-`；
- 版本或更新时间；
- 稳定链接或路径；
- 修改后如何通知下游；
- 哪些下游门禁因修改而失效。

硬规则：

1. Leader 派发下游任务时显式携带上游引用。
2. 下游不得靠搜索或会话记忆猜产物位置。
3. 同一类产物由同一编排接口落地。
4. 上游产物修改后，所有受影响的下游门禁必须重判。

## 五、工作三：分别建模 Feature 与 Bug Fix

两类任务共享证据与独立判门原则，但不应共用同一条重型路径。

### 5.1 Feature 基线

通用 Feature 流程可从下面的骨架裁剪：

```text
Issue / 需求输入
  ↓ G0：目标、范围、非目标、AC 就绪
[技术设计 ∥ UI 设计]
  ↓ G1：设计对齐需求
[API 契约 ∥ 功能用例]
  ↓ 汇合门禁
[前端实现 ∥ 后端实现 ∥ 接口用例]
  ↓ G2：实现与契约通过
[构建与测试环境部署]
  ↓ G2.5：环境可用
[回归 / 自动化 / 验收测试]
  ↓ G3：AC 全部有证据
Human
  ↓ G4：合并、发布或上线决定
```

不是每个项目都需要全部节点。每个节点必须声明：

- 启用条件；
- 负责人；
- 输入引用；
- 调用的 Skill；
- 输出产物；
- 成功证据；
- FAIL 返回谁；
- BLOCKED 等待什么；
- 是否允许与其他节点并行。

### 5.2 Bug Fix 基线

Bug Fix 的目标是恢复正确行为，默认不重新走完整产品与架构流程：

```text
Bug Issue
  ↓ B0：复现条件完整
复现并收集证据
  ↓
定位根因与影响面
  ↓ B1：根因可解释、修复范围明确
[对应端最小修复 ∥ 回归用例]
  ↓ B2：原问题不再出现，既有行为不回归
[必要时部署与环境验证]
  ↓ B3：目标环境验证通过
Human
  ↓ 发布 / Done
```

遇到以下情况，Bug Fix 必须升级到 Feature 或设计流程：

- 需要改变产品规则或 API 语义；
- 根因暴露架构缺陷，最小修复不可接受；
- 修复跨多个系统且影响范围无法局部验证；
- 涉及数据迁移、安全边界或不可逆发布。

### 5.3 Worktree 与 Loop 的隔离策略

Feature 实现路径必须消费 W1 已接受的项目策略：

- 默认 worktree：使用已选择的 worktree 入口，向每个下游节点传递已解析的
  repository root。Loop 可作为候选，但必须显式使用 `isolation: none`，在该
  已接受 checkout 中工作，不创建嵌套 iteration worktree。
- 非默认 worktree：不得自动启用 Loop。仅当 Loop Skill 合同、独立
  maker/checker、共享可读状态、预算和真实 Human guard 都满足时选择 Loop；
  isolation 可为经接受的 `none` 或 `worktree`。
- 同一个 Feature 在第一次源码修改前只选择 Core Implement 或 Loop。不得先运行
  一条路径后再把同一改动交给另一条，也不得让两条路径并行写同一个 checkout。
- `default_worktree` 描述 Feature checkout context；`loop_isolation` 描述 Loop
  是否额外创建 iteration worktree。二者不是同一个决策。

这项策略不是 W6 才补写的权限细节。它从 W1 的输入基线开始约束 Skill
分类、W2 canonical 选择、W3 artifact root、W4 DAG，最终传播到 W5–W8。

### 5.4 明确并行和汇合

只有输入已经稳定、输出互不覆盖的节点才并行。

汇合门禁应记录每个分支，而不是给整个阶段一个模糊 PASS：

```text
G2
- frontend: APPROVED
- backend: APPROVED
- api-cases: BLOCKED
结论：BLOCKED；仅等待 api-cases，不返工已通过分支。
```

## 六、工作四：从责任边界派生 Agent

不要“一 Skill 一个 Agent”。Agent 应代表持续稳定的责任边界或独立判断点。

### 6.1 四类基本责任

| 责任 | 主要工作 | 约束 |
| --- | --- | --- |
| Producer | 生产需求、设计、代码、用例或部署产物 | 不批准自己的产物 |
| Verifier | 复跑客观检查、逐条核对 AC | 不代替 Producer 修改 |
| Reviewer | 判断专业质量和业务风险 | 不替代客观验证 |
| Leader | 路由、汇合、判门、失败升级 | 不亲自生产范围内产物 |

一个角色可以调用多个紧密相关的 Skill；一个 Skill也可以被不同角色调用，但调用权不等于批准权。例如 Producer 可调用验证 Skill 自查，最终门禁仍必须由 Leader、独立 Verifier 或 CI 判定。

### 6.2 Feature 与 Bug 执行角色必须分离

Feature 和 Bug 可以共享中立的 Intake、Leader 以及只做平台 readback 的
角色，但不能共享执行责任：

- Feature 的规格、规划、实现、合同评审和验证 Skill 只绑定
  `work_type: feature` Agent；
- Bug 的 assessment、fix 和 test Skill 只绑定 `work_type: bug` Agent；
- 任一 Agent 都不得同时生产、评审或验证 Feature 与 Bug 产物；
- Agent、Squad membership 和 package manifest 必须显式携带
  `work_type`，使该约束可以机械检查。

Bug 升级为 Feature 时，Bug 路径终止并保留已有证据，由共享 Intake 生成新的
current Feature Brief。Bug Producer 不得继续写 Feature Spec 或作为 Feature
Producer 复用。相同 runtime 或相同工程专业并不是合并 Agent 的理由。

### 6.3 决定是否拆角色

满足任一条件时考虑拆分：

- 需要独立判断，不能由产出者自审；
- 输入、产物和专业知识明显不同；
- 两项工作可以真正并行；
- 一项能力包含高风险外部副作用；
- 角色上下文已经大到影响稳定性。

以下情况通常不需要拆分：

- 只是调用另一个工具；
- 两个 Skill 总是处理同一产物且顺序固定；
- 新角色没有独立产物或判断权；
- 单 Agent 已能可靠完成低风险单步任务。

### 6.4 形成责任矩阵

```markdown
| 阶段/产物 | Producer | Verifier | Reviewer | 最终决策 |
| --- | --- | --- | --- | --- |
| <artifact> | <role> | Leader/CI | <optional reviewer> | Leader/Human |
```

检查矩阵中是否出现：

- 同一人既生产又批准；
- 多人同时 owner 同一产物；
- 有产物但没有消费者；
- 有门禁但没有可复跑证据；
- Leader 成为实现兜底。

## 七、工作五：建立 Skill 挂载矩阵

不同角色只挂载完成职责所需的最小 Skill 集合。

```markdown
| Agent | 必备 Skill | 可选 Skill | 禁止直接调用 |
| --- | --- | --- | --- |
| <role> | <required> | <conditioned> | <out-of-scope> |
```

挂载原则：

1. **最小权限**：不要把所有 Skill 挂给所有 Agent。
2. **平台隔离**：Producer 优先调用产物编排 Skill，不直接处理平台地址和凭据。
3. **副作用隔离**：部署、发布、删除、状态流转等能力只给明确责任人。
4. **凭据运行时注入**：凭据不进入 Agent Instructions 或 Squad Instructions。
5. **名称稳定**：Squad 只通过 Skill 名称引用，不依赖仓库相对路径。

6. **工作类型隔离**：Feature 与 Bug 执行 Skill 不得挂到同一个 Agent；
   shared Agent 不得借“平台能力”获得两类业务产物写权限。
7. **策略闭包**：默认 worktree 与 Loop 同时入选时，Loop binding、Squad
   Instructions 和 manifest 必须固定 `loop_isolation: none`，并禁止创建嵌套
   iteration worktree；每个 Feature 仍只能选择一个实现路径。

## 八、工作六：编写 Squad Instructions

每份 Squad Instructions 至少包含以下段落：

1. **目标与事实来源**：Issue、外部资料、冲突处理、待确认项。
2. **团队与角色边界**：谁在场、谁可选、谁不做什么。
3. **范围路由**：根据 Issue 字段启用哪些角色和产物。
4. **阶段图**：顺序、并行、汇合和人类边界。
5. **Skill 调用**：每个节点调用什么，输入输出是什么。
6. **产物传递**：稳定引用如何交给下游。
7. **门禁规则**：谁判、依据什么证据、有哪些结论。
8. **失败处理**：FAIL、BLOCKED、临时故障、方向错误分别怎么处理。
9. **失效规则**：上游修改后哪些门禁必须重判。
10. **升级规则**：安全、发布、数据、反复失败如何交给人类。
11. **完成定义**：Agent 完成不等于 Issue 完成。

推荐统一使用四值结论：

- `APPROVED`：满足条件，开放下游。
- `APPROVED_NA`：经确认不适用，记录理由后走无该产物分支。
- `REJECTED`：给出阻断问题、证据、责任人和可验证的通过条件。
- `BLOCKED`：等待缺失信息、环境或依赖，不得当作通过。

禁止在 Squad Instructions 中：

- 重复每个 Skill 的完整操作步骤；
- 写死内部 URL、Token、个人账号或机器路径；
- 让 Leader“必要时亲自实现”；
- 用“大家协作完成”代替明确路由；
- 默认所有角色和所有 Skill 永远在场。

## 九、工作七：设计 Feature 与 Bug Issue 模板

### 9.1 Feature Issue 最小字段

```markdown
# Feature

## 来源
<!-- 外部链接或自包含，二选一 -->

## 背景

## 目标

## 范围与涉及端

## 非目标

## 验收标准
- [ ] AC-1 ...

## 约束与参考资料
```

范围字段必须足以驱动 Squad 路由。例如设计、前端、后端、数据、CI/CD 是否涉及，不能由 Leader临场猜测。

### 9.2 Bug Issue 最小字段

```markdown
# Bug

## 来源与环境

## 复现步骤
1.

## 期望行为

## 实际行为

## 影响范围与严重程度

## 验收标准
- [ ] 原复现路径不再失败
- [ ] 相关既有行为不回归

## 日志、截图与参考资料
```

Bug 输入的第一优先级是可复现。如果环境、数据或版本缺失导致任何人无法复现，B0 必须 BLOCKED。

## 十、工作八：验证编队，而不是只评审文档

至少选择两个真实或可控任务试跑：

1. 一个跨两个以上产物的 Feature。
2. 一个有稳定复现步骤的 Bug。

每条工作流至少验证以下场景：

| 场景 | 要证明什么 |
| --- | --- |
| 正常路径 | 能从 Issue 走到 Human，产物引用完整 |
| 范围裁剪 | 无前端、无后端、无设计或无部署时仍能闭环 |
| 产物 FAIL | 只退回责任分支，不误重跑无关分支 |
| BLOCKED | 不会被误判为 PASS，也不会无限重试 |
| 上游变更 | 下游门禁会失效并重新执行 |
| 外部平台失败 | 有明确降级或人工处理，不伪造成功 |
| 三次不通过 | 能停止循环并升级人类 |
| 高风险副作用 | 发布、数据、安全边界受到 CI/权限/审批保护 |

试跑时记录：

- 实际派发顺序；
- 每个 Agent 调用的 Skill；
- 产物链接与状态；
- 门禁证据；
- 返工次数和耗时；
- 发生歧义的位置；
- 为完成任务临时补充的规则。

任何需要临场口头补充的关键规则，都应回写到对应的 Issue、Agent、Skill 或 Squad 层，而不是依赖操作者记忆。

## 十一、实施顺序

建议按以下工作包执行：
```text
W1 固定输入 revision、需求、输出所有权、状态词汇和 Human worktree 决定，
   然后盘点 Skill 与运行前提
  ↓
W2 清理重复、失效和隐藏依赖
  ↓
W3 建立产物契约与依赖图
  ↓
W4 分别绘制 Feature / Bug Fix DAG
  ↓
W5 派生分离的最小 Agent 责任矩阵
  ↓
W6 建立 Skill 挂载与权限矩阵
  ↓
W7 编写 Agent / Squad / Issue 模板
  ↓
W8 接入 CI、分支保护和人类审批
  ↓
W9 用真实 Feature 与 Bug 试跑（独立授权）
  ↓
W10 根据失败证据修订后发布（独立授权）
```

W1–W8 必须顺序执行，调用者不选择单独 stage。每一步结束时先总结本步输入
revision、关键发现、决策、产物、blocker 和下一步，再询问：
**“是否需要修改本步骤？如果不需要，请回复继续。”** 有修改就停留在当前步骤，
修订后再次总结；用户确认无需修改或回复“继续”后，才接受当前步骤并进入下一步。
不得用静默、文件已存在或命令成功代替用户确认。

不要先写完整 Squad Prompt 再反推职责。正确顺序是：

```text
Skill 能力 → 产物 → 依赖 → 责任 → 门禁 → Squad Instructions
```

## 十二、完成检查清单

### Skill

- [ ] 每个 Skill 都有明确输入、输出、副作用、依赖和成功证据。
- [ ] 重复 Skill 已选定 canonical 实现。
- [ ] 未使用 Skill 被明确标记为可选、无关或待退役。
- [ ] 平台配置和凭据没有进入角色或 Squad 提示词。
- [ ] 平台状态 key/category 来自权威合同；未把 Gate 结论当成 Issue status。
- [ ] Human 已明确 `default_worktree` 与 `loop_isolation`；默认 worktree 下启用 Loop 时固定为 `none`。

### Workflow

- [ ] Feature 与 Bug Fix 使用不同的最小路径。
- [ ] 每个节点都有启用条件、owner、输入、输出和失败去向。
- [ ] 并行节点不存在共享写入冲突。
- [ ] 汇合门禁要求所有必需分支通过。
- [ ] N/A 有理由、有确认、有明确下游分支。
- [ ] 上游修改会使相关下游门禁失效。
- [ ] Bug 升级 Feature 会终止 Bug 路径并回到共享 Intake。

### Responsibility

- [ ] 没有 Producer 批准自己的产物。
- [ ] Verification 与专业 Review 没有混为一谈。
- [ ] Leader 只编排、判门和升级，不承担实现兜底。
- [ ] 每类产物只有一个明确 owner。

- [ ] Feature 与 Bug 的生产、评审和验证 Skill 位于不同执行 Agent。
- [ ] shared Agent 不拥有 Feature/Bug 业务产物或执行 Skill。

### Enforcement

- [ ] Test、Lint、Build 等硬约束进入 CI。
- [ ] 合并和发布受分支保护、权限或审批控制。
- [ ] 安全、数据和不可逆操作有人类检查点。
- [ ] 凭据只通过运行时环境提供。

### Proof

- [ ] Feature 正常路径已试跑。
- [ ] Bug 复现—修复—回归路径已试跑。
- [ ] 至少一个 FAIL、一个 BLOCKED 和一个裁剪场景已验证。
- [ ] Squad Instructions、Agent Instructions 和 Issue 模板可直接复制使用。

## 十三、常见失败

### 失败 1：一个 Skill 对应一个 Agent

结果是 Agent 数量随工具数量膨胀，产物责任反而不清楚。

改法：先按产物和独立判断点归并责任，再给角色挂载多个相关 Skill。

### 失败 2：把所有 Skill 挂给 Leader

Leader 逐渐成为实现者、平台管理员和发布者，失去独立判门资格。

改法：Leader 只持有路由、读取证据和判门所需能力；副作用能力交给对应 Producer 或平台责任人。

### 失败 3：Feature 与 Bug Fix 共用完整流程

紧急修复被需求和设计阶段拖慢，或者 Feature 被压缩成“直接改代码”。

改法：共享证据原则，不共享同一条阶段路径；定义明确的升级条件。

### 失败 4：只有流程图，没有产物契约

角色知道下一个是谁，却不知道要把什么交给他。

改法：每条边都携带稳定产物引用和可检查的内容规范。

### 失败 5：Skill 调用成功等于阶段通过

脚本退出码为 0 只能证明调用完成，不一定证明满足验收标准。

改法：把技术执行成功与业务验收通过分开；门禁逐条映射 AC 和证据。

### 失败 6：先追求覆盖全部 Skill

为了不让 Skill“闲置”而制造无价值阶段，增加上下文和失败点。

改法：以最小可行流程为目标；Skill 是否进入 Squad 由任务需要决定。

## 为什么有效

这套方法先把已有 Skill 还原为可验证的能力，再从产物依赖派生角色和流程。它避免两个极端：一是所有能力塞给一个全能 Agent，二是每个 Skill 都创建一个角色。Feature 与 Bug Fix 共享责任分离、证据和升级原则，但保留不同的最小路径，因此既能复用治理规则，也不会让简单修复承担完整功能开发的流程成本。
