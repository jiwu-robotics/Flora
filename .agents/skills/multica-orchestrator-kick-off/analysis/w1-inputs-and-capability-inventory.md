```yaml
coach_stage: W1
decision: ACCEPTED
source_project: capability-sample-robox-nexus
source_revision: git:d24411c8840bab361745c1ed7b41cf4b3a43b3e3+mapping:sha256:8ab657d28bbb9ac295dd7c3c12d6cf9e54b150a2b6f2b29d6af4b7ccdbe3b6b8
requirements_revision: sha256:3b6caab15839cd7489bf30c23f9598a45fa309a3ade7a6227597ab83cb237d94
input_artifacts:
  - requirements/orchestration-requirements.md#sha256:3b6caab15839cd7489bf30c23f9598a45fa309a3ade7a6227597ab83cb237d94
  - requirements/generate-squads.prompt.md#sha256:32b53efd4fe809ceaf1784dc667dd626897a2a511a486d9c861502b43cb74762
  - requirements/tutorial-for-multica.md#sha256:74e2fe177d87a69944e0f74f4157dbc13fdc7fe268cf12365fe8e2d06a891d06
  - capability-sample:.agents/skills#git:d24411c8840bab361745c1ed7b41cf4b3a43b3e3
  - capability-sample:.multica/agents/triage-mapping.md#sha256:8ab657d28bbb9ac295dd7c3c12d6cf9e54b150a2b6f2b29d6af4b7ccdbe3b6b8
decisions:
  default_worktree: false
  loop_eligible: true
  loop_isolation: none
  artifact_index_accepted: true
  status_authority: requirements-and-maintained-triage-contract
open_blockers: []
supersedes: analysis/w1-inputs-and-capability-inventory.md#sha256:01bce2874628fedbc4126af26abf3bf50827ecf3d4d380ad8302a8f50a8f1800
```

# W1 输入、需求、来源与能力盘点

## 1. 本步骤结论

- 已固化需求 SSOT：[`../requirements/orchestration-requirements.md`](../requirements/orchestration-requirements.md)。
- 已盘点能力样本的 37 个 Skill 包，以及会改变实际可执行性的 preset、extension、script、template、schema、hook 和 runtime config。
- Human 已选择单一 collaboration Runtime + repository `local_directory(execution_mode=worktree)`；每个 Agent run 使用 Runtime-managed task branch/worktree，同一 Work Item writer 通过 stable integration branch 串行，不同 Work Item 经 scope/lease 门禁并行。`speckit-worktrees-*` 不进入 Agent/Squad 候选。
- Loop 合同同时具备外部状态、迭代预算、独立 checker、Human guard，并显式支持 `isolation:none`，因此 W1 判断 `loop_eligible:true`；Loop 复用当前 Runtime outer worktree，不创建 nested worktree。
- Human 已指定需求 SSOT 与维护中的 `multica-triage` 为 portable status 权威；样本 mapping 已改为相同 key/category，并把旧 workspace 状态显式标为 legacy/conflict。文档级 `STATUS_CONTRACT_DRIFT` 已解除；任何 live application 前仍须由 Human 在 Multica Web 核对五个 key/category 并明确同意，无需保存 readback evidence。

## 2. 需求来源与边界

| 来源 | 用途 | 是否进入生成产物 | 处理决定 |
| --- | --- | --- | --- |
| 编队 prompt | W1–W8 方法、治理不变量、状态合同、工作流约束 | 仅保留需求语义和内容摘要 | 接受 |
| Multica 人机协作教程 | Feature/Fix 分流、Human gate、Core/Loop、状态语义 | 仅保留可移植流程语义 | 接受 |
| 能力样本 `.agents/skills` | 证明可复用 Skill 的真实输入、输出、副作用和失败方式 | 只保留相对 Skill 名称与合同 | 接受为 capability evidence |
| 能力样本 `.specify` | 解析 Skill 的隐藏模板、脚本、extension、hook、schema 与配置依赖 | 只保留通用版本/路径合同与风险 | 接受为 runtime evidence |
| 样本 `.multica` runtime state | 仅用于检查已验证 mapping 是否漂移 | 不复制 workspace 名、UUID、账号、server 或 snapshot | 排除为 reusable input；漂移仍须显式解决 |
| 现有生成输出 | Human 将旧输出根改名为 repository-local `orchestrator/` | 全部受管产物已原样迁移；相对链接保持不变 | W1 路径合同待重新接受 |

### 不进入后续候选的能力

`multica-orchestrator-link-up`、`multica-orchestrator-nail-down`、`multica-create-agent`、`speckit-setup-project`、`speckit-taskstoissues`、全部 `speckit-worktrees-*`、`multica-coach` 只做盘点。`conventional-commit` 是唯一 retained commit capability，只绑定后续专职 committer；其余 Agent、Squad、Issue DAG 和 package manifest 不得绑定上述 excluded Skills。

`multica-cli` 是 Multica 访问的 canonical platform prerequisite；不得产生独立 Agent、Squad 成员、workflow node 或业务 ownership。

## 3. 拟议逻辑产物索引

W1 只创建需求和 W1 分析。其余路径是待 Human 接受的 stable logical artifact IDs，不表示文件已经生成。

| Logical artifact ID | 拟议路径 | Producer stage | 主要 Consumers |
| --- | --- | --- | --- |
| `REQUIREMENTS_PROVENANCE` | `orchestrator/requirements/orchestration-requirements.md` | W1 | W1–W8 |
| `W1_ANALYSIS` | `orchestrator/analysis/w1-inputs-and-capability-inventory.md` | W1 | W2–W8 |
| `W2_ANALYSIS` | `orchestrator/analysis/w2-capability-rationalization.md` | W2 | W3–W8 |
| `W3_ANALYSIS` | `orchestrator/analysis/w3-artifact-dependencies.md` | W3 | W4–W8 |
| `HANDOFF_GATE_SCHEMAS` | `orchestrator/contracts/handoff-gate-contracts.md` | W3 | W4–W8 |
| `W4_ANALYSIS` | `orchestrator/analysis/w4-feature-fix-dags.md` | W4 | W5–W8 |
| `W5_ANALYSIS` | `orchestrator/analysis/w5-agent-responsibility-matrix.md` | W5 | W6–W8 |
| `W6_ANALYSIS` | `orchestrator/analysis/w6-skill-permission-bindings.md` | W6 | W7–W8 |
| `W7_ANALYSIS` | `orchestrator/analysis/w7-template-delivery.md` | W7 | W8 |
| `AGENT_INSTRUCTIONS` | `orchestrator/agents/agent-instructions.md` | W7 | package installer/operator |
| `SQUAD_INSTRUCTIONS` | `orchestrator/squads/squad-instructions.md` | W7 | package installer/operator |
| `ISSUE_INPUT_CONTRACTS` | `orchestrator/issues/issue-input-contracts.md` | W7 | issue author/intake |
| `PACKAGE_MANIFEST` | `orchestrator/manifests/orchestration-package.yaml` | W7 | package installer/operator |
| `DELIVERY_NOTES` | `orchestrator/delivery/delivery-notes.md` | W7 | Human/operator |
| `W8_ANALYSIS` | `orchestrator/analysis/w8-enforcement-controls.md` | W8 | Human/operator |
| `CI_PROPOSAL` | `orchestrator/controls/ci-proposal.yaml` | W8 | repository admin |
| `PROVIDER_CONTROLS` | `orchestrator/controls/provider-controls.md` | W8 | Multica/provider admin |
| `HUMAN_APPROVAL_CONTROLS` | `orchestrator/controls/human-approvals.md` | W8 | Human Authority |

## 4. Skill 能力卡

### 4.1 共享、平台与安装能力

| Skill | 类型 / W1 状态 / 范围 | 目的、触发与输入 | 输出与副作用 | 依赖、runtime 与 owner 边界 | 验证与失败方式 |
| --- | --- | --- | --- | --- | --- |
| `multica-triage` | shared intake；`candidate`；候选 | Issue 创建/mention/字段变化后读取 Issue、comments、labels、subscriber、project/status、linked PR 和 current brief，判定 Feature/Fix/Needs Information/Invalid | `inspect` 只报告；`apply` 可写 comment、Brief、status；`dispatch` 才启动 run | 依赖 `multica-cli`、受支持字段读写与已验证 mapping；owner 是 Shared Intake/Orchestrator，不得实现 | 必须 readback comment/status/Brief/run；信息不足保持 blocked；混合范围不得猜；mapping 不一致即停 |
| `multica-cli` | platform；`canonical`；基础能力 | 任何确需访问 Multica 的 Agent 通过已认证 profile/workspace 读取或执行明确授权变更 | 可读取或改变 Issue、Agent、Squad、Project、Skill、metadata；side effect 取决于子命令 | 依赖本地认证、明确 profile/workspace、CLI 最低版本；owner 是 platform access，不是业务 Agent | 每次写入后精确 readback；认证、scope、ID 不明确即失败；禁止把 live ID 写入模板 |
| `multica-orchestrator-link-up` | setup；`canonical`；仅盘点 | 配置/检查 workspace、labels、Issue Status 与 Runtime foundation | `inspect` 无写；`apply` 可创建或校验基础 Workspace 资源 | 依赖 CLI、认证、支持的 workspace APIs；foundation owner | 逐项 readback、幂等；禁止测试 Issue/dispatch；本编队只消费 handoff |
| `multica-orchestrator-nail-down` | setup；`canonical`；仅盘点 | 把 repository 连接到已验证 orchestrator workspace 并生成项目级配置 | 可写 repository `.multica` 与 workspace project metadata | 依赖 server handoff、CLI、repo 权限、support templates；project-binding owner | 双向 readback；路径/remote/project 不明确即停；本编队不绑定 |
| `multica-create-agent` | setup；`candidate`；仅盘点 | Human 选择 runtime/model 后导入真实 network Skill 并创建 Multica Agent | 可导入 Skill、创建/更新 Agent；live side effect 高 | 依赖 CLI、可用 runtime/model、network Skill 内容与 Human 选择；setup owner | 创建后读取 runtime/model/Skills；不得用占位 Skill；本编队不绑定 |
| `speckit-setup-project` | setup；`candidate`；仅盘点 | 检查/初始化 Spec Kit、preset、extensions、workflow integrations | 可大量写 `.specify`、agent Skill 和项目配置 | 依赖 `specify` CLI、所需 revision、权限、目标路径；setup owner | 先 preflight/inspect；readback versions/files；禁止为验证创建 Issue 或启动实现 |
| `speckit-taskstoissues` | bridge；`candidate`；仅盘点 | 把 `tasks.md` 映射为外部 Issues | 创建 Issues、关系和 metadata，是 live side effect | 依赖任务结构和 issue provider；bridge owner | 数量/关系/readback；本编队使用自身 Issue 输入合同，不绑定该 Skill |
| `conventional-commit` | source-control commit/validation；`candidate`；保留 | repository writer 从本 run scope-bound candidate 构造并校验 Conventional Commit 和 Work-Item footer；独立 reviewer 只读复验 | writer 创建一个普通 immutable commit；reviewer 产 policy verdict；均不 push/merge/改写历史 | 依赖 approved provider-managed checkout、hook/validator、scoped writer permission；owner 是当前 writer，验证 owner 是 `commit-policy-reviewer` | candidate diff/path、footer、hook、commit SHA 与 provider run identity readback；进入所有 repository-writing role |
| `multica-coach` | design；`candidate`；仅盘点 | 从能力样本与需求按 W1–W8 生成 portable 编队包 | 只写 output_dir 本地产物并停在逐步 checkpoint；不得 live provision | 依赖完整 reference、Human 决策和 provenance；design owner | 每阶段 acceptance、revision、invalidation；生成编队不绑定自己 |

### 4.2 Feature 需求、治理与规划能力

| Skill | 类型 / W1 状态 / 范围 | 目的、触发与输入 | 输出与副作用 | 依赖、runtime 与 owner 边界 | 验证与失败方式 |
| --- | --- | --- | --- | --- | --- |
| `speckit-constitution` | governance；`candidate`；候选 | 初始化或 amendment 时，基于 Human 已确认目标、授权来源和 scope 维护 SDD Constitution 与 repository Architecture | 写 `.specify/memory/constitution.md` 和单一 Architecture 文件；可能触发 after_constitution hook | 依赖 constitution/architecture templates、仓库技术证据；owner 是 Feature Governance Draft，Human ratifies | 独立 output gate、无占位/越权来源、diff 审阅；Human 未接受即 BLOCKED |
| `speckit-roadmap-write` | governance ledger；`candidate`；候选 | Constitution 后初始化 Roadmap，或明确 delta 时非破坏 amendment | 写/增量修改 roadmap；不写 ADR/PRD | 依赖 roadmap config/template 和 Human 对 proposal/diff 的确认；owner 是 Roadmap Steward | 结构、版本 bump、无覆盖/重复；Human 未接受、结构损坏或输入缺口即停 |
| `speckit-roadmap-sync` | read-only audit；`candidate`；候选 | 明确请求 reconciliation 时比较 roadmap 与 specs | 只新增带 timestamp 的 sync report，不改 ledger/spec | 依赖 roadmap loader、review template、spec directories；owner 是 Roadmap Reviewer | orphan/phantom/status/dependency/ADR drift 分类；缺 roadmap 时停止并建议 write |
| `speckit-specify` | requirement authoring；`candidate`；候选 | current Feature Brief、approved checkout 和授权来源齐备后创建单一 WHAT/WHY spec | 在已提供 checkout 写 feature metadata/spec；任何 branch/worktree mutation 是 runtime drift，不得由该 Agent 接受 | 依赖 resolved spec template、extensions config、branch provisioning receipt；owner 是 Feature Spec Producer | stable IDs、source provenance、无 planning readiness 自判；mandatory hook 或 branch mutation 即失败 |
| `speckit-checklist` | requirement gate；`candidate`；条件候选 | Spec 可审查后按规则片段生成一个 canonical `checklists/requirements.md` | 写单一 Requirement Gate；不得创建 legacy domain checklist | 依赖 `.specify/templates/requirements/*.md`、spec revision；owner 是 Requirement Reviewer | 六 logical gates、PASS evidence、open blocker、sha256 revision；规则片段缺失即失败 |
| `speckit-clarify` | requirement repair；`candidate`；候选 | Requirement Gate 暴露 product decision 时，最多处理高影响问题并同步 spec/gate | 修改 `spec.md` 与 canonical requirement gate；产生 revision invalidation | 依赖 current spec 和 blocker ownership；owner 是 Feature Clarifier | 问题逐个接受、stable refs 同步；不得回答 source-owner/template blocker |
| `speckit-adrkit-context` | ADR read；`candidate`；候选 | Plan 前拉取治理当前路径或 open queue 的 ADR | stdout JSON；不写文件 | 依赖 `adrkit` CLI、ADR corpus/config；owner 是 Architecture Context Reader | CLI JSON/exit status；缺 corpus/tool 即 BLOCKED，不得伪造 decision |
| `speckit-plan` | technical planning；`candidate`；候选 | canonical Requirement Gate READY 且 governance/spec 可用后生成技术计划与 X0–X4 设计 | 写 `plan.md`、research、data-model、contracts、quickstart、test conditions 与设计 artifacts | 依赖 setup-plan/check-prerequisites/template resolver、preset templates/schemas、constitution/architecture；owner 是 Feature Planner | `PLAN_OUTPUT_READY`、stable ref coverage、test schema、无 unresolved blockers；gate drift 即回退 |
| `speckit-adrkit-check` | ADR verification；`candidate`；候选 | Plan 完成后核对 governing ADR；有 snapshot 时做 deterministic routing | stdout check/evaluate JSON；绝不写文件 | 依赖 `adrkit` CLI、plan、ADR corpus；snapshot 可选但缺失必须明示；owner 是 Architecture Reviewer | 非零 exit 阻塞；无 snapshot 只能证明 governing decisions，不能声称 routing 完整 |
| `speckit-adrkit-draft` | ADR draft；`candidate`；候选 | Plan 证明正式架构决策缺口且 Human 授权 drafting 时生成一个 ADR draft | 创建 schema-valid `draft` ADR；不得 ratify | 依赖 `adrkit` CLI、current plan、唯一 title/ID；owner 是 Architecture Draft Producer | 文件/status/schema/readback；Human 审阅取舍与 consequences 后才可 ratify |
| `speckit-tasks` | task planning；`candidate`；候选 | Plan 与设计交接完整后，把 stable refs 映射为可执行任务 | 写/重写 `tasks.md`，含路径、依赖、tests、parallel markers 与 final review | 依赖 setup-tasks、resolved tasks template、plan/spec/design artifacts；owner 是 Task Planner | 每个 plan output 有 task/NA、task ID 唯一、依赖可执行；生成后必须 Human Review |
| `speckit-analyze` | read-only consistency；`candidate`；候选 | Human 接受 `tasks.md` 后审计 Constitution、Architecture、Spec、Requirement Gate、Plan、Tasks | 只输出 severity findings；不得修改 artifacts | 依赖 check-prerequisites 与所有上游 revisions；owner 是 Independent Plan Reviewer | CRITICAL/coverage/constitution violations 阻塞；stale input 不得 PASS |
| `speckit-roadmap-brief` | pre-implementation audit；`candidate`；候选 | Analyze 通过后，将 active Feature 对齐 roadmap outcome/scope/dependencies/ADR | 只新增 timestamped brief report，不修改 ledger/spec/code | 依赖 roadmap loader/review template/check-prerequisites；owner 是 Roadmap Reviewer | PROCEED verdict 且无 Must-Address 才可交接；未匹配/歧义/缺 roadmap 即停 |

### 4.3 Feature 实现、Loop 与收敛能力

| Skill | 类型 / W1 状态 / 范围 | 目的、触发与输入 | 输出与副作用 | 依赖、runtime 与 owner 边界 | 验证与失败方式 |
| --- | --- | --- | --- | --- | --- |
| `speckit-implement` | Core implementation；`candidate`；候选 | Human 在首次源码修改前选择 Core 后，按 accepted tasks 实现 | 修改应用代码、tests、task completion state；运行项目命令与 hooks | 依赖 approved checkout、tasks/spec/plan、语言工具链；owner 是 Feature Core Maker | 对每 task 做行为验证并保留 evidence；blocker/失败测试不得伪报完成 |
| `speckit-loop-define` | Loop contract；`candidate`；候选 | Human 选择 Loop 前定义 recursive goal、done criteria、预算、maker/checker 与 guard | 写 feature-scoped loop contract/state | 依赖 tasks 与 loop config；owner 是 Loop Contract Producer | max iterations、criteria、allowed tools、state path 均明确；无独立 checker/Human guard 即不合格 |
| `speckit-loop-run` | Loop maker；`candidate`；候选 | 有有效 loop contract 且预算剩余时执行一次或多次 maker iteration | 修改代码/tests并 append externalized iteration state；不得自评 PASS | 依赖批准的 collaboration Runtime outer worktree、stable integration baseline、共享 loop state、工具权限；owner 是 Feature Loop Maker | 每 iteration evidence、预算和 stop reason；checker 不得与 maker 同 session |
| `speckit-loop-check` | Loop verifier；`candidate`；候选 | Maker handoff 后由独立 session/Agent 对 latest immutable revision 对抗式检查 | 写 durable checker verdict/state；正常不得修改代码 | 依赖同一 loop contract/revision/evidence、独立身份；owner 是 Loop Checker | 每 criterion 客观 PASS/FAIL；不确定默认 FAIL；self-check 即失败 |
| `speckit-loop-guard` | Human guard；`candidate`；候选 | checker PASS 后或预算/风险触发时，呈现 comprehension debt 与未验证风险 | 写 guard/sign-off state；不替 Human 决定 | 依赖 loop state、checker verdict、真实 Human；owner 是 Human Authority supported by Guard Agent | open blocking debt 或无显式 sign-off 时不得 done |
| `speckit-loop-status` | state rendering；`candidate`；候选 | session resume/查询时渲染 budget-aware state slice 和唯一 next action | 只读 loop state并输出摘要 | 依赖完整外部状态与 rendering budget；owner 是 Orchestrator/Observer | revision、iteration、debt、verdict 可追溯；状态缺失/冲突即 BLOCKED |
| `speckit-roadmap-debrief` | post-implementation audit；`candidate`；候选 | Core/Loop 完成后对照 roadmap outcome/scope/ADR 检查 drift | 只新增 timestamped debrief report，提议状态，不改 roadmap/code | 依赖 roadmap loader/review template、实现证据；owner 是 Roadmap Reviewer | outcome met 且无 Must-Address 才可建议 verified；缺 evidence 不得通过 |
| `speckit-converge` | post-implementation convergence planning；`candidate`；候选 | Debrief 后检查实现与 spec/plan/tasks 是否闭环 | 唯一写入是向 `tasks.md` append Convergence phase；不改代码/spec/plan | 依赖全部 artifacts、implementation evidence、hooks；owner 是 Convergence Reviewer | 无 finding 时不写空 phase；有任务则返回 Implement 路径，不得由 reviewer 自己修代码 |

### 4.4 Fix 能力

| Skill | 类型 / W1 状态 / 范围 | 目的、触发与输入 | 输出与副作用 | 依赖、runtime 与 owner 边界 | 验证与失败方式 |
| --- | --- | --- | --- | --- | --- |
| `speckit-bug-assess` | Fix assessment；`candidate`；候选 | current Fix Brief 到达后基于报告和代码定位症状、root cause、severity 与 remediation | 只在 `.specify/bugs/<slug>/assessment.md` 写评估，不改源码 | 依赖可读代码/日志/复现证据、唯一 slug；owner 是 Fix Assessor | verdict 必须为可路由结果；无法理解则 invalid；已有文件不得静默覆盖 |
| `speckit-bug-fix` | Fix implementation；`candidate`；候选 | assessment verdict 可修且范围明确时应用最小 remediation | 修改源码/tests并写 `fix.md`；运行针对性 checks | 依赖 immutable assessment 与批准 checkout；owner 是 Fix Maker，不能承担 Feature 工作 | 发现 assessment 错误立即停写并记录偏差；partial/failed 如实报告 |
| `speckit-bug-test` | Fix verification；`candidate`；候选 | fix report 完成后重跑原始复现与 regression | 运行 checks并写 `test.md`；通常不改源码 | 依赖 assessment/fix、测试工具与可执行环境；owner 是独立 Fix Verifier | 只有症状不再复现且关键 checks 通过才 verified；未运行/跳过必须显式记录 |

### 4.5 Worktree 能力（只盘点）

| Skill | 类型 / W1 状态 / 范围 | 目的、触发与输入 | 输出与副作用 | 依赖、runtime 与 owner 边界 | 验证与失败方式 |
| --- | --- | --- | --- | --- | --- |
| `speckit-worktrees-specify` | isolation wrapper；`candidate`；仅盘点 | 在独立 checkout 中执行 Specify | 创建 branch/worktree/spec；可能打开 IDE | 依赖 git、worktree config、Specify；repository integration owner | git worktree/branch/path readback；不进入编队 |
| `speckit-worktrees-create` | isolation mutation；`candidate`；仅盘点 | 为 feature branch 创建 nested/sibling worktree | 修改 git worktree state 与目录 | 依赖 git、唯一 branch、clean metadata；repository integration owner | `git worktree` readback；已有/冲突路径即停；不进入编队 |
| `speckit-worktrees-list` | isolation read；`candidate`；仅盘点 | 展示 active worktrees、spec/task progress | 只读 dashboard | 依赖 git worktree metadata；repository integration owner | 输出与 git 状态一致；不进入编队 |
| `speckit-worktrees-clean` | destructive isolation maintenance；`candidate`；仅盘点 | Human 明确选择后删除 merged/orphan/stale worktree | 删除 checkout/prune metadata，具有破坏性 | 依赖 git、merge/stale evidence、Human confirmation；repository integration owner | 删除前复核 branch/path/uncommitted changes；不进入编队 |

## 5. 隐藏依赖与适配性发现

### 5.1 Preset 与 runtime assets

- 样本安装了 workflow preset `3.3.0`；其 manifest 提供 wrapped/replaced Constitution、Architecture、Spec、Requirement Gate、Plan、Tasks、Analyze 模板与命令，以及 test/behavior JSON Schemas。
- `speckit-plan`、`speckit-tasks` 和分析链依赖 `.specify/scripts/bash` 的路径解析、template resolution、prerequisite checks；这些脚本可能持久化 feature metadata，只有 `--paths-only --no-persist` 路径是只读。
- ADRKit 的 `context`/`check` 是 read-only；`draft` 是唯一写操作且强制从 current plan 创建 `draft` 状态 ADR。
- Roadmap `brief`、`debrief`、`sync` 会写新的 report 文件，但不会修改 roadmap；只有 `roadmap-write` 修改 ledger。

### 5.2 Requirement Gate materialization gap

`speckit-checklist` 的有效合同直接读取 `.specify/templates/requirements/*.md`。样本 repository 的规则片段实际只存在于 preset 源目录，resolved runtime 路径没有该目录。结论：

- Skill 语义有效，但样本安装状态不能证明该 Skill 当前可运行。
- W2 必须把它标为“保留但带安装/解析前置条件”，不能把 preset 源路径硬编码进 portable Agent。
- W8 provider/CI proposal 必须验证 canonical runtime fragments 可解析；缺失时 blocker key 为 `REQUIREMENT_RULES_UNAVAILABLE`。

### 5.3 Worktree hook 冲突

样本 extension config 启用了 unconditional、mandatory `after_specify -> speckit.worktrees.create`，同时全局 auto hook execution 打开；已接受需求改为 Multica Runtime 管理 Project `local_directory(execution_mode=worktree)` 的外层 worktree，并排除所有 Spec Kit worktree Skill 节点。若直接复用该配置，会创建 nested worktree，破坏 Runtime task-branch ownership、baseline 和 cleanup。

- 该 hook 是 source-sample runtime drift，不是 portable template 的合法工作流节点。
- W2/W8 必须要求目标 integration 在使用生成模板前禁用/移除该 mandatory hook，并 readback effective hook graph；不得在 Agent 指令中“忽略失败”。
- 目标 Feature Handoff 必须携带 `WorkItemBranchRef.v1`、`RunCheckoutRef.v1` 与 `CheckoutRef.v5`；下游按 current stable integration head 创建各自 run checkout。

### 5.4 Loop 适配性

样本 Loop config 默认 `max_iterations:8`、`done_requires_checker_pass:true`、`checker.independent:true`、`guard.require_human_signoff:true`，状态外置到 feature 目录；合同允许 `isolation:worktree|none`。本编队固定采用 `default_worktree:false` 和：

```yaml
loop_eligible: true
loop_isolation: none
```

后续仍须由 W5/W6 提供不同 maker/checker Agent/session、最小权限和 Human guard；否则该决定失效并回退到 Core Implement。

## 6. 已解除：STATUS_CONTRACT_DRIFT

Human 已选择需求 SSOT + 维护中的 `multica-triage` 合同作为 portable
package 的唯一状态权威。样本 `.multica/agents/triage-mapping.md` 已同步为：

- `needs_information` / `blocked`
- `ready_for_human` / `todo`

映射同时保留真实配置边界：旧 `needs_info`/`backlog` 被标记为
legacy/non-authoritative；旧 `ready_for_human`/`backlog` 被标记为不可原地
协调的 category conflict。CLI 不支持 status definition 管理，浏览器入口在本次
执行环境不可用，因此没有伪造 live provisioning 结果。

这解除了 reusable package 的文档级状态合同阻塞。W8 必须继续生成 provider
precondition：任何 live application 或 triage write 前，由 Human 在 Multica Web
核对 canonical status 配置并明确同意。该同意不需要 Web evidence ref；未完成时
provider control 必须拒绝 dispatch。

## 7. W1 验收检查

| 检查 | 结果 |
| --- | --- |
| 首个直接 Human 决策已记录 | PASS：`default_worktree:true`、single collaboration Runtime、`execution_mode=worktree`、no nested worktree |
| 原始需求已固化为独立、可审计 SSOT | PASS |
| source_project/source_revision/requirements_revision 完整 | PASS |
| 37 个 Skill 均有能力卡 | PASS |
| exclusions 与 `multica-cli` 平台边界明确 | PASS |
| 支持文件、脚本、模板、schema、hook、runtime config 纳入分析 | PASS |
| Loop eligibility/isolation 明确 | PASS：`true` / `none` |
| 稳定逻辑产物索引已提出 | PASS，待 Human 接受 |
| 不复制 live IDs/路径/凭据/runtime snapshot | PASS |
| 状态合同无文档漂移 | PASS：样本 mapping、需求 SSOT、`multica-triage` 已统一 |

W1 已由 Human 接受。repository-local `orchestrator/` 成为 W2–W8 的稳定路径合同；下游阶段必须逐步更新 requirements/W1 revision 后重新接受。
