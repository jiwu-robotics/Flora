# Server/workspace 预检

本阶段只验证 `multica-orchestrator-link-up` 产生的 current portable
Foundation bundle、`WorkspaceFoundationRef.v6`、完整 Runtime fleet 与 native
Squad orchestration capability readback，并读取 workspace Agent layer。不得创建
Workspace、标签或 Runtime，不得启动 daemon，不读取或修改目标项目。
## Operator-local state

创建 mode-0700、不会提交的目录，记录：

```text
Foundation manifest digest and CAS state root
server kind/ref
profile
workspace ID
authenticated account identity
Runtime alias -> Runtime/daemon/capability revision
role -> Runtime alias/model/thinking/concurrency
Skill source/archive/workspace digests
role -> Agent ID
Squad -> Squad ID
before/after readbacks and authorization refs
```

禁止记录 secret value、repository URL、Project ID、repository absolute path、Work
Item、checkout root 或项目 participation plan。后者由
`multica-orchestrator-nail-down` 管理。

从 [`../controls/server-application-input.template.json`](../controls/server-application-input.template.json)
复制 application input 到受限目录后填写，不得修改 tracked template。

## 只读检查

先验证 Foundation 文件摘要、schema、`WORKSPACE_FOUNDATION_VERIFIED` 状态、
status contract、online Runtime 与全部 native Squad routing capability surfaces。
然后使用 handoff 中的 explicit profile/workspace 读取：

```bash
multica --profile <profile> --workspace-id <workspace-id> workspace get <workspace-id> --output json
multica --profile <profile> --workspace-id <workspace-id> runtime list --output json
multica --profile <profile> --workspace-id <workspace-id> skill list --output json
multica --profile <profile> --workspace-id <workspace-id> agent list --include-archived --output json
multica --profile <profile> --workspace-id <workspace-id> squad list --output json
```

Self-hosted server 的每个 `multica` process 清除六个 proxy environment variable；
Multica Cloud 保留 inherited proxy。两者都不得修改 `NO_PROXY`。

同名 Agent/Skill/Squad 按 exact name 分类为 reusable、missing 或 conflict。多个
同名、archived 冲突或不可回读对象保持 BLOCKED；不得创建后缀副本、覆盖或自动
archive/delete。Foundation 不一致时返回 `STALE_WORKSPACE_FOUNDATION`，不得在本
Skill 修补。
