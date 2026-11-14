请使用 `$multica-orchestrator-dispatch` 对一个已经 `ACTIVE` 的 Project release 执行一次只读 dispatch readiness 检查。

## 输入

- Multica profile：`<profile>`
- Workspace：`<workspace>`
- Project key：`<project-key>`
- canonical Multica Work Item：`<issue-uuid-or-key>`
- work type：`<feature|fix>`
- Runtime alias：`<runtime-alias>`

## 执行步骤

1. 从 current pointer、Foundation → Server → Project bundle closure、Runtime activation receipts 和 `ActiveProjectRelease.v2` 解析 immutable lineage。
2. 从 Multica CLI readback 解析 canonical Issue UUID/key、Runtime capability、exact Squad ref 和 workflow-leader ref。
3. 验证 Project binding、ACTIVE release、Dispatch contract、Runtime、Issue、work type、Squad 与 leader 一致。
4. 生成只读 readiness 报告，列出将用于 `RunAdmissionRef.v1` 的字段和 digests。

## 停止条件

任何 pointer、digest、identity、capability、Issue、work type、Squad/leader、receipt 或 ACTIVE state 缺失、歧义、冲突、stale 时立即停止。不要扫描目录猜测“最新”artifact，也不要把旧 admission 当作 current。

## 安全边界

- 不执行 `admit-or-resume`，不初始化或迁移 control store。
- 不 assign/mention/dispatch Agent 或 Squad，不创建 Issue/Run，不改变 Issue 状态。
- 不修改 Foundation、Server、Project bundle、candidate/pointer、Runtime `local_directory` 或 repository。
- 不运行 CI/provider mutation，不创建 branch/worktree/lease/queue/Human decision。

## 输出

报告 `dispatch_state=READY|BLOCKED`、Project binding/ACTIVE release/Dispatch contract digest、Issue UUID/key、work type、Runtime capability revision、Squad/Leader refs、blockers，以及所有未执行副作用。

> **占位符脚注**
> - `<profile>`：已认证的 Multica CLI profile 名称；例如 `production`。
> - `<workspace>`：Workspace ID、名称或 slug；例如 `production-workspace`。
> - `<project-key>`：current Project pointer 中的 `sha256:` Project key；例如 `sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef`。
> - `<issue-uuid-or-key>`：canonical Multica Issue UUID 或 routable key；例如 `MUL-42`。
> - `<feature|fix>`：选择 `feature` 或 `fix`；例如 `feature`。
> - `<runtime-alias>`：ACTIVE release receipts 覆盖的 Runtime alias；例如 `primary-runtime`。
> - 替换占位符时去掉尖括号。
