请使用 `$multica-orchestrator-link-up` 完成一个 Workspace Foundation 的精确计划调和与发布。

## 输入

- Multica profile：`<profile>`
- Workspace：`<workspace>`
- 本机 Runtime provider：`<runtime-provider>`

## 执行步骤

本次 prompt 调用就是此 Stage 的一次 Human 授权。它只授权当前
digest-bound plan 中的 Foundation 操作：创建 Workspace、`bug`/`enhancement`
label、Runtime profile，或在既有 idle-daemon/provider 规则下启动 Runtime daemon。
每个 operation 必须携带同一次 prompt-run 的 authorization ref、exact
`plan_digest` 和 operation id；不得使用该授权执行其他 mutation。

1. 检查 profile 登录状态；已登录则继续，否则按 `$multica-login` 完成认证并重新读取。
2. 运行 `prepare`，读取 account、Workspace、labels、Runtime fleet、daemon 与 capability。
   `ohmypi` 必须规范化为 `omp`。在线的本机 provider Runtime 必须跳过 bootstrap。
3. 运行 `inspect` 和 `plan`。身份、Workspace、label、Runtime、daemon、capability、
   digest 或唯一性不一致时立即停止，报告 blocker；Issue Status 只作为 Human reminder。
4. 当 plan 含 operation 时，严格按一项一次执行 `apply`，取得 fresh readback 后从
   `prepare → inspect → plan` 重来。不得修补旧 readback、不得等待第二次授权。
5. 仅当 operations 和 blockers 均为空时，运行 `verify`，并始终传入 input-bound
   `--state-root ~/.local/state/multica-orchestrator/bundle-store` 与
   `--pointer-state-root ~/.local/state/multica-orchestrator`。验证必须发布 Foundation
   CAS bundle、Workspace pointer 和 `WorkspaceDeploymentIndex.v1`。

## 停止条件

身份、Workspace、label、Runtime、daemon、capability、plan 或 digest 不一致时立即停止，
只报告 blocker；Issue Status 只提醒 Human 确认，不作为 Foundation blocker。

## 安全边界

- 不导入或更新 Workspace Skill，不创建 Agent、Squad、Project、Issue 或 Run。
- 不 dispatch Agent 或 Squad，不修改目标 repository。
- 不接受过期 plan、歧义 live identity、unsupported action 或 out-of-contract mutation。
- 所有身份和状态只以本次 CLI readback 为准。

## 输出

报告 applied operation、fresh postcondition、Foundation bundle/artifact digest、pointer、
deployment-index lineage、最终
`WORKSPACE_FOUNDATION_VERIFIED/BLOCKED_ORCHESTRATOR_LAYER`、完整 fleet、blockers、
Issue Status Human reminder，以及确认未发生的副作用。

> **占位符脚注**
> - `<profile>`：Multica CLI profile 名称；例如 `production`。
> - `<workspace>`：Workspace ID、名称或 slug；例如 `production-workspace`。
> - `<runtime-provider>`：本机应提供的 Agent Runtime provider；例如 `omp`。
> - 替换占位符时去掉尖括号。
