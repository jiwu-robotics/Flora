# Multica 配置：Agents 与 Squads

返回 [配置入口](../guide-to-setup-multica.md)。先完成 [Runtime 与 Skills](runtime-and-skills.md)；所有 Skills 必须先通过 integrity verifier 的 `--phase skills`。

`MULTICA_ORCHESTRATOR_SKILL_ROOT` 必须从当前 coding agent 的 active Skill catalog 解析到本 package 根，不能猜全局安装路径。

## 1. 创建或更新 16 个 Agents

### 1.1 创建顺序

推荐顺序：

1. `shared-intake`
2. `workflow-leader`
3. `commit-policy-reviewer`
4. 十个 Feature execution Agents
5. 三个 Fix execution Agents

完整 role key 与 Instructions 路径见 [`../agents/agent-instructions.md`](../agents/agent-instructions.md)。每个 Agent 只使用 `manifest.agents[*].instructions` 指向的一个独立文件。

每个 Agent identity 可服务多个 Work Item，但每个 run 只固化一个 `ExecutionContextRef.v1`、一个 `WorkItemExecutionRef.v4`、一个 `WorkItemBranchRef.v1`、一个 `RunCheckoutRef.v1`、一个 `CheckoutRef.v5`、一个 exact `role_key` 和一个 manifest-allowed `operation_key`；不为并发复制角色。Server application input 顶层唯一的 `collaboration_runtime_alias` 原子应用于全部 16 个 Agent，role 配置不得覆盖 Runtime。Multica 原生 Squad 首次 assignment 唤醒 Leader；execution member 只接受 current Leader 的 exact roster mention 和唯一 `LeaderDispatchRef.v1`。创建前验证 manifest 与 input 都把每个 role 的 `max-concurrent-tasks` 固定为 `1`；同一 Work Item writer runs 串行，每个 run 使用独立 Runtime task branch/worktree，并由 provider 通过 stable integration branch 衔接。

### 1.2 幂等判断

对每个 role：

1. 从 `agent list --include-archived --output json` 按 exact name 查找；
2. 不存在：执行 create；
3. 恰好一个 active 对象：执行 get 并生成差异，再决定 update；
4. archived 同名：由 Human 决定 restore、保留或新命名；
5. 多个同名：BLOCKED，不猜对象。

不要自动 archive/delete 现有 Agent。

### 1.3 创建 Agent

当前 CLI 的 `agent create/update` 接受 `--instructions`，没有 `--instructions-file`。使用已确认的本地文件读入 shell variable，始终双引号展开；Instructions 不是 secret，但仍不得把内容拼进 shell history。

`THINKING_LEVEL=null` 只代表 Human 明确选择 selected runtime default。把 optional runtime parameter 转为 CLI arguments 时，`null` 必须省略 flag；任何其他值必须原样传递，不能因为 server rejection 而自行清空：

```bash
ROLE_KEY='shared-intake'
ROLE_DESCRIPTION='replace-with-manifest-agent-description'
ROLE_MAX_CONCURRENT_TASKS='1'
INSTRUCTIONS_FILE="$MULTICA_ORCHESTRATOR_SKILL_ROOT/agents/roles/${ROLE_KEY}.md"
INSTRUCTIONS="$(cat "$INSTRUCTIONS_FILE")"
THINKING_LEVEL='null'
THINKING_ARGS=()
if [[ "$THINKING_LEVEL" != null ]]; then
  THINKING_ARGS=(--thinking-level "$THINKING_LEVEL")
fi

"${M[@]}" agent create \
  --name "$ROLE_KEY" \
  --description "$ROLE_DESCRIPTION" \
  --instructions "$INSTRUCTIONS" \
  --runtime-id "$RUNTIME_ID" \
  --model "$MODEL_ID" \
  "${THINKING_ARGS[@]}" \
  --max-concurrent-tasks "$ROLE_MAX_CONCURRENT_TASKS" \
  --permission-mode private \
  --output json

unset INSTRUCTIONS
unset THINKING_ARGS
```

`private` 是保守初始值。若业务需要其他 workspace member 调用，Human 必须明确 allow-list；优先 `--permission-mode public_to --public-to-member <member-id>`，不要默认开放到整个 workspace。

如果 Instructions 因 shell/argv 限制无法完整提交，使用 Multica Web 或受支持的无 shell argv wrapper；不得截断文件。

### 1.4 更新已有 Agent

先读取并展示实际差异，再执行：

```bash
AGENT_ID='replace-with-agent-id'
ROLE_KEY='replace-with-role-key'
ROLE_DESCRIPTION='replace-with-manifest-agent-description'
ROLE_MAX_CONCURRENT_TASKS='1'
INSTRUCTIONS="$(cat "$MULTICA_ORCHESTRATOR_SKILL_ROOT/agents/roles/${ROLE_KEY}.md")"
THINKING_LEVEL='null' # use the Human-approved value from the operator-local record
THINKING_ARGS=()
if [[ "$THINKING_LEVEL" != null ]]; then
  THINKING_ARGS=(--thinking-level "$THINKING_LEVEL")
fi

"${M[@]}" agent update "$AGENT_ID" \
  --description "$ROLE_DESCRIPTION" \
  --instructions "$INSTRUCTIONS" \
  --runtime-id "$RUNTIME_ID" \
  --model "$MODEL_ID" \
  "${THINKING_ARGS[@]}" \
  --max-concurrent-tasks "$ROLE_MAX_CONCURRENT_TASKS" \
  --permission-mode private \
  --output json

unset INSTRUCTIONS
unset THINKING_ARGS
```

不要顺手改变 name、visibility、runtime、model、thinking level 或 concurrency；每个字段必须来自本次批准的安装记录。`null` 的 effective default 也必须在 update readback 中确认。全部 Agent 的 `runtime-id` 必须解析为 Server handoff 中同一个 `collaboration_runtime_alias`；任一角色漂移到其他 Runtime 时 application 为 BLOCKED。

`max-concurrent-tasks=1` 是此单目录协作模式的保守固定值。并发只允许发生在一个 Agent run 内部不触碰共享目录的独立计算，或未来由另一套合同为不同 repository/root 提供独立 Runtime；不得仅提高该字段就在同一 collaboration root 并发 Agent runs。

### 1.5 设置精确 Skill 集

对一个 Agent，目标 Skill 集是 manifest 中：

```text
required_skills ∪ optional_skills[*].name
```

Optional 表示有条件调用，不表示可以绑定给其他角色。用 name→ID 映射生成逗号分隔 ID，并使用 `set` 做精确替换：

```bash
AGENT_ID='replace-with-agent-id'
SKILL_IDS='replace-with-comma-separated-skill-ids'

"${M[@]}" agent skills set "$AGENT_ID" \
  --skill-ids "$SKILL_IDS" \
  --output json
```

不要使用 `add` 作为最终收敛方式；它会保留历史多余 Skill。执行 `set` 前必须确认所有目标 IDs，否则会用不完整集合覆盖现有 assignment。

立即 readback：

```bash
ROLE_KEY='replace-with-role-key'
"${M[@]}" agent get "$AGENT_ID" --output json \
  > "$LOCK_DIR/readback/agents/$ROLE_KEY.json"
"${M[@]}" agent skills list "$AGENT_ID" --output json \
  > "$LOCK_DIR/readback/agents/$ROLE_KEY.skills.json"
```

必须证明：

- role name、manifest description、Instructions、runtime、model 和 invocation permission 正确；
- Skill 集与 manifest 精确相等；
- Feature/Fix execution Skill 零交叉；
- 只有 `shared-intake` 和 `workflow-leader` 绑定 `multica-cli`；
- 只有 `shared-intake` 绑定 `multica-triage`；
- 所有 repository-writing execution Agents 和 `commit-policy-reviewer` 绑定 `conventional-commit`；后者只有只读 validator 权限；
- `workflow-leader` 的 Multica access 精确为 native Squad coordination、recording 和 designated-Human notification；Squad/`@all` mention、Issue assignment、直接 rerun/cancel 均未授权；
- excluded Skills 为零；
- 每个 role 的 effective concurrency 与 manifest policy 一致；`workflow-leader`/`commit-policy-reviewer` fallback=1；
- 每个 run 可被约束到唯一 ExecutionContext/execution/checkout/root、manifest-allowed operation 与单一 HandoffRef.v3；member result 只重触发 Leader 重新评估，不自动启动下一角色。

全部 16 个 role 完成 readback 后，运行 full phase：

```bash
python3 "$MULTICA_ORCHESTRATOR_SKILL_ROOT/cli/verify_skill_integrity.py" \
  --phase full \
  --manifest "$MULTICA_ORCHESTRATOR_SKILL_ROOT/manifests/orchestration-package.yaml" \
  --lock "$LOCK_DIR/skill-integrity-lock.json" \
  --source-root 'replace-with-clean-skill-source-git-root' \
  --skill-readback-dir "$LOCK_DIR/readback/skills" \
  --skill-list-readback "$LOCK_DIR/readback/skill-list.json" \
  --agent-readback-dir "$LOCK_DIR/readback/agents"
```

只有 full phase `ok: true` 才构成 applied Agent/Skill binding readback；Project/provider 控制仍由 `multica-orchestrator-nail-down` 验证。

### 1.6 Secret 和 Multica access

只有 `shared-intake` 与 `workflow-leader` 可以获得运行时 Multica credential。Leader 的 credential 只允许 recording/readback 和 current participation plan 指向的 exact Human member notification；其余 14 个 Agent 必须是 `credentials: none`、`multica_access: none`。

不要通过 `--custom-env` 在命令行传 secret；它会出现在 shell history 和 `ps`。确需设置时，在受限 operator 工作目录创建 mode `0600` 的 JSON 文件，并使用：

```bash
"${M[@]}" agent env set "$AGENT_ID" \
  --custom-env-file './restricted-agent-env.json' \
  --output json
```

写后立即安全删除临时文件。不要在共享终端执行可能显示 secret value 的 `agent env get`。如果平台不能证明 `shared-intake`/`workflow-leader` 的有效 access scope，记录 `APPLIED_PERMISSION_READBACK_UNAVAILABLE` 并停止。

Repository write scope、git control 和 destructive deny 不是 `permission-mode`。`permission-mode` 只控制谁能调用 Agent；实际文件/命令权限必须由 runtime sandbox、repository provider 和 CI 按 W6 强制。

## 2. 创建或更新 Squads

### 2.1 固定结构

Feature Squad：

- Leader：`workflow-leader`
- Members：十个 `feature-*` execution Agents，加共享支持成员 `shared-intake` 与 `commit-policy-reviewer`
- Description 和 Instructions：必须分别等于 manifest 与 [`../squads/feature-squad.md`](../squads/feature-squad.md)

Fix Squad：

- Leader：`workflow-leader`
- Members：`fix-assessor`、`fix-maker`、`fix-verifier`，加共享支持成员 `shared-intake` 与 `commit-policy-reviewer`
- Description 和 Instructions：必须分别等于 manifest 与 [`../squads/fix-squad.md`](../squads/fix-squad.md)

Human Authority、管理员和 provider control 不是 Squad member。两个 shared support role 是成员，但不承担 Feature/Fix producer、maker 或 reviewer 身份。

Squad 是稳定角色集合和原生路由边界，不是共享工作区或自动业务调用链。首次 assignment 只唤醒 Leader；Leader comment 的 exact member mention 触发成员，成员在自己 Runtime-managed run worktree 中完成业务写入和 scoped commit，回复 parent trigger comment 后重触发 Leader；Leader 再路由 `commit-policy-reviewer`，VERIFIED 后由 provider fast-forward stable integration branch，才进入下一业务节点。跨 Work Item 并发由不同 `WorkItemExecutionRef.v4`、`RunCheckoutRef.v1`、ScopeConflictGate 和 resource leases 控制；同一 Work Item writers 串行。

### 2.2 创建 Squad

```bash
LEADER_AGENT_ID='replace-with-workflow-leader-id'
SQUAD_DESCRIPTION='replace-with-manifest-squad-description'

"${M[@]}" squad create \
  --name feature \
  --description "$SQUAD_DESCRIPTION" \
  --leader "$LEADER_AGENT_ID" \
  --output json
```

`squad create` 当前没有 Instructions flag。创建后使用 returned squad ID 更新完整 Instructions：

```bash
SQUAD_ID='replace-with-created-squad-id'
SQUAD_INSTRUCTIONS="$(cat "$MULTICA_ORCHESTRATOR_SKILL_ROOT/squads/feature-squad.md")"

"${M[@]}" squad update "$SQUAD_ID" \
  --description "$SQUAD_DESCRIPTION" \
  --instructions "$SQUAD_INSTRUCTIONS" \
  --leader "$LEADER_AGENT_ID" \
  --output json

unset SQUAD_INSTRUCTIONS
```

Fix Squad 使用相同步骤，name 为 `fix`，Instructions 文件为 `$MULTICA_ORCHESTRATOR_SKILL_ROOT/squads/fix-squad.md`。

已有同名 Squad 时先 `squad get` 和 `squad member list`；不得创建重复对象。

### 2.3 设置 members

逐个添加 manifest 中的全部 ordinary members，并把 `--role` 设为该 member 的 exact `squad_role`：

```bash
"${M[@]}" squad member add "$SQUAD_ID" \
  --member-id "$AGENT_ID" \
  --type agent \
  --role "$EXACT_SQUAD_ROLE" \
  --output json
```

添加前后都读取 member list，避免重复。不要把 Leader 当作普通 execution member重复添加，除非 provider readback 明确要求且 manifest 已同步修改。

Loop bundle 必须 all-or-none：

- `feature-loop-maker`
- `feature-loop-checker`
- `feature-loop-guard`

当前 accepted manifest 启用了 Loop，三者必须全部存在、全部加入 Feature Squad，并满足独立 checker session、共享状态、预算、Human guard 和 `isolation: none`。无法满足时不能只删一个 member；必须停止 application 并回到 W1–W7 修改设计。

### 2.4 Squad readback

```bash
"${M[@]}" squad get "$FEATURE_SQUAD_ID" --output json
"${M[@]}" squad member list "$FEATURE_SQUAD_ID" --output json
"${M[@]}" squad get "$FIX_SQUAD_ID" --output json
"${M[@]}" squad member list "$FIX_SQUAD_ID" --output json
```

检查：

- 两个 Squad 的 Leader 都是同一个 `workflow-leader`；
- Feature 恰好十二个 ordinary members：十个 Feature execution roles 与两个 shared support roles；
- Fix 恰好五个 ordinary members：三个 Fix execution roles 与两个 shared support roles；
- Feature/Fix execution Agent 无交叉，shared support membership 精确一致；
- 每个 Agent/Squad description 与 manifest 精确一致；
- Instructions 与文件全文一致；
- 每个 ordinary member 的 role text 与 manifest `squad_role` 精确一致；
- Loop 三角色 all-or-none；
- Feature/Fix Instructions 明确原生 Leader-first、exact member mention、member reply 重触发 Leader、execution/checkout/root isolation、scope conflict gate 和同一 target integration serialization；
- Leader effective concurrency 在原子 ledger/notification control 未验证时为一；
- 每个 role 的 `role_key`/`operation_key` 与 manifest invocation policy 精确一致，每条 Handoff 只有一个 consumer，任何 member chaining 均不能绕过 dispatch、Gate、Human decision 与 dedupe。
