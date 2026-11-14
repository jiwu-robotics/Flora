```yaml
coach_stage: W5
decision: ACCEPTED
source_project: capability-sample-robox-nexus
source_revision: git:d24411c8840bab361745c1ed7b41cf4b3a43b3e3+mapping:sha256:8ab657d28bbb9ac295dd7c3c12d6cf9e54b150a2b6f2b29d6af4b7ccdbe3b6b8
requirements_revision: sha256:3b6caab15839cd7489bf30c23f9598a45fa309a3ade7a6227597ab83cb237d94
input_artifacts:
  - analysis/w4-feature-fix-dags.md#sha256:dbd02ee0e78cf2881e2ecd0931d773a836a5183c072c08baa4e9df035ca63673
  - analysis/w3-artifact-dependencies.md#sha256:f0f7748d0017b0424bd444654e923584d12abb2cc4980b6161a5c7d385d5caeb
  - contracts/handoff-gate-contracts.md#sha256:eef42b00a7630f5c801d87fe0bce9403fb09cea8f5625df7f72e0bcfc8c7cfbd
  - requirements/orchestration-requirements.md#sha256:3b6caab15839cd7489bf30c23f9598a45fa309a3ade7a6227597ab83cb237d94
decisions:
  default_worktree: false
  loop_eligible: true
  loop_isolation: none
  agent_roster_accepted: true
open_blockers: []
supersedes: analysis/w5-agent-responsibility-matrix.md#sha256:13ee5468df395ec04425c79929a5d60cff78eaa9612c6693b826cb55a0dea55e
```

# W5 Agent 责任矩阵

## 1. 本步骤结论

从 W3 artifact ownership 与 W4 独立判断点派生 16 个唯一 Agent role key：

- 3 个共享中立角色；
- 10 个 Feature-only 角色，其中 3 个只在 Loop route 启用；
- 3 个 Fix-only 角色；
- Human Authority、Project/Runtime 和 CI/provider control 是外部权威，不伪装成 Agent。

Feature Squad 与 Fix Squad 共享 `workflow-leader`，并都包含 `shared-intake` 与 `commit-policy-reviewer` 两个 shared support members；后两者不承担 Feature/Fix execution role。任何 Agent 都不同时生产、评审或验证 Feature 与 Fix artifacts。

若目标项目裁剪 Loop，可整体移除 3 个 Loop-only Agent，并将 `loop_eligible=false`；不得保留只含 Maker 或缺少 Checker/Guard 的残缺 Loop。保留 Loop 时，16 个角色已是满足 writer/reviewer、maker/checker、Feature/Fix 分离、producer-owned commit 与独立 commit-policy verification 后的最小集合。

## 2. Agent roster

| ID | Role key | Work type | Responsibility class | Squad membership | 核心使命 |
| --- | --- | --- | --- | --- | --- |
| `A01` | `shared-intake` | `shared` | Producer / Intake | Feature + Fix shared support | 基于证据分类、维护 current Brief、创建唯一 WorkItemExecution admission、处理 clarification 和显式 dispatch 前置条件 |
| `A02` | `workflow-leader` | `shared` | Leader | Feature + Fix | 校验 execution/Handoff/Gate/revision/scope/lease/integration attempt，路由、汇合、失效、升级和 lifecycle readback；不生产业务产物 |
| `A03` | `feature-governance-producer` | `feature` | Producer | Feature | 持有 repository-global lease 后起草 Constitution、Architecture、Roadmap 和 ADR draft；全部交 Human ratify |
| `A04` | `feature-requirement-producer` | `feature` | Producer | Feature | 从 accepted Feature Brief 生产/澄清 Feature Spec |
| `A05` | `feature-requirement-reviewer` | `feature` | Reviewer / Gate Producer | Feature | 独立生成 canonical Requirement Gate；不回答产品问题 |
| `A06` | `feature-planning-producer` | `feature` | Producer | Feature | 获取 ADR context，生成 Plan bundle 与 Tasks；不批准自己的输出 |
| `A07` | `feature-reviewer` | `feature` | Reviewer | Feature | 独立执行 ADR Check、Analyze、Roadmap Sync/Brief/Debrief；只写评审报告 |
| `A08` | `feature-core-maker` | `feature` | Producer / Maker | Feature | 仅在 Core route 中按 accepted Tasks 修改代码和测试 |
| `A09` | `feature-loop-maker` | `feature` | Producer / Maker | Feature，Loop-only | 定义 Loop contract、执行 maker iterations、维护 maker/state status；不评分自己 |
| `A10` | `feature-loop-checker` | `feature` | Verifier | Feature，Loop-only | 在独立 session/Agent 中对 immutable iteration 做对抗式 criterion 检查 |
| `A11` | `feature-loop-guard` | `feature` | Human-support Guard | Feature，Loop-only | 呈现 debt、预算和未验证风险，记录 Human sign-off；不替 Human 决定 |
| `A12` | `feature-convergence-reviewer` | `feature` | Reviewer / Append-only Producer | Feature | 实现后检查闭环；只向 Tasks 追加 Convergence phase，不改代码 |
| `A13` | `fix-assessor` | `fix` | Producer / Reviewer | Fix | 复现、定位根因和影响，生成 assessment 或 Feature escalation evidence |
| `A14` | `fix-maker` | `fix` | Producer / Maker | Fix | 按 assessment 做最小修复、补测试并记录 fix evidence |
| `A15` | `fix-verifier` | `fix` | Verifier | Fix | 独立重放原始症状与 regression，生成 test report；不修代码 |
| `A16` | `commit-policy-reviewer` | `shared` | Read-only commit policy reviewer | Feature + Fix shared support | 独立验证 producer-owned current CommitRef 的 candidate mapping、scope、message、Work-Item footer 与 provider receipt；不写业务文件、不 commit |

## 3. 外部权威与非 Agent 角色

| Boundary | 身份 | 责任 | 不能被谁替代 |
| --- | --- | --- | --- |
| `human-authority` | `multica auth status` 登录账号已获 explicit consent 的 Human | Constitution、Architecture、ADR、Roadmap、Tasks、Core/Loop route、Loop sign-off、风险 override、final acceptance | Agent、Squad、CI、命令退出 0 |
| `repository-provider` | Project/Runtime/repository integration | 在 dispatch 前提供独立 approved checkout/branch/root；维护 scope registry、原子 resource lease、target integration queue 与 provider receipts | `speckit-worktrees-*` Agent 节点、Leader 自行创建 checkout |
| `workspace-administrator` | Multica workspace 管理员 | 配置 status key/category；协助 Human 在 Web 核对五个状态 | CLI 私有 API、真实 Issue probe |
| `human-designation-operator` | operator + designated Human | 记录 authenticated Multica account email 与 explicit consent；维护 append-only designation/participation-plan/request/notification/decision ledger 和 recipient mapping | Agent/Leader 选择 Human、伪造 consent、把投递地址当作决定者或以通知代替决定 |
| `ci-provider-control` | 目标 repo/provider policy | 校验 execution/worktree 隔离、scope/lease、manifest、work_type、permissions、baseline checks、approval 与 exact source/target integration receipts | Leader 自述、模板文件存在 |
Human Authority 不是 Squad member。Agent 可以准备 diff、问题和证据，但不得生成代表 Human acceptance 的 `HumanDecisionRef`。

## 4. Agent role cards

### A01 `shared-intake`

- **Owns**：TRIAGE_EVIDENCE、CURRENT_BRIEF、type/status recommendation、clarification checkpoint、FIX_ESCALATION_PACKET 到新 Feature Brief 的转换。
- **Required inputs**：Work Item/PR、comments、runs、repository/PR evidence、status contract 的 Human confirmation、Human clarification，以及 `repository_ref + work_item_ref + work_type + workflow_epoch` dispatch key。
- **Allowed writes**：经授权的 Multica triage comment/Brief/type label/status；明确拒绝 enhancement 时的既有 rejection-memory 路径；显式 dispatch 时创建唯一 current execution admission。
- **Forbidden**：Spec/Plan/Tasks/code/test/ADR/Roadmap 写入；Squad 内 Gate approval；无授权或重复 dispatch；同时给一个 Issue 两个 type；复用其他 Work Item 的 checkout/run。
- **Success evidence**：恰好一个 current Brief revision、一个 type、一个 current execution epoch、write readback、无 accidental/duplicate run。
- **Escalation**：范围混合到 Human；信息不足到 named party/system；status drift 到 workspace administrator；execution 冲突到 provider/A02。

### A02 `workflow-leader`

- **Owns**：WORKFLOW_LEDGER、WorkItemExecutionRef、GateRecord、HandoffRef、WorkScope/ScopeConflictGate、Human refs、repository resource lease/route state、IntegrationAttempt routing、invalidation、join、failure routing、最终 lifecycle recording。
- **Required inputs**：current execution/checkout、artifacts/gates/scope/leases/integration attempt、current HumanDesignationRef/ParticipationPlanRef、Human approval requests/decisions、exact revisions。
- **Allowed writes**：通过 compare-and-set 写 workflow ledger、scope/lease/attempt state；current plan 授权的 exact designated-Human member notification/reminder及 provider readback；已作出决定的 recording-only 持久化，以及明确授权且 recording-only 的 Issue status/metadata/comment readback。
- **Forbidden**：生产或修改业务 artifacts；选择或改变 Human email/member、伪造 consent、broad/ad-hoc mention、将通知/超时当作 approval、assign/dispatch/rerun/cancel、替 Human 决定；自行创建 checkout、解决内容冲突或成为 implementation fallback。
- **Success evidence**：每个 Work Item 一个 current execution/checkout；scope conflict 与 resource lease current；每个 request 恰好一次 initial；同一 target 一个 active integration attempt；Handoff inputs 可解析；精确 stale 传播；无重复 dispatch。
- **Escalation**：schema/ledger原子性/execution/scope/lease/recipient/scheduler/queue 冲突立即 BLOCKED；把内容失败返回唯一 owner。

### A03 `feature-governance-producer`

- **Owns**：CONSTITUTION、ARCHITECTURE、ROADMAP、ADR_DRAFT。
- **Required inputs**：current execution/checkout、Human governance input、authorized sources、repository evidence、current governance revisions、Plan/ADR finding，以及目标 repository-global resource lease。
- **Allowed writes**：持有 current `repository_ref + resource_key` lease 时写 canonical governance paths 和 draft ADR；不得额外建第二套 SSOT。
- **Forbidden**：Human ratification、Feature Spec/Plan/Tasks/code、Roadmap/ADR 自批、无 Plan 起草 ADR、与其他 Work Item 并行写同一治理资源。
- **Success evidence**：execution/checkout/lease 一致；stable IDs、source evidence、actual diff、non-destructive roadmap delta、ADR status=draft。
- **Escalation**：来源不足到 source owner；scope/decision 到 Human；resource conflict 等待指定 integration/lease；评审 finding 返回自己修订。

### A04 `feature-requirement-producer`

- **Owns**：FEATURE_SPEC、经 Human 回答后的 CLARIFICATION_DECISION 投影。
- **Required inputs**：current WorkItemExecutionRef、approved checkout、current Feature Brief、accepted governance、authorized sources、Requirement Gate product blockers。
- **Allowed writes**：固定 execution/root 下 resolved FEATURE_DIR 的 `spec.md` 和 Skill 允许的 feature metadata；Clarify 时同步 canonical gate。
- **Forbidden**：Plan/Tasks/code/Architecture/Roadmap；自行回答 product decision；声明 Planning Ready；跨 execution/root 写入。
- **Success evidence**：execution/checkout 一致；WHAT/WHY、scope/non-goal、AC、stable refs、provenance、unresolved blockers 完整。
- **Escalation**：产品问题到 Human；source evidence 到 source owner；runtime hook或 checkout conflict 到 provider。

### A05 `feature-requirement-reviewer`

- **Owns**：REQUIREMENT_GATE。
- **Required inputs**：current execution/checkout、current FEATURE_SPEC revision、canonical requirement fragments。
- **Allowed writes**：同一 execution 的唯一 `FEATURE_DIR/checklists/requirements.md`。
- **Forbidden**：修改 Spec；回答产品问题；读取 Plan/Tasks 作为策略；创建 legacy checklist；批准自己生成的 GateRecord；跨 root 写入。
- **Success evidence**：execution/checkout/spec SHA 一致；六 logical gates、stable checks、PASS evidence 或唯一 owned blocker。
- **Escalation**：product blocker 到 A04+Human；source blocker 到 source owner；template/checkout blocker 到安装 owner/provider。

### A06 `feature-planning-producer`

- **Owns**：ADR_CONTEXT、PLAN_BUNDLE、TASKS。
- **Required inputs**：current execution/checkout、accepted governance、FEATURE_SPEC、REQUIREMENT_GATE READY、repository facts、ADR corpus、Human-accepted prior Tasks corrections。
- **Allowed writes**：同一 execution 的 Plan bundle、`tasks.md` 和基于 accepted Tasks 生成的 `WorkScopeRef`；Tasks 使用 canonical-path `EXCLUSIVE_WRITE` lease。
- **Forbidden**：修改 Spec/Requirement Gate/governance/code；批准 Plan/Tasks/ScopeConflictGate；绕过 ADR Check、Human Tasks Review 或跨 Work Item scope comparison。
- **Success evidence**：PLAN_OUTPUT_READY、X0–X4、stable derivation/test/VAL refs；Tasks paths/deps/[P]/tests/final review 与 WorkScope paths/resources 完整。
- **Escalation**：product gap 到 A04；governance conflict 到 A03+Human；未知动态路径到 provider/Human；评审 finding 返回自己。

### A07 `feature-reviewer`

- **Owns**：ADR_CHECK、ANALYZE_REPORT、ROADMAP_SYNC_REPORT、ROADMAP_BRIEF_REPORT、ROADMAP_DEBRIEF_REPORT。
- **Required inputs**：current execution/checkout 与各节点要求的 immutable governance/spec/plan/tasks/implementation revisions。
- **Allowed writes**：当前 root 的 timestamped review reports 和 workflow evidence；ADR Check/Analyze otherwise read-only。
- **Forbidden**：修改被评审 artifacts/code；生成 Convergence tasks；替 Human 接受 Roadmap/ADR；跨 execution 复用报告或可变 working tree。
- **Success evidence**：execution、checkout、CommitRef 与每个 finding 的 severity/owner/artifact/evidence ref 一致；报告不覆盖旧 revision。
- **Escalation**：finding 返回对应 Producer；Roadmap/ADR delta 到 A03+Human；缺 evidence、execution 或 target revision 为 BLOCKED。

### A08 `feature-core-maker`

- **Owns**：CORE_CHANGESET 及 Core route 的 task-level implementation evidence。
- **Required inputs**：current execution/checkout、route=core、current Spec/Plan/Tasks/Human Tasks acceptance、current WorkScopeRef、`ScopeConflictGate=CLEAR` 和所需 resource leases。
- **Allowed writes**：当前 root 内批准 scope 的 source/tests、Skill 允许的 task completion markers。
- **Forbidden**：Loop state；切换 route；修改治理/Spec/Plan；批准 implementation gate；忽略失败测试；跨 scope/execution 写入。
- **Success evidence**：execution/checkout/scope/lease 一致；每个完成 task 有 diff、test/command result 和 revision；无越界文件。
- **Escalation**：scope conflict 等待 dependency/integration/Human；合同变化到 A01；Plan/Task 缺陷到 A06；环境/风险到 A02/Human。

### A09 `feature-loop-maker`

- **Owns**：LOOP_CONTRACT、LOOP_ITERATION、maker-side LoopState。
- **Required inputs**：current execution/checkout、route=loop、current Tasks/WorkScope、`ScopeConflictGate=CLEAR`、resource leases、checker feedback、预算。
- **Allowed writes**：当前 root 的批准 scope source/tests 和 feature-local loop state；固定 isolation none。
- **Forbidden**：调用 Core Implement；自评 criterion PASS；写 checker verdict/Human sign-off；超预算；创建 iteration worktree；跨 execution/root 写入。
- **Success evidence**：execution/checkout/scope/lease 一致；contract criteria/budget/tools/state 完整；iteration 单调、diff/tests/stop reason 完整。
- **Escalation**：scope conflict 等待 dependency/integration/Human；checker FAIL 且有预算则重试；exhausted/risk/debt 到 A11+Human；合同变化到 A01。

### A10 `feature-loop-checker`

- **Owns**：LOOP_CHECK_VERDICT。
- **Required inputs**：current execution/checkout、immutable latest iteration、Loop contract、objective evidence；session/context 与 A09 及其他 execution 隔离。
- **Allowed writes**：当前 execution 的 checker report/state only。
- **Forbidden**：修改代码/tests/maker state；与 A09 共用 session/context；读取其他 execution state；不确定时给 PASS。
- **Success evidence**：execution/root/身份独立、逐 criterion evidence、uncertain=FAIL、revision exact。
- **Escalation**：FAIL 到 A09；execution/evidence/环境缺失 BLOCKED；预算耗尽到 A11。

### A11 `feature-loop-guard`

- **Owns**：debt/risk presentation、guard record；Human owns acceptance。
- **Required inputs**：current execution/checkout、checker verdict、actual changes、budget、open debt。
- **Allowed writes**：当前 execution 的 guard/debt state 和 Human 决定的受证据支持记录。
- **Forbidden**：代码修改、自行签署 HumanDecisionRef、把沉默视为同意、覆盖 checker verdict、混用其他 Work Item evidence。
- **Success evidence**：execution/revisions 一致；所有 blocking debt surfaced；Human identity 与 exact revisions 绑定。
- **Escalation**：未理解变化、open debt、风险或预算问题留给 Human，不宣称 done。

### A12 `feature-convergence-reviewer`

- **Owns**：CONVERGENCE_RESULT；必要时 Tasks 的 append-only Convergence phase。
- **Required inputs**：current execution/checkout、current Spec/Plan/Tasks/implementation/Debrief。
- **Allowed writes**：取得 canonical tasks path 的 APPEND_ONLY lease 后只向当前 Work Item 的 `tasks.md` 追加新 phase。
- **Forbidden**：修改既有 Tasks、Spec、Plan、代码；执行追加任务；在 append 后自己运行 Analyze 批准；跨 execution/path append。
- **Success evidence**：execution/lease 一致；converged 时无空写；tasks_appended 时 ID 连续、finding 可执行、new Tasks revision 已发布。
- **Escalation**：lease conflict 等待 owner；新 Tasks 到 Human Review/A07；实现 gap 返回当前 selected maker。

### A13 `fix-assessor`

- **Owns**：FIX_ASSESSMENT、FIX_ESCALATION_PACKET。
- **Required inputs**：current execution/checkout、current Fix Brief、code、logs/reproduction、expected contract。
- **Allowed writes**：当前 Fix root 的 `.specify/bugs/<slug>/assessment.md`、escalation evidence，并在 verdict=fixable 后发布 `WorkScopeRef`。
- **Forbidden**：修改源码；复用 Feature Spec/Plan writer；在需要合同变化时继续 Fix workflow；批准 ScopeConflictGate。
- **Success evidence**：execution/checkout 一致；symptom、expected/actual、root cause、severity、impact、remediation、verdict 和 scope 完整。
- **Escalation**：信息不足到 A01；Feature 条件到新 Brief；scope 冲突到 provider/Human；错误假设由自己重评。

### A14 `fix-maker`

- **Owns**：FIX_CHANGESET、`fix.md`、修复相关 tests。
- **Required inputs**：current execution/checkout、fixable assessment、current WorkScopeRef、`ScopeConflictGate=CLEAR`、resource leases。
- **Allowed writes**：当前 root 和 scope 内的 source/tests 与 upstream fix report。
- **Forbidden**：Feature Spec/Plan/Tasks；扩大范围不记录；assessment 错误后继续写；批准自己的 fix；跨 execution/scope 写入。
- **Success evidence**：execution/checkout/scope/lease 一致；最小 diff、tests、targeted checks、deviations 与 revision 完整。
- **Escalation**：scope conflict 等待 dependency/integration/Human；assessment 错误到 A13；合同变化到 A01；环境/风险到 Human。

### A15 `fix-verifier`

- **Owns**：FIX_TEST_REPORT。
- **Required inputs**：current execution/checkout、immutable assessment、current CommitRef、fix revision、原始 reproduction、regression commands/environment。
- **Allowed writes**：当前 execution 的 `.specify/bugs/<slug>/test.md` 和 verification evidence。
- **Forbidden**：修改源码/tests/fix report；未执行复现却标 verified；加入 Feature Squad；跨 execution/root 复用 evidence。
- **Success evidence**：execution/checkout/CommitRef 一致；原症状重放、critical regression、skipped/not-run 原因、verified/partial/failed 真实。
- **Escalation**：failed 到 A14；assessment 错误到 A13；manual/target env 或 execution mismatch 到 Human/provider。

### A16 `commit-policy-reviewer`

- **Owns**：`COMMIT_POLICY_VERDICT`，不拥有 `CommitRef`；每个 `CommitRef.v2` 由 exact repository-writing producer 在自己的 run 内创建。
- **Required inputs**：current execution、WorkItemBranchRef.v1、RunCheckoutRef.v1、CheckoutRef.v5、producer-owned CommitRef.v2、ChangesetCandidateRef、WorkScopeRef、ScopeConflictGate、approved scope、actual diff/tests、provider commit-policy/readback receipt。
- **Allowed writes**：仅 execution-scoped immutable policy report/ledger output；Git、index 和业务文件只读。
- **Forbidden**：stage、commit、业务文件写入、Feature/Fix execution Skill、Multica、push、merge、amend、rebase、reset、cherry-pick、branch/worktree mutation、force-push、`--no-verify`；不得修复 producer commit。
- **Success evidence**：execution/run checkout/provider identity 一致；commit SHA/parent/runtime task branch/stable integration branch/diff 与 candidate 一致；唯一末尾 Work-Item footer、hook/validator receipt 和完整 commit range 有效。
- **Escalation**：scope/diff/message/footer 问题到 exact Producer；execution/branch/parent/root/readback 到 repository provider；hook/policy/permission 到 repository administrator。

## 4A. 跨 Work Item 并发模型

- A01 可并行处理不触碰 repository root 的 intake 计算，但 dispatch compare-and-set 必须保证同一 Work Item 只有一个 current execution epoch。
- A02 只有在 ledger、resource lease、notification reservation 和 integration queue 都支持原子 compare-and-set 且可 readback 时才能跨 Work Item 协调；否则 `max-concurrent-tasks=1`。
- A03 的只读调查可在单个 run 内并行；Constitution、Architecture、Roadmap 和同一 ADR writer 必须由 repository-global lease 串行。
- A03–A15 每个 run 必须命中同一 collaboration Runtime 上 current `RunCheckoutRef.root_locator`；同一 Work Item writer 按 DAG 串行，不同 Work Item 仅在独立 worktree、scope gate CLEAR、resource lease 无冲突时并行。
- A16 只验证冻结的 CommitRef，不使用 Git index；其 report namespace 隔离不可 readback 时 `max-concurrent-tasks=1`。
- 同一 repository target 的 provider integration 串行；不同 repository 可并行。Human/provider 以 target-project priority policy 处理 Hotfix、安全/数据完整性 Fix 与 Feature 冲突，不硬编码普通 Fix 自动抢占。

## 5. Artifact 责任矩阵

| Artifact / Gate | Producer | Objective verifier | Professional reviewer | Final decision |
| --- | --- | --- | --- | --- |
| TRIAGE_EVIDENCE / CURRENT_BRIEF | A01 | A02 校验 schema/revision/readback | Human 处理异常 scope/override | A02 admission gate；Human override |
| WORKFLOW_LEDGER / Handoff / lease / route persistence | A02 | W8 CI/provider schema control | Human audit/high-risk decision | provider/Human；A02 不自批 ledger policy |
| CONSTITUTION | A03 | A07 可做一致性 finding | Human Constitution review | Human Authority |
| ARCHITECTURE | A03 | A07 ADR/Analyze evidence | Human Architecture review | Human Authority |
| ROADMAP | A03 | A07 Sync/Brief/Debrief | Human roadmap review | Human Authority |
| ADR_DRAFT | A03 | A07 ADR Check | Human options/tradeoffs review | Human ratify/reject/amend |
| FEATURE_SPEC | A04 | A05 Requirement quality | A07 later cross-artifact Analyze | Human product decisions；A02 gate records |
| REQUIREMENT_GATE | A05 | A07 later Analyze/Plan precondition | A04 only repairs Spec-owned blockers | A02 gate records；Producer不自批 |
| PLAN_BUNDLE | A06 | A07 ADR Check + Analyze | Human when governance decision required | A02 gate records |
| TASKS | A06；A12仅 append convergence phase | Human actual diff review；A07 Analyze | Human | Human Tasks acceptance |
| ANALYZE / ADR_CHECK / ROADMAP reports | A07 | A02 schema/revision/check completeness | Human for governance delta | A02 routing；Human final governance decision |
| CORE_CHANGESET | A08 | A16 验证 producer-owned candidate/commit scope boundary | A07 Roadmap Debrief 只消费 VERIFIED current CommitRef | Human final acceptance |
| CHANGESET_CANDIDATE / COMMIT | exact repository-writing Producer | A16 验证 lineage、run identity、diff、footer、hook 与 receipt；CI 再验证完整 range | 独立业务 reviewer/Human 只消费 VERIFIED current CommitRef | Producer owns commit；Human 不因 commit 自动接受 |
| LOOP_CONTRACT / ITERATION | A09 | A10 + A16 commit-policy verdict | A11 surfaces Human risk/debt | Human sign-off + A02 gate |
| LOOP_CHECK_VERDICT | A10 | A02 identity/revision check + A16 commit-policy verdict | A11/Human | Human sign-off for done |
| CONVERGENCE_RESULT | A12 | A07 analyzes appended Tasks；A02 schema check；A16 commit-policy verdict | Human Tasks review when appended | Human final acceptance |
| FIX_ASSESSMENT | A13 | A02 route/evidence completeness + A16 commit-policy verdict | Human unusual verdict | A02 route gate/Human |
| FIX_CHANGESET | A14 | A16 验证 producer-owned candidate/commit scope boundary | A15 reproduction/regression 只消费 VERIFIED current CommitRef | Human final acceptance |
| FIX_TEST_REPORT | A15 | A02 revision/evidence completeness + A16 commit-policy verdict | Human | Human final acceptance |
| FIX_ESCALATION_PACKET | A13 | A02 hard-cut check | A01 re-triage | A01 creates new Feature Brief；Human handles scope |

## 6. Squad membership contract

### Feature Squad

```yaml
work_type: feature
leader: workflow-leader
members:
  - feature-governance-producer
  - feature-requirement-producer
  - feature-requirement-reviewer
  - feature-planning-producer
  - feature-reviewer
  - feature-core-maker
  - feature-loop-maker
  - feature-loop-checker
  - feature-loop-guard
  - feature-convergence-reviewer
```

Loop-disabled target removes all three `feature-loop-*` members together and records `loop_eligible: false`。Core Maker 仍按 Human route 才启用。

### Fix Squad

```yaml
work_type: fix
leader: workflow-leader
members:
  - fix-assessor
  - fix-maker
  - fix-verifier
```

### Shared Intake

```yaml
work_type: shared
role: shared-intake
membership: none
hands_off_to:
  - workflow-leader@feature
  - workflow-leader@fix
```

`workflow-leader` 允许复用于两个 Squad，因为它只路由中立合同；每次 run 必须携带唯一 current WorkItemExecutionRef 和单一 `work_type`，不得在一个 run 中混用 Feature/Fix 或不同 Work Item artifacts。缺 ledger 原子性 readback 时其并发上限为一。

## 7. 不可合并证明

| 候选合并 | 拒绝原因 |
| --- | --- |
| A01 Intake + A02 Leader | Intake 生产 Brief；Leader 必须独立执行 admission/revision gate，合并会自批 |
| A03 Governance Producer + A07 Reviewer | Constitution/Architecture/ADR/Roadmap 会由同一身份生产和评审 |
| A04 Requirement Producer + A05 Requirement Reviewer | Spec writer 会控制自己的 Requirement Gate |
| A05 Requirement Reviewer + A07 Feature Reviewer | A05 生产 Requirement Gate，A07 后续必须独立 Analyze 该 Gate |
| A06 Planning Producer + A07 Feature Reviewer | Plan/Tasks 会被同一身份通过 ADR Check/Analyze |
| A08 Core Maker + A09 Loop Maker | 破坏 Core/Loop route 排他并扩大写权限 |
| A09 Loop Maker + A10 Loop Checker | 违反独立 checker；自评风险直接失去 Loop eligibility |
| A10 Loop Checker + A11 Loop Guard | Checker verdict 与 Human-facing debt/sign-off 边界不同；Human 不能被 verifier 代替 |
| A07 Feature Reviewer + A12 Convergence Reviewer | A12 会 append Tasks，A07 必须独立 Analyze 新 revision |
| A13 Fix Assessor + A14 Fix Maker | assessment 偏差时 Fixer 需要停写并返回 Assessor；合并弱化 hard cut |
| A14 Fix Maker + A15 Fix Verifier | 违反独立 reproduction/regression verification |
| 任一 Feature + 任一 Fix execution role | 违反明确 `work_type` isolation；相同技术栈/runtime 不是合并理由 |

## 8. W5 验收检查

| 检查 | 结果 |
| --- | --- |
| Agent 来自稳定责任/独立判断，不是一 Skill 一 Agent | PASS |
| 所有 Agent 有唯一 role key、work_type、owned outputs 与 forbidden writes | PASS |
| Feature/Fix execution Agents 完全分离 | PASS |
| 只有中立 Leader 被两个 Squad 共享 | PASS |
| Producer 不批准自己的 artifact | PASS |
| Loop Maker/Checker/Guard 身份分离 | PASS |
| Tasks Planner、Convergence appender、Analyze reviewer 分离 | PASS |
| Leader 不成为实现兜底 | PASS |
| Human/Project/Runtime/CI 没有伪装成 Agent | PASS |
| Loop 可整体裁剪，不留下残缺 route | PASS |
| 每个 Work Item execution/checkout/root 隔离且跨项 scope/lease 可判定 | PASS |
| A02/A16 并发以 ledger 或 cwd/index readback 为前提 | PASS |
| 同一 repository target integration 由 provider 串行 | PASS |

W5 并发 amendment 保持 16 个角色和 Feature/Fix membership 不变；它把 execution admission、scope/lease、integration attempt 与安全并发条件分配给现有 owners，不新增越权角色。
