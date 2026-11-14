请使用 `$multica-orchestrator-dispatch` 对一个已经 `ACTIVE` 的 Project release 执行一次只读 dispatch readiness 检查。

## 输入

- Multica profile：`<profile>`
- Workspace：`<workspace>`
- canonical Multica Work Item：`<issue-uuid-or-key>`

## 执行步骤

1. 执行 `python3 cli/run.py inspect --profile <profile> --workspace <workspace> --issue <issue-uuid-or-key>`。
2. 从 Runtime-local registry、fenced ACTIVE pointer、Foundation → Server → Project closure 和 live Multica CLI readback 解析 canonical Issue UUID/key、Project、Runtime、exact Squad ref、workflow-leader ref 与唯一 running Leader run。
3. 验证 Project binding、ACTIVE release、Dispatch contract、Runtime、Issue/Squad assignment 与 leader run 一致；不接受手填 internal ID/digest。
4. 生成只读 readiness JSON，列出 resolved identities/digests、`admission_action=CREATE|REUSE` 和 blockers。

## 停止条件

任何 pointer、digest、identity、capability、Issue、work type、Squad/leader、receipt 或 ACTIVE state 缺失、歧义、冲突、stale 时立即停止。不要扫描目录猜测“最新”artifact，也不要把旧 admission 当作 current。

## 安全边界

- 不执行 `admit-or-resume`，不初始化或迁移 control store。
- 不 assign/mention/dispatch Agent 或 Squad，不创建 Issue/Run，不改变 Issue 状态。
- 不修改 Foundation、Server、Project bundle、candidate/pointer、Runtime `local_directory` 或 repository。
- 不运行 CI/provider mutation，不创建 branch/worktree/lease/queue/Human decision。

## 输出

报告 `dispatch_state=READY|BLOCKED`、`admission_action`、Project binding/ACTIVE release/Dispatch contract digest、Issue UUID/key、work type、Runtime、Squad/Leader refs、blockers，以及所有未执行副作用。

> **占位符脚注**
> - `<profile>`：已认证的 Multica CLI profile 名称；例如 `production`。
> - `<workspace>`：Workspace ID、名称或 slug；例如 `production-workspace`。
> - 替换占位符时去掉尖括号。
