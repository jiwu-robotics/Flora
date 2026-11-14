请使用 `$multica-orchestrator-nail-down` 完成一个 Project binding 的精确计划调和与发布。

## 输入

- Multica profile：`<profile>`
- Workspace：`<workspace>`
- Repository root：`<repository-root>`
- Project subpath：`<project-subpath>`
- Required Runtime alias：`<runtime-alias>`

## 执行步骤

1. 先通过 deployment index、Server pointer 和 Foundation → Server CAS closure 验证上游；closure
   无效必须在 Git repository discovery 前停止。
2. 运行 `prepare`。它从 `ProjectBindingInput.v12` 和 Server handoff 生成 request/input、确定性 policy digests、primary Runtime local-directory observation 与四个 mode-0600、无 placeholder 的 portable config 文件；这些文件路径只来自 stdout/resolution。
3. 使用生成的四个文件运行 `plan`。本次 prompt 是一次 bounded Human authorization，只允许 `repo-add`、`project-create`、`project-resource-add`、`bind-primary-local-directory` 与四个 `write-portable-config` operation。
4. 按计划逐项运行 `apply-operation`；每次 operation 在相同 input/snapshot 重新读取并拒绝 stale live state。
5. 使用 repository-installed binding manifest 与 input-bound pointer state root、primary authorization 和 primary receipt/aggregate/release paths 运行 `verify`，发布 `ProjectBindingRef.v12`、Project bundle、`ProjectReleaseCandidate.v8`、primary `ActiveProjectRelease.v2`、Project pointer 和 deployment-index entry；最终必须为 `PROJECT_BOUND/ACTIVE`。

## 停止条件

identity、lineage、capability、policy、template、plan 或 live Project/repository identity 不唯一或漂移时，
mutation 前停止；不选择替代资源，不发明 command、approval 或 repository context。

## 安全边界

- 不执行 Migrate、`local_directory`、Issue/Run、dispatch、checkout、branch、worktree、PR 或 ACTIVE release mutation。
- 只可写计划中的 Project association 与四个 portable repository config 文件。
- 不修改 Foundation/Server、Agent、Squad、Skill 或 Runtime。

## 输出

报告 applied operations、Project/artifact/candidate digests、Server parent、pointers、deployment-index lineage、
最终状态、blockers，以及确认未执行的 Migrate/Dispatch/Issue/Run side effects。

> **占位符脚注**
> - `<profile>`：已认证的 Multica CLI profile 名称；例如 `production`。
> - `<workspace>`：Workspace ID、名称或 slug；例如 `production-workspace`。
> - `<repository-root>`：目标 repository root；例如 `.`。
> - `<project-subpath>`：repository 内的 Project 相对路径；例如 `.`。
> - `<runtime-alias>`：Server/Foundation fleet 中已验证的 Runtime alias；例如 `primary-runtime`。
> - 替换占位符时去掉尖括号。
