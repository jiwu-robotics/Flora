# Project 与 repository 绑定

Nail Down 通过 ProfileSession 与 `WorkspaceDeploymentIndex.v1` 消费 parent-linked `ServerOrchestrationRef.v10`，只创建或复用一个 repository registry、一个 Multica Project 和一个 Project GitHub resource。

## 只读盘点

使用 explicit profile/workspace 读取：

```bash
multica --profile <profile> --workspace-id <workspace-id> repo list --output json
multica --profile <profile> --workspace-id <workspace-id> project list --output json
multica --profile <profile> --workspace-id <workspace-id> project get <project-id> --output json
multica --profile <profile> --workspace-id <workspace-id> project resource list <project-id> --output json
multica --profile <profile> --workspace-id <workspace-id> runtime list --output json
```

按 provider identity 和规范化 URL 分类为 reusable、missing 或 conflict。禁止把同名但不同 repository 的 Project 当成可复用对象。

Runtime readback 在此只验证 `RuntimeTargetPolicy.v4.required_capability_revision` 与 Server fleet/current live Runtime 一致；不解析或绑定 target-local path/resource。

## 经授权写入

Reviewed plan 只允许：

```bash
multica --profile <profile> --workspace-id <workspace-id> repo add <repository-url> --output json
multica --profile <profile> --workspace-id <workspace-id> project create --title <title> --repo <repository-url> --output json
multica --profile <profile> --workspace-id <workspace-id> project resource add <project-id> --type github_repo --url <repository-url> --output json
```

以及四个 portable `.multica/agents/` 文件。写后读取 Project、GitHub resource 和 repository registry；网络中断后先读实际状态再决定是否重试。

`local_directory` add/update、absolute checkout root、daemon binding 与 `execution_mode=worktree` 完全属于 `multica-orchestrator-migrate`。Nail Down plan/apply 不得包含这些 operation。
