# Squad Instructions 索引

> W9 ACCEPTED。Feature 与 Fix Squad 的完整中文 Instructions 位于独立文件。此索引不创建 live Squad、不添加成员、不 dispatch 或发送 notification。

| Squad key | Work type | Leader | Instructions |
| --- | --- | --- | --- |
| `feature` | `feature` | `workflow-leader` | [`feature-squad.md`](feature-squad.md) |
| `fix` | `fix` | `workflow-leader` | [`fix-squad.md`](fix-squad.md) |

## 共享成员

`shared-intake` 与 `commit-policy-reviewer` 必须加入 Feature 和 Fix Squad，使用相同 Agent identity 和受限 role text。它们仍是共享支持角色：前者只做 intake/admission/reclassification，后者只读验证业务 writer 已在自己 run 内创建的 ordinary commit；均不得成为业务 Producer/Reviewer 或 Leader。

## 使用规则

1. 每个 Squad 只使用对应的一个 Instructions 文件。
2. Feature 与 Fix execution members 不得交叉；两个 shared support roles 是唯一例外。所有 repository-writing execution member 使用 `conventional-commit` 提交自己的 exact run scope；`commit-policy-reviewer` 不 commit。
3. 两个 Squad 共享同一个 `workflow-leader`，但 Leader 不是 ordinary member。每个 admitted run 先固化一个 `ExecutionContextRef.v1`、一个 current `ProjectBindingRef.v12`、`ActiveProjectReleaseRef`、`RunAdmissionRef.v1`、work item/execution/work type 和 role key；任一 digest 不一致即 `STALE`。
4. Human Authority、Project/Runtime、workspace administrator 和 CI/provider control 不是 Agent 或 Squad member；裸 actor class 不能替代 typed ref。
5. Instructions 描述期望状态；实际 leader、membership、squad role text、Skill binding、private same-owner access 和 capability revision 必须通过 provider readback 验证。
6. Leader-first：首次 assignment 唤醒 Leader；Leader 用一条 comment 的 exact roster mention 路由成员，并为每个 mention 记录独立 `LeaderDispatchRef.v1`。成员回报自动重触发 Leader；成员不得链式 mention 下一成员。
7. Handoff READY、Human accepted 或 native trigger 只产生 evaluation eligibility。Leader 每次必须重验 Gate、revision、scope、lease、queued/running runs 和 HumanDecisionRef，且每个 dispatch 使用业务 dedupe key。
8. 每个 Human Gate 使用 current participation plan；Leader 可发送独立的 exact designated Human notification 和最多两次 provider-scheduled reminder，但 notification comment 不得同时 mention Agent。
9. 同一 Work Item 的 repository writer runs 必须在同一 collaboration Runtime 上串行，每个 run 使用独立 Runtime task branch/worktree，并由 provider 通过 stable integration branch 衔接。跨 Work Item 可在独立 worktree 并发，但必须 ScopeConflictGate=CLEAR 且 leases 不冲突。
10. Leader ledger/notification 缺原子 readback或 commit-policy report namespace 缺隔离 readback时，对应并发上限为一；同一 repository target 的 integration queue 串行。
