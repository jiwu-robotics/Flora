```yaml
coach_stage: W8
artifact: PROVIDER_CONTROLS
decision: ACCEPTED
application_state: proposal
installed: false
live_readback: false
requirements_revision: sha256:3b6caab15839cd7489bf30c23f9598a45fa309a3ade7a6227597ab83cb237d94
w7_analysis_revision: sha256:fa7cb25cced83939df9d8ce999f7ac79db62567a05cf0060a6da174d488f717f
package_manifest_revision: sha256:9d898b10f1b33a3e6c54eed4239cba220d36a33950f01cf6b1aed57c3114004d
open_blockers:
  - TARGET_PROVIDER_UNRESOLVED
  - APPLIED_PERMISSION_READBACK_UNAVAILABLE
  - STATUS_CONTRACT_HUMAN_CONFIRMATION_PENDING
  - MULTI_WORK_ITEM_EXECUTION_ISOLATION_UNVERIFIED
  - WORKFLOW_LEDGER_ATOMICITY_UNVERIFIED
  - RESOURCE_LEASE_CONTROL_UNVERIFIED
  - INTEGRATION_QUEUE_UNVERIFIED
  - COMMIT_CONTEXT_ISOLATION_UNVERIFIED
  - HUMAN_NOTIFICATION_DEDUPE_UNVERIFIED
supersedes: controls/provider-controls.md#sha256:705fc3ea381d18aad3625da3c4ed2e1cb7aac1b7ed27fb6d546a6c3ea2cd8be7
```

# W8 Provider 与权限控制方案

## 1. 决策边界

本文定义 target Project/repository 的安装与 readback 合同。`multica-orchestrator-nail-down` 可在逐项授权下修改 Project/repository integration 和 portable repository 配置，但不得修改 workspace Skills、Agents、Squads、runtime 或 secret。GitHub private repository 的 ruleset、branch protection 和 branch-permission 配置不属于强制安装项；没有相应 provider readback 前，依赖控制保持 `BLOCKED`。

硬约束必须由 provider、CI 或 Human 执行，不能只写在 Agent/Squad Instructions 中。Agent 输出、模板文件存在、CLI 退出 0 或 Issue status 都不能证明控制已安装。

GitFlow 的 merge、release tag 与 promotion workflow 已由 branch-and-commit contract 定义，但只授予 provider/Human integration authority；所有 Agent 的 merge、release、tag 和 deployment 权限继续拒绝。

## 2. 控制层与权威

| 层 | 权威 | 负责 | 不负责 |
| --- | --- | --- | --- |
| Multica workspace | workspace administrator | status key/category、Agent/Squad/Skill/permission/runtime readback | 业务 Gate、Human 产品决定 |
| Project/Runtime integration | repository provider | 每个 Work Item 独立 execution/checkout/root/session、branch/base/head、执行环境 | 自动决定 Core/Loop、代替 Human 接受 |
| Repository integration procedure | repository administrator + Human integration operator | GitFlow branch provisioning、scope registry、resource lease、repository-target queue、PR source/target/head、检查收据、merge receipt、Human review | 通过 GitHub ruleset、branch protection 或 bypass 配置强制这些步骤 |
| CI | target repository maintainers | 在 exact source/target proposed merge revision 执行项目 checks、execution/scope/lease/integration 合同检查 | 用模拟结果替代目标命令 |
| Human designation | operator + designated Human | `multica auth status` account email、explicit consent、current `HumanDesignationRef`、matching decision records 和不可代理决定的 ledger persistence | Agent/bot 自签、伪造 consent、让 Agent 选择或改变 email |
| Human participation | human-designation operator + provider scheduler + `workflow-leader` | current plan、exact member recipient、原子 notification reservation、bounded reminders、receipt；Leader 仅发送与记录 | 以 recipient/delivery 替代 Human、自动启动 Agent、broad/duplicate mention |
| Runtime secret store | platform/security administrator | 最小 secret binding、审计和轮换 | 把凭据写入模板或日志 |

## 3. Provider control matrix

| ID | 控制 | Provider enforcement | 必需 readback | 失败状态 |
| --- | --- | --- | --- | --- |
| `PC-001` | GitFlow dual-branch procedure | provider/Human 为每个 Work Item 创建稳定 integration branch；Runtime 为每个 Agent/run 管理 task branch/worktree；provider 仅在 commit verdict 后 fast-forward integration branch，并以其 exact head 发起 PR | branch policy digest、WorkItemBranchRef、RunCheckoutRef、base/target、push/readback receipt、PullRequestRef | `BRANCH_POLICY_VIOLATION` |
| `PC-002` | Integration checks | 十二个 baseline check 在 exact source/target proposed merge revision 成功；它们是人工 integration 前提，不要求 GitHub required-check setting | 当前 check receipt、source/target revision、N/A policy（适用时） | `REQUIRED_CHECK_DRIFT` |
| `PC-003` | Human integration accountability | 经授权 Human/integration operator 核对检查与 approval 后执行 provider merge，并生成 IntegrationRef | Human identity、PR/integration receipt、merge method | `INTEGRATION_POLICY_INVALID` |
| `PC-004` | Human review ownership | governance、workflow control、security/data-sensitive paths 由 current designated Human 分项决定；不要求 CODEOWNERS/ruleset enforcement | current HumanDesignationRef、exact-revision HumanDecisionRef | `OWNER_REVIEW_MISSING` |
| `PC-005` | Multica status contract | Human 在 Multica Web 核对五个 status key/category 后明确同意；不要求 evidence ref | Human confirmation | `STATUS_CONTRACT_DRIFT` |
| `PC-006` | Agent/Squad binding | applied role、work_type、Instructions、Skills、permissions、membership 与 manifest 一致；每个 bound Skill 都必须有 current operator-local source→archive→workspace integrity PASS | supported Agent/Squad/Skill/permission readback、operator-local integrity verifier report | `APPLICATION_NOT_VERIFIED` |
| `PC-007` | Multica least privilege | 只有 A01/A02 可访问 Multica；其余 14 个 Agent 无 access | per-Agent effective permission readback | `MULTICA_PERMISSION_BREACH` |
| `PC-008` | Dispatch deduplication | `ready_for_agent` 不自动启动；显式 dispatch 以 repository/work-item/work-type/epoch 原子查 current/active/queued run | WorkItemExecutionRef、Issue status、run list、dispatch audit | `DUPLICATE_OR_IMPLICIT_DISPATCH` |
| `PC-009` | Worktree Runtime authority | Human 选择一个声明 `local-worktree-v1` 的 verified collaboration Runtime；Project 在 owning daemon 上绑定唯一 repository `local_directory(execution_mode=worktree)` | Agent runtime refs、capability revision、Project resource/mode、run branch/baseline/root/cwd/session/head readback | `WRITE_SCOPE_BLOCKED` |
| `PC-010` | Run checkout/Loop | 每个 run 使用独立 Runtime worktree/task branch；同一 Work Item writer 串行；Loop isolation 为 none 并复用当前外层 worktree，禁止 nested worktree | effective hook/config/runtime/resource/ownership/baseline/session/root/active-run evidence | `WORKTREE_OR_LOOP_POLICY_DRIFT` |
| `PC-011` | Runtime secrets | 只向 A01/A02 运行时注入所需 secret；禁止输出和持久化 | secret binding metadata，不读取 secret value | `SECRET_SCOPE_VIOLATION` |
| `PC-012` | Human designation matching | HumanDecisionRef 的 email 必须匹配 `multica auth status` 所示且已明确同意的 current HumanDesignationRef | authenticated account email/consent、decision time/revision | `HUMAN_IDENTITY_UNVERIFIED` |
| `PC-013` | Lifecycle readback | recording-only 状态写入使用 no-start 语义并写后读取 | before/after status、runs、metadata snapshot | `LIFECYCLE_READBACK_FAILED` |
| `PC-014` | Destructive actions | Agent 默认无删除 provider object、强推、merge、release、deploy、secret/schema 管理权限 | effective deny/readback | `DESTRUCTIVE_PERMISSION_EXPOSED` |
| `PC-015` | Human designation | operator 在首个 producer 前记录 `multica auth status` account email 与 explicit consent；无 Project Owner 或 role binding 要求 | current designation、state、consent time | `HUMAN_DESIGNATION_UNCONFIRMED` |
| `PC-016` | Human decision evidence | 每个 subject 由 designated Human 对 exact revisions/diff 单独决定；Leader 只持久化已发生决定 | designation ref、email matching、decision、input/evidence refs、supersedes | `HUMAN_APPROVAL_EVIDENCE_INVALID` |
| `PC-017` | GitFlow branch provisioning | provider/Human provision Feature/Fix stable integration branch；每次 dispatch 前将 clean local base 对齐 current integration head，Runtime 再创建 Agent task branch/worktree；Feature/Fix 从/回 `develop`，Hotfix 从/回 `main`；Agent 不变更 branch/worktree | Work Item UUID/key、branch policy digest、integration branch/head、Runtime task branch/ownership/baseline、run root/cwd/session、push/readback receipt | `BRANCH_POLICY_VIOLATION` |
| `PC-018` | Conventional Commit boundary | 每个 repository-writing Agent 从本 run scope-bound candidate 创建 ordinary commit；独立 commit-policy-reviewer 只读验证；hook 与 PR commit-range validator 强制唯一末尾 canonical Multica Issue key/URL footer | writer/reviewer effective permission、producer run identity、candidate/SHA mapping、hook/range-validator readback、Issue UUID/key resolution | `COMMIT_POLICY_INVALID` |
| `PC-019` | PR integration | `main`、`develop` 和 active Release/Hotfix 的 integration 必须有 PR、十二个 baseline check 收据、Human approval 与 provider server merge commit；PR source 必须是 stable integration branch exact head | IntegrationAttempt exact source/target、check 收据、approval、merge method、IntegrationRef.v2 receipt | `INTEGRATION_POLICY_INVALID` |
| `PC-020` | Release/Hotfix promotion | Release/Hotfix primary IntegrationRef.v2 后必须按 GitFlow back-merge，tag 仅由 provider/Human 创建；冲突统一使用 MergeResolutionRef.v2 | primary integration、back-merge、tag、resolution 与 PromotionRef receipts | `PROMOTION_INCOMPLETE` |
| `PC-021` | Human participation plan | operator-local current plan 必须把 current designation 解析到一个 exact member，固定原子 reservation key、scheduler、interval、两次 reminder 上限、stop conditions 和 append-only receipt store | plan/designation/member mapping、reservation、scheduler config、receipt reader | `HUMAN_PARTICIPATION_PLAN_UNRESOLVED` |
| `PC-022` | Human notification and decision routing | A02 仅对 current request 在原子预留成功后发送 initial notification 或响应 scheduler reminder；发送前后 readback；Human result 不自动启动 Agent | request key、reservation、before/after decision state、receipt、reminder count、active/queued runs | `HUMAN_NOTIFICATION_CONTROL_UNVERIFIED` |
| `PC-023` | Work Item execution isolation | 一个 repository/work-item 只有一个 current epoch，同一 Work Item 同时只有一个 writer run；不同 Work Item 可在独立 Runtime worktree 并发，仍受 ScopeConflictGate 与 leases 约束 | WorkItemExecutionRef.v4、WorkItemBranchRef.v1、RunCheckoutRef.v1、Runtime/local-directory ref、execution mode、cwd/session/root/active-run readback | `MULTI_WORK_ITEM_EXECUTION_ISOLATION_UNVERIFIED` |
| `PC-024` | Atomic workflow ledger | Gate/Handoff/lease/notification/integration updates 以 expected revision compare-and-set；不允许 lost update | append history、CAS receipt、current pointer/readback | `WORKFLOW_LEDGER_ATOMICITY_UNVERIFIED` |
| `PC-025` | Work scope conflict gate | 首次源码写前比较所有 current WorkScopeRef 的 path/resource/dependency overlap；未 CLEAR 不 dispatch writer | scope registry snapshot、ScopeConflictGate、resolution/dependency ref | `WORK_SCOPE_CONFLICT_UNRESOLVED` |
| `PC-026` | Repository-global resource lease | Constitution、Architecture、Roadmap、同一 ADR、API/schema、dependency/config、migration 和 integration target 用原子 LeaseRecord.v2 | resource key、holder execution、expected revision、acquire/release receipt | `RESOURCE_LEASE_CONTROL_UNVERIFIED` |
| `PC-027` | Repository target integration queue | 每个 repository/target 同时最多一个 EVALUATING/READY/MERGING attempt；target 前进使旧 attempt stale | IntegrationAttemptRef、queue CAS、exact source/target、status history | `INTEGRATION_QUEUE_UNVERIFIED` |
| `PC-028` | Per-run Git context | 每个 writer 固定 RunCheckoutRef 的 Runtime/daemon/resource/root/cwd/session/task branch/ownership/baseline/HEAD 和 scoped staged set；同一 Work Item writer runs 串行 | runtime/resource/execution-mode/run/root/branch/ownership/baseline/HEAD/index/staged-set readback | `COMMIT_CONTEXT_ISOLATION_UNVERIFIED` |
| `PC-029` | Human notification deduplication | initial notification 以 project/work-item/subject/designation/plan/sorted-inputs 原子预留；同一 current request 恰好一次 | reservation key/state、receipt、supersession/readback | `HUMAN_NOTIFICATION_DEDUPE_UNVERIFIED` |

## 4. Repository integration procedure

GitFlow branch 流向保留为操作合同，不翻译成 GitHub ruleset、branch protection、bypass actor、required-check 或 CODEOWNERS 配置。GitHub private repository 无法提供这些能力不阻止 passive application，但缺 execution/scope/lease/integration 原子控制会阻止并发 dispatch/write/integration。

passive Agent/Squad application 不要求 work-item receipt。首次 dispatch 前必须验证全部 Agent 指向同一声明 `local-worktree-v1` 的 collaboration Runtime、Project `local_directory` 为 `execution_mode=worktree`、WorkItemExecution admission、stable integration branch、atomic workflow ledger、scope registry/resource lease 和 notification reservation。每次 writer dispatch 前必须生成 ACTIVE `RunCheckoutRef.v1`，且同一 Work Item 无另一 active writer；不同 Work Item 只有 ScopeConflictGate=CLEAR 且 leases 不冲突时才可并行。ordinary commit 前验证 run-scoped Git context 和 staged set；verdict 后 provider 才能 fast-forward integration branch。PR integration 前验证 repository-target queue。

`prepare` 必须从 Foundation/Server CAS、repository control surface、Git provider readback
和 project-scoped control authority 自动生成十四项 setup control evidence；operator
不复制模板、不填写 setup receipt。缺失的 authority 由 plan 暴露为
`control-authority-init`，经授权 apply 后重跑 `prepare`。

For a deployment that has exactly one selected runtime daemon and one control
operator, the package's `../cli/control_store.py` is the concrete setup-control
implementation. Store its SQLite database in a restricted operator-local
directory, never in the target repository. `execution-admit`, `branch-bind`,
`branch-advance`, `run-checkout-bind`/`run-checkout-refresh`/`run-checkout-release`,
`ledger-append`, `scope-claim`, `lease-acquire`/`lease-release`,
`queue-enter`/`queue-transition`, `notification-*`, and the supervised
`../cli/notification_scheduler.py` provide atomic transactions, bounded
reminder scheduling, and readback. This authority is not distributed: adding
another daemon or independent writer invalidates the evidence and requires
migration to a shared transactional store before further dispatch.


每次 integration 由 repository administrator 或经授权 Human/integration operator 执行：

1. 原子进入 `integration:<repository>:<target>` 队列，冻结 PR source head 和最新 target head；
2. 比较 active WorkScope/dependencies 与 target delta；仅在 overlap 或检查失败时扩大 source artifact invalidation；
3. 在 exact source/target proposed merge revision 上运行十二个 baseline checks；
4. 核对 current Human final acceptance 和 provider integration approval；
5. 使用 provider server-managed merge commit，记录 merge method、source/target/checks 到 `IntegrationRef.v2`；
6. 对 Release/Hotfix 完成 required back-merge、tag（适用时）和 MergeResolutionRef.v2，再标记 `PromotionRef=COMPLETE`。

GitHub branch protection 若可用，只能作为 defense in depth；它不是 acceptance blocker。缺原子 integration queue 时并发 integration 必须 BLOCKED，不得以 Human 手工注意力替代。

十二个 baseline check 是：

1. `orchestration-contract`
2. `work-type-isolation`
3. `work-item-execution-isolation`
4. `cross-work-item-scope-conflict`
5. `resource-lease-integrity`
6. `integration-target-freshness`
7. `artifact-revision-integrity`
8. `permission-boundary`
9. `human-approval-evidence`
10. `project-test`
11. `project-lint`
12. `project-build`

目标项目明确无 lint 或 build 时，仍不能让 Maker 临场跳过。必须由 Human/maintainer 接受项目级 N/A policy，并让对应 check 验证该 policy 后成功。

控制检查的 evidence 必须由 `capture-control-evidence` 从 operator control
store 的 current state 自动求值：它冻结 exact `IntegrationAttemptRef`、
source/target，读取 execution/checkout、ledger、scope、lease、current setup
verification，以及 designated Human 对 exact attempt/revisions 的真实决定。
不得接受或拼接手写 PASS receipt。导出的 `check-evidence.v2` 作为显式
provider-dispatch input；不得提交一个声称绑定自身 commit SHA 的 evidence
文件，也不得用一个会被并发 integration 覆盖的 repository secret。
`project-test`、`project-lint`、`project-build` 有 command 时必须实际执行该
command；只验证 command 字符串或 policy 文件不是成功证据。

## 5. Human designation policy

Human review 不映射到 Multica Project role、CODEOWNERS、approval-provider 或 path-owner binding。operator 只维护一个 current authenticated Multica account email，并取得该 Human 的 explicit consent；该 designation 覆盖全部 required Human decision subjects。

notification recipient 是 participation plan 中解析到 current designation email 的投递地址，不是新的 selector 或 approval role。同一个 Agent/bot identity 不能作为 designated Human。designation/plan 缺失、撤销、email/member mismatch 或 Human 未明确同意时，相关 request 为 BLOCKED。

## 6. Multica 控制

### 6.1 Status contract

安装/dispatch 前由 workspace administrator 在 Multica Web 逐项核对：

| 语义 | Key | Category |
| --- | --- | --- |
| 等待维护者评估 | `needs_triage` | `backlog` |
| 等待可执行信息 | `needs_information` | `blocked` |
| 等待显式 Agent dispatch | `ready_for_agent` | `backlog` |
| 等待 Human 工作或决定 | `ready_for_human` | `todo` |
| 明确拒绝 | `wontfix` | `cancelled` |

核对后只需 Human 明确同意；不保存 Web screenshot、readback evidence ref 或独立 status artifact。发现旧 key、同 key 不同 category 或重复 display name 时记录 `STATUS_CONTRACT_DRIFT` 并停止 application。CLI 当前不承担 status definition 管理，不使用私有 API 或真实 Issue probe。

### 6.2 Effective Agent/Squad policy

- `shared-intake`：triage inspect/apply/readback 和显式 first dispatch；按 repository/work-item/work-type/epoch 原子创建唯一 WorkItemExecution；不得管理 workspace schema。
- `workflow-leader`：current Issue/run/execution/ledger/handoff/scope/lease/integration attempt/designation/plan/request/decision read，compare-and-set recording，以及 current plan 授权的 exact designated-Human member notification；不得 mention Agent/Squad/`@all`、assign、dispatch、rerun、cancel。无 ledger 原子 readback 时 concurrency=1。
- 其余 14 个 Agent：无直接 Multica access。
- Feature/Fix execution identities 和 Skills 零交叉。
- `shared-intake` 不加入 execution Squad。
- Loop maker/checker/guard all-or-none；checker 必须独立 identity/session，Loop state 只属于一个 execution。

应用后必须逐 Agent、逐 Squad、逐 Skill、逐 permission、逐 concurrency precondition readback；只读取列表摘要不足以证明 effective configuration。

### 6.3 Mention、notification、assignment 与 dispatch

- 普通 metadata/status/comment 更新不得触发 run；使用 provider 支持的 no-start 语义。
- Gate owner 先生成 current `HumanApprovalRequestRef`。Leader 必须先取得 atomic reservation，再依 current plan 发送一次 exact Human member mention；provider scheduler 最多触发两次 reminder。
- 每次通知前 readback request、designation、plan、decision、reservation、receipt、work item 和 active/queued runs；发送后保存 provider-native receipt。网络失败或 delivery unknown 时先 readback，不能盲目重试。
- Agent/Squad/`@all` mention、assignment、dispatch、rerun、cancel、recipient 猜测、无上限或重复 reminder 和把 delivery/timeout 当作 decision 均禁止。
- first dispatch 前原子检查 current/active/queued runs并创建唯一 execution epoch；`ready_for_agent` 不是 dispatch authorization。
- Human decision 只改变 gate eligibility 或返回唯一 owner，不得自动启动 Agent；resume/dispatch 仍需显式授权和 execution dedupe。

### 6.4 Human designation

安装者应用 `multica-orchestrator-kick-off` 的 Human designation/decision contracts，并将 [`../templates/human-participation-plan.template.yaml`](../templates/human-participation-plan.template.yaml) 复制到受限目录。portable package 不含实际 email/member/scheduler；operator 在副本中维护 current plan、email、explicit consent、recipient mapping、request、notification receipt 和 decision ledger。

`workflow-leader` 只消费 current designation/plan、subject 与 exact artifact revisions；不得选择/改变 email/member、发送 broad/ad-hoc mention、伪造 consent 或把通知/超时当作 approval。HumanDecisionRef 必须与 designation email 匹配；recipient ref 只用于投递。Agent、Squad、bot、CI 和 runtime identity 一律不能成为 Human。

普通新 Feature 在 `/speckit.specify` 前确认 designation/plan；初始化和重大调整在 governance-input 前确认；Fix 在 `/speckit.bug.assess` 前确认。无回复保持 `ready_for_human` 或 BLOCKED。

## 7. Checkout、branch 与 route 控制

Provider 在 Feature/Fix admission 后生成并持久化 `WorkItemBranchRef.v1`：Multica Issue UUID、canonical routable key/URL、normalized branch token、GitFlow branch role、creation base/target、base revision、stable integration branch/current head、branch policy、provider receipt 和 current 状态。

固定协作模式为 `default_worktree:true` 与 `execution_mode=worktree`：

- Human 选择一个 Foundation 已验证、声明 `local-worktree-v1` 的 collaboration Runtime；全部 16 个 Agent 固定到该 Runtime；
- Project 在该 Runtime daemon 上把现有 repository root 添加为唯一 `local_directory` resource，并显式设置 `worktree`；
- provider/Human 创建 stable integration branch：Feature 使用 `feature/<owner>/<branch-work-item-token>-<slug>`，Fix 使用 `fix/<owner>/<branch-work-item-token>-<slug>`，二者 creation base/target 均为 `develop`；
- 每次 dispatch 前 provider 把 clean local base 对齐 current integration head；Runtime 为该 Agent + Issue 创建或续接 task branch和独立 worktree，并由 run readback 生成 `RunCheckoutRef.v1`/`CheckoutRef.v5`；
- repository-writing Agent 只能在本 run task branch commit，不 push；policy verdict 后 provider 将 integration branch fast-forward 到 exact CommitRef。不同 Agent task branch 名称可不同，禁止自动 merge/cherry-pick；
- Release 使用 `release/<version>`，base=`develop`、target=`main`；Hotfix 使用 `hotfix/<owner>/<branch-work-item-token>-<slug>`，base/target=`main`；
- 同一 Work Item writer runs 串行；不同 Work Item 可在隔离 worktree 并行，但 WorkScope/ScopeConflictGate 和 repository-global leases 仍必须 current/CLEAR；
- Loop 若启用，effective `isolation:none` 并复用本 run 外层 worktree；禁止 nested worktree，Core/Loop route 在首次源码写入前由 Human 选择，first-write 后锁定。

source branch/head/root/route 变化使依赖 source 的 artifact/candidate/commit/review/approval stale。target head 单独前进只使 mergeability、proposed-merge CI、integration approval/readback 与 attempt stale；只有 scope/dependency/governance overlap 或验证失败时扩大失效。

### 7.1 Commit、PR 与 promotion boundary

Target repository 必须安装与 `conventional-commit` 一致的 commit-msg hook 和 PR commit-range validator。每个 ordinary 编队 commit 由 exact repository-writing Agent 在自己的 Runtime-managed run 内从 current execution/scope-bound `ChangesetCandidateRef` 产生，格式含唯一、最后的 `Work-Item: <canonical-Multica-Issue-key-or-URL>` footer。独立 `commit-policy-reviewer` 只读验证 producer run identity、Issue UUID/key mapping、candidate mapping、commit range、message/footer、hook 与 provider receipt。provider merge commit 是 IntegrationRef.v2 证明的 integration event，不伪造 ordinary commit footer。

Writer 只可 stage 本 run exact scope并创建普通 commit；禁止跨角色业务文件写入、push、merge、amend、rebase、reset、cherry-pick、force-push、branch/worktree mutation 和 `--no-verify`。Reviewer 不可写 Git index 或 commit。同一 Work Item writer runs 必须串行；每个 run branch/baseline 对齐 current integration head，verified CommitRef 由 provider fast-forward 到 stable integration branch。Runtime checkpoint 无 producer-owned `CommitRef.v2`/validator receipt 时不得进入下游。

Release/Hotfix 只在 primary `IntegrationRef.v2(target=main)`、required back-merge、tag receipt（适用时）和 MergeResolutionRef.v2 current 后，才能把 `PromotionRef` 标记为 `COMPLETE`。

## 8. 凭据与审计

- 不在 Agent/Squad Instructions、Issue、artifact、workflow ledger、日志或模板中写 secret value。
- secret binding 只声明用途、scope、consumer、expiry/rotation 和 audit ref。
- A01/A02 只获得其操作所需的最小 profile/workspace/repository scope。
- 任何 credential echo、CLI config dump 或错误堆栈泄漏都视为 `SECRET_SCOPE_VIOLATION`。
- 控制 readback 只能证明 binding metadata，不能读取 secret 本身。

## 9. 安装与 readback 顺序

1. Human 选择 target provider、repository、GitFlow dual-branch policy 和 integration operator。
2. 配置一个声明 `local-worktree-v1` 的 collaboration Runtime和 Project `local_directory(execution_mode=worktree)`；配置同一 Work Item one-active-writer admission、run checkout readback、atomic workflow ledger、scope registry/resource lease 和 repository-target integration queue。
3. Operator 记录 designated Human email/consent 并填写 plan；配置 atomic notification reservation、scheduler、stop conditions 和 receipt readback。
4. Repository maintainer 固定 test/lint/build commands 与 matrix。
5. 安装十二个 CI adapter，并读取实际 check names/触发器/权限。
6. 配置 stable integration branch provisioning、run 前 base alignment、verdict 后 fast-forward、人工 PR integration、commit hook/range validator、run-scoped Git state readback 和 approval persistence。
7. 消费 current parent-linked Server bundle、`ServerOrchestrationRef.v9`、
   current ServerVerificationSpec、`ServerReissueSpec.v1` 及 Foundation manifest lineage；
   确认 workspace status、Runtime fleet/capability revision、placement、
   Agent/Squad/Skill/permission readback current；不得在本阶段修补通用层。
8. 运行项目绑定只读验证；不得创建测试 Issue 或 dispatch。
9. 关联完成生成 `ProjectBindingRef.v9`、`RuntimeTargetPolicy.v3`、
   `ProjectVerificationSpec.v6`、`ProjectReissueSpec.v1` 与
   revision/native-dispatch-bound `ProjectReleaseCandidate.v8`；Nail Down 只在
   primary Runtime 验证 native Squad CLI capability、local-directory、closure 并发布
   `ACTIVE` release 后，后续显式 dispatch 才可另行评估。

## 10. 当前结论

本文件仍是 provider-neutral proposal。Target provider、execution/checkout isolation、atomic ledger/scope/lease/integration queue、Human designation/plan/notification reservation、CI commands、applied permissions 和 status confirmation 尚未提供，因此不能声称并发 dispatch、人工 integration、notification、approval、CI 或 Multica controls 已安装。