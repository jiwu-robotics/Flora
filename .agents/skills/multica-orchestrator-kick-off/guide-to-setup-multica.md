# 配置通用 Multica 编队

本指南消费 `multica-orchestrator-link-up` 生成的已验证 Workspace 基础，只配置
workspace Skills、16 个 Agents 和 Feature/Fix Squads。Workspace、标签、Issue
Status、Runtime 生命周期、Project、repository、CI 和 provider 控制都不由本 Skill
修改。

## 权威输入

- [`manifests/orchestration-package.yaml`](manifests/orchestration-package.yaml)：package `9.0.0`，16 个 Agent、两个 Squad、精确 Skill bindings 与 role/operation invocation policy。
- [`contracts/handoff-gate-contracts.md`](contracts/handoff-gate-contracts.md)：运行时 `ExecutionContextRef.v1`、`ArtifactRef.v2`、`GateRecord.v2`、`HandoffRef.v3`、`LeaderDispatchRef.v1`、`WorkItemExecutionRef.v4`、`WorkItemBranchRef.v1`、`RunCheckoutRef.v1` 与 `CheckoutRef.v5` 协议。
- [`contracts/server-orchestration-ref.schema.json`](contracts/server-orchestration-ref.schema.json)：`ServerOrchestrationRef.v10` 交接格式。
- [`setup/preflight.md`](setup/preflight.md)：Foundation handoff 与 server/workspace 只读预检。
- [`setup/runtime-and-skills.md`](setup/runtime-and-skills.md)：继承 Runtime 和配置 workspace Skills。
- [`setup/agents-and-squads.md`](setup/agents-and-squads.md)：Agent/Squad application。

## 硬停止条件

以下任一项未解析时不得写 workspace Agent layer：

- Foundation bundle 或其 current `WorkspaceFoundationRef.v6` 缺失、摘要不符、状态非 verified；
- Foundation 中 server/profile/account/workspace 不唯一；
- Foundation Runtime fleet 任一目标非 online、daemon ref 或 capability revision 缺失；
- Foundation 中五个 canonical status key/category 未验证；
- target model、per-role Runtime alias、nullable thinking level 或 concurrency 未由 Human 选择；
- required Skill source、archive 或 workspace content digest 不一致；
- Agent/Squad/Skill 的有效配置无法 readback；
- 输入包含 repository、Project、local path、checkout 或 Work Item。

## 顺序

1. 按 [`setup/preflight.md`](setup/preflight.md) 验证 Foundation handoff，并创建
   mode-0700 operator-local state。
2. 按 [`setup/runtime-and-skills.md`](setup/runtime-and-skills.md) 验证完整 online Runtime
   fleet，解析每个 role 的 Runtime alias，构建 Skill integrity lock，并取得 Skills phase PASS。
3. 按 [`setup/agents-and-squads.md`](setup/agents-and-squads.md) 精确应用 16 个 Agent、逐角色 Runtime placement 和两个 Squad。
4. 每次已授权的 operation 后都捕获完整 readback 并重新 plan；只有当前计划的
   `operations` 为空时，才开始最终验证。
5. 从最终 readback 运行 `cli/verify_skill_integrity.py --phase full` 和
   `cli/verify_server_application.py`；后者生成
   `multica-orchestrator.server-verification.v3` report。
6. 使用该 v3 report 调用 `cli/emit_server_handoff.py`，生成含
   `ServerOrchestrationRef.v10`、`ServerVerificationSpec.v3` 与
   `ServerReissueSpec.v1` 的 parent-linked bundle，并原子发布到本地 CAS、Server
   pointer 和 deployment index。

每个 live mutation 必须来自已审阅 plan，并由 `cli/apply_server_operation.py`
一次执行一个 operation。写后立即 readback；中断时先读实际状态，不盲目重试。

## 完成边界

成功状态固定为：

```text
ORCHESTRATOR_LAYER_VERIFIED
BLOCKED_PROJECT_BINDING
```

它不授权创建 Issue、dispatch、branch、checkout、commit、PR、merge、release 或部署。
每个目标项目继续调用 `multica-orchestrator-nail-down`。
