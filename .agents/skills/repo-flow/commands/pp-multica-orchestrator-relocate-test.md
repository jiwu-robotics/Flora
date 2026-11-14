请使用 `$multica-orchestrator-relocate` 在 Multica 服务主机迁移完成后，重签发编排状态并原子切换 deployment。

## 输入

- 私有 operator state root：`<state-root>`
- 目标 Multica profile：`<target-profile>`
- 已完成的 `$multica-migrate-server` capture ID：`<migration-capture-id>`
- Runtime 目标配置：`<runtime-targets>`

## 执行步骤

1. 只读取 `.prompt-and-report/<migration-capture-id>.report.md`，解析该次迁移实际签发的唯一 receipt path 和 digest。
2. 重新验证 receipt bytes、target authority、source stopped、Runtime readiness，以及 receipt 与 source `WorkspaceDeploymentIndex.v1` 的 identity。
3. 根据 active Projects 声明的 required Runtime aliases 检查目标配置，并在新的私有 run directory 中自动生成 mode-0600 `RuntimeTargetInventory.v1`。调用者不需要准备 receipt 或 inventory JSON 文件。
4. 使用 exact receipt、target readback、旧 graph/pointers、mutation barrier 和 active Project inventory 执行 prepare、readback、capture 和 plan。
5. 只有在相应步骤分别取得明确 Human authorization 后，才执行 fence、Foundation → Server → Project reissue、release reactivation 和 index commit/verify。

## 停止条件

- 找不到指定 capture 或 receipt：`SERVER_MIGRATION_RECEIPT_REQUIRED`。
- 同一 capture 出现多个 receipt path/digest，或 identity 不匹配：`SERVER_MIGRATION_RECEIPT_AMBIGUOUS`。
- Runtime 机器信息不完整：`RUNTIME_TARGET_CONFIGURATION_REQUIRED`。
- identity、inventory、revision、Runtime、mutation barrier、fence 或 target authority 发生变化：立即停止并重新生成 readback/plan。

不要按文件名或修改时间寻找“最新”receipt/inventory，也不要猜测机器信息。

## 安全边界

- Relocate 不依赖 Migrate Skill。
- 保留所有旧 bundle、pointer、release 和 receipt。
- 不创建替代资源，不重启 retired source，不迁移 service data。
- 不 dispatch Agent 或 Squad。

## 输出

报告 relocation lifecycle state、migration capture/receipt digest、生成的 inventory digest、deployment identity/index、old/new graph 和 release lineage、Runtime receipts、blockers、fence、最终 live readback，以及确认未执行的副作用。

> **占位符脚注**
> - `<state-root>`：私有 operator state root 的绝对路径；例如 `/home/operator/.local/state/multica-orchestrator`。
> - `<target-profile>`：已认证的目标 Multica CLI profile 名称；例如 `production-target`。
> - `<migration-capture-id>`：完成服务迁移并签发 receipt 的 exact `multica-migrate-server` prompt/report capture ID；例如 `20260914T120000Z-multica-migrate-server-abcd1234`。
> - `<runtime-targets>`：逐 required Runtime alias 给出 SSH config host、consumer profile、绝对 target state root 和绝对 repository parent；例如 `primary-runtime: host=runtime-a, profile=production-runtime, state=/srv/multica/state, repositories=/srv/multica/repositories`。
> - 替换占位符时去掉尖括号。
