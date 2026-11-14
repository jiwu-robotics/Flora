# Inherited Runtime 与 workspace Skills

返回 [配置入口](../guide-to-setup-multica.md)。本阶段不创建或修改 Workspace、
标签、Issue Status、Runtime、Project 或 repository。

## Inherited Runtime fleet

从 current `WorkspaceFoundationRef.v6` 读取完整 Runtime fleet 与
`orchestration_capabilities`，并用 `runtime list --output json` 验证每个 alias
对应同一 UUID、daemon ref 且 `status=online`。Foundation 中 native Squad
routing surface 必须全部为 true；缺 leader-first、exact member routing、
no-start assignment、thread reply、run readback、membership role 或 private
Agent capability 时返回 `FOUNDATION_NATIVE_SQUAD_CAPABILITY_UNVERIFIED`。
Application input 只在顶层声明一个 `collaboration_runtime_alias`；该 alias 必须
存在于 Foundation fleet，并解析为一个 online、具备 native Squad routing 且声明
`local-worktree-v1` 的 Runtime。16 个 role 记录只声明 model 与 thinking 配置，
不得覆盖 Runtime placement。本 Skill 不创建 Runtime Profile，不启动或替换 daemon，
不猜 UUID，也不选择未声明 Runtime。任何 membership/identity/capability 漂移均返回
`FOUNDATION_RUNTIME_NOT_ONLINE`、`RUNTIME_WORKTREE_CAPABILITY_MISSING` 或
`STALE_WORKSPACE_FOUNDATION`；必须由 `multica-orchestrator-link-up` 修复并重新发布 Foundation bundle。

Model、thinking level 和 service tier 都是显式 Human 输入。选定的
`collaboration_runtime_alias` 原子应用于全部 16 个 role；这不授权 Human
直接调用任一 Runtime。

Application schema 与 manifest 把每个 role 的 `max-concurrent-tasks` 固定为
`1`。目标 Project 必须显式绑定 `local_directory(execution_mode=worktree)`；
每个 Agent run 使用 Runtime-managed task branch/worktree。相同 Work Item 的 writer
runs 由 provider 通过 stable integration branch 串行衔接；不同 Work Item 仅在
ScopeConflictGate=CLEAR 且 leases 不冲突时并行。任何 Runtime alias/capability、
RunCheckout ownership/baseline/HEAD 或 integration head 漂移都必须阻止 dispatch。

## Pinned execution Skill profile

目标 Skill 名称来自 manifest 中所有 `required_skills` 与 `optional_skills[*].name`
的并集。Skill 内容来自已授权、固定 revision 的 canonical source，不从任一目标项目
随意复制生成目录。项目的 Spec Kit profile 是否兼容在 nail-down 阶段验证。

Application 前：

1. 在受限目录建立 `skill-integrity-lock.json`；
2. 使用 `cli/build_skill_archives.py` 构建 deterministic `.skill` archives；
3. 对 workspace `skill list/get --with-content` 做完整 readback；
4. 运行 `cli/verify_skill_integrity.py --phase skills`；
5. 只有 `ok: true` 才能绑定 Agent。

同名不等于内容一致。source、archive 和 workspace canonical content digest 必须
一致；archive raw digest 另外固定批准字节。默认 import conflict strategy 为
`fail`，未经独立 diff/授权不得 overwrite。

Agent binding 完成后运行 `--phase full`，证明每个 role 的 Skill ID 集精确等于
manifest。所有 archive、完整 content readback、live IDs 和报告只保存在受限目录。
