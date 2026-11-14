# Multica 编队需求基线

## 目标

生成一套目标项目无关、可复制、可裁剪、可审计的 Multica Agent、Squad、Issue、manifest 与控制模板，用于高复用度的“超级个体”工程编排。模板只描述本地期望状态和控制合同，不导入 Skill、不创建 Agent/Squad/Issue、不 dispatch、不修改 live workspace，也不声称 CI 或 provider 控制已经安装。

## 输入与优先级

1. 本文是 W1 固化后的需求 SSOT。
2. 编队方法严格采用 `multica-coach` 的 W1–W8 顺序；W9 live trial 与 W10 修订发布不在本次范围。
3. Feature/Fix 流程语义参考维护仓库中的 Multica + Spec Kit 人机协作指南；Git branch、PR、release 和 promotion 遵循 target project 锁定的外部 `git-workflow` Skill 之 GitFlow policy。与本文冲突时，以本文和当前 `multica-coach` 合同为准。
4. 能力样本仅用于证明 Skill 能力，不向模板复制样本项目路径、产品事实、账号、workspace UUID、server、runtime、私有地址、凭据或 live snapshot。
5. 所有 W1–W8 本地产物固定写入 repository-local `orchestrator/`；不得使用其他输出根。

## 编队范围

### 可进入后续候选分析的能力

- 共享入口与平台：`multica-triage`；`multica-cli` 仅作为确需访问 Multica 的 Agent 的基础平台能力，不单独派生 Agent、Squad 角色或工作流节点。
- Feature：`speckit-constitution`、`speckit-specify`、`speckit-checklist`、`speckit-clarify`、`speckit-adrkit-context`、`speckit-plan`、`speckit-adrkit-check`、`speckit-adrkit-draft`、`speckit-tasks`、`speckit-analyze`、`speckit-roadmap-write`、`speckit-roadmap-sync`、`speckit-roadmap-brief`、`speckit-implement`、`speckit-loop-define`、`speckit-loop-run`、`speckit-loop-check`、`speckit-loop-guard`、`speckit-loop-status`、`speckit-roadmap-debrief`、`speckit-converge`。
- Fix：`speckit-bug-assess`、`speckit-bug-fix`、`speckit-bug-test`；这些是 upstream Skill names，不定义本编队的 work type、Agent 或 branch prefix。
- Commit：`conventional-commit` 绑定所有 repository-writing Agent，用于本 run 的 scoped ordinary commit；另绑定共享只读 `commit-policy-reviewer` 验证 commit contract。

### 只盘点、不进入 Agent 或 Squad 候选

- `multica-orchestrator-link-up`
- `multica-orchestrator-nail-down`
- `multica-create-agent`
- `speckit-setup-project`
- `speckit-taskstoissues`
- `speckit-worktrees-specify`
- `speckit-worktrees-create`
- `speckit-worktrees-list`
- `speckit-worktrees-clean`
- `multica-coach`

这些能力仍需能力卡和依赖分析，但 W2–W8 不得把它们绑定到生成的执行 Agent、Squad membership、工作流节点或 package manifest。

## 人工权威

下列行为在首次生成和每次修改时都必须由真实 Human 参与，不能由 AI 输出、命令成功、Gate PASS、read-only report 或 Multica 状态替代：

1. Human designation：在每个 Feature/Fix 的首个 producer 前，operator 使用 `multica auth status` 所示的登录账号 email 并获得该 Human 的明确同意；它只指定后续决定者，不授予 Multica、repository、runtime 或 orchestration-control 权限。
2. Constitution：确认目标、授权来源和写入范围；审阅实际 diff；显式接受。
3. Architecture：确认证据范围和 amendment 范围；审阅事实、推断、决策、风险与 gap；显式接受。
4. Architecture 对应 ADR：审阅选项、取舍、后果、适用范围与 supersession；执行 ratify/reject/修改决定。
5. Roadmap：确认 Vision、范围、依赖、状态变化与版本级别；审阅实际 diff；显式接受。
6. 每次生成或重新生成 `tasks.md`：Human Review 覆盖、粒度、路径、依赖、并行标记、验证任务和 blocker；接受后才允许 Analyze。
7. 从 `inspect` 到 `apply`、从 `ready_for_agent` 到 dispatch、Core Implement/Loop 路径选择、Loop 最终 sign-off、高风险或不可逆操作、Release/Hotfix promotion、最终完成与 Issue `done`。
## Human designation and decisions

- [`controls/human-designation-policy.yaml`](../controls/human-designation-policy.yaml) 与 [`controls/human-designation-contract.md`](../controls/human-designation-contract.md) 规定唯一的 designation 前提：`multica auth status` 所示登录账号 email 加该 Human 的 explicit consent。
- Multica Project Lead 不是 permission setting，不能替代 designation；不要求 provider role binding、Project Owner、authorization receipt 或 provider identity readback。
- email 和 consent 不进入 portable package；workflow ledger append-only 记录 current `HumanDesignationRef`、后续 exact-revision `HumanDecisionRef`、supersession 与 stale 状态。
- 普通 Feature 在 Specify 前、初始化/重大调整在 governance-input 前、Fix 在 Assess 前确认 current designation。Agent 只能消费 designation，不能选择 Human、伪造 consent 或以 silence/timeout 推进。

## 协作 checkout 与 Loop 决策

- Native Squad 的 repository-writing execution members 与 `commit-policy-reviewer` 必须固定到 Server handoff 指定 collaboration Runtime；目标 Project 在 owning daemon 上绑定唯一 `local_directory(execution_mode=worktree)`。
- selected Runtime 必须在线并声明 `local-worktree-v1`。Capability 来自 current Runtime readback，不从 CLI 版本推断；缺失时 BLOCKED，绝不回退 `in_place`。
- Multica Runtime 管理外层 worktree、runtime task branch、baseline 和 cleanup；业务 Agent 不创建、切换、删除、重命名或 force-move branch/worktree，也不调用 `speckit-worktrees-*`。
- 每个 Work Item 固化 `WorkItemBranchRef.v1`；每个 run 固化独立 `RunCheckoutRef.v1`，包含 exact root、cwd、session、branch 和 head。ephemeral root 跨 run 变化不使 immutable artifact stale。
- Loop 保持候选；入选时固定 `loop_isolation:none` 并复用本轮 Multica worktree。禁止 nested iteration worktree。
- 每个 Feature 在第一次源码修改前必须恰好选择 Core Implement 或 Loop；两条路径不得同时或先后写同一 change/branch lineage。

## 多 Work Item 并发决策

- 一个 `repository_ref + work_item_ref` 同时只能有一个 current `WorkItemExecutionRef.v4`；每次恢复或替换使用新 `workflow_epoch`。
- `work_item_ref` 是 Multica Issue UUID；`work_item_id` 是同一 Issue 的 canonical routable key。bare number 不得进入 execution、branch 或 commit 合同。
- 同一 Work Item 同时最多一个 active writer run；正常 DAG 不接受 overlapping-run `-<task>` branch。
- 不同 Work Item 可以在同一 repository 的不同 Runtime worktree 并行，但必须具有不同 execution、run checkout root/cwd/session/state namespace，且 `ScopeConflictGate=CLEAR`。
- Constitution、Architecture、Roadmap、同一 ADR、依赖锁、migration 序列、共享 API/schema 与同一 repository target integration 继续使用 repository-global `LeaseRecord` 串行。文件系统隔离不能替代语义冲突判断。
- Feature 在 Tasks acceptance 后、route decision 前发布 WorkScope；Fix 在 Assessment=`fixable` 后、Maker 前发布。未知动态路径必须扩大 lease 或 BLOCKED。
- 同一 repository target 的最终 integration 使用串行 `IntegrationAttemptRef` 队列；target head 前进默认只使 mergeability、proposed-merge checks、integration approval/readback 失效。
- workflow ledger、lease、notification reservation、run admission 和 integration queue 必须支持原子 compare-and-set；不能验证时阻止相应并发。

## GitFlow、Branch 与 Commit 决策

- GitFlow integration flow 保留：`main` 是生产发布线，`develop` 是唯一开发集成线。
- Multica Runtime branch 和 provider integration branch 是两个身份。Runtime branch 由 Multica readback 给出，通常形如 `agent/<agent>/<issue>`；不得要求或重命名为 GitFlow branch。
- Feature provider branch 为 `feature/<owner>/<branch-work-item-token>-<slug>`；Fix 为 `fix/<owner>/<branch-work-item-token>-<slug>`，均从/回 `develop`。token 由 canonical Issue key 做 branch-safe normalization。
- Release 为 `release/<version>`；Hotfix 为 `hotfix/<owner>/<branch-work-item-token>-<slug>`，按既有 main/develop promotion 与 back-merge 义务执行。
- Provider/Human 将 verified Runtime source SHA 推送到规范 remote integration branch；必须证明 runtime head、remote head、PR source head 与 current CommitRef 相同。Agent 不 push、PR、merge、tag 或 deploy。
- 每个 repository-writing Agent 在自己的 run 内先交付 `ChangesetCandidateRef`，再使用 `conventional-commit` 创建 producer-owned `CommitRef.v2`；独立 `commit-policy-reviewer` 只读验证后，immutable revision 才可进入下游 reviewer、Human Gate 或 CI。
- Commit message 必须以唯一且最后的 `Work-Item: <canonical-work-item-id-or-url>` footer 关联 current work item；footer、branch normalized ID 与 provider work item readback 不一致时 BLOCKED。
- Writer 只允许 stage 本 run candidate 精确 diff 和正常 `git commit`；禁止跨角色业务修改、push、merge、amend、rebase、reset、cherry-pick、force-push 及 `--no-verify`。任何没有 producer-owned CommitRef/validator receipt 的新 commit 都会阻塞下游。
- GitFlow branch 流向是操作合同，不要求 GitHub ruleset、branch protection、bypass actor 或其他分支权限配置。repository provider/Human 为 Work Item provision 稳定 integration branch；每次 Agent run 前把 local base 对齐该 branch current head，验证 Runtime task branch/baseline，producer commit 通过后再 fast-forward integration branch。PR source head、current target evaluation revision、required check receipts 和 Human approval 共同约束 integration。source head 改变使 candidate/commit 及其下游 stale；target head 单独前进默认只使 integration evaluation/CI/readback stale，只有 scope/dependency/governance 输入语义改变时才传播到业务 artifacts。
- `IntegrationRef` 证明 PR 已合入；Release/Hotfix 还必须有 `PromotionRef` 证明 required back-merge、tag receipt（适用时）及 merge resolution 已完成。

## Multica 状态合同

Portable contract 使用以下精确 key/category；Human 必须在 Multica Web 逐项核对后明确同意。该确认不要求 Web screenshot、readback evidence ref 或独立 status artifact；发现不一致即 `STATUS_CONTRACT_DRIFT` 并停止 dispatch/template application：

| 含义 | Status key | Category |
| --- | --- | --- |
| 等待 maintainer 评估 | `needs_triage` | `backlog` |
| 等待可执行信息 | `needs_information` | `blocked` |
| Brief 完整，等待显式 agent dispatch | `ready_for_agent` | `backlog` |
| 明确的人类实现或决策工作 | `ready_for_human` | `todo` |
| 明确拒绝 | `wontfix` | `cancelled` |

`ready_for_agent` 不是 started run；`ready_for_human` 不是例行 PR review。编队 Gate 使用 `APPROVED`、`APPROVED_NA`、`REJECTED`、`BLOCKED`，不得作为 Issue status。

每个 Human Gate 必须生成绑定 current designation、participation plan、subject、exact revisions 和 actual diff/evidence 的唯一 current approval request。`workflow-leader` 可依据 current plan 自动向 designated Human 的 exact member ref 发送首次提醒，并由受控 provider scheduler 最多触发两次 reminder；每次发送前必须 readback request、designation、decision 和 receipt。Agent/Squad/`@all` mention、assignment、dispatch、rerun、cancel、无上限提醒和把 delivery/timeout 当作 decision 均禁止。

Human `ACCEPTED` 只开放 exact downstream gate，`REVISION_REQUESTED` 返回唯一 owning Producer/Maker，`REJECTED` 停止或按当前 workflow contract 返回；三种结果都不自动启动 Agent，仍要求显式 resume/dispatch 和 active/queued run 去重。

## 共享入口与分流

1. 所有请求先由共享 intake/triage 读取证据、分类并形成 current Agent Brief。
2. 需要定义或改变预期行为、Constitution、Architecture、ADR、Roadmap 或 active Feature 合同的请求进入 Feature。
3. 只有实现偏离既有、明确、仍有效合同的局部缺陷进入 Fix。
4. 混合 fix/enhancement 保持 `needs_triage`，由 Human 选择单一范围或批准拆分。
5. Fix 调查若证明必须改变合同，则终止 Fix 路径、保留 evidence、返回共享 intake，创建新的 current Feature Brief；Fix Agent 不继续写 Feature 产物。

## Feature 顺序

```text
approved checkout
  -> current Human designation + participation plan
  -> Specify
  -> Requirement Checklist / Clarify
  -> ADR Context / Plan / ADR Check
  -> Tasks
  -> Human Review tasks.md
  -> Analyze
  -> Roadmap Brief
  -> Human selects exactly one: Core Implement | Loop(isolation=none)
  -> Source-control Commit
  -> Roadmap Debrief
  -> Converge
  -> Human final acceptance
```

初始化或重大治理调整时，Constitution、Architecture、Architecture ADR 和 Roadmap 使用“人工确认输入 → Skill 起草 → 人工审阅实际 diff → 显式接受”的回路。普通新增 Feature 不在入口例行重跑治理；只有下游证据证明需要 amendment 时才返回相应 Human gate。

## Fix 顺序

```text
Fix Brief
  -> approved CheckoutRef(base=develop, target=develop)
  -> current Human designation + participation plan
  -> Assess
  -> verdict routing
  -> Fix
  -> Source-control Commit
  -> Independent Test (reproduction + regression)
  -> Provider PR / IntegrationRef
```

Feature 与 Fix 的 production、review、verification、implementation Skills 必须绑定到不同 `work_type` Agent。只有 intake、orchestration 和纯平台 readback 可以共享，且共享 Agent 不得获得 Feature/Fix 执行 Skill。

## Release 与 Hotfix promotion

Release/Hotfix 是 provider/Human-owned GitFlow integration lifecycle，不新增 business implementation Agent。它们只消费已验证的 `CommitRef`、`PullRequestRef`、`IntegrationRef` 和 Human approval；provider 执行 server merge、tag 与 required back-merge，Leader 仅记录 immutable receipts 并在 `PromotionRef=COMPLETE` 前保持 work item 未完成。

## 产物、门禁与失效

- 每个 handoff 必须有稳定引用、唯一 Producer、明确 Consumers、不可变 revision、客观检查与 invalidation rule。
- Producer 不得批准自己的输出；Verifier 与 Reviewer 分离；Leader 只路由、汇合、记录 Gate 和升级，不实现。
- 上游 revision 改变后，所有依赖的 Gate/产物变为 stale，并从最早受影响节点重判。
- 文件存在、命令退出 0、Agent 自述完成或 Multica 状态均不等于 Gate 通过。
- CI、provider checkout permissions、人工 integration 和 Human approval 承担硬约束；GitHub branch protection 不是前置条件，W8 输出只能标注为 proposal。
