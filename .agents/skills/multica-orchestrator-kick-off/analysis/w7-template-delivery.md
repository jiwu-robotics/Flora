```yaml
coach_stage: W7
decision: ACCEPTED
source_project: capability-sample-robox-nexus
source_revision: git:d24411c8840bab361745c1ed7b41cf4b3a43b3e3+mapping:sha256:8ab657d28bbb9ac295dd7c3c12d6cf9e54b150a2b6f2b29d6af4b7ccdbe3b6b8
requirements_revision: sha256:3b6caab15839cd7489bf30c23f9598a45fa309a3ade7a6227597ab83cb237d94
input_artifacts:
  - analysis/w6-skill-permission-bindings.md#sha256:180dac825603282c9c879c9ffb31e7a411af5a73131a77dc94a44fee8ebf1b32
  - analysis/w5-agent-responsibility-matrix.md#sha256:9a5013063787d7cb08aa765bf0a811a223372e138b6164f16cf2c46581f68d5c
  - analysis/w4-feature-fix-dags.md#sha256:dbd02ee0e78cf2881e2ecd0931d773a836a5183c072c08baa4e9df035ca63673
  - contracts/handoff-gate-contracts.md#sha256:eef42b00a7630f5c801d87fe0bce9403fb09cea8f5625df7f72e0bcfc8c7cfbd
  - requirements/orchestration-requirements.md#sha256:3b6caab15839cd7489bf30c23f9598a45fa309a3ade7a6227597ab83cb237d94
output_artifacts:
  - manifests/orchestration-package.yaml#sha256:d57997843ace312a4e21d7f636f07e91491d12d819e964ded94359a3b6787f1a
  - agents/agent-instructions.md#sha256:94549a9aeda14790a8b1138a20060e25c9dacb9246f638720f60316770ec349b
  - agents/roles/shared-intake.md#sha256:9beea76baff897fc8f2812b3bd1b3a5315c5b4b85876ce4c4665d77634c061a6
  - agents/roles/workflow-leader.md#sha256:bd26591d749976add54b98f26aef7652e8e69e883407cccc4356e12752d3f925
  - agents/roles/feature-governance-producer.md#sha256:bfa48399d9dd7492749848a3224e7729c57c57f1115b86901252251d65875c65
  - agents/roles/feature-requirement-producer.md#sha256:b810465bc8d43b1c12b1e359e7c1990233c0eccbedacba70677334eaa3274fa0
  - agents/roles/feature-requirement-reviewer.md#sha256:0d4e95c0063350ccce80de2d79d61d126e50bf8b6cd65cb84212941e64f2d34d
  - agents/roles/feature-planning-producer.md#sha256:db2de80f1cc3d1c7381006877a814ad2c95eee77f4b3f5b5fc16d743238fa104
  - agents/roles/feature-reviewer.md#sha256:302d2c93e2f662c2b02df964abce3acc2abd674cebf3e977985377de50e134bc
  - agents/roles/feature-core-maker.md#sha256:9c010227443f939ec3de0cb1ab7b30c57019840636d4093dce53c8823306bb3c
  - agents/roles/feature-loop-maker.md#sha256:117b1cf79f7d2c4cbb2c821b3be0de35744a0a3a394ba3a1f6452772c1dd32ed
  - agents/roles/feature-loop-checker.md#sha256:0c792f03bbacefff4383584c0513de7c0667c54403cb850c64f2f4caf0211efd
  - agents/roles/feature-loop-guard.md#sha256:43be0318e50872e774b0e260bf28c6a8d7ba3a24b7420d7725d736f805fa2218
  - agents/roles/feature-convergence-reviewer.md#sha256:b5a33f4af2c616da8f8c150d7bb8a34a3972c1722a02df8e73e9bde52e6a6943
  - agents/roles/fix-assessor.md#sha256:9f1f72bab2bf73eca25ae3f52fa48944b59f2bc631603530f5b6b63154d6f649
  - agents/roles/fix-maker.md#sha256:39dada5cf60cf0e4088294fad6ed0725a421d257d4a3e79623c366fc07608528
  - agents/roles/fix-verifier.md#sha256:410e5d1128be64f8446e0ce6aecb6337fcfe7b9cd760b9bdd6f41ef823cd6321
  - squads/squad-instructions.md#sha256:6714cd5901a106eaf7d25ad0c3a000023268aedb89c76c6d2ac31024797644e5
  - squads/feature-squad.md#sha256:6d5cbd0712b6d43768cc1ac4e41e9030114549a5a7c2a805fc8493156153c416
  - squads/fix-squad.md#sha256:b55459930bd23561904649fb44b66d55b61d7ba2e2a187a4db1b2d32a97b1cdd
  - issues/issue-input-contracts.md#sha256:5ea341c588ef7089d5060b992f384b474a01f63a01a6b0a6b8dcb58bb62a73fc
  - delivery/delivery-notes.md#sha256:93778cf8d3838e128ef83ef88f129bca9b6b8bbf510926329cba697429316fde
decisions:
  default_worktree: false
  loop_eligible: true
  loop_isolation: none
open_blockers: []
supersedes: analysis/w7-template-delivery.md#sha256:a4f767e30f21cba61ed1220664fa4c577a0f60783dcffbce0f538685f231e8ed
```

# W7 Agent、Squad、Issue 与 Package 模板交付分析

## 1. 本步骤结论

W7 已把 W1–W6 接受的设计转换为 Human 已接受的本地期望状态模板，并纳入多 Work Item execution、scope conflict、repository-global lease、source/target revision 分离和 integration queue。模板的 application state 仍是 `proposal`：没有创建或修改 live Multica 对象、repository integration 或 provider policy，也没有 dispatch 或运行 W9。

交付采用一个 manifest、一个 Agent 索引、16 份独立中文 Agent Instructions、一个 Squad 索引、两份独立 Squad Instructions、两份 Issue input template、branch/commit contract 和 delivery note。每个 Agent/Squad 文件都是完整可复制单元；并发能力来自 execution-bound refs 和 provider enforcement，不来自复制角色或扩大权限。

## 2. Artifact index 与完整性

| Logical ID | Path | SHA-256 | 作用 |
| --- | --- | --- | --- |
| `PACKAGE_MANIFEST` | `../manifests/orchestration-package.yaml` | `33ab037396e576c2058beafee22e02829e704cd0876f14795d4126bac4655809` | Agent/Skill/permission/Squad/policy/precondition 的 machine-readable SSOT |
| `AGENT_INSTRUCTIONS` | `../agents/agent-instructions.md` + `../agents/roles/*.md` | 索引和各文件 digest 见 provenance | 16 个独立、完整、中文 role Instructions |
| `SQUAD_INSTRUCTIONS` | `../squads/squad-instructions.md` + `../squads/*-squad.md` | 索引和各文件 digest 见 provenance | 独立中文 Feature/Fix 路由、Gate、失败和 Human 边界 |
| `ISSUE_INPUT_CONTRACTS` | `../issues/issue-input-contracts.md` | `7bca83da3a6045d08c5bd331342cc4904b751326f6661d912953259b842c18bc` | Feature/Fix 可判定输入模板 |
| `DELIVERY_NOTES` | `../delivery/delivery-notes.md` | `3cb561d3918a0a12d0aa6a75d9de1f68d6e5e11e6674ae383585b6726a94d8e6` | operator assembly、前置条件、已知 drift 和未执行边界 |
| `BRANCH_COMMIT_POLICY` | `../contracts/branch-and-commit-policy.md` | policy digest 见 manifest | branch identity、candidate/commit、Work-Item footer 和 provider readback contract |

所有相对链接均解析在 `orchestrator/` 内。Sibling outputs 已以当前 exact digest 进入 W7 provenance；任何后续变更都会使依赖的 W8 产物失效。

## 3. Agent Instructions 覆盖

`agent-instructions.md` 只保留索引；`agents/roles/` 下 16 个文件与 W5 role key 一一对应，并由 manifest 的 `agents[*].instructions` 显式引用：

- 每个文件描述身份、Skill/权限、execution/checkout/scope 输入、职责、门禁、禁止项、失败和完成条件。
- 每个 Multica Agent 直接使用一个 role 文件，不拼接总文件，也不为每个 Work Item 复制 Agent identity。
- Shared Intake/Leader 之外没有 Multica 权限。
- A01 的 dispatch 使用 repository/work-item/work-type/epoch 原子去重。
- A02 维护 execution/scope/lease/integration-attempt state；无原子 ledger readback 时并发上限为一。
- A16 只绑定 `conventional-commit` 和 commit-only permission；无 cwd/Git index 隔离 readback 时并发上限为一。
- Feature/Fix execution 文件零交叉；A04–A15 只有在独立 execution/checkout/root/session、scope CLEAR 和无冲突 lease 时才可跨 Work Item 并发。
- Core/Loop、Loop Maker/Checker/Guard、Task Planner/Convergence/Analyze 的写入和批准边界保持不变。
这种拆分让每个 Agent 的实际 Instructions 文件可独立审阅和应用，同时防止把全部 Skills 或职责集中到一个 Agent。“超级个体”来自编排完整性，不来自单 Agent 越权。

## 4. Squad Instructions 覆盖

Feature 与 Fix Squad 均包含 reference 要求的 11 个部分：

1. 目标与事实来源；
2. 团队与角色边界；
3. 范围路由；
4. 阶段图；
5. Skill 调用；
6. 产物传递；
7. 门禁规则；
8. 失败处理；
9. 失效规则；
10. 升级规则；
11. 完成定义。

`squad-instructions.md` 只保留索引；`feature-squad.md` 与 `fix-squad.md` 分别是完整中文模板。Feature template 固定 Human governance loop、Tasks Review、Core/Loop 路由、Loop isolation none、Debrief/Converge 和同 route 返工。Fix template 固定 Assess/Fix/Test 分离和 Feature escalation hard cut。两者均声明 Agent 完成不等于 Issue 完成，且不包含部署、发布、merge 或 live setup 权限。

## 5. Issue Templates 覆盖

### Feature

除 reference 最小字段外，还提供：

- 明确 `work_type: feature`；
- source type/ref/revision/authorized scope；
- affected surface routing flags；
- stable `AC-*`；
- governance impact；
- dependencies/environment；
- verification expectations；
- permissions/risk；
- open question owner；
- intake readiness checklist。

任一 `unknown` 必须有 owner/resolution trigger。模板完整只允许产生 Current Brief，不自动 dispatch。

### Fix

除 reference 最小字段外，还提供：

- 明确 `work_type: fix`；
- existing accepted contract ref；
- version/environment/config/test data；
- deterministic reproduction；
- severity/evidence；
- stable `BAC-*`；
- Feature escalation screen；
- authorized check/write boundaries；
- Human/manual evidence；
- intake readiness checklist。

缺 reproduction/environment/expected contract 时 XG0 BLOCKED；任一 Feature escalation 条件成立时不得启动 Fix workflow。

## 6. Manifest 闭包

Manifest 同时固定：

- 五个 Multica status key/category 和四个独立 Gate values；
- single collaboration Runtime、Project `local_directory(execution_mode=worktree)`、`local-worktree-v1` capability、same-Work-Item writer serialization、no nested worktree；
- WorkItemExecutionRef.v4、WorkItemBranchRef.v1、RunCheckoutRef.v1、CheckoutRef.v5、WorkScope、ScopeConflictGate、repository-global resource lease；
- source head 与 target evaluation revision 的精确失效边界；
- 同一 repository target 串行 IntegrationAttempt queue；
- Core/Loop exactly-one route 与 first-write lock；
- Loop all-or-none membership/binding/config；
- 21 个 Feature、3 个 Fix、10 个 excluded Skill bundles 和单一 source-control bundle；
- 16 个 role bindings、permissions、并发前提和 Squad memberships；
- Shared Intake 与 A16 位于执行 Squads 之外；
- Human approval/notification 原子去重；
- runtime preconditions、失败 key 和 Issue done 条件；
- `live_resources_created: false` 与 `live_trial_executed: false`。

Manifest 不包含 Agent/Squad/runtime/workspace UUID、profile、server 或 credential。它描述期望状态，不能代替 supported application/readback。

## 7. 交付前置条件

W7 保留以下真实环境前置条件，不提供假 fallback：

| 前置条件 | Owner | 未满足 |
| --- | --- | --- |
| Human 在 Multica Web 核对并同意 status key/category | Human + workspace administrator | `STATUS_CONTRACT_DRIFT` |
| canonical Requirement fragments 可解析 | repository provider | `REQUIREMENT_RULES_UNAVAILABLE` |
| mandatory after-Specify worktree hook 已禁用 | repository provider | `WORKTREE_HOOK_CONFLICT` |
| 每个 Work Item 独立 execution/checkout/root | Project/Runtime + Human | `MULTI_WORK_ITEM_EXECUTION_ISOLATION_UNVERIFIED` |
| 原子 ledger、scope registry 与 repository-global resource lease | orchestration owner + provider | `WORKFLOW_LEDGER_ATOMICITY_UNVERIFIED` 或 `RESOURCE_LEASE_CONTROL_UNVERIFIED` |
| 同一 repository target 串行 integration queue | repository provider | `INTEGRATION_QUEUE_UNVERIFIED` |
| Conventional Commit hook/range validator、A16 cwd/index isolation | repository provider/admin | `COMMIT_POLICY_INVALID` 或 `COMMIT_CONTEXT_ISOLATION_UNVERIFIED` |
| Human notification reservation 原子去重 | provider + designation operator | `HUMAN_NOTIFICATION_DEDUPE_UNVERIFIED` |
| Loop effective isolation none + independent checker + shared state/budget + Human guard | runtime/provider/Human | `LOOP_INELIGIBLE` |

这些 blocker 不阻止生成或 passive application portable templates，但会阻止相应 live concurrent dispatch/write/integration。

## 8. 未执行与非目标

- 未调用 `multica-orchestrator-link-up`、`multica-orchestrator-nail-down`、`multica-create-agent`、`speckit-setup-project` 或 `speckit-taskstoissues`。
- 未创建测试 Issue、Agent、Squad 或 run。
- 未导入/绑定 Skill。
- 未修改 live status definition、labels、properties、projects、runtimes 或 repositories。
- 未触发 mention、assignment、dispatch、rerun、cancel、commit、push、merge、release 或 deployment。
- 未声称 W8 controls 已安装，未声称 W9 trial 已执行。

## 9. W7 验收检查

| 检查 | 结果 |
| --- | --- |
| Agent/Squad/Issue/manifest/delivery 五类产物齐全 | PASS |
| 16 个独立中文 Agent 文件与索引、manifest 一一对应 | PASS |
| 两个独立中文 Squad 文件包含 execution/scope/lease/integration queue 规则 | PASS |
| Feature/Fix Issue 输入足以驱动路由而无需 Leader 猜测 | PASS |
| Feature/Fix Skill 与 Agent identity 未交叉 | PASS |
| 单一 collaboration Runtime、per-run Runtime worktree、same-Work-Item writer serialization 与 scope/lease-gated cross-item parallelism | PASS |
| source head 与 target evaluation revision 失效分离 | PASS |
| 全部 Agent `max-concurrent-tasks=1`，A02/A16 原子性与隔离 readback 保留 | PASS |
| Human governance/tasks/route/guard/final authority 与通知去重保留 | PASS |
| Loop all-or-none 且 isolation none | PASS |
| exclusions 未进入 required/optional bindings | PASS |
| 无 live identifier、credential、绝对机器路径或部署成功声明 | PASS |
| delivery notes 明确 proposal、并发前置条件和 W8/W9 边界 | PASS |

W7 并发 amendment 已纳入 Agent/Squad/manifest 期望状态；当前 exact-revision templates 成为 W8 的强制输入。
