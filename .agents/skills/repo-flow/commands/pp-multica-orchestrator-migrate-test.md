请使用 `$multica-orchestrator-migrate` 将一个 Project release candidate 安装到全部 required Runtime target，并在验证后激活 release。

## 输入

- 协调端 Multica profile：`<profile>`
- Workspace：`<workspace>`
- Repository root：`<repository-root>`
- Project subpath：`<project-subpath>`
- Runtime 目标配置：`<runtime-targets>`

## 执行步骤

1. 从 `WorkspaceDeploymentIndex.v1` 和当前 Project candidate pointer 解析 release candidate，并校验完整 Project → Server → Foundation CAS closure。
2. 以 candidate 声明的 required Runtime aliases 为准，检查本次目标配置没有缺项，也没有 policy 外 alias。
3. 根据每个 alias 的 SSH config host、consumer profile、target state root 和 repository parent，在新的私有 run directory 中自动生成 mode-0600 `RuntimeTargetInventory.v1`。调用者不需要准备 JSON 文件。
4. 对每个 target 重新执行只读 preflight。
5. 按当前 digest-bound plan 的固定顺序执行 receiver、bundle transfer/import、detached checkout、`local_directory(execution_mode=worktree)` binding 和 activation verification。
6. 每个 operation 和最终 activation 都必须分别取得明确的 Human authorization。

## 停止条件

目标机器信息不完整时报告 `RUNTIME_TARGET_CONFIGURATION_REQUIRED`。identity、revision、bundle closure、plan、SSH target、Runtime/daemon 或 Project resource 在执行期间发生变化时立即停止，并重新 capture/plan。不要猜测机器信息，也不要扫描目录选择“最新”文件。

## 安全边界

- 不接受 candidate policy 之外的 Runtime alias。
- 不创建测试 Issue。
- 不 dispatch Agent 或 Squad。
- 未取得对应 authorization 时不执行任何 operation 或 activation。

## 输出

报告生成的 inventory digest、逐 target operations、Runtime activation receipts、aggregate、active release/generation、optional target failures、blockers 和确认未执行的副作用。

> **占位符脚注**
> - `<profile>`：已认证的协调端 Multica CLI profile 名称；例如 `production`。
> - `<workspace>`：Workspace ID、名称或 slug；例如 `production-workspace`。
> - `<repository-root>`：目标 repository root；例如 `.`。
> - `<project-subpath>`：repository 内的 Project 相对路径；例如，根 Project 使用 `.`。
> - `<runtime-targets>`：逐 Runtime alias 给出 SSH config host、consumer profile、绝对 target state root 和绝对 repository parent；例如 `primary-runtime: host=runtime-a, profile=production-runtime, state=/srv/multica/state, repositories=/srv/multica/repositories`。
> - 替换占位符时去掉尖括号。
