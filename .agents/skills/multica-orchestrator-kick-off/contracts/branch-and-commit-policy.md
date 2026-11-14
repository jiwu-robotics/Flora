# GitFlow Branch 与 Commit 边界合同

## 1. 目标与边界

本合同采用 GitFlow integration flow：`main` 是生产发布线，`develop` 是唯一开发集成线。Multica Runtime 负责本地 `worktree` checkout 与任务分支生命周期；repository provider/Human 负责规范 remote integration branch、push、PR、merge、release tag 和 deployment。业务 Agent/Squad 不执行这些 provider 操作。

每个 Work Item 同时具有两个不可混淆的 branch identity：

- `runtime_branch_ref`：Multica 管理的本地任务分支，实际名称必须来自 run/resource readback，通常形如 `agent/<agent>/<issue>`；
- `integration_branch_ref`：provider 管理的规范 remote GitFlow branch。

不得重命名、删除或 force-move Runtime branch 来伪装成 GitFlow branch。Provider 只可把已验证的 exact source SHA 推送到规范 remote ref。

## 2. Work Item identity

`work_item_ref` 是 Multica Issue UUID，用于 ledger、去重和对象关联。`work_item_id` 是当前 workspace 中可路由的 canonical Issue key，例如 `MUL-42`，用于 Human readback 和 `Work-Item` footer。禁止使用 bare number。

`branch_work_item_token` 是 `work_item_id` 的 branch-safe lowercase normalization。它只用于 provider branch；footer 始终保留 canonical Issue key。三者必须由 current Issue readback 证明解析到同一 Work Item。

## 3. Branch identity 与流向

| Work type | Provider integration branch | Immutable base | PR target | 完成条件 |
| --- | --- | --- | --- | --- |
| Feature | `feature/<owner>/<branch-work-item-token>-<slug>` | `develop` | `develop` | provider merge commit 的 `IntegrationRef` |
| Fix | `fix/<owner>/<branch-work-item-token>-<slug>` | `develop` | `develop` | provider merge commit 的 `IntegrationRef` |
| Release | `release/<version>` | `develop` | `main`，随后 `main` 回合并 `develop` | `PromotionRef=COMPLETE` |
| Hotfix | `hotfix/<owner>/<branch-work-item-token>-<slug>` | `main` | `main`，随后回合并 `develop` 和 active release（如存在） | `PromotionRef=COMPLETE` |

`owner` 和 `slug` 使用 `[a-z0-9]+(?:-[a-z0-9]+)*`。`owner` 来自 current Brief 和 target-project policy，不是 Agent、runtime、committer、临时 assignee、邮箱或 provider UUID。`slug` 由已接受 Brief 派生。owner 转移不改写已有 provider branch。

Runtime task branch 必须由每个 `RunCheckoutRef.v1` 的 Multica run/ownership readback 证明；它按 Agent + Issue 管理，不要求跨 Agent 名称相同。正常 DAG 中同一 Work Item 同时最多一个 writer run；只有 overlapping runs 才可能出现 `agent/<agent>/<issue>-<task>`，且在未登记分叉与 scope/lease 冲突消解前必须 BLOCKED。

Provider push 后必须满足：

```text
WorkItemBranchRef.current_integration_head_revision
  == integration_branch_ref head
  == PullRequestRef.source_head_revision
  == current CommitRef.commit_id
```

任何一项不等都使 integration evidence stale。

## 4. Provisioning、PR 与 promotion

首次 dispatch 前，provider/Human 固定 expected base/target 和 base revision，并创建规范 `integration_branch_ref`。每个后续 dispatch 前，checkout provisioner 必须把 clean local-directory base 精确对齐 current integration head；Multica Runtime 再从该状态创建本轮 worktree/task branch。Runtime 可执行已验证的 managed checkout/worktree lifecycle，但 Agent 不创建、切换、删除或重命名 branch/worktree。

`WorkItemBranchRef.v1` 在 Work Item execution 内稳定记录 integration branch；`RunCheckoutRef.v1` 每个 run 独立记录 Runtime task branch、ownership/baseline、daemon、resource、ephemeral root、cwd、session、observed branch/head 和释放状态。ephemeral root 与 Runtime task branch 跨 run 变化不使 immutable artifact stale；integration head、ownership、baseline 或 source lineage 变化会使其 stale。

每个 producer commit 经独立 policy verdict 后，provider/Human 将规范 `integration_branch_ref` 快进到 exact Runtime source SHA，并持久化 push/readback receipt；下一 run 必须以该 head 为 baseline。业务 Agent 不 push；无法 fast-forward、branch 分叉或 baseline 不一致时 BLOCKED，不自动 merge/cherry-pick。Release/Hotfix branch 仍完全由 provider/Human provision。

GitFlow branch 流向是操作合同，不要求 GitHub ruleset、branch protection、bypass actor 或 CODEOWNERS。每次 integration 前必须核对 current source head、target revision、`ScopeConflictGateRef`、required checks 和 Human approval，使用 provider server-managed merge commit并记录 `IntegrationRef.v2`。

Release/Hotfix primary integration 后必须按合同 back-merge。mechanical conflict resolution 由 Human/provider 完成并重新验证；semantic conflict 返回 owning Producer/Maker 产生新 candidate/commit。

## 5. 并发、scope 与 lease

同一 `repository_ref + work_item_ref` 同时只能有一个 current execution；同一 Work Item 同时只能有一个 active writer run。不同 Work Item 可以在同一 repository 的不同 Runtime worktree 并行，但首次 source write 前必须有 current `WorkScopeRef` 且 `ScopeConflictGateRef.result=CLEAR`。

文件系统隔离不替代语义冲突控制。Constitution、Architecture、Roadmap、同一 ADR、依赖锁、migration 序列、共享 API/schema 和 integration target 使用 repository-global `resource_key` 与原子 `LeaseRecord.v2`。同一 repository/target 同时最多一个 `IntegrationAttemptRef` 处于 `EVALUATING`、`READY` 或 `MERGING`。

## 6. Commit message

每个 ordinary repository commit 必须满足 `conventional-commit`，并以唯一 footer 结束：

```text
<type>(<kebab-case-scope>)[!]: <imperative description>

- <concrete detail>
- <verification detail>

Work-Item: <canonical-Multica-Issue-key-or-URL>
```

footer 必须是最后一个非空行，恰好出现一次。其值必须等于 `WorkItemBranchRef.work_item_id`，或由 provider readback 解析为相同 `work_item_ref` 的 canonical HTTPS URL。URL 不得包含 userinfo、query、fragment 或 credential。

每个 repository-writing Agent 在本 run 完成实际验证后，先固化 exact-scope `ChangesetCandidateRef`，再在当前 `RunCheckoutRef` 中创建 normal commit和 `CommitRef.v2`。必须在 Runtime cleanup 前保持 worktree clean，避免把 Runtime checkpoint commit 当作合格交付。

Agent 不得使用 `--no-verify`、`--amend`、rebase、reset、cherry-pick、push、merge、force-push 或 branch/worktree mutation。`commit-policy-reviewer` 在独立 run 中只读验证 immutable commit range；不得修复 producer commit。

## 7. Required readback

首次 dispatch 前必须 read back：

1. selected Runtime 与 owning daemon 均在线，Runtime 声明 `local-worktree-v1`；
2. Project local-directory resource 精确绑定 daemon/path，且 `execution_mode=worktree`；
3. repository 至少一个 commit、clean、origin 与 expected base revision 可解析；
4. Work Item UUID、canonical Issue key/URL、work type、owner/slug 与 base/target；
5. 每个 run 的不同 root/cwd/session 与 exact branch/head；
6. 同一 Work Item 无 overlapping writer，每个 run 的 Runtime branch ownership/baseline current，且 baseline 等于 dispatch 时 integration head；
7. WorkScope、ScopeConflictGate、repository-global lease 和 integration queue；
8. commit hook、PR range validator、Agent Git permission 与 provider push/PR/merge readback。

缺 capability、mode、branch continuity 或 run checkout isolation 时必须 BLOCKED；绝不回退 `in_place`。