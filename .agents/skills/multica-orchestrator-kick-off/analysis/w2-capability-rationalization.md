```yaml
coach_stage: W2
decision: ACCEPTED
source_project: capability-sample-robox-nexus
source_revision: git:d24411c8840bab361745c1ed7b41cf4b3a43b3e3+mapping:sha256:8ab657d28bbb9ac295dd7c3c12d6cf9e54b150a2b6f2b29d6af4b7ccdbe3b6b8
requirements_revision: sha256:3b6caab15839cd7489bf30c23f9598a45fa309a3ade7a6227597ab83cb237d94
input_artifacts:
  - analysis/w1-inputs-and-capability-inventory.md#sha256:66d7dadaed6a1883b12d1f115f9fdcb4e0c13ace7de24fef11192bea3bb6d13f
  - requirements/orchestration-requirements.md#sha256:3b6caab15839cd7489bf30c23f9598a45fa309a3ade7a6227597ab83cb237d94
decisions:
  default_worktree: false
  loop_eligible: true
  loop_isolation: none
  capability_set_accepted: true
open_blockers: []
supersedes: analysis/w2-capability-rationalization.md#sha256:897bb440058723be43e36ef75d91bd56d2414693a63e21d45d3f82f07524de39
```

# W2 能力清理、归并与适配性分析

## 1. 本步骤结论

W1 的 37 个 Skill 中，没有证据支持删除或退役任何维护中的 Skill；需要清理的是“编队内职责重叠”和“样本 runtime 集成漂移”，而不是 Skill 文件本身。

最终分类：

- 25 个 Skill 进入编队工作流：1 个共享 intake、21 个 Feature、3 个 Fix。
- `multica-cli` 作为唯一 Multica platform prerequisite，随确需访问 Multica 的角色挂载，但不形成独立角色或 DAG 节点。
- 11 个 Skill 保持各自领域的 canonical 包，但按已接受需求只盘点，不进入本编队。
- 没有 `legacy` 或 `retire` Skill。旧 status mapping、mandatory worktree hook 和 Loop 的 `worktree` 默认值属于 configuration/runtime drift，不应伪装成第二套 Skill。

最小可用集合不是“每个 Skill 一个 Agent”，而是按不可合并的产物 ownership、独立判断和副作用边界归并。W5 才命名具体 Agent；W2 只固定能力边界。

## 2. 最终 Skill disposition

### 2.1 共享入口与平台

| Skill | Lifecycle status | W2 disposition | 启用条件 | 不得承担 |
| --- | --- | --- | --- | --- |
| `multica-triage` | `canonical` | 工作流使用：唯一共享 intake/triage/dispatch 入口 | Issue/PR 进入、恢复、显式 apply 或 dispatch | Feature/Fix 内容生产、代码修改、Human 决策 |
| `multica-cli` | `canonical` | platform-only；按需挂载，不是 Agent/Squad/node | 某角色必须读写 Multica，且 profile/workspace/权限明确 | 业务 ownership、status 猜测、私有 API、独立工作流节点 |

决策：不拆出第二个 Issue router，也不为 CLI 创建“平台 Agent”。`multica-triage` 拥有分类语义；`multica-cli` 只提供受控访问机制。

### 2.2 Feature 能力

| Skill | Lifecycle status | W2 disposition | 启用条件 | Canonical ownership |
| --- | --- | --- | --- | --- |
| `speckit-constitution` | `canonical` | 条件工作流使用 | 初始化治理，或证据证明 Constitution/Architecture 必须 amendment，且 Human 已确认输入范围 | Constitution + 单一 Architecture 的唯一写入 Skill；Human ratifies |
| `speckit-roadmap-write` | `canonical` | 条件工作流使用 | 初始化 Roadmap，或 Human 接受明确 delta | Roadmap ledger 的唯一写入 Skill；Human ratifies |
| `speckit-roadmap-sync` | `canonical` | 可选维护分支 | Human 请求 project-wide reconciliation，或治理证据要求全局对账 | 只生成 sync report，不改 Roadmap |
| `speckit-specify` | `canonical` | 主路径使用 | current Feature Brief、批准 checkout、授权来源齐备 | `spec.md` 的 Feature requirement producer |
| `speckit-checklist` | `canonical` | 主路径使用，带 runtime precondition | `spec.md` 可审查且 canonical requirement fragments 可解析 | 单一 `checklists/requirements.md` producer |
| `speckit-clarify` | `canonical` | 条件 repair loop | Requirement Gate 产生 `product-decision` blocker | 只解决产品歧义并同步 spec/gate；不代替 source owner 或 template owner |
| `speckit-adrkit-context` | `canonical` | 主路径使用 | Plan 前需要读取 governing decisions/open queue | ADR read/context；不写 ADR |
| `speckit-plan` | `canonical` | 主路径使用 | Requirement Gate READY、governance/spec revisions 有效 | `plan.md`、X0–X4 与 test-first design producer |
| `speckit-adrkit-check` | `canonical` | 主路径验证 | Plan revision 已固定 | governing ADR verifier；无 snapshot 时不得宣称 deterministic routing |
| `speckit-adrkit-draft` | `canonical` | 条件治理分支 | Plan/ADR check 证明正式决策缺口，Human 授权起草 | 只创建 draft ADR；Human ratifies/rejects |
| `speckit-tasks` | `canonical` | 主路径使用 | Plan/design handoff 完整 | `tasks.md` producer；之后必须 Human Review |
| `speckit-analyze` | `canonical` | 主路径独立评审 | Human 已接受当前 `tasks.md` revision | 实现前跨产物一致性 reviewer；只读 |
| `speckit-roadmap-brief` | `canonical` | 主路径独立评审 | Analyze 通过且 Roadmap entry 唯一 | pre-implementation roadmap reviewer；只写 report |
| `speckit-implement` | `canonical` | Core 写入路径 | Human 为该 Feature 选择 Core，且尚无 Loop 写入 | Core implementation producer |
| `speckit-loop-define` | `canonical` | Loop bundle | Human 选择 Loop，done criteria、预算、maker/checker/guard 可定义 | Loop contract/state producer |
| `speckit-loop-run` | `canonical` | Loop bundle | 有效 Loop contract、预算剩余、current Runtime outer worktree 已批准 | Loop maker；不得自评 |
| `speckit-loop-check` | `canonical` | Loop bundle | latest maker revision immutable，独立 checker session 可用 | adversarial verifier；正常不改代码 |
| `speckit-loop-guard` | `canonical` | Loop bundle | checker PASS、预算/风险触发或请求完成 | Human sign-off 与 comprehension-debt guard |
| `speckit-loop-status` | `canonical` | Loop bundle | resume、路由或查询 Loop state | budget-aware state renderer；只读 |
| `speckit-roadmap-debrief` | `canonical` | 主路径独立评审 | Core 或 Loop 路径完成并有验证证据 | post-implementation roadmap reviewer；只写 report |
| `speckit-converge` | `canonical` | 主路径收敛 | Debrief 完成 | 只向 `tasks.md` append convergence tasks；不修代码 |

Loop 五个 Skill 是一个不可拆的 optional bundle。不能只挂 `loop-run`，也不能让 maker 同时拥有 `loop-check`。本设计已满足 W1 eligibility，因此 W2 保留 Loop；执行时固定 `isolation: none`。

### 2.3 Fix 能力

| Skill | Lifecycle status | W2 disposition | 启用条件 | Canonical ownership |
| --- | --- | --- | --- | --- |
| `speckit-bug-assess` | `canonical` | Fix 主路径 | current Fix Brief 完整 | `assessment.md` producer；不改源码 |
| `speckit-bug-fix` | `canonical` | Fix 主路径 | assessment verdict 可修且范围仍是 Fix | 最小修复与 `fix.md` producer |
| `speckit-bug-test` | `canonical` | Fix 主路径独立验证 | fix revision 固定 | reproduction/regression verifier 与 `test.md` producer |

`speckit-bug-fix` 运行的针对性本地检查属于 Producer evidence，不替代 `speckit-bug-test` 的独立重放。Fix Agent 不挂载 Feature Spec/Plan/Tasks/Implement Skill；一旦需要改变合同，返回 intake 并生成新的 Feature Brief。

### 2.4 Source-control capability

| Skill | Lifecycle status | W2 disposition | 启用条件 | Canonical ownership |
| --- | --- | --- | --- | --- |
| `conventional-commit` | `canonical` | producer-owned commit + independent policy verification | current provider-managed CheckoutRef、scope-bound ChangesetCandidateRef、hook/validator/readback 都 current | 每个 repository-writing Agent 在自己的 run 内创建 scoped ordinary commit；`commit-policy-reviewer` 只读验证；均不得 push/merge/amend/branch mutation |

`conventional-commit` 是每个 repository-writing Feature/Fix role 的提交能力，也是共享 `commit-policy-reviewer` 的只读验证能力。业务 writer 在实际验证后、run 结束前创建 producer-owned `CommitRef.v2`；独立 reviewer、Human Gate 或 CI 只消费 VERIFIED verdict 对应的 immutable revision。commit message 必须携带与 checkout work item 匹配的 Work-Item footer。

### 2.5 只盘点、不进入本编队

| Skill | Lifecycle status | W2 disposition | 排除理由 |
| --- | --- | --- | --- |
| `multica-orchestrator-link-up` | `canonical` | out-of-scope | workspace foundation provisioning，不属于日常 Feature/Fix 执行 |
| `multica-orchestrator-nail-down` | `canonical` | out-of-scope | project association/config 生成，不属于编队节点 |
| `multica-create-agent` | `canonical` | out-of-scope | live Agent 创建；W1–W8 禁止 provisioning |
| `speckit-setup-project` | `canonical` | out-of-scope | Spec Kit 安装/升级，不属于业务工作流 |
| `speckit-taskstoissues` | `canonical` | out-of-scope | 会创建外部 Issues；本编队直接定义 Issue 输入合同，避免双重 issue ownership |
| `speckit-worktrees-specify` | `canonical` | out-of-scope | checkout 由 Project/Runtime 在 dispatch 前提供 |
| `speckit-worktrees-create` | `canonical` | out-of-scope | 同上；禁止产生第二层 worktree |
| `speckit-worktrees-list` | `canonical` | out-of-scope | worktree inventory 由 repository integration 承担 |
| `speckit-worktrees-clean` | `canonical` | out-of-scope | 破坏性 maintenance，不属于 Feature/Fix 编队 |
| `multica-coach` | `canonical` | out-of-scope | 生成编队设计，不应被生成的编队递归调用 |

## 3. 重叠能力的 canonical 决策

| 看似重叠的能力 | 不合并原因 | Canonical 路由决定 |
| --- | --- | --- |
| `speckit-constitution` 与独立 Architecture 角色 | Skill 已把 Constitution 与单一 Architecture 定义为两个独立 output gate；新增第二个 Architecture writer 会形成双 SSOT | 只让 `speckit-constitution` 写两者；Human 分别审阅/接受，后续 reviewer 不写 |
| `speckit-roadmap-write` 与 `brief`/`debrief`/`sync` | `write` 改 ledger；其余只生成 report | Roadmap 只有一个 writer；三个 report Skill 是不同时间/范围的 reviewers |
| `speckit-checklist` 与 `speckit-analyze` | 前者判断 requirements writing quality，后者审计跨产物一致性 | Checklist 在 Plan 前；Analyze 在 Human 接受 Tasks 后；不可互相替代 |
| `speckit-adrkit-context`、`check`、`draft` | 分别是读取上下文、验证 plan、创建 draft；副作用和 authority 不同 | 保持三段；draft 后强制 Human ratification，不允许 check 自动起草 |
| `speckit-implement` 与 `speckit-loop-run` | 都会改源码，若同时启用会形成两个 writer | 每个 Feature 在首次源码写入前由 Human 选择恰好一个 route；后续 convergence 返回同一路径 |
| `speckit-loop-run` 与 `speckit-loop-check` | maker/checker 独立是 Loop 正确性的核心 | 不合并 Agent/session/permissions；checker 无写代码权限 |
| `speckit-bug-fix` 与 `speckit-bug-test` | Fixer 的本地检查证明“做过检查”；Verifier 证明“原始症状消失且无回归” | 分离 Fix Producer 与 Fix Verifier；Verifier 不接受 fix 自述代替复现 |
| `speckit-analyze`、`roadmap-brief`、`roadmap-debrief`、`converge` | 检查对象和时点不同：设计一致性、实现前意图、实现后结果、最终闭环 | 保持四个门禁；结果以 stable report/Gate 引用交接 |
| `multica-triage` 与未来 Squad Leader | Triage 拥有分类/status/Brief/dispatch；Leader 拥有已分类工作流的 DAG 路由和 Gate ledger | Leader 不重新分类或改 triage 语义；Triage 不实现或审批内部产物 |
| `speckit-taskstoissues` 与 W7 Issue templates | 前者把 tasks 转成 live Issues，后者定义 portable 输入合同 | 按用户排除 `speckit-taskstoissues`；只输出模板，不创建 Issues |
| `speckit-worktrees-*` 与 Project/Runtime checkout | 两者都会决定 execution root | 只接受 Project/Runtime 提供的批准 checkout；禁止 worktree Skill 作为 DAG 节点 |

## 4. Runtime drift 与处理决定

### 4.1 Requirement fragments 未物化

事实：`speckit-checklist` 读取 `.specify/templates/requirements/*.md`，样本仅在 preset 源目录保有 fragments，canonical runtime 路径不存在。

决定：

- 保留 `speckit-checklist` 为 canonical；不新增替代 Checklist Skill，不硬编码 preset checkout 路径。
- 把 `REQUIREMENT_RULES_AVAILABLE` 设为 Feature Specify → Checklist 的前置 Gate。
- W7 manifest 声明目标 integration 必须通过受支持的 preset/template resolver 把规则暴露到 canonical runtime path。
- W8 proposal 在 dispatch 前验证四个 rule fragments 可解析；失败返回 `REQUIREMENT_RULES_UNAVAILABLE`，不得降级为无规则 Checklist。

### 4.2 Mandatory `after_specify` worktree hook

事实：样本启用 unconditional mandatory `after_specify -> speckit.worktrees.create`，与 Multica Runtime 管理 Project `local_directory(execution_mode=worktree)` 的合同冲突，因为它会创建 nested worktree。

决定：

- 该 hook 不进入工作流，也不由 Agent 忽略失败。
- 目标 provider/integration 必须在使用模板前禁用或移除该 hook，并 readback effective hook graph。
- Handoff 携带 `WorkItemBranchRef.v1`、`RunCheckoutRef.v1`、`CheckoutRef.v5` 与 artifact root；每个 run 使用自己的 Runtime task branch/worktree，不由 Agent 创建或切换。

### 4.3 Loop 默认隔离

事实：样本 Loop config 默认 `isolation: worktree`，但 Skill 合同支持 `none`。

决定：

- Loop 仍是 canonical optional route。
- W3 contract 固化 `loop_isolation:none`；W6 只允许 Loop maker 复用 current Runtime outer worktree。
- 若 runtime 不能证明 effective isolation 为 `none`，Loop route 不可用；Human 只能选择 Core 或先修复配置。

### 4.4 Status definition confirmation

事实：repository contracts 已统一；当前 CLI 可使用已知 status key，但不能 list/create/edit custom status definitions。

决定：

- portable package 只使用已接受的五行状态合同。
- W7 不写 live UUID/status IDs。
- W8 要求 Human 在 Multica Web 核对精确 key/category 后明确同意，作为 application/dispatch prerequisite；不需要 Web readback evidence，不使用真实 Issue 作为探针，也不调用私有 API。

## 5. 适配性评估

| 能力组 | 复用性 | Ownership 清晰度 | 副作用可控性 | 客观验证 | 结论 |
| --- | --- | --- | --- | --- | --- |
| Shared triage + CLI | 高 | 中：Skill 同时有 inspect/apply/dispatch | 高：mode、`--no-start`、readback 可约束 | 高，但 status definition 需 Web | 保留；W6 按 mode 缩权 |
| Constitution/Architecture/Roadmap/ADR | 高 | 高：writer 与 read-only reviewer 可区分 | 中：治理写入影响范围大 | 高，前提是真实 Human diff acceptance | 保留；强制 Human gates |
| Specify/Checklist/Clarify | 高 | 高 | 中：spec/gate revision 会级联失效 | 高；fragments 必须可用 | 保留；runtime precondition |
| Plan/Tasks/Analyze | 高 | 高 | 中：Plan/Tasks 写，Analyze 只读 | 高：stable refs、coverage、severity | 保留；Tasks 后强制 Human Review |
| Core Implement | 高 | 高 | 低到中：可改代码/运行命令 | 取决于目标项目验证命令 | 保留为默认可选 writer route |
| Loop bundle | 中到高 | 高，前提是 maker/checker 分离 | 中：预算和 state 可约束 | 高：checker + guard + Human | 保留为 optional route，固定 isolation none |
| Roadmap reviews + Converge | 高 | 高 | 高：reports/append-only tasks | 高 | 保留；不得变成源码 writer |
| Fix Assess/Fix/Test | 高 | 高 | 中：Fix 可改代码 | 高：reproduction + regression | 保留；与 Feature agents 分离 |
| Setup/worktree/task bridge | 各自领域高 | 高 | 多为高副作用 | 可验证 | 按明确需求排除，不包装进 Squad |

## 6. 需要由编队合同补齐、而不是新增 Skill 的能力

| 缺口 | 为什么不是新 Skill | 后续归属 |
| --- | --- | --- |
| Immutable `HandoffRef`、`GateRecord`、revision 与 invalidation | 这是跨 Skill 的数据合同，不是专业内容能力 | W3 schema；W4 routing；W7 templates |
| Producer 不能自批、maker/checker/reviewer 分离 | 这是职责和权限不变量 | W5 responsibility；W6 permissions；W8 controls |
| Human 对 Constitution/Architecture/ADR/Roadmap/Tasks/Core-vs-Loop/final acceptance 的真实决定 | Human Authority 不可包装成 AI Skill | W4 Human nodes；W8 approval controls |
| Project/Runtime 提供批准 checkout | Worktree Skills 已被用户排除，且重复创建会破坏 root continuity | W3 checkout artifact；W8 provider precondition |
| Status definition provisioning/readback | CLI 明确不覆盖该管理面 | Human/workspace administrator + Multica Web；W8 只提 proposal |
| Requirement fragment materialization | 属于 Spec Kit 安装/preset resolution，不是 Checklist 的替代能力 | W7 manifest prerequisite；W8 preflight |
| Core/Loop 恰好选择一条写路径 | 属于路由锁和 lease，不应由两个 writer 临时协商 | W3 route record；W4 DAG；W8 enforcement |
| `tasks.md` single-writer lease 与 Convergence append | 属于共享产物并发控制 | W3 artifact contract；W4 convergence loop |

## 7. W2 验收检查

| 检查 | 结果 |
| --- | --- |
| 37 个 Skill 均有最终 lifecycle status 与 disposition | PASS |
| 每个工作流 Skill 有唯一 canonical purpose | PASS |
| Feature 与 Fix 写入能力未混用 | PASS |
| Core 与 Loop 双 writer 冲突已消除 | PASS：Human 选择恰好一条 |
| Loop bundle 完整且 isolation 策略一致 | PASS：eligible，`none` |
| exclusions 未被偷渡为 Agent/Squad/node | PASS |
| runtime drift 有显式 precondition/失败状态 | PASS |
| 未新增重复 Skill 或第二套 SSOT | PASS |
| 缺口已路由到 W3–W8 合同/控制，而非伪造能力 | PASS |

W2 已由 Human 接受。目录变更不影响 37 个 Skill 的能力证据、canonical/optional/platform-only/out-of-scope disposition；当前 revision 成为 W3–W8 的能力边界。
