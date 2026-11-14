```yaml
coach_stage: W8
decision: ACCEPTED
source_project: capability-sample-robox-nexus
source_revision: git:d24411c8840bab361745c1ed7b41cf4b3a43b3e3+mapping:sha256:8ab657d28bbb9ac295dd7c3c12d6cf9e54b150a2b6f2b29d6af4b7ccdbe3b6b8
requirements_revision: sha256:3b6caab15839cd7489bf30c23f9598a45fa309a3ade7a6227597ab83cb237d94
input_artifacts:
  - analysis/w7-template-delivery.md#sha256:de926790b0402a22b5738a9f577d73d5399092086f8a9f0ac340a0227f55bd3a
  - manifests/orchestration-package.yaml#sha256:d57997843ace312a4e21d7f636f07e91491d12d819e964ded94359a3b6787f1a
  - analysis/w6-skill-permission-bindings.md#sha256:180dac825603282c9c879c9ffb31e7a411af5a73131a77dc94a44fee8ebf1b32
  - contracts/handoff-gate-contracts.md#sha256:eef42b00a7630f5c801d87fe0bce9403fb09cea8f5625df7f72e0bcfc8c7cfbd
  - requirements/orchestration-requirements.md#sha256:3b6caab15839cd7489bf30c23f9598a45fa309a3ade7a6227597ab83cb237d94
output_artifacts:
  - controls/ci-proposal.yaml#sha256:9274eb16fd1ca3df9285952d841faceb761cdbefe6ec41b7cf3156e08134bba5
  - controls/provider-controls.md#sha256:9e9549ee694597981df37a70afb0f5ec761e6d7bec4b4cdb101f20b7f74dc564
  - controls/human-approvals.md#sha256:a8876cff824a1c435d43fcc6a45e4ce7cc1adf53c322c16574fd4633926a00a2
  - controls/human-participation-plan.template.yaml#sha256:48928b501ed776f7db53b9b74a8f99cd74e0d9cc7d22bc5634e83df7e1f797d4
decisions:
  control_mode: proposal-only
  default_worktree: false
  loop_isolation: none
  merge_release_deploy: denied-until-separately-defined
open_blockers:
  - TARGET_PROVIDER_UNRESOLVED
  - PROJECT_TEST_LINT_BUILD_COMMANDS_UNRESOLVED
  - HUMAN_IDENTITY_PROVIDER_UNRESOLVED
  - HUMAN_PARTICIPATION_PLAN_UNRESOLVED
  - APPROVAL_RECORD_STORE_UNRESOLVED
  - HUMAN_NOTIFICATION_CONTROL_UNVERIFIED
  - APPLIED_AGENT_SQUAD_PERMISSION_READBACK_UNAVAILABLE
  - MULTI_WORK_ITEM_EXECUTION_ISOLATION_UNVERIFIED
  - WORKFLOW_LEDGER_ATOMICITY_UNVERIFIED
  - RESOURCE_LEASE_CONTROL_UNVERIFIED
  - INTEGRATION_QUEUE_UNVERIFIED
  - COMMIT_CONTEXT_ISOLATION_UNVERIFIED
  - HUMAN_NOTIFICATION_DEDUPE_UNVERIFIED
  - STATUS_CONTRACT_HUMAN_CONFIRMATION_PENDING
supersedes: analysis/w8-enforcement-controls.md#sha256:f9acc9f7c276b559d69b82777d00dadc27ac6e2c13fd047d72ef63e9310478cc
```

# W8 CI、Provider 与 Human 强制控制分析

## 1. 本步骤结论

W8 已把 W3–W7 的合同、责任、权限和模板映射为三类控制 proposal：

1. CI 在 proposed merge revision 上验证什么；
2. repository/Multica/runtime provider 必须真正限制什么；
3. 哪些决定必须由可验证的 Human identity 作出。

这些文件没有安装控制，也没有修改 live workspace、repository、ruleset、branch protection、CODEOWNERS、CI、Agent、Squad、runtime、secret 或 Issue。Target provider 和目标项目命令尚未确定，因此不能生成声称可运行的 provider-specific workflow，也不能把当前仓库的 validation commands 冒充目标项目 Test/Lint/Build。

## 2. Instruction 与 enforcement 的边界

| 规则 | Instructions 作用 | 硬控制 owner | 不能接受的替代证据 |
| --- | --- | --- | --- |
| Agent write scope | 告知角色允许/禁止行为 | repository/provider permission + CI changed-path check | Agent 自述“未越界” |
| Feature/Fix 隔离 | 定义身份与 Skill 边界 | applied binding readback + CI manifest comparison | 文件名或 Squad prompt |
| baseline tests | 要求 Maker/Verifier提供证据 | target CI baseline checks + Human integration checkpoint | 本地未绑定 revision 的日志 |
| Human governance | 要求展示 diff 和等待决定 | authenticated Multica-account designation + Human review ledger | review Agent PASS、沉默、Issue status |
| GitFlow branch procedure | 定义 branch/base/target 与 Agent deny | provider checkout/PR/IntegrationRef + Human integration operator | 将 README/模板或 GitHub branch protection 当作已执行 integration |
| secret scope | 禁止输出凭据 | runtime secret store + effective permissions | 模板中没有 token |
| Core/Loop exactly-one | 定义 route 与 handoff | ledger/CI route check + provider checkout lock | Leader 口头说明 |
| lifecycle readback | 要求写后读取 | Multica/provider audit | CLI exit 0 |
| Work Item checkout | 要求每个 run 固定 execution、同一 Runtime 与独立 task branch/worktree | WorkItemBranchRef/RunCheckoutRef/CheckoutRef、Project resource/capability、cwd/session/branch/HEAD readback | Agent 声称“在正确目录” |
| Cross-item scope/resource control | 要求同一 Work Item writer 串行，并保留 WorkScope/ScopeConflictGate | provider admission + scope registry + atomic LeaseRecord | “不同 Agent 会自动隔离” |
| Integration concurrency | 要求 exact source/target attempt | repository-target atomic queue + proposed-merge checks | PR 可合并图标或旧 CI |
| Notification concurrency | 要求 request-bound发送 | atomic reservation + provider receipt | 进程内检查后直接发送 |

结论：Instructions 是可审计意图，不是安全边界。能由机器阻断的规则进入 CI/provider；需要价值判断的规则进入 Human checkpoint。

## 3. CI proposal

`multica-orchestrator-nail-down/references/ci-proposal.yaml` 定义十二个 integration baseline checks：

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

route/Loop 完整性折叠进 `orchestration-contract`，portable/secret safety 折叠进 `permission-boundary`。十二个 checks 必须在 current `IntegrationAttemptRef` 的 exact source/target proposed merge revision 上成功，并由 Human integration operator 核对；不要求 GitHub branch protection 使用这些名称。

`project-test`、`project-lint`、`project-build` 的命令刻意保持 `unresolved`。安装前必须由目标项目 maintainer 从其维护的 CI contract 解析；本模板不能根据能力样本或当前生成仓库猜命令。项目确实没有 lint/build 时，只能用 Human/maintainer 接受的项目级 N/A policy，不能由 Maker 临场跳过。

### 3.1 关键 failure

| Check | Failure | 处理 |
| --- | --- | --- |
| orchestration contract | `ORCHESTRATION_CONTRACT_INVALID` | 修复 manifest/schema/reference owner；禁止 merge |
| work type isolation | `WORK_TYPE_ISOLATION_BREACH` | 平台管理员撤销交叉 binding/membership |
| execution isolation | `MULTI_WORK_ITEM_EXECUTION_ISOLATION_UNVERIFIED` | 修复 current execution/checkout/root/session readback |
| scope conflict | `WORK_SCOPE_CONFLICT_UNRESOLVED` | 收紧 scope、等待依赖/integration 或交 Human |
| resource lease | `RESOURCE_LEASE_CONTROL_UNVERIFIED` | 修复原子 lease store，禁止冲突 writer |
| integration target | `INTEGRATION_QUEUE_UNVERIFIED` | 在最新 target revision 重新入队和检查 |
| artifact revision | `ARTIFACT_REVISION_MISMATCH` | 从最早 stale dependency 重跑 |
| permission boundary | `PERMISSION_BOUNDARY_VIOLATION` | 撤销越权并由正确 owner 重新产生 change |
| Human evidence | `HUMAN_APPROVAL_EVIDENCE_INVALID` | 请求真实 Human 对 exact revision 决定 |
| test/lint/build | 对应 `PROJECT_*_FAILED` | 返回 artifact owner；环境缺失为 BLOCKED，不假 PASS |

## 4. Provider controls

`multica-orchestrator-nail-down/references/provider-controls.md` 定义 29 个控制，覆盖：

- GitFlow branch provisioning、每个 current Work Item 独立 execution/checkout/root；
- WorkScope registry、ScopeConflictGate 与 repository-global atomic resource lease；
- source head 与 target evaluation revision 分离和精确 invalidation；
- 同一 repository target 串行 IntegrationAttempt queue；
- PR exact source/target、十二个 baseline checks 和人工 integration；
- governance/control/security/data path 的真实 Human owners；
- Multica status 的 Human Web confirmation；
- Agent/Squad/Skill/permission effective readback；
- A01 execution admission 与原子 dispatch 去重；
- A02 compare-and-set ledger + bounded designated-Human notification；
- current HumanParticipationPlanRef、exact recipient mapping、atomic notification reservation 和 receipt；
- provider-approved WorkItemBranchRef.v1、RunCheckoutRef.v1 与 CheckoutRef.v5；
- 全部 Agent 指向一个声明 `local-worktree-v1` 的 collaboration Runtime，Project `local_directory` 为 `execution_mode=worktree`；同一 Work Item writer 串行，不同 Work Item 受 scope/lease 门禁；
- repository-writing Agent 的 scoped ordinary commit、A16 read-only validation、run worktree cwd/task-branch/HEAD/index readback、Work-Item footer、hook 与 PR range validator；
- IntegrationRef.v2 与通用 MergeResolutionRef.v2 readback；
- Release/Hotfix back-merge、tag 与 PromotionRef；
- runtime-only secret injection；
- authenticated Multica account email matching and explicit consent；
- Human decision 不自动 dispatch；
- Agent 默认拒绝 destructive/merge/release/tag/deploy/schema 管理。

Provider-specific syntax 延迟到已选择真实 provider 后处理。当前只给出语义规则、baseline check names、Human review mapping、安装顺序和必要的 receipts/confirmations，避免生成不能运行却看似完整的 GitHub/GitLab 配置。

## 5. Human approval controls

[`../controls/human-approvals.md`](../controls/human-approvals.md) 使用 W3 canonical `HumanDecisionRef.v4`，并以 [`../controls/human-designation-policy.yaml`](../controls/human-designation-policy.yaml) 和 [`../controls/human-designation-contract.md`](../controls/human-designation-contract.md) 约束 designation。它覆盖十个 subject：

- `governance-input`
- `constitution`
- `architecture`
- `adr`
- `roadmap`
- `tasks`
- `implementation-route`
- `loop-signoff`
- `risk-override`
- `final-acceptance`

每个 subject 都定义触发点、Human evidence、接受效果和自动失效条件。首个 producer 前必须有 current designation/plan；scope conflict 的非机械优先级由 Human 决定，但不新增泛化 approval subject。recipient 只用于投递，不接受业务产物。

Gate owner 生成 current request 后，Leader 必须先按 project/work item/subject/designation/plan/sorted revisions 原子预留 initial notification，再发送 exact member mention并 readback；并发 Leader task 不得重复发送。`final-acceptance` 不授权 integration，最新 target 上的 provider integration approval 仍由 integration operator负责。

## 6. 高风险副作用处理

当前 W1–W7 没有部署、发布、迁移或 workspace schema 管理能力，因此 W8 不为其制造“审批后可执行”路径，而是默认拒绝：

| 副作用 | 当前策略 | 未来启用所需 |
| --- | --- | --- |
| merge | deny | provider merge artifact、八个 baseline check 收据、独立 Human approval、权限/readback |
| release | deny | release producer/verifier、artifact、rollback、approval |
| deployment | deny | environment/provider、deployment evidence、target verification、approval |
| data migration | deny | migration plan、backup/rollback、dry run、data owner approval |
| secret/permission change | deny | security owner、narrow diff、audit/readback |
| workspace schema/status definition | workspace admin only；本流程不执行 | Human Web confirmation of key/category；无需 status evidence |

这不是功能缺失的 fallback，而是对未建模高风险能力的正确拒绝。

## 7. Status、Gate 与 approval 分离

- Multica status 只表示平台生命周期：`needs_triage/backlog`、`needs_information/blocked`、`ready_for_agent/backlog`、`ready_for_human/todo`、`wontfix/cancelled`。
- Gate 只使用 `APPROVED|APPROVED_NA|REJECTED|BLOCKED`；运行态可记录 `STALE`。
- Human decision 只使用 `ACCEPTED|REJECTED|REVISION_REQUESTED`。

三者不能互相代替。特别是 `ready_for_agent` 不会启动 run，`ready_for_human` 不表示批准，CI success 不表示 Human acceptance。

## 8. 安装前必须解析的信息

1. provider 类型、repository、default branch 与 GitFlow integration-branch provisioning/PR integration capability；
2. Human 选择的 collaboration Runtime、全部 Agent runtime binding、`local-worktree-v1` capability 与 Project `local_directory(execution_mode=worktree)` readback；
3. same-Work-Item writer serialization、cross-Work-Item scope/lease policy、独立 session/worktree 与 task-branch/baseline/HEAD readback；
4. workflow ledger compare-and-set、scope registry 和 repository-global lease；
5. repository-target integration queue、stable integration fast-forward、exact source/target proposed-merge check 和 merge receipt；
6. designated Human authenticated email 与 explicit consent；
7. participation plan、exact recipient、atomic notification reservation、scheduler、stop policy 与 receipt；
8. project Test/Lint/Build commands、matrix 和 N/A policy；
9. canonical Issue identity、branch naming、Work-Item footer、commit hook/range validator 和 scoped staged-set readback；
10. Agent/Squad/Skill/permission effective readback 与 status contract 的 Human Web confirmation。

因此控制文件保持 `proposal`，这些项是 application blocker，不是 W8 文档生成 blocker。

## 9. 安装与验证合同

经 Human 接受 W8 后，未来 installer 必须按以下顺序工作：

1. 选择 target provider/repository/integration operator 和 collaboration Runtime；
2. 验证 Runtime `local-worktree-v1`，将全部 Agent 绑定到该 Runtime，并配置 Project `local_directory(execution_mode=worktree)`；
3. 配置 WorkItemBranch/RunCheckout readback、same-Work-Item writer serialization、cross-Work-Item scope/lease-gated parallelism 和 repository-target integration queue；
4. 配置 workflow ledger compare-and-set 与 dispatch dedupe；
5. 在 operator-local ledger 记录 authenticated email、explicit consent 和 participation plan；
6. 验证 exact recipient、atomic notification reservation、scheduler、reminder 上限、stop conditions 和 receipt；
7. 固定 target CI commands/matrix，安装十二个 check adapter并读取触发器、permissions 和 names；配置 GitFlow provisioning、provider baseline/fast-forward、人工 integration、commit hook/range validator 和 secret binding；
8. Human 在 Multica Web 核对 status key/category；
9. 应用 Agent/Squad/Skill/permission 并逐项 readback；全部 Agent concurrency 固定为一，且 A02 原子性/A16 report isolation 仍必须验证；
10. 只读验证所有配置；另行取得 W9 live trial 授权后才可创建真实任务或 dispatch。

禁止用创建测试 Issue、dispatch Agent、修改 live schema、文件存在或 CLI exit 0 验证 W8 installation。

## 10. W8 验收检查

| 检查 | 结果 |
| --- | --- |
| CI、provider、Human 三类 proposal 齐全 | PASS |
| 十二个 baseline checks 在 exact source/target proposed merge revision 上定义 | PASS |
| 每个 Work Item 独立 execution/checkout/root，跨项 scope/lease 有硬控制 | PASS |
| source head 与 target evaluation revision 精确失效 | PASS |
| 同一 repository target integration queue 串行 | PASS |
| Feature/Fix identity 与 Skill 隔离可机械检查 | PASS |
| W6 write scope 映射到 scope registry、lease 与 changed-path control | PASS |
| Constitution、Architecture、ADR、Roadmap、Tasks、route、Loop、final acceptance 保留 Human | PASS |
| Human notification 原子去重、bounded reminder 和 non-auto-dispatch 完整 | PASS |
| A02/A16 缺并发 readback 时 concurrency=1 | PASS |
| branch provisioning、CommitRef、Work-Item footer、IntegrationAttempt/Ref 可机械检查 | PASS |
| 凭据仅 runtime 注入且 portable template 禁止敏感信息 | PASS |
| 未建模 release/deploy/data/schema side effect 默认拒绝 | PASS |
| provider-specific 未知项明确为安装 blocker | PASS |
| 没有 live provisioning、dispatch、W9 或安装成功声明 | PASS |

W8 并发 amendment 已纳入 proposal-only controls；它不授权 W9/W10、live provisioning、trial、merge、release 或 deployment。
