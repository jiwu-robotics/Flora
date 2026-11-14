# Project binding 完成判定

## Binding gates

Nail Down 只验证 Project/repository 静态绑定：

1. current Foundation → Server bundle closure 与 live ProfileSession 一致；
2. `ServerOrchestrationRef.v10`、Agent/Squad generation 与 Runtime fleet 已验证；
3. repository registry、Project 和 Project GitHub resource 唯一且身份一致；
4. `RuntimeTargetPolicy.v4` 只有一个 feature/fix collaboration Runtime，并绑定 current `required_capability_revision`；
5. Project policy、command profiles、native Squad routing 和 Dispatch contract digest 完整；
6. 四个 portable repository files 实际存在且 digest 非空。

Work Item execution、checkout、scope、lease、queue、Human decision 和 provider checks 不属于 binding gate。它们由 `multica-orchestrator-dispatch` 在每次真实 execution/integration 中验证。

## Repository files

Nail Down 只允许提交：

```text
.multica/agents/issue-tracker.md
.multica/agents/triage-mapping.md
.multica/agents/domain.md
.multica/agents/orchestrator-binding.yaml
```

禁止写入 workspace/Project/resource/Agent/Squad/Skill/runtime UUID、server、账号、Human identity、receipt、secret、absolute path、repository HEAD 或 control-store path。

## State

成功状态固定为：

```text
state=PROJECT_BOUND
activation_state=ACTIVE
```

任何 blocker 都在 Project binding、bundle、candidate 和 pointer 写入前停止；不存在 `PARTIAL`、`PROVIDER_BOOTSTRAP_PENDING` 或 `DISPATCH_BLOCKED` candidate。

`multica-orchestrator-migrate` 创建/更新 target-local `local_directory(execution_mode=worktree)` resource，验证 capability revision，汇总 Runtime receipts，并发布 `ActiveProjectRelease.v2`。之后 `multica-orchestrator-dispatch` 才可为 canonical Work Item 创建 `RunAdmissionRef.v1` 与 mutable execution controls。
