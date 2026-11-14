请使用 `$multica-orchestrator-kick-off` 完成 Workspace 可复用编排层的精确计划调和与发布。

## 输入

- Multica profile：`<profile>`
- Workspace：`<workspace>`
- 协作 Runtime alias：`<runtime-alias>`
- 角色模型档位：`<role-tier>`（`Lite`、`Pro` 或 `Max`；新 generation 默认 `Pro`）

## 执行步骤

1. 通过 `WorkspaceDeploymentIndex.v1`、Foundation pointer 和 CAS closure 验证上游；按 live
   `omp models --json` 将所选档位的 Luna/Terra/Sol 映射为唯一模型 ID。Thinking 值必须使用
   `medium`，不得使用 `median`。
2. 本次 prompt 是此 Stage 的一次 Human 授权：依序运行
   `materialize-profile → build-archives → prepare → inspect → plan`。archive source 固定为已安装
   checkout 与其 `.agents/skills` fallback，不把内部路径作为 Human 输入。
3. 当 plan 含 Skill import/update 时，每次只 apply 一个 digest-bound operation，带 prompt-run
   authorization ref；refresh inspect/plan。Skill detail canonical content 必须先匹配 archive，之后才可
   计划 Agent 或 Squad。
4. Skills 收敛后按同一单项循环调和 16 Agents 和两个 Squads。完成 fresh inspect 后运行
   `materialize-integrity-lock`（含 manifest、Skill 与全部 16 Agent list/detail readbacks），再仅通过
   central `verify-integrity --phase full` 验证。
5. operations/blockers 为空且 Server/integrity reports 成功时，运行 `verify` 与 `emit`，使用 package
   `9.0.0`、Server contract v10、`--state-root ~/.local/state/multica-orchestrator/bundle-store` 和
   `--pointer-state-root ~/.local/state/multica-orchestrator`，发布 parent-linked Server bundle、pointer、
   deployment-index entry。

## 停止条件

身份、Foundation closure、模型、Skill/Agent/Squad identity、archive、snapshot、plan 或 capability
不唯一或漂移时，在 mutation 前停止；不选择替代资源，不绕过 integrity。

## 安全边界

- 只可修改 manifest-pinned Workspace Skills、16 Agents 与 `feature`/`fix` Squads。
- 不创建 Project、Issue、Run，不修改目标 repository，不 dispatch Agent 或 Squad。
- 不执行不在当前 plan 中的 mutation；每个 apply 后必须 fresh readback/replan。

## 输出

报告每个 applied operation、最终 Server/artifact digest、Foundation parent、pointer、
deployment-index lineage、`integrity.ok`、最终
`ORCHESTRATOR_LAYER_VERIFIED/BLOCKED_PROJECT_BINDING` 与确认未执行的副作用。

> **占位符脚注**
> - `<profile>`：已认证的 Multica CLI profile 名称；例如 `production`。
> - `<workspace>`：Workspace ID、名称或 slug；例如 `production-workspace`。
> - `<runtime-alias>`：Foundation fleet 中在线的协作 Runtime alias；例如 `primary-runtime`。
> - `<role-tier>`：角色模型档位；例如 `Pro`。
> - 替换占位符时去掉尖括号。
