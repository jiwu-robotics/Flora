```yaml
coach_stage: W3
decision: ACCEPTED
source_project: capability-sample-robox-nexus
source_revision: git:d24411c8840bab361745c1ed7b41cf4b3a43b3e3+mapping:sha256:8ab657d28bbb9ac295dd7c3c12d6cf9e54b150a2b6f2b29d6af4b7ccdbe3b6b8
requirements_revision: sha256:3b6caab15839cd7489bf30c23f9598a45fa309a3ade7a6227597ab83cb237d94
input_artifacts:
  - analysis/w2-capability-rationalization.md#sha256:9cf7ee6b5ed3c2c3b9c8352f278e365f142fedd0ee34f52a14da4330021fc0fe
  - requirements/orchestration-requirements.md#sha256:3b6caab15839cd7489bf30c23f9598a45fa309a3ade7a6227597ab83cb237d94
decisions:
  default_worktree: false
  loop_eligible: true
  loop_isolation: none
  contract_schema_accepted: true
open_blockers: []
supersedes: contracts/handoff-gate-contracts.md#sha256:db92bac7630973139d4b7d4e279e8a97ebd2b7d0056b45b86edd355516163786
```

# Handoff、Gate 与共享状态合同

## 1. 合同目标

这些 schema 是 W3–W8 的唯一跨 Agent 数据语言。它们不创建新的产品文档 SSOT，也不替代 Spec Kit artifacts；只为已有文件、provider 对象、Human 决定和验证证据提供稳定引用、不可变 revision、路由与失效关系。

硬规则：

1. 每次 handoff 必须携带完整引用；Consumer 不得靠目录搜索、会话记忆或 Agent 名称猜输入。
2. `ArtifactRef` 的 `artifact_id` 表示逻辑身份；内容改变时创建新 revision，并通过 `supersedes` 指向旧 revision。
3. Producer 不能批准自己的输出。`GateRecord.evaluator_role` 必须与被评估 artifact 的 `producer_role` 不同；Human gate 除外，其 evaluator 必须是 Human。
4. Gate 值只有 `APPROVED`、`APPROVED_NA`、`REJECTED`、`BLOCKED`。这些值绝不是 Multica Issue status。
5. `REJECTED` 表示证据已足够且不满足门禁；`BLOCKED` 表示缺少外部信息、权限、环境、Human 决定或可执行证据。
6. 上游 revision 改变后，下游 `GateRecord` 不会自动继续有效；Leader 必须按 invalidation matrix 持久化 `invalidated_by` 并从最早受影响节点重判。source head 改变使 candidate/commit 链失效；target head 单独前进默认只使 integration evaluation、proposed-merge CI 与 integration approval/readback 失效。
7. 所有时间使用 UTC RFC3339。所有 actor、repository、Issue、comment、run 和 provider 引用使用 opaque locator；模板不得包含 live UUID、账号、server 或绝对机器路径。

## 2. 公共枚举

```yaml
work_type: feature | fix
branch_role: feature | fix | release | hotfix
artifact_state: CURRENT | SUPERSEDED | STALE | BLOCKED
execution_state: QUEUED | RUNNING | BLOCKED | COMPLETED | STALE | CANCELLED
run_checkout_state: ACTIVE | RELEASED | RETAINED_ON_FAILURE
gate_decision: APPROVED | APPROVED_NA | REJECTED | BLOCKED
handoff_state: READY | CONSUMED | STALE | BLOCKED
approval_subject: governance-input | constitution | architecture | adr | roadmap | tasks | implementation-route | loop-signoff | final-acceptance | risk-override
implementation_route: core | loop
loop_isolation: none
lease_mode: EXCLUSIVE_WRITE | APPEND_ONLY | READ_ONLY
resource_class: feature-local | fix-local | repository-global | integration-target
integration_attempt_state: WAITING | EVALUATING | READY | MERGING | INTEGRATED | STALE | BLOCKED
promotion_state: PENDING | COMPLETE | BLOCKED
```

## 3. ArtifactRef.v2

```yaml
schema: multica-coach.artifact-ref.v2
artifact_id: "<work_type>:<work_item_ref>:<artifact_kind>"
artifact_kind: "<stable-kind>"
work_type: feature | fix
work_item_ref: "<opaque Issue/PR/work item ref>"
execution_ref: "<current WorkItemExecutionRef>"
locator: "<repository-relative path or provider-opaque ref>"
revision: "<sha256/git/provider immutable revision>"
producer_role: "<exact role-key>"
produced_at: "<UTC RFC3339>"
state: CURRENT | SUPERSEDED | STALE | BLOCKED
source_refs:
  - "<ArtifactRef.v2 artifact_id@revision>"
evidence_refs:
  - "<command/report/diff/provider ref>"
supersedes: "<artifact_id@revision or null>"
```

### 检查

- `execution_ref`、`work_item_ref` 和 `work_type` 必须与生产该 artifact 的 ExecutionContextRef、LeaderDispatchRef、HandoffRef 和 CheckoutRef 一致。
- `locator` 必须唯一可解析；文件使用 repository-relative path。
- `revision` 必须不可变。mtime、自然语言“最新版”和会话 ID 不合格。
- `source_refs` 必须列出同一 execution 的直接输入，不列“整个仓库”这种不可判定范围。
- `evidence_refs` 只能引用实际观察结果，不能引用 Producer 自述。
- 同一 `artifact_id` 同时只能有一个 `CURRENT` revision；新 execution 不得复用旧 execution 的 CURRENT pointer。

`ArtifactRef.v1` 只可在显式 clean-upgrade 窗口只读消费，且必须由
execution-bound `HandoffRef.v3` 包装并能从全部 source refs 唯一证明 execution。
存在多个 epoch、缺失 source closure 或任何歧义时必须 BLOCKED；不得回写或就地
重解释 v1。

## 4. WorkItemBranchRef、RunCheckoutRef 与 CheckoutRef

```yaml
schema: multica-coach.work-item-branch-ref.v1
branch_id: "branch:<work_item_ref>:<sequence>"
repository_ref: "<opaque repository identity>"
work_item_ref: "<Multica Issue UUID>"
work_item_id: "<canonical routable Multica Issue key>"
work_item_url: "<canonical HTTPS URL or null>"
branch_work_item_token: "<branch-safe normalized Issue key>"
work_type: feature | fix
branch_role: feature | fix | release | hotfix
integration_branch_ref: "<provider-managed GitFlow remote branch>"
creation_base_ref: main | develop
target_ref: main | develop
creation_base_revision: "<immutable git revision>"
current_integration_head_revision: "<immutable current integration branch SHA>"
integration_target_revision: "<latest target SHA evaluated or null>"
branch_policy_ref: "<branch-and-commit-policy content digest>"
provider_ref: "<Project/Runtime/repository integration ref>"
approval_ref: "<HumanDecisionRef>"
state: CURRENT | STALE | REVOKED
created_at: "<UTC RFC3339>"
supersedes: "<branch_id or null>"
```

```yaml
schema: multica-coach.run-checkout-ref.v1
run_checkout_id: "run-checkout:<run_ref>"
execution_ref: "<current WorkItemExecutionRef.v4>"
run_ref: "<opaque Multica run ref>"
work_item_branch_ref: "<WorkItemBranchRef.v1 branch_id>"
runtime_ref: "<Runtime identity>"
daemon_ref: "<owning daemon identity>"
resource_ref: "<Project local-directory resource>"
execution_mode: worktree
root_locator: "<ephemeral Runtime-managed worktree root>"
cwd: "<exact project subpath within root>"
session_ref: "<Agent session identity>"
runtime_branch_ref: "<Multica-managed task branch from run readback>"
runtime_branch_ownership_ref: "<Multica hidden ownership ref/baseline readback>"
runtime_baseline_revision: "<Multica baseline commit>"
observed_branch_ref: "<actual branch>"
observed_head_revision: "<immutable SHA>"
state: ACTIVE | RELEASED | RETAINED_ON_FAILURE
observed_at: "<UTC RFC3339>"
```

```yaml
schema: multica-coach.checkout-ref.v5
checkout_id: "checkout:<work_item_ref>:<run_ref>"
work_item_branch_ref: "<WorkItemBranchRef.v1 branch_id>"
run_checkout_ref: "<RunCheckoutRef.v1 run_checkout_id>"
isolation: worktree
state: APPROVED | STALE | REVOKED
```

### 检查

- `work_item_ref` 必须是 Multica Issue UUID；`work_item_id` 必须是同一 Issue 的 canonical routable key，禁止 bare number。
- Feature/Fix handoff 必须绑定 CURRENT `WorkItemBranchRef.v1`、ACTIVE `RunCheckoutRef.v1`、`CheckoutRef.v5(isolation=worktree)` 和 Server handoff 指定 Runtime。
- Runtime branch 名称只能来自 Multica run readback，并允许不同 Agent/run 使用不同 task branch；integration branch 按 branch policy 在 Work Item 生命周期内稳定。
- 每次 dispatch 前，provider/Human 必须把 clean local-directory base 精确对齐 current integration head；run 的 baseline/observed HEAD 必须等于该 revision。producer CommitRef 验证后，provider 才可把 integration branch 快进到 exact commit。跨 Agent task branch 不自动 merge/cherry-pick。
- `root_locator`、cwd、session 和 runtime branch 按 run 隔离；它们跨 run 变化不使 immutable artifact stale。integration branch identity/head、runtime ownership/baseline、source lineage、work item 或 policy 变化使依赖 artifact stale。
- Runtime cleanup 后必须记录 `RELEASED`；无法保存未提交改动时记录 `RETAINED_ON_FAILURE` 并保持 execution BLOCKED。

## 5. ChangesetCandidateRef

```yaml
schema: multica-coach.changeset-candidate.v1
candidate_id: "candidate:<work_item_ref>:<sequence>"
work_item_ref: "<opaque work item ref>"
checkout_ref: "<CheckoutRef.v5 checkout_id>"
base_revision: "<immutable git revision>"
changed_path_digest: "<sha256>"
diff_digest: "<sha256>"
artifact_refs:
  - "<ArtifactRef.v2 artifact_id@revision>"
verification_refs:
  - "<actual test/lint/typecheck/smoke evidence>"
approved_scope_ref: "<task/route/scope ref>"
producer_handoff_ref: "<HandoffRef.v3>"
state: READY | STALE | REJECTED | COMMITTED
```

`candidate` 只表达可复算、scope-bound 的 working-tree change；它不代表 commit、review、CI、Human acceptance、push、PR 或 merge。unrelated dirty work 无法精确隔离时必须 BLOCKED。

## 6. CommitRef.v2

```yaml
schema: multica-coach.commit-ref.v2
commit_id: "<immutable git SHA>"
candidate_ref: "<ChangesetCandidateRef candidate_id>"
execution_ref: "<WorkItemExecutionRef.v4>"
producer_role: "<exact repository-writing manifest role-key>"
producer_run_ref: "<opaque Multica run ref>"
checkout_ref: "<CheckoutRef.v5 checkout_id>"
branch_ref: "<current Runtime-managed task branch identity>"
parent_revision: "<expected parent SHA>"
message_digest: "<sha256>"
work_item_footer:
  kind: id | url
  value: "<exact Work-Item footer value>"
  resolved_work_item_ref: "<canonical work item ref>"
commit_policy_ref: "<conventional-commit policy digest>"
validator_receipt_ref: "<hook/CI validator evidence>"
provider_run_receipt_ref: "<provider readback proving the run and resulting head>"
state: CURRENT | STALE | REJECTED
created_at: "<UTC RFC3339>"
```

每个会写 repository 的 Agent 必须在自己的 provider-managed run 结束前，先把本轮 exact scope 固化为 `ChangesetCandidateRef`，再使用 `conventional-commit` 创建一个普通 commit 和 `CommitRef.v2`。这样运行时收尾时工作树应已 clean；运行时自动生成但没有 producer-owned CommitRef、validator receipt 或正确 Work-Item footer 的 checkpoint commit 不得被下游消费。

`CommitRef.v2` 必须对应同一 execution、producer run、checkout、candidate、branch lineage 和 work item。footer 缺失、重复、非末尾或无法解析到 current work item时为 `COMMIT_POLICY_INVALID`。`commit-policy-reviewer` 只读验证 commit range，绝不 stage、commit、amend、rebase 或修复历史。新 commit 使消费旧 commit 的 review、CI、final acceptance 和相关 Human decision stale。

## 7. PullRequestRef

```yaml
schema: multica-coach.pull-request-ref.v2
pr_id: "<provider-opaque PR identity>"
repository_ref: "<opaque repository identity>"
checkout_ref: "<CheckoutRef.v5 checkout_id>"
source_branch: "<WorkItemBranchRef.v1 integration_branch_ref>"
target_ref: main | develop
source_head_revision: "<immutable SHA equal to current CommitRef>"
target_evaluation_revision: "<immutable target SHA at evaluation>"
work_item_refs:
  - "<canonical work item ref>"
required_check_refs:
  - "<provider/CI immutable receipt>"
approval_refs:
  - "<HumanDecisionRef or provider approval receipt>"
state: DRAFT | OPEN | MERGE_QUEUED | MERGED | CLOSED | STALE | BLOCKED
provider_readback_receipt_ref: "<provider-native immutable readback>"
```

`source_head_revision` 必须等于 current `CommitRef.commit_id`。source head 改变使 candidate/commit、review、CI、Human final acceptance 与 integration eligibility stale；target evaluation revision 单独前进默认只使 mergeability、proposed-merge checks、provider integration approval 与 `IntegrationAttemptRef` stale，除非 scope/dependency/governance overlap 或验证证据要求扩大失效。

## 7A. IntegrationAttemptRef

```yaml
schema: multica-coach.integration-attempt-ref.v1
attempt_id: "integration-attempt:<pr_id>:<sequence>"
repository_ref: "<opaque repository identity>"
target_ref: main | develop
work_item_ref: "<opaque work item ref>"
checkout_ref: "<CheckoutRef.v5 checkout_id>"
pull_request_ref: "<PullRequestRef pr_id>"
source_head_revision: "<current CommitRef SHA>"
target_revision: "<target SHA evaluated>"
scope_conflict_gate_ref: "<current ScopeConflictGateRef>"
required_check_refs:
  - "<receipt for the proposed merge revision>"
human_final_acceptance_ref: "<HumanDecisionRef>"
provider_integration_approval_ref: "<provider/Human receipt>"
queue_key: "integration:<repository_ref>:<target_ref>"
state: WAITING | EVALUATING | READY | MERGING | INTEGRATED | STALE | BLOCKED
created_at: "<UTC RFC3339>"
supersedes: "<attempt_id or null>"
```

同一 `queue_key` 同时最多一个 attempt 为 `EVALUATING`、`READY` 或 `MERGING`。不同 repository 可并行。target 前进使尚未集成的 attempt stale；重新比较 scope/dependencies 并在新 target revision 上运行 proposed-merge checks 后创建 superseding attempt。

## 8. IntegrationRef

```yaml
schema: multica-coach.integration-ref.v2
integration_id: "integration:<pr_id>:<merge_sha>"
pr_ref: "<PullRequestRef pr_id>"
integration_attempt_ref: "<IntegrationAttemptRef attempt_id>"
source_head_revision: "<PullRequestRef source_head_revision>"
target_revision: "<IntegrationAttemptRef target_revision>"
target_ref: main | develop
merge_revision: "<provider server merge commit SHA>"
merge_method: provider-merge-commit
merge_resolution_ref: "<MergeResolutionRef or null>"
check_receipt_refs:
  - "<baseline CI receipt>"
approval_receipt_refs:
  - "<provider Human approval receipt>"
provider_readback_receipt_ref: "<provider-native immutable merge readback>"
state: CURRENT | STALE | REJECTED
```

`IntegrationRef` 是已集成的唯一证明。它不同于 repository-writing Agent 创建的 ordinary commit，必须以 provider readback 验证 current attempt、PR source head、evaluated target revision、server merge method、八个 baseline check 收据、scope conflict state 与 Human approval。

## 9. PromotionRef 与 MergeResolutionRef

```yaml
schema: multica-coach.promotion-ref.v1
promotion_id: "promotion:<release-or-hotfix-ref>:<sequence>"
kind: release | hotfix
work_item_refs:
  - "<canonical work item ref>"
primary_integration_ref: "<IntegrationRef target=main>"
required_backmerge_refs:
  - "<IntegrationRef target=develop>"
  - "<IntegrationRef target=active-release or none>"
release_tag_ref: "<provider tag receipt>"
state: PENDING | COMPLETE | BLOCKED
```

```yaml
schema: multica-coach.merge-resolution-ref.v2
resolution_id: "merge-resolution:<pr-or-source-ref>:<target-ref>:<sequence>"
repository_ref: "<opaque repository identity>"
work_item_ref: "<opaque work item ref>"
source_ref: "<branch/ref>"
source_head_revision: "<immutable source SHA>"
target_ref: "<branch/ref>"
target_revision: "<immutable target SHA>"
conflicted_paths:
  - "<repository-relative path>"
resolution_diff_ref: "<immutable diff>"
resolution_class: mechanical | semantic
human_approval_ref: "<HumanDecisionRef or provider Human approval receipt>"
verification_refs:
  - "<actual evidence>"
provider_merge_receipt_ref: "<provider-native immutable readback>"
state: CURRENT | STALE | REJECTED
```

`PromotionRef` 只有所有 required back-merge、tag receipt（适用时）和 conflict-resolution evidence current 时才可为 `COMPLETE`。Feature/Fix integration conflict 也必须使用 `MergeResolutionRef.v2`：mechanical resolution 由 Human/provider 执行并重新验证；semantic resolution 返回 exact owning producer/maker role 生成新 candidate/commit。`commit-policy-reviewer` 和 execution Agent 均不执行 merge 或 resolution。

## 10. HumanDecisionRef

```yaml
schema: multica-coach.human-decision-ref.v4
decision_id: "human:<work_item_ref>:<subject>:<sequence>"
work_item_ref: "<opaque work item ref>"
execution_ref: "<current WorkItemExecutionRef>"
subject: governance-input | constitution | architecture | adr | roadmap | tasks | implementation-route | loop-signoff | final-acceptance | risk-override
human_designation_ref: "<HumanDesignationRef>"
human_participation_plan_ref: "<current HumanParticipationPlanRef>"
human_email: "<authenticated Multica account email from multica auth status>"
input_refs:
  - "<ArtifactRef.v2 artifact_id@revision>"
diff_or_evidence_refs:
  - "<actual diff/report/evidence ref>"
decision: ACCEPTED | REJECTED | REVISION_REQUESTED
reason: "<non-empty Human reason or acceptance scope>"
decided_at: "<UTC RFC3339>"
supersedes: "<decision_id or null>"
```

### 检查

- `human_email` 必须等于 `HumanDesignationRef` 中经明确同意且由 `multica auth status` 确认的登录账号 email；Agent、Squad、bot、CI 和 runtime identity 不合格。
- execution、designation、participation plan、subject 与全部 exact input revision 必须在 `decided_at` current；不匹配为 BLOCKED。
- 每个 subject 都需要独立决定；一个泛化 approval 不能覆盖其他治理、Tasks、route、Loop 或最终接受。
- 只有看到实际 artifact revision/diff 后的决定有效；对 proposal 的预先同意不等于接受生成结果。

## 11. HumanDesignationRef

```yaml
schema: multica-coach.human-designation-ref.v1
designation_id: "designation:<opaque-project-ref>:<sequence>"
project_ref: "<opaque target Project ref>"
scope: project | work-item
work_item_ref: "<opaque work item ref or null for project scope>"
human_email: "<authenticated Multica account email from multica auth status>"
consent: true
consented_at: "<UTC RFC3339>"
state: CURRENT | REVOKED | SUPERSEDED
supersedes: "<designation_id or null>"
```

### 检查

- authenticated Multica account email 与 explicit consent 是唯一 designation 前提；Multica Project Lead、workspace role 和 provider role binding 都不替代或扩大它。
- project-scope designation 在 Feature governance-input/Specify 和 Fix Assess 前必须 current；work-item override 必须有新的 explicit consent。
- revocation、email change、Brief/work type 或 scope change 使待处理请求 BLOCKED；已接受决定保持历史但不会覆盖新 revision。
- designation 与 HumanDecisionRef 由 workflow ledger append-only 持久化；Agent/Leader 不得创建、修改或伪造 consent。

## 12. ImplementationRouteRef


```yaml
schema: multica-coach.implementation-route-ref.v1
route_id: "route:<work_item_ref>:1"
work_item_ref: "<Feature work item ref>"
execution_ref: "<current WorkItemExecutionRef.v4>"
checkout_ref: "<CheckoutRef.v5 checkout_id>"
route: core | loop
selected_by: "<HumanDecisionRef subject=implementation-route>"
selected_at: "<UTC RFC3339>"
source_write_started: false
locked: true
loop_isolation: none
loop_contract_ref: "<ArtifactRef.v2 or null; required only for loop before run>"
state: CURRENT | ABANDONED
```

### 检查

- 每个 Feature 恰好一个 `CURRENT` route。
- `route=core` 时 `loop_contract_ref=null`；`route=loop` 时首次 maker write 前必须非空。
- 第一次源码修改后将 `source_write_started=true`。此后不得把同一 checkout/change 切换到另一 route。
- 若 Human 必须改 route，先将原 route 和 checkout 标为 `ABANDONED/REVOKED`，保留证据，并用新的 work item/checkout 从受影响的最早节点重启；不得把半成品交给另一 writer。

## 13. HumanParticipationPlanRef、HumanApprovalRequestRef 与 HumanNotificationReceipt

Portable template 由 `multica-orchestrator-nail-down` 的 `templates/human-participation-plan.template.yaml` 提供。template 只能保存 portable schema 和占位值；填写后的 plan、member ref、email、notification receipt 与 scheduler ref 必须位于受限 operator-local state directory。

```yaml
schema: multica-coach.human-participation-plan-ref.v1
plan_id: "participation:<opaque-project-ref>:<sequence>"
project_ref: "<opaque target Project ref>"
scope: project | work-item
work_item_ref: "<opaque work item ref or null for project scope>"
human_designation_ref: "<current HumanDesignationRef>"
notification_recipient_ref: "<operator-local Multica member ref>"
notification_channel: multica-member-mention
notification_actor: workflow-leader
reminder_scheduler_ref: "<operator-local provider scheduler ref>"
decision_routing_mode: explicit-resume-or-dispatch
state: CURRENT | REVOKED | SUPERSEDED
supersedes: "<plan_id or null>"
```

```yaml
schema: multica-coach.human-approval-request-ref.v2
request_id: "approval-request:<work_item_ref>:<subject>:<sequence>"
work_item_ref: "<opaque work item ref>"
execution_ref: "<current WorkItemExecutionRef>"
subject: governance-input | constitution | architecture | adr | roadmap | tasks | implementation-route | loop-signoff | final-acceptance | risk-override
human_participation_plan_ref: "<current HumanParticipationPlanRef>"
human_designation_ref: "<current HumanDesignationRef>"
input_refs:
  - "<ArtifactRef.v2 artifact_id@revision>"
diff_or_evidence_refs:
  - "<actual diff/report/evidence ref>"
required_action: "<one concrete Human action>"
dedupe_key: "<project + work-item + execution + subject + designation + plan + sorted input revisions>"
notification_reservation_state: UNRESERVED | RESERVED | SENT | FAILED
state: CURRENT | DECIDED | STALE | CANCELLED
created_at: "<UTC RFC3339>"
supersedes: "<request_id or null>"
```

```yaml
schema: multica-coach.human-notification-receipt.v1
notification_id: "notification:<request_id>:<attempt>"
request_ref: "<current HumanApprovalRequestRef>"
attempt: 0 | 1 | 2
kind: INITIAL | REMINDER
actor_role: workflow-leader
recipient_ref: "<member ref resolved by current participation plan>"
provider_receipt_ref: "<provider-native comment/notification readback>"
sent_at: "<UTC RFC3339>"
delivery_state: DELIVERED | FAILED | UNKNOWN
state: CURRENT | STALE
```

### 检查

- `notification_recipient_ref` 只是通知地址，不是第二套 Human selector。它必须解析到 current designation 的 authenticated email；决定权仍只来自 `HumanDesignationRef` 与 `HumanDecisionRef`。
- Gate owner 在单一 HandoffRef 中提供 exact revisions、actual diff/evidence、一个 concrete Human action 和 typed external actor refs；`workflow-leader` 校验后才以原子 compare-and-set 记录 current `HumanApprovalRequestRef`。无 Multica recording 权限的 execution Agent 不得自行创建 ledger ref。
- `workflow-leader` 记录 request 后才可自动发送首次 exact designated Human member mention；该 notification comment 不得 mention Agent、Squad 或 `@all`。reminder 只由 plan 中的 typed scheduler ref 触发；每次发送前必须 readback current request、designation、decision 和已有 receipt。
- Human/provider-native decision record 是 `HumanDecisionRef` 的唯一来源；Leader 只 readback、验证并持久化引用，Guard 或其他 Agent 不得创建、签署或改写决定。已有 current decision、request stale、designation 改变或达到上限时不得发送。
- provider delivery/readback 只证明通知尝试，绝不等于 consent、decision 或 approval。失败/未知状态先 readback；禁止盲目重试。`ACCEPTED` 只使 exact downstream gate eligible；notification event 不得自动 dispatch、rerun 或 resume；Human comment 重触发 Leader 后仍须重验并显式创建 dispatch。

## 13A. RunAdmissionRef.v1

`multica-orchestrator-dispatch` creates the only admission authority for a real
Feature/Fix execution. A workflow-leader native bootstrap invokes the verified
local facade with only profile, Workspace selector and canonical Issue. The
facade resolves the exact assigned Squad, ACTIVE release, Runtime and unique
running Leader run before persisting this artifact:

```yaml
schema: multica-orchestrator-dispatch.run-admission-ref.v1
admission_ref: "<opaque admission ref>"
execution_ref: "<WorkItemExecutionRef.v4>"
project_key: "<Project key digest>"
project_ref: "<exact Project ref>"
repository_ref: "<exact repository ref>"
active_release_digest: "<ACTIVE Project release digest>"
project_binding_digest: "<ProjectBindingRef.v12 artifact digest>"
dispatch_contract_digest: "<Dispatch contract digest from ProjectBindingRef.v12>"
runtime_alias: "<selected activated Runtime alias>"
work_item_ref: "<canonical Multica Issue UUID>"
work_item_id: "<canonical routable Issue key>"
work_item_url: "<canonical Issue URL or null>"
work_type: feature | fix
squad_ref: "<exact immutable Feature/Fix Squad ref>"
leader_ref: "<exact immutable workflow-leader Agent ref>"
epoch: "<positive integer>"
state: ACTIVE
created_at: "<UTC RFC3339>"
admission_digest: "<digest of every preceding field>"
```

相同 `repository_ref + work_item_ref` 同时只能有一个 `ACTIVE` admission。
Project binding、ACTIVE release、Dispatch contract、Runtime capability、
Squad/Leader generation 或 work type 任一变化必须 BLOCKED；不得由 intake 手填、
就地改写或自动结束旧 execution。admission 只建立 local execution identity；
不表示首次启动、Human gate 或 member dispatch 已获授权。

## 13B. WorkItemExecutionRef.v4

```yaml
schema: multica-coach.work-item-execution-ref.v4
execution_id: "execution:<work_item_ref>:<epoch>"
repository_ref: "<opaque repository identity>"
work_item_ref: "<Multica Issue UUID>"
work_item_id: "<canonical routable Multica Issue key>"
work_type: feature | fix
workflow_epoch: "<positive integer>"
squad_ref: "<exact feature/fix Squad ref>"
leader_ref: "<exact workflow-leader Agent ref>"
issue_assignee_ref: "<current Squad assignee ref>"
active_release_ref: "<ActiveProjectReleaseRef>"
run_admission_ref: "<RunAdmissionRef.v1>"
work_item_branch_ref: "<WorkItemBranchRef.v1 or null while QUEUED>"
current_run_checkout_ref: "<RunCheckoutRef.v1 or null outside an active run>"
source_head_revision: "<WorkItemBranchRef current source head or null while QUEUED>"
state: QUEUED | RUNNING | BLOCKED | COMPLETED | STALE | CANCELLED
created_at: "<UTC RFC3339>"
supersedes: "<execution_id or null>"
```

同一 `repository_ref + work_item_ref` 同时只能有一个 current execution。`QUEUED`
允许 branch/run checkout/source head 为 `null`；Runtime 领取后必须从实际 resource/run
readback 固化 `WorkItemBranchRef.v1` 与 `RunCheckoutRef.v1`，才能进入 `RUNNING`、
生成 path-derived artifact 或调用 execution member。

每个 Agent run 必须具有独立 root、cwd、session 和 temporary state；同一 Work Item
同时最多一个 writer run。不同 Work Item 只有在 `ScopeConflictGate=CLEAR` 且所需
repository-global lease 无冲突时，才可在同一 repository 的不同 worktree 并行。

`WorkItemExecutionRef.v1/v2/v3` 只可在 clean upgrade 中读取；旧记录不得进入新的
worktree dispatch。升级器必须补齐 Issue UUID/key、branch ownership、Runtime baseline
和 run checkout lineage；无法唯一补齐时保持 `BLOCKED_CONTRACT_UPGRADE`。
## 13C. WorkScopeRef 与 ScopeConflictGateRef

```yaml
schema: multica-coach.work-scope-ref.v1
scope_id: "scope:<work_item_ref>:<sequence>"
repository_ref: "<opaque repository identity>"
work_item_ref: "<opaque work item ref>"
work_type: feature | fix
execution_ref: "<WorkItemExecutionRef.v4>"
checkout_ref: "<CheckoutRef.v5>"
based_on_refs:
  - "<Tasks acceptance or FixAssessment revision>"
read_paths:
  - "<repository-relative path or bounded glob>"
write_paths:
  - "<repository-relative path or bounded glob>"
logical_resources:
  - resource_key: "<canonical repository/resource key>"
    mode: READ | WRITE | APPEND
    class: feature-local | fix-local | repository-global | integration-target
unknown_dynamic_paths: false
approved_by_ref: "<Gate or Human decision>"
state: CURRENT | SUPERSEDED | STALE | BLOCKED
created_at: "<UTC RFC3339>"
supersedes: "<scope_id or null>"
```

```yaml
schema: multica-coach.scope-conflict-gate-ref.v1
gate_id: "scope-conflict:<work_item_ref>:<sequence>"
repository_ref: "<opaque repository identity>"
work_item_ref: "<opaque work item ref>"
scope_ref: "<current WorkScopeRef>"
compared_active_scope_refs:
  - "<other current WorkScopeRef>"
result: CLEAR | SERIALIZE | DEPENDS_ON | HUMAN_DECISION_REQUIRED | BLOCKED
conflicts:
  - resource_key: "<canonical resource>"
    conflicting_work_item_ref: "<other work item>"
    reason: "<path/resource/dependency conflict>"
resolution:
  strategy: parallel | wait-for-integration | explicit-dependency | split-scope | cancel
  dependency_ref: "<work item/integration ref or null>"
state: CURRENT | STALE | SUPERSEDED
created_at: "<UTC RFC3339>"
```

Feature 在 Tasks acceptance 后、route decision 前发布 scope；Fix 在 Assessment=`fixable` 后、Maker 前发布。`CLEAR` 才可并行写入；`SERIALIZE/DEPENDS_ON` 等待指定 current `IntegrationRef` 或 lease release；动态/未知写路径必须扩大 resource lease 或保持 BLOCKED。Constitution、Architecture、Roadmap、同一 ADR、依赖锁、migration 序列、共享 API/schema 与 target integration 使用 repository-global resource key。


## 14. GateRecord.v2

```yaml
schema: multica-coach.gate-record.v2
gate_id: "gate:<work_item_ref>:<gate_kind>:<sequence>"
gate_kind: "<stable gate kind>"
work_type: feature | fix
work_item_ref: "<opaque work item ref>"
execution_ref: "<current WorkItemExecutionRef.v4>"
input_refs:
  - "<ArtifactRef.v2 artifact_id@revision>"
evaluator_role: "<exact role-key or human-authority>"
decision: APPROVED | APPROVED_NA | REJECTED | BLOCKED
checks:
  - check_id: "<stable check id>"
    result: PASS | FAIL | NOT_APPLICABLE | BLOCKED
    evidence_refs:
      - "<actual evidence ref>"
    reason: "<required for non-PASS>"
blocker_refs:
  - "<typed waiting actor/system/permission/environment ref>"
decided_at: "<UTC RFC3339>"
valid_for_revisions:
  - "<artifact_id@revision>"
state: CURRENT | STALE | SUPERSEDED
invalidated_by: "<new artifact_id@revision or null>"
supersedes: "<gate_id or null>"
```

### 检查

- `execution_ref` 必须与全部 inputs、evidence、HandoffRef、ExecutionContextRef 和 LeaderDispatchRef 一致。
- `decision=APPROVED`：每个 required `checks[].result=PASS`，且无 blocker。
- `decision=APPROVED_NA`：仅在整个 gate 对该 work item 不适用时使用，必须有客观 N/A reason；不能用来跳过失败检查。
- `decision=REJECTED`：至少一个 required `checks[].result=FAIL`，证据足以返回一个 exact producer role。
- `decision=BLOCKED`：至少一个 `checks[].result=BLOCKED` 或 blocker_ref 非空，必须写明 typed waiting actor 和恢复条件。
- Gate 必须绑定精确 revisions；只写文件路径不合格。`state=STALE` 不是 decision，`PASS` 不是 GateRecord decision。
- Producer、maker 或 Squad Leader 不能把自己的输出标为 `decision=APPROVED`。

`GateRecord.v1` 只可在 clean upgrade 中只读消费，且必须由同一 execution 的
HandoffRef 包装；不能唯一证明 execution 时必须重新评估为 v2，不得复制旧 decision。

## 15. HandoffRef.v3

```yaml
schema: multica-coach.handoff-ref.v3
handoff_id: "handoff:<work_item_ref>:<from_role>:<to_role>:<sequence>"
work_type: feature | fix
work_item_ref: "<opaque work item ref>"
execution_ref: "<WorkItemExecutionRef.v4 or null before admission>"
from_role: "<exact producer/orchestrator role-key>"
to_role: "<single exact consumer role-key>"
artifact_refs:
  - "<ArtifactRef.v2 artifact_id@revision>"
gate_refs:
  - "<GateRecord.v2 gate_id>"
checkout_ref: "<CheckoutRef.v5 checkout_id or null before checkout binding>"
scope_ref: "<WorkScopeRef or null before scope declaration>"
scope_conflict_gate_ref: "<ScopeConflictGateRef or null before conflict evaluation>"
route_ref: "<ImplementationRouteRef route_id or null>"
changeset_candidate_ref: "<ChangesetCandidateRef candidate_id or null>"
commit_ref: "<CommitRef commit_id or null>"
pull_request_ref: "<PullRequestRef pr_id or null>"
integration_attempt_ref: "<IntegrationAttemptRef attempt_id or null>"
integration_ref: "<IntegrationRef integration_id or null>"
promotion_ref: "<PromotionRef promotion_id or null>"
human_designation_ref: "<HumanDesignationRef or null before designation>"
human_participation_plan_ref: "<HumanParticipationPlanRef or null before plan activation>"
human_approval_request_ref: "<HumanApprovalRequestRef or null when no Human action is required>"
required_action: "<one concrete next action>"
state: READY | CONSUMED | STALE | BLOCKED
created_at: "<UTC RFC3339>"
consumed_at: "<UTC RFC3339 or null>"
blocker_refs:
  - "<typed ref>"
supersedes: "<handoff_id or null>"
```

### 检查

- `to_role` 必须唯一且使用 manifest role key。执行成员的完成 Handoff 默认
  `to_role=workflow-leader`；成员不得直接 mention、assign、dispatch、rerun 或
  cancel 下一角色。
- `state=READY` 要求所有 required GateRecord 为 `state=CURRENT` 且
  `decision=APPROVED|APPROVED_NA`。
- Consumer 开始前必须核对 execution、artifact revision、checkout、scope、
  scope-conflict、route、gate、Squad 和 run-admission state；不一致则写
  `STALE/BLOCKED`，不执行。
- Handoff 只表达 next-stage eligibility。真正的 member run 由 Leader 的 exact
  roster mention 触发，并由 provider run readback 证明。

`HandoffRef.v1/v2` 只可在 clean upgrade 中读取；新 native Squad execution
只能生成 v3。

## 15A. ExecutionContextRef.v1

每个 Agent 在 run claim 后，根据 Multica native run context 和 current Project
binding 固化唯一执行上下文：

```yaml
schema: multica-coach.execution-context-ref.v1
context_id: "run-context:<provider_run_ref>"
provider_run_ref: "<opaque Multica run ref>"
trigger_kind: direct-intake | squad-assignment | squad-mention | leader-mention | member-result | human-comment | stage-barrier
trigger_ref: "<opaque assignment/comment/barrier ref>"
trigger_comment_ref: "<opaque comment ref or null>"
work_item_ref: "<opaque work item ref>"
work_type: unclassified | feature | fix
execution_ref: "<WorkItemExecutionRef.v4 or null only for pre-admission shared-intake or workflow-leader bootstrap>"
squad_ref: "<exact Squad ref or null only for pre-admission shared-intake or workflow-leader bootstrap>"
leader_ref: "<exact workflow-leader Agent ref or null only for pre-admission shared-intake or workflow-leader bootstrap>"
agent_ref: "<exact current Agent ref>"
role_key: "<single exact manifest role-key>"
checkout_ref: "<CheckoutRef.v5 or null only for pre-checkout operations>"
root_locator: "<approved root or null only for pre-checkout operations>"
session_ref: "<unique provider session ref>"
project_binding_ref: "<ProjectBindingRef.v12 or null before Project binding>"
project_binding_digest: "<ProjectBindingRef.v12 artifact digest or null before Project binding>"
active_release_ref: "<ActiveProjectReleaseRef or null before Project activation>"
active_release_digest: "<ACTIVE Project release digest or null before Project activation>"
run_admission_ref: "<RunAdmissionRef.v1 or null only for pre-admission shared-intake or workflow-leader bootstrap>"
run_admission_digest: "<RunAdmissionRef.v1 admission digest or null only for pre-admission shared-intake or workflow-leader bootstrap>"
state: CURRENT | STALE | BLOCKED
created_at: "<UTC RFC3339>"
```

`workflow-leader` 只把 `squad-assignment|member-result|human-comment|stage-barrier|squad-mention`
解释为自己的 evaluation trigger。`shared-intake` 的 pre-admission run 只接受明确寻址到
本 Agent 的 `direct-intake`；作为 Squad member 时与其他 ordinary member 一样，只接受
`leader-mention`。所有 ordinary member 的 current trigger comment 必须携带一个精确指向
本 Agent/role 的 `LeaderDispatchRef.v1`。comment-triggered run 必须回复在
`trigger_comment_ref` 下；无 comment trigger 时才可发顶层结果。

## 15B. LeaderDispatchRef.v1、LeaderDispatchSetRef.v1 与 ProviderRunReceiptRef.v1

```yaml
schema: multica-coach.leader-dispatch-ref.v1
dispatch_id: "dispatch:<work_item_ref>:<to_role>:<operation_key>:<sequence>"
work_item_ref: "<opaque work item ref>"
work_type: feature | fix
execution_ref: "<WorkItemExecutionRef.v4>"
squad_ref: "<exact current Squad ref>"
leader_ref: "<exact workflow-leader Agent ref>"
leader_run_ref: "<current Leader provider run ref>"
to_role: "<single exact manifest member role-key>"
to_agent_ref: "<exact current roster Agent ref>"
operation_key: "<one role-allowed operation key>"
handoff_ref: "<single HandoffRef.v3>"
input_refs:
  - "<exact immutable input ref>"
required_gate_refs:
  - "<GateRecord.v2 gate_id>"
expected_output_kind: "<one exact artifact/record kind>"
write_scope_ref: "<WorkScopeRef or null for read-only/pre-scope operation>"
lease_refs:
  - "<active LeaseRecord.v2 ref>"
issue_revision: "<provider issue/comment snapshot revision>"
dedupe_key: "<execution + target + operation + handoff + sorted input revisions digest>"
state: READY | CONSUMED | STALE | BLOCKED
created_at: "<UTC RFC3339>"
```

```yaml
schema: multica-coach.leader-dispatch-set-ref.v1
dispatch_set_id: "dispatch-set:<work_item_ref>:<leader_run_ref>"
execution_ref: "<WorkItemExecutionRef.v4>"
leader_run_ref: "<current Leader provider run ref>"
dispatch_refs:
  - "<one LeaderDispatchRef.v1 per mentioned Agent>"
state: READY | CONSUMED | STALE | BLOCKED
created_at: "<UTC RFC3339>"
```

```yaml
schema: multica-coach.provider-run-receipt-ref.v1
dispatch_ref: "<LeaderDispatchRef.v1>"
trigger_comment_ref: "<provider comment ref>"
target_agent_ref: "<exact mentioned Agent ref>"
provider_run_ref: "<opaque run ref or null when not enqueued>"
enqueue_outcome: ENQUEUED | DEDUPED | REJECTED | UNKNOWN
observed_at: "<UTC RFC3339>"
```

```yaml
schema: multica-coach.member-result-ref.v1
result_id: "member-result:<provider_run_ref>"
dispatch_ref: "<LeaderDispatchRef.v1>"
execution_context_ref: "<ExecutionContextRef.v1>"
handoff_ref: "<HandoffRef.v3 to_role=workflow-leader>"
outcome: SUCCEEDED | BLOCKED | FAILED
artifact_refs:
  - "<exact output ref>"
gate_refs:
  - "<GateRecord.v2 ref>"
next_owner_role: "<exact manifest role-key or null>"
external_actor_ref: "<typed external actor ref or null>"
required_action: "<one concrete next action or null>"
reply_to_comment_ref: "<trigger comment ref>"
observed_at: "<UTC RFC3339>"
```

MemberResultRef 只回报事实与 next owner，不是 dispatch。`next_owner_role` 与
`external_actor_ref` 最多一个非空；成员不得用结果 comment mention 该 owner。

Leader 每个 turn 只做一次协调决定：

1. 验证 native Squad context、current execution、Gate、revision、scope、lease、
   access、admission 和已有 queued/running run。
2. 需要派活时只发一条 delegation comment，复制 roster 提供的 exact mention
   markdown，并为每个被 mention Agent 建立一个独立 dispatch/Handoff。随后记录
   `multica squad activity <issue> action` 并停止。
3. 无需派活时记录 `no_action`；错误记录 `failed`。禁止为了观察状态制造 mention。
4. 成员回报不 mention 下一 Agent；Multica 自动重触发 Leader，由 Leader 决定下一步。
5. Human Gate 只在 exact `HumanDecisionRef` current 后开放后继边。native trigger
   本身不等于 Gate、Human decision 或业务授权。

### Role operation keys

| `to_role` | Allowed `operation_key` |
| --- | --- |
| `shared-intake` | `triage-inspect`, `triage-apply`, `squad-bind`, `reclassify` |
| `workflow-leader` | `coordinate-trigger`, `validate-handoff`, `record-gate`, `record-scope-lease`, `record-invalidation`, `notify-human`, `record-lifecycle` |
| `feature-governance-producer` | `governance-draft`, `roadmap-write`, `adr-draft` |
| `feature-requirement-producer` | `specify`, `clarify-spec` |
| `feature-requirement-reviewer` | `requirement-check` |
| `feature-planning-producer` | `adr-context`, `plan`, `tasks` |
| `feature-reviewer` | `adr-check`, `analyze`, `roadmap-sync`, `roadmap-brief`, `roadmap-debrief` |
| `feature-core-maker` | `implement-core` |
| `feature-loop-maker` | `loop-define`, `loop-iterate`, `loop-status` |
| `feature-loop-checker` | `loop-check`, `loop-status-read` |
| `feature-loop-guard` | `loop-guard` |
| `feature-convergence-reviewer` | `converge` |
| `fix-assessor` | `fix-assess` |
| `fix-maker` | `fix-implement` |
| `fix-verifier` | `fix-verify` |
| `commit-policy-reviewer` | `verify-commit` |

`workflow-leader` 的 operation 只来自 Multica native leader trigger，不得作为 `LeaderDispatchRef.to_role`；其余表项只可由 Leader 对 current roster member 的 exact mention 派发。

### Native Squad trigger and consumption rules

1. `shared-intake` 可在 Backlog 中以 `--no-start` 预绑定 exact Squad；只有一次
   Human-authorized Backlog-to-todo 状态变更可以启动首次 Leader run。
2. Leader 只可 mention 当前 roster 中的 Agent。delegation comment 不得 mention
   Human、Squad 或 `@all`；Human notification comment 只可 mention exact
   designated Human，不能同时派活。
3. 每个 execution member run 只消费一个 `state=READY` dispatch，并只执行一个
   role-allowed `operation_key`。fan-out 集合中每个 Agent 只读取 `to_agent_ref`
   等于自己的记录。
4. 调用去重键为 `execution_ref + to_agent_ref + operation_key + handoff_ref +
   sorted input revisions`。Multica native dedupe 不能替代 ledger 中的业务去重。
5. 成员不得链式调用成员。Leader 的 own comment 不应自触发；成员无 mention 的
   回报、Human comment 和 stage barrier 可重触发 Leader，但只产生 evaluation
   eligibility。
6. Leader 最多把实际归本 Squad 的父 Issue 推到 `in_review`；`done` 仅由 Human
   或既有 integration 设置。`@squad` 临时唤醒到其他 assignee 的 Issue 时不得改状态。

7. Collaboration Runtime 必须证明所有 repository-writing members 与 `commit-policy-reviewer` 命中支持 `local-worktree-v1` 的同一 Runtime，且 Project local-directory 为 `execution_mode=worktree`。每次 dispatch 前必须核对 current Work Item、integration branch/head、Runtime task branch baseline、run root/cwd/session、HEAD 与上一 `CommitRef.v2`；不同 Work Item 可在隔离 worktree 中并行，但同一 Work Item writer 串行，且 scope/lease 冲突仍立即 `BLOCKED`。

## 16. LeaseRecord.v2

```yaml
schema: multica-coach.lease-record.v2
lease_id: "lease:<repository_ref>:<resource-key>:<sequence>"
repository_ref: "<opaque repository identity>"
work_item_ref: "<opaque work item ref>"
execution_ref: "<WorkItemExecutionRef.v4>"
checkout_ref: "<CheckoutRef.v5>"
artifact_ref: "<ArtifactRef.v2 current revision or null before first write>"
resource_key: "<canonical logical resource>"
holder_role: "<role-key>"
holder_run_ref: "<provider run ref>"
mode: EXCLUSIVE_WRITE | APPEND_ONLY | READ_ONLY
scope: "<exact relative path or provider object>"
expected_revision: "<revision at acquisition>"
acquired_at: "<UTC RFC3339>"
release_condition: "<deterministic condition>"
state: ACTIVE | RELEASED | REVOKED | STALE
released_at: "<UTC RFC3339 or null>"
supersedes: "<lease_id or null>"
```

Lease acquisition 必须以 `repository_ref + resource_key` 原子 compare-and-set。`EXCLUSIVE_WRITE` 与任何 active writer 冲突；`APPEND_ONLY` 只有存储支持原子 append 且 scopes 不重叠时才能并发；READ/WRITE 冲突按 provider policy 阻塞。不能只因 wall-clock timeout 抢锁，必须 read back holder run terminal/cancelled、当前 revision 和无 active writer，再由 provider/Human revoke。

### `tasks.md` 特例

- `speckit-tasks` 获得 path-scoped `EXCLUSIVE_WRITE` lease，生成/重新生成后释放。
- Human Review 和 `speckit-analyze` 只持有 `READ_ONLY`。
- `speckit-converge` 只能在其他 write lease 已释放后获得 `APPEND_ONLY`，只追加新 Convergence phase。
- Convergence append 产生新的 Tasks revision，自动使旧 Tasks Human Review、Analyze、Roadmap Brief 和 implementation-completion gates 失效；必须重新 Human Review 和 Analyze。

## 17. LoopStateRef

```yaml
schema: multica-coach.loop-state-ref.v1
loop_id: "loop:<work_item_ref>:1"
work_item_ref: "<Feature work item ref>"
route_ref: "<ImplementationRouteRef route=loop>"
contract_ref: "<ArtifactRef.v2 LOOP_CONTRACT revision>"
state_root: "<repository-relative state directory under approved checkout>"
iteration: 0
max_iterations: "<positive integer>"
latest_maker_ref: "<ArtifactRef.v2 or null>"
latest_checker_ref: "<ArtifactRef.v2 or null>"
open_debt_refs:
  - "<debt ref>"
human_signoff_ref: "<HumanDecisionRef or null>"
status: DEFINED | MAKER_READY | CHECKER_READY | HUMAN_GUARD | DONE | BLOCKED | EXHAUSTED
updated_at: "<UTC RFC3339>"
```

### 检查

- `state_root` 必须位于 `CheckoutRef.root_locator` 对应的 Feature artifact root；`loop_isolation` 固定 `none`。
- iteration 不得超过 max_iterations。
- Maker revision 改变立即使旧 checker verdict 和 Human sign-off 失效。
- `DONE` 同时要求 latest checker APPROVED、无 blocking debt、Human sign-off ACCEPTED。

## 18. 失效传播算法

Leader 对每次新 revision 执行：

1. 找到所有直接引用旧 revision 的 ArtifactRef、GateRecord、HandoffRef、HumanDecisionRef、Route/Loop state。
2. 将 Gate/Handoff 标为 `STALE`，记录 `invalidated_by=<new revision>`；不得覆盖旧记录。
3. 沿依赖边传递，直到没有新的下游引用。
4. 返回最早拥有修复权的 Producer；若需要 Human 或外部系统，记录 `BLOCKED` 和恢复条件。
5. 重判产生新 GateRecord，通过 `supersedes` 关联旧记录。
6. 只有全部 required downstream gates 重新有效后，Leader 才能记录 next-stage eligibility；随后必须在新的 native Squad turn 重验 scope、lease、admission 和 run dedupe，再决定是否生成新的 LeaderDispatchRef 并 mention exact roster member。

## 19. 持久化边界

- Spec Kit 文件产物：使用 repository-relative path + content SHA-256 或 git object/revision。
- Multica Issue/Brief/comment/run：使用 provider 返回的 opaque ref；写后 readback。
- Gate/Handoff/Route/Lease：由 W7 Squad instructions 指定的单一 workflow ledger 持久化接口写入，不能只留在聊天上下文。
- Human 决定：必须由 workspace member identity 或批准系统的 Human approval record 证明；Agent 转述不合格。
- 本文件只定义期望 schema，不声明 provider 已支持或部署这些对象。
