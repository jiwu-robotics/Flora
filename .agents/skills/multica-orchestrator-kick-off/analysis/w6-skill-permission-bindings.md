```yaml
coach_stage: W6
decision: ACCEPTED
source_project: capability-sample-robox-nexus
source_revision: git:d24411c8840bab361745c1ed7b41cf4b3a43b3e3+mapping:sha256:8ab657d28bbb9ac295dd7c3c12d6cf9e54b150a2b6f2b29d6af4b7ccdbe3b6b8
requirements_revision: sha256:3b6caab15839cd7489bf30c23f9598a45fa309a3ade7a6227597ab83cb237d94
input_artifacts:
  - analysis/w5-agent-responsibility-matrix.md#sha256:9a5013063787d7cb08aa765bf0a811a223372e138b6164f16cf2c46581f68d5c
  - analysis/w4-feature-fix-dags.md#sha256:dbd02ee0e78cf2881e2ecd0931d773a836a5183c072c08baa4e9df035ca63673
  - contracts/handoff-gate-contracts.md#sha256:eef42b00a7630f5c801d87fe0bce9403fb09cea8f5625df7f72e0bcfc8c7cfbd
  - requirements/orchestration-requirements.md#sha256:3b6caab15839cd7489bf30c23f9598a45fa309a3ade7a6227597ab83cb237d94
decisions:
  default_worktree: false
  loop_eligible: true
  loop_isolation: none
  skill_permission_bindings_accepted: true
open_blockers: []
supersedes: analysis/w6-skill-permission-bindings.md#sha256:dcbb846addcb6f301c1b9d29227efac60aed52609c292e35279bbbe96f5fdbb4
```

# W6 Skill 挂载与最小权限矩阵

## 1. 本步骤结论

W6 将 W5 的 16 个 role key 绑定到完成职责所需的最小 Skill 集。绑定使用稳定 Skill name，不写 repository 路径。只有 `shared-intake` 和 `workflow-leader` 获得 `multica-cli`；每个 repository-writing Feature/Fix role 使用 `conventional-commit` 提交自己的 run scope，A16 只读验证；内容角色不直接处理 workspace 地址、profile 或凭据。

Feature 与 Fix execution bundles 完全隔离。Loop 的三个角色只有在 manifest 同时声明 `loop_eligible: true`、`loop_isolation: none`、完整 Maker/Checker/Guard membership 时才可绑定；缺一项则整体禁用 Loop。

## 2. 规范化 Skill bundles

### `FEATURE_EXECUTION_SKILLS`

```yaml
- speckit-constitution
- speckit-roadmap-write
- speckit-roadmap-sync
- speckit-specify
- speckit-checklist
- speckit-clarify
- speckit-adrkit-context
- speckit-plan
- speckit-adrkit-check
- speckit-adrkit-draft
- speckit-tasks
- speckit-analyze
- speckit-roadmap-brief
- speckit-implement
- speckit-loop-define
- speckit-loop-run
- speckit-loop-check
- speckit-loop-guard
- speckit-loop-status
- speckit-roadmap-debrief
- speckit-converge
```

### `FIX_EXECUTION_SKILLS`

```yaml
- speckit-bug-assess
- speckit-bug-fix
- speckit-bug-test
```

### `COMMIT_AND_POLICY_SKILLS`

```yaml
- conventional-commit
```

### `EXCLUDED_SKILLS`

```yaml
- multica-orchestrator-link-up
- multica-orchestrator-nail-down
- multica-create-agent
- speckit-setup-project
- speckit-taskstoissues
- speckit-worktrees-specify
- speckit-worktrees-create
- speckit-worktrees-list
- speckit-worktrees-clean
- multica-coach
```

`EXCLUDED_SKILLS` 对全部 16 个 Agent 均为 forbidden。`COMMIT_AND_POLICY_SKILLS` 绑定每个 repository-writing Agent 和只读 `commit-policy-reviewer`；它不扩大任何角色的业务写入范围。`multica-cli` 不属于 execution bundle，但只允许绑定 A01/A02。`multica-triage` 只允许绑定 A01。

## 3. Binding record contract

W7 manifest 中每个 Agent binding 必须可机械投影为：

```yaml
role_key: "<W5 role key>"
work_type: shared | feature | fix
required_skills:
  - "<canonical Skill name>"
optional_skills:
  - name: "<canonical Skill name>"
    when: "<deterministic condition>"
forbidden_skill_bundles:
  - "<bundle name>"
forbidden_skills:
  - "<canonical Skill name>"
permissions:
  repository_read: "<scope>"
  repository_write:
    - "<exact relative path/pattern or none>"
  command_execution: none | read_only_checks | scoped_build_test | skill_required
  git_control: none | read_only | working_tree_only | commit_only
  multica_access: none | inspect | triage_apply_dispatch | recording_and_designated_human_notification
  network_access: none | provider_scoped
  destructive_operations: false
  credentials: runtime_injected | none
constraints:
  producer_cannot_approve: true
  work_type_isolation: true
  checkout_ref_required: true | false
```

`forbidden_skill_bundles` 展开后不得与 required/optional Skill 相交。Permissions 是上限；Skill 自身更窄的限制继续生效。

## 4. Skill 挂载矩阵

| Agent | Work type | 必备 Skills | 条件/可选 Skills | 禁止直接调用 |
| --- | --- | --- | --- | --- |
| `shared-intake` | shared | `multica-triage`, `multica-cli` | 无 | `FEATURE_EXECUTION_SKILLS`, `FIX_EXECUTION_SKILLS`, `EXCLUDED_SKILLS` |
| `workflow-leader` | shared | `multica-cli` | 无；读取 W3 contract 不需要新 Skill | `multica-triage`, `FEATURE_EXECUTION_SKILLS`, `FIX_EXECUTION_SKILLS`, `EXCLUDED_SKILLS` |
| `feature-governance-producer` | feature | `speckit-constitution`, `speckit-roadmap-write`, `conventional-commit` | `speckit-adrkit-draft`：仅 Human 授权且 current Plan/ADR finding 存在 | 所有未列 Feature Skills、`FIX_EXECUTION_SKILLS`, `multica-cli`, `multica-triage`, `EXCLUDED_SKILLS` |
| `feature-requirement-producer` | feature | `speckit-specify`, `conventional-commit` | `speckit-clarify`：仅 Requirement Gate 的 product-decision blocker | 所有未列 Feature Skills、`FIX_EXECUTION_SKILLS`, `multica-cli`, `multica-triage`, `EXCLUDED_SKILLS` |
| `feature-requirement-reviewer` | feature | `speckit-checklist`, `conventional-commit` | 无 | 所有其他 Feature Skills、`FIX_EXECUTION_SKILLS`, `multica-cli`, `multica-triage`, `EXCLUDED_SKILLS` |
| `feature-planning-producer` | feature | `speckit-adrkit-context`, `speckit-plan`, `speckit-tasks`, `conventional-commit` | 无 | 所有未列 Feature Skills、`FIX_EXECUTION_SKILLS`, `multica-cli`, `multica-triage`, `EXCLUDED_SKILLS` |
| `feature-reviewer` | feature | `speckit-adrkit-check`, `speckit-analyze`, `speckit-roadmap-brief`, `speckit-roadmap-debrief`, `conventional-commit` | `speckit-roadmap-sync`：仅 Human 请求或已有 project-wide drift evidence | 所有未列 Feature Skills、`FIX_EXECUTION_SKILLS`, `multica-cli`, `multica-triage`, `EXCLUDED_SKILLS` |
| `feature-core-maker` | feature | `speckit-implement`, `conventional-commit` | 无 | 全部 Loop Skills、其他 Feature production/review Skills、`FIX_EXECUTION_SKILLS`, `multica-cli`, `multica-triage`, `EXCLUDED_SKILLS` |
| `feature-loop-maker` | feature | `speckit-loop-define`, `speckit-loop-run`, `speckit-loop-status`, `conventional-commit` | 无 | `speckit-implement`, `speckit-loop-check`, `speckit-loop-guard`, 其他 Feature Skills、`FIX_EXECUTION_SKILLS`, `multica-cli`, `multica-triage`, `EXCLUDED_SKILLS` |
| `feature-loop-checker` | feature | `speckit-loop-check`, `conventional-commit` | `speckit-loop-status`：只读 current state slice | `speckit-implement`, `speckit-loop-define`, `speckit-loop-run`, `speckit-loop-guard`, 其他 Feature Skills、`FIX_EXECUTION_SKILLS`, `multica-cli`, `multica-triage`, `EXCLUDED_SKILLS` |
| `feature-loop-guard` | feature | `speckit-loop-guard`, `speckit-loop-status`, `conventional-commit` | 无 | `speckit-implement`, `speckit-loop-define`, `speckit-loop-run`, `speckit-loop-check`, 其他 Feature Skills、`FIX_EXECUTION_SKILLS`, `multica-cli`, `multica-triage`, `EXCLUDED_SKILLS` |
| `feature-convergence-reviewer` | feature | `speckit-converge`, `conventional-commit` | 无 | 其他 Feature Skills、`FIX_EXECUTION_SKILLS`, `multica-cli`, `multica-triage`, `EXCLUDED_SKILLS` |
| `fix-assessor` | fix | `speckit-bug-assess`, `conventional-commit` | 无 | `FEATURE_EXECUTION_SKILLS`, `speckit-bug-fix`, `speckit-bug-test`, `multica-cli`, `multica-triage`, `EXCLUDED_SKILLS` |
| `fix-maker` | fix | `speckit-bug-fix`, `conventional-commit` | 无 | `FEATURE_EXECUTION_SKILLS`, `speckit-bug-assess`, `speckit-bug-test`, `multica-cli`, `multica-triage`, `EXCLUDED_SKILLS` |
| `fix-verifier` | fix | `speckit-bug-test`, `conventional-commit` | 无 | `FEATURE_EXECUTION_SKILLS`, `speckit-bug-assess`, `speckit-bug-fix`, `multica-cli`, `multica-triage`, `EXCLUDED_SKILLS` |
| `commit-policy-reviewer` | shared | `conventional-commit` | 无 | `FEATURE_EXECUTION_SKILLS`, `FIX_EXECUTION_SKILLS`, `multica-cli`, `multica-triage`, `EXCLUDED_SKILLS` |

## 5. Repository 与 command 权限矩阵

`<FEATURE_DIR>`、`<FIX_DIR>` 和 `<APPROVED_SCOPE>` 都必须从 current WorkItemExecutionRef/HandoffRef/WorkItemBranchRef.v1/RunCheckoutRef.v1/CheckoutRef.v5/WorkScopeRef 解析，不能由 Agent 搜索、进程 cwd 或会话记忆猜测。每个 run 的 cwd、session、Runtime task branch/worktree 和临时状态必须隔离。

| Agent | Repository read | Repository write | Command execution | Git control |
| --- | --- | --- | --- | --- |
| `shared-intake` | Brief 所需 repo/domain/spec/ADR/PR evidence | 仅既有 rejection-memory 路径，且只限明确拒绝 enhancement | read-only investigation/verification | read-only |
| `workflow-leader` | current execution 与 ArtifactRef 指向的 headers/metadata/evidence slices | 无业务 repo write；workflow ledger 若落库则只通过原子 ledger/lease/scope/queue interface | schema/hash/readback/compare-and-set checks | read-only |
| `feature-governance-producer` | current execution、authorized sources、governance、repo evidence、current Plan | 持有 repository-global lease 时写 Constitution、Architecture、configured roadmap/ADR path | Skill-required governance/adrkit commands、candidate 固化、message validator、ordinary commit | scoped ordinary commit；不 push/merge/history rewrite |
| `feature-requirement-producer` | current execution、Brief、accepted governance、authorized sources、current blockers | 当前 root 的 `<FEATURE_DIR>/spec.md` 及 Skill 明示 metadata | Skill-required path/template commands、candidate 固化、ordinary commit | scoped ordinary commit；不 push/merge/history rewrite |
| `feature-requirement-reviewer` | current execution、Spec、canonical rule fragments | 当前 root 的 `<FEATURE_DIR>/checklists/requirements.md` only | hash/template checks、candidate 固化、ordinary commit | scoped report commit；不 push/merge/history rewrite |
| `feature-planning-producer` | current execution、accepted governance、Spec、Gate、ADR corpus、repo facts | 当前 root 的 Plan bundle、`tasks.md` 与 WorkScopeRef；Tasks path lease | skill-required design/schema/check commands、candidate 固化、ordinary commit | scoped ordinary commit；不 push/merge/history rewrite |
| `feature-reviewer` | current execution、current governance/Spec/Gate/Plan/Tasks/CommitRef/evidence | 当前 root 的 timestamped roadmap reports only；其他 outputs 进 ledger | read-only checks/analysis/adrkit/roadmap loader、report candidate、ordinary commit | scoped report commit；不改被评审内容 |
| `feature-core-maker` | current execution、accepted artifacts、WorkScope、ScopeConflictGate 与 leases | 当前 root 的 `<APPROVED_SCOPE>` source/tests + authorized markers | scoped build/test/lint/typecheck/smoke、candidate 固化、ordinary commit | scoped ordinary commit；不 push/merge/history rewrite |
| `feature-loop-maker` | current execution、Loop contract/Tasks/WorkScope/checker feedback与 leases | 当前 root 的 `<APPROVED_SCOPE>` source/tests + feature-local state | scoped build/test + loop commands、candidate 固化、ordinary commit | scoped ordinary commit；禁止 worktree create/push/merge |
| `feature-loop-checker` | current execution、immutable maker revision、contract、tests/evidence | 当前 execution checker verdict/state only | adversarial checks、non-destructive tests、report candidate、ordinary commit | scoped report commit；不改 maker state |
| `feature-loop-guard` | current execution、loop state、diff/evidence、debt、budget | 当前 execution guard/debt state only | status/guard commands、report candidate、ordinary commit | scoped report commit；不改 maker/checker state |
| `feature-convergence-reviewer` | current execution、Spec/Plan/Tasks/implementation/Debrief | 当前 tasks path 的 append-only lease 内写 `tasks.md` | convergence checks、candidate 固化、ordinary commit | scoped append-only commit |
| `fix-assessor` | current execution、Brief、code、logs/reproduction evidence | 当前 `<FIX_DIR>/assessment.md`、escalation evidence 与 WorkScopeRef | reproduction/investigation、report candidate、ordinary commit | scoped report commit |
| `fix-maker` | current execution、assessment、WorkScope/ScopeConflictGate/leases | 当前 root/approved scope 的 source/tests + `<FIX_DIR>/fix.md` | scoped build/test/check、candidate 固化、ordinary commit | scoped ordinary commit；不 push/merge/history rewrite |
| `fix-verifier` | current execution、immutable assessment/fix/CommitRef/tests | 当前 `<FIX_DIR>/test.md` only | reproduction/regression/lint/typecheck、report candidate、ordinary commit；高风险检查需 Human | scoped report commit；不改 code |
| `commit-policy-reviewer` | current execution、WorkItemBranchRef.v1、RunCheckoutRef.v1、CheckoutRef.v5、producer candidate/CommitRef、WorkScope、ScopeConflictGate、commit policy | 仅 execution-scoped immutable policy verdict；Git/index/业务文件只读 | exact diff/range、message/footer、hook/provider receipt 验证 | read-only；不 stage/commit/push/merge |

所有角色默认禁止删除 checkout、删除 provider objects、强推、merge、release、deploy、修改 secrets、修改 workspace schema 或绕过 GitFlow branch procedure。repository-writing Agent 只可提交本 run exact scope；`commit-policy-reviewer` 不可提交。若 Skill 合同要求更窄权限，以更窄规则为准。

## 6. Multica 权限矩阵

| Agent | Read | Write | Start/notify | Admin |
| --- | --- | --- | --- | --- |
| `shared-intake` | Issue、comments、labels、status、metadata、PR、runs、subscriber | explicit apply 的 type/status/comment/Brief/rejection record；显式 dispatch 时原子创建唯一 execution epoch | 仅 explicit dispatch，且按 repository/work-item/work-type/epoch 查无等价 current/active/queued run | 禁止 Agent/Squad/runtime/project/status definition 管理 |
| `workflow-leader` | 当前 execution/Issue/run/ledger/handoff/scope/lease/integration-attempt/Human 状态 | compare-and-set recording、current plan 授权的 exact Human notification reservation/readback | initial/reminder only；禁止 Agent/Squad/`@all` mention、assign、dispatch、rerun、cancel | 禁止 workspace schema、Agent/Squad/runtime/project 管理 |
| 其余 14 个 Agents | 无直接 Multica access；只消费 current HandoffRef 提供的 execution-bound opaque refs/content | 无 | 无 | 无 |

凭据只由 runtime 注入 A01/A02；不进入 Agent Instructions、Squad Instructions、Issue、artifact、日志或模板。A01/A02 不得输出 token、cookie、API key 或 CLI config secret。

## 7. Side-effect capability map

| Side effect | 唯一允许角色 | 前置证据 | 强制限制 |
| --- | --- | --- | --- |
| Triage status/type/comment/Brief | A01 | explicit apply、status mapping readback、Issue current | `--no-start`；写后 readback；保留 unrelated labels |
| First dispatch/execution admission | A01 | explicit dispatch、Brief complete、A02 route ready、原子 dedupe key 无 current/active/queued run | 恰好一个 current epoch/start entry；不盲目 retry |
| Workflow state + Human notification | A02 | current execution/Gate/Handoff/request/designation/plan；原子 reservation；exact recipient | compare-and-set；写后 readback；不得 assign/dispatch/rerun/cancel |
| Scope conflict/lease routing | A02 + provider | WorkScope、active scope registry、resource revision | repository/resource 原子 lease；非机械取舍交 Human |
| Governance write | A03 | Human input decision + execution/checkout + repository-global lease | actual diff 后 Human acceptance |
| Feature Spec write | A04 | current execution/Brief + approved checkout | 单一 Spec writer；不得执行 mandatory worktree hook |
| Requirement Gate write | A05 | current execution + fragments + current Spec SHA | 单一 canonical file |
| Plan/Tasks/WorkScope write | A06 | upstream gates current + path lease | Tasks 后 Human Review；scope 在 route 前比较 |
| Core source write | A08 | route=core + ScopeConflictGate=CLEAR + leases | 禁止任何 Loop/cross-scope write |
| Loop source write | A09 | route=loop + scope CLEAR + leases + contract/budget/isolation none | 禁止 Core；不得自评 |
| Loop verdict | A10 | execution-bound immutable maker revision + independent identity | 不改 code；uncertain=FAIL |
| Loop Human guard record | A11 + Human | execution-bound checker/debt/budget evidence | Agent 不生成 Human acceptance |
| Convergence Tasks append | A12 | current execution + APPEND_ONLY path lease | 不改既有 task/code；append 后失效链 |
| Fix assessment/WorkScope | A13 | current execution/Fix Brief | 不改 source；fixable 后发布 scope |
| Fix source write | A14 | scope CLEAR + leases + fixable assessment | 最小范围；合同变化即停 |
| Fix verification report | A15 | execution-bound immutable fix/assessment/CommitRef | 不改 source；未跑不标 verified |
| Candidate commit | A16 | current execution/WorkItemBranchRef.v1/RunCheckoutRef.v1/CheckoutRef.v5/scope/candidate/footer；cwd/index isolation | 仅普通 commit；无法证明隔离则串行 |
| Provider integration | provider/Human | current IntegrationAttempt exact source/target/checks/approvals | 同一 repository target 串行；Agent 不 merge |

## 7A. 跨 Work Item concurrency closure

```yaml
one_current_execution_per_work_item: true
distinct_checkout_root_per_current_work_item: true
scope_conflict_gate_before_source_write: true
repository_global_resource_lease: atomic
same_repository_target_integration: serialized
workflow_leader_parallelism_requires_atomic_ledger: true
committer_parallelism_requires_checkout_index_isolation: true
notification_initial_reservation: atomic
```

A04–A15 只有在 execution、cwd/session、checkout/root、scope 与 lease 隔离均可 readback 时才可跨 Work Item 并发。A02 或 A16 任一原子性/隔离 readback 缺失时，其安全 `max-concurrent-tasks` 为一；不得用 Instructions 代替 enforcement。

## 8. Loop binding closure

W7 manifest 只有满足以下全部条件才可包含 Loop bindings：

```yaml
loop_eligible: true
loop_isolation: none
required_members:
  - feature-loop-maker
  - feature-loop-checker
  - feature-loop-guard
required_skills:
  feature-loop-maker:
    - speckit-loop-define
    - speckit-loop-run
    - speckit-loop-status
  feature-loop-checker:
    - speckit-loop-check
  feature-loop-guard:
    - speckit-loop-guard
    - speckit-loop-status
forbidden:
  - speckit-implement@feature-loop-maker
  - speckit-loop-run@feature-loop-checker
  - speckit-loop-check@feature-loop-maker
  - speckit-worktrees-create@any-loop-role
```

任一 member/Skill/independent session/shared state/budget/Human guard 缺失时：

- manifest 设置 `loop_eligible: false`；
- 移除全部 Loop bindings/membership；
- Feature 只能由 Human 选择 Core；
- 不提供“降级为 maker 自检”或“临时在 Core Agent 上挂 Loop”的 fallback。

## 9. Runtime 前置条件

| Role/Skill | 必须验证 | 失败状态 |
| --- | --- | --- |
| A01/A02 + Multica | authenticated profile/workspace、accepted status mapping、execution/ledger/notification 原子 readback、权限 | `STATUS_CONTRACT_DRIFT`、`PLATFORM_ACCESS_BLOCKED` 或 `WORKFLOW_LEDGER_ATOMICITY_UNVERIFIED` |
| A04 `speckit-specify` | current execution/approved checkout；effective hooks 中无 mandatory worktree creation | `WORKTREE_HOOK_CONFLICT` |
| A05 `speckit-checklist` | canonical `.specify/templates/requirements/*.md` 可解析 | `REQUIREMENT_RULES_UNAVAILABLE` |
| A06/A07 Plan/Analyze | preset templates/schemas/scripts、current revisions、execution/root isolation | `SPECKIT_RUNTIME_INCOMPLETE` |
| A03/A07 ADRKit | `adrkit` CLI/corpus；repository-global resource lease；snapshot 结论边界明确 | `ADRKIT_BLOCKED` 或 `RESOURCE_LEASE_CONTROL_UNVERIFIED` |
| A09–A11 Loop | effective isolation none、execution-local shared state、budget、independent checker、Human guard | `LOOP_INELIGIBLE` |
| A08/A09/A14 source writers | WorkItemBranchRef.v1、RunCheckoutRef.v1、CheckoutRef.v5、WorkScope、ScopeConflictGate=CLEAR、resource leases、toolchain | `WRITE_SCOPE_BLOCKED` 或 `WORK_SCOPE_CONFLICT_UNRESOLVED` |
| A10/A15 verifiers | execution-bound immutable target revision、可执行 evidence/environment | `VERIFICATION_BLOCKED` |
| A16 `conventional-commit` | current execution/checkout/candidate/scope、cwd/index isolation、hook/CI validator | `COMMIT_POLICY_INVALID`、`COMMIT_SCOPE_VIOLATION` 或 `COMMIT_CONTEXT_ISOLATION_UNVERIFIED` |
| provider integration | atomic repository-target queue、exact source/target proposed-merge checks | `INTEGRATION_QUEUE_UNVERIFIED` |

这些是 dispatch/节点 entry preconditions，不通过时不得给 Agent 扩权或跳过检查。

## 10. 机械一致性检查

W7/W8 必须能够机械验证：

1. 每个 binding 有一个 `work_type`。
2. shared role 不含 Feature/Fix execution Skill。
3. feature role 不含任何 `speckit-bug-*`。
4. fix role 不含任何 `FEATURE_EXECUTION_SKILLS`。
5. 只有 A01/A02 含 `multica-cli`；只有 A01 含 `multica-triage`。
6. A02 的 notification 能力只能指向 current plan 解析出的 designated Human member；Agent/Squad/`@all` mention、assignment、dispatch、rerun、cancel 均为 0。
7. `EXCLUDED_SKILLS` 在所有 required/optional bindings 中出现次数为 0。
8. `COMMIT_AND_POLICY_SKILLS` 只出现在 repository-writing roles 与 A16 required bindings；A16 Git 权限只读。
9. A08 与任何 Loop Skill 不相交；A09 与 `speckit-implement` 不相交。
10. A09 与 A10 的 Agent identity/runtime session 不同。
11. A12 对 Tasks 只有 append-only permission；A07/A10/A15 无 code write。
12. repository-writing Agents 只获得本 run scoped ordinary commit 权限；A16 只获得 read-only commit policy validation；没有 role 获得 push/merge/release/deploy/workspace-admin 权限。
13. credentials 只标 `runtime_injected`，没有值。
14. Loop membership/bindings/config 满足完整闭包或全部不存在。
15. 全部 Agent 指向同一 collaboration Runtime；每个 current run 使用独立 Runtime task branch/worktree，Handoff 不跨 execution，同一 Work Item writer 串行。
16. WorkScope/ScopeConflictGate 在首次源码写前 current，repository-global leases 无冲突。
17. 全部 Agent `max-concurrent-tasks=1`；不同 Work Item 仅在 scope/lease 门禁允许时并行，同一 Work Item 由 stable integration branch 串行衔接；A02 ledger/lease/notification/queue 与 A16 report namespace 仍需 readback。
18. 同一 repository target 只有一个 evaluating/ready/merging IntegrationAttempt。

## 11. W6 验收检查

| 检查 | 结果 |
| --- | --- |
| 16 个 Agent 均有 required/optional/forbidden Skill | PASS |
| Skill 挂载来自 W5 responsibility，不是一律全挂 | PASS |
| Feature/Fix execution Skill 零交叉 | PASS |
| shared Agents 无业务产物 Skill，A16 只拥有 read-only commit-policy Skill | PASS |
| `multica-cli` 只给 A01/A02，`multica-triage` 只给 A01 | PASS |
| excluded Skill 无任何 binding；`conventional-commit` 只给 repository-writing roles 与 A16 | PASS |
| repository/command/git/Multica/network/destructive 权限有上限 | PASS |
| 凭据只允许 runtime injection | PASS |
| Loop bindings 固定 isolation none 且闭包完整 | PASS |
| Core/Loop、maker/checker、producer/reviewer 权限隔离可机械检查 | PASS |

W6 并发 amendment 固定单一 collaboration Runtime、Runtime-managed per-run worktrees、same-Work-Item writer serialization、cross-Work-Item scope/lease-gated parallelism、独立 session、repository-global lease、integration queue 和 stable integration branch continuity；commit amendment 把 producer-owned commit 与 A16 read-only policy verification 写入 Skill bundles 和权限上限。当前 revision 成为 W7–W8 的强制输入。
