# Agent Instructions 索引

> W9 ACCEPTED。此文件仅是索引；每个 Agent 的完整中文 Instructions 位于独立文件。模板没有创建 live Agent、绑定 Skill 或授予权限。

## 使用规则

1. 每个 Multica Agent 只能使用与其 `role_key` 对应的一个文件。
2. 独立文件均包含完整 native Squad trigger、职责、输入、写入范围、禁止项、回报和完成合同，不需要拼接本索引。
3. 保留文件中的 `role_key`、`work_type`、Skill 名称和权限边界。
4. 只替换尖括号占位符；不得写入凭据、workspace UUID、server、个人账号或绝对机器路径。
5. `workflow-leader` 是两个 Squad 的唯一 Leader；`shared-intake` 和 `commit-policy-reviewer` 是两个 Squad 的共享成员。其他 Feature/Fix execution members 不得交叉。
6. Leader 可在一条 delegation comment 中使用 current roster 提供的 exact mention 路由一个或多个成员；每个成员必须有独立 `LeaderDispatchRef.v1`。Leader 不 assign、直接 rerun/cancel、mention Squad/`@all`，也不把 Human notification 与 Agent delegation 混在同一 comment。
7. 每个 run 必须先固化 `ExecutionContextRef.v1`。pre-admission `shared-intake` 与 workflow-leader native bootstrap 不得伪装为已有 execution context；Leader 成功 `admit-or-resume` 后，context 必须同时绑定 current `ProjectBindingRef.v12`、`ActiveProjectReleaseRef`、`RunAdmissionRef.v1` 及其 digest。execution member 只接受 current Leader mention 并消费唯一 `LeaderDispatchRef.v1`、`HandoffRef.v3` 和 role-allowed `operation_key`。完成后不 mention 下一 Agent，...
8. Handoff READY、Gate approved、Human accepted 或 native trigger 只表示本轮 evaluation eligibility，不等于业务授权。Leader 必须重验 current revision、scope、lease、run dedupe 和 HumanDecisionRef 后才可决定下一次 mention。
9. 所有 repository-writing Agent 与 `commit-policy-reviewer` 命中同一支持 `local-worktree-v1` 的 collaboration Runtime。每个 run 使用独立 Multica worktree/task branch；不同 Work Item 可并行，但同一 Work Item writer 串行，且每次 dispatch 前由 provider 将 local base 对齐 current integration branch head。
10. 每个 repository-writing Agent 必须在自己的 run 结束前用 `conventional-commit` 创建 scope-bound `CommitRef.v2`；`commit-policy-reviewer` 只读验证，provider 再将 stable integration branch 快进到 exact commit。任何未登记 commit、baseline 分叉或跨 Agent 自动 merge/cherry-pick 一律阻塞。

## 文件清单

| Role key | Work type | Instructions |
| --- | --- | --- |
| `shared-intake` | `shared` | [`roles/shared-intake.md`](roles/shared-intake.md) |
| `workflow-leader` | `shared` | [`roles/workflow-leader.md`](roles/workflow-leader.md) |
| `feature-governance-producer` | `feature` | [`roles/feature-governance-producer.md`](roles/feature-governance-producer.md) |
| `feature-requirement-producer` | `feature` | [`roles/feature-requirement-producer.md`](roles/feature-requirement-producer.md) |
| `feature-requirement-reviewer` | `feature` | [`roles/feature-requirement-reviewer.md`](roles/feature-requirement-reviewer.md) |
| `feature-planning-producer` | `feature` | [`roles/feature-planning-producer.md`](roles/feature-planning-producer.md) |
| `feature-reviewer` | `feature` | [`roles/feature-reviewer.md`](roles/feature-reviewer.md) |
| `feature-core-maker` | `feature` | [`roles/feature-core-maker.md`](roles/feature-core-maker.md) |
| `feature-loop-maker` | `feature` | [`roles/feature-loop-maker.md`](roles/feature-loop-maker.md) |
| `feature-loop-checker` | `feature` | [`roles/feature-loop-checker.md`](roles/feature-loop-checker.md) |
| `feature-loop-guard` | `feature` | [`roles/feature-loop-guard.md`](roles/feature-loop-guard.md) |
| `feature-convergence-reviewer` | `feature` | [`roles/feature-convergence-reviewer.md`](roles/feature-convergence-reviewer.md) |
| `fix-assessor` | `fix` | [`roles/fix-assessor.md`](roles/fix-assessor.md) |
| `fix-maker` | `fix` | [`roles/fix-maker.md`](roles/fix-maker.md) |
| `fix-verifier` | `fix` | [`roles/fix-verifier.md`](roles/fix-verifier.md) |
| `commit-policy-reviewer` | `shared` | [`roles/commit-policy-reviewer.md`](roles/commit-policy-reviewer.md) |

Manifest 必须逐项引用上述文件并把两个 shared support roles 加入两个 Squad；缺少 required Agent、membership、squad role text、private same-owner access readback 时 application 为 `BLOCKED`。`commit-policy-reviewer` 只消费 producer-owned immutable CommitRef，不能成为业务 writer 或修改 Git 历史。
