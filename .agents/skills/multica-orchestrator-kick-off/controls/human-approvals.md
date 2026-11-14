```yaml
coach_stage: W8
artifact: HUMAN_APPROVAL_CONTROLS
decision: ACCEPTED
application_state: proposal
installed: false
live_readback: false
requirements_revision: sha256:3b6caab15839cd7489bf30c23f9598a45fa309a3ade7a6227597ab83cb237d94
w7_analysis_revision: sha256:de926790b0402a22b5738a9f577d73d5399092086f8a9f0ac340a0227f55bd3a
human_decision_schema_revision: sha256:eef42b00a7630f5c801d87fe0bce9403fb09cea8f5625df7f72e0bcfc8c7cfbd
open_dispatch_blockers:
  - HUMAN_DESIGNATION_UNCONFIRMED
  - HUMAN_PARTICIPATION_PLAN_UNRESOLVED
  - APPROVAL_RECORD_STORE_UNRESOLVED
  - HUMAN_NOTIFICATION_CONTROL_UNVERIFIED
  - HUMAN_NOTIFICATION_DEDUPE_UNVERIFIED
supersedes: controls/human-approvals.md#sha256:5d5f17ea0b56c4262bec31e3319d6aac6b1ab696936656a7fb7533cd2cdf8058
```

# W8 Human Approval 控制方案

## 1. 原则

Human Authority 是经 `multica auth status` 确认、operator 指定且已明确同意的登录账号所代表的真实 Human，不是 Agent、Squad、bot、CI job、命令结果或 Issue status。Human 可以接受、拒绝或要求修订；沉默、超时、默认选项和“未发现问题”都不是接受。

designation 的唯一前提是：authenticated Multica account email 加该 Human 的 explicit consent。它不是 Multica Project Lead、workspace role、provider role binding、quorum、delegation 或 authorization receipt，也不授予任何 Multica、repository、runtime、merge、release 或 deployment 权限。

Constitution、Architecture、Roadmap 和对应 ADR 在首次生成与后续每次有效修改时都必须有人类参与。AI 可以准备草案、diff、options、tradeoffs 和问题，不能独立生成最终治理决定。

本文件不要求 identity provider 或 approval provider。没有已同意的 Human designation 和 append-only record store 前，不声称 approval control 已安装。

## 2. Canonical refs

每个 designation 与决定必须符合 [`../contracts/handoff-gate-contracts.md`](../contracts/handoff-gate-contracts.md) 的 `HumanDesignationRef.v1` 和 `multica-coach.human-decision-ref.v4`：

```yaml
schema: multica-coach.human-decision-ref.v4
decision_id: "<opaque stable id>"
work_item_ref: "<opaque work item ref>"
execution_ref: "<current WorkItemExecutionRef>"
subject: governance-input | constitution | architecture | adr | roadmap | tasks | implementation-route | loop-signoff | final-acceptance | risk-override
human_designation_ref: "<current HumanDesignationRef>"
human_participation_plan_ref: "<current HumanParticipationPlanRef>"
human_email: "<authenticated Multica account email matching the designation>"
input_refs:
  - "<ArtifactRef artifact_id@revision>"
diff_or_evidence_refs:
  - "<actual diff/report/check ref>"
decision: ACCEPTED | REJECTED | REVISION_REQUESTED
reason: "<非空的人类理由或接受范围>"
decided_at: "<UTC RFC3339>"
supersedes: "<decision_id or null>"
```

portable template 不写个人邮箱。workflow ledger 的 operator-local record 只接受 `multica auth status` 所示且与 current designation 匹配的 email；Agent、Squad、bot、CI 或 runtime identity 均不能创建 designation、consent 或决定。

## 3. 必需审批矩阵

| Subject | 触发时点 | Human 必须看到 | 接受后的效果 | 自动失效条件 |
| --- | --- | --- | --- | --- |
| `governance-input` | 初始化治理或扩大治理修改范围前 | sources、目标、scope、未知项、拟写 artifact | 允许 Governance Producer 起草指定对象 | scope/source/目标改变或授权撤回 |
| `constitution` | 首次生成或任何内容修改后 | actual diff、原则、governance rule、版本影响、open question | 对 exact revision 开放依赖节点 | Constitution revision、governance input 或证据改变 |
| `architecture` | 首次生成或任何内容修改后 | actual diff、observed/inferred/target/gap、tradeoff、影响面 | 对 exact revision 开放 ADR/Plan | Architecture revision、Constitution 或关键仓库事实改变 |
| `adr` | Plan/ADR Check 要求正式决定且 draft 已生成 | context、options、tradeoffs、consequences、actual diff、review finding | ratify/reject/amend exact ADR revision | ADR/Architecture/Plan context 改变或被 supersede |
| `roadmap` | 首次生成或任何 Roadmap delta 后 | actual diff、优先级、依赖、非破坏性 delta、Brief/Debrief finding | 对 exact Roadmap revision 开放依赖节点 | Roadmap revision 或 governing artifact 改变 |
| `tasks` | 初始 Tasks、Producer 修订或 Convergence append 后 | complete actual diff、stable IDs、路径、依赖、测试、route implications | 允许为 exact Tasks revision 选择 route/实现 | Tasks/Plan/Spec/required review revision 改变 |
| `implementation-route` | 首次源码写入前 | accepted Tasks、checkout、Core/Loop差异、Loop资格、风险/预算 | 固定唯一 `core|loop` route | Tasks、checkout、Loop eligibility 改变；route 切换需新决定 |
| `loop-signoff` | checker verdict 后、Loop 结束前 | immutable iteration、逐 criterion verdict、debt、风险、预算、not-run | 允许 Loop changeset 进入 Commit boundary | iteration、verdict、debt、risk 或 budget record 改变 |
| `risk-override` | 控制阻断且 Human 被允许承担风险时 | 原始失败、不可验证项、blast radius、替代方案、expiry/rollback | 只豁免明确 subject/scope；不得自动豁免其他 check | scope/revision/risk 改变或 expiry 到期 |
| `final-acceptance` | 所有 required Gate、review、test 和 Convergence current 后 | current CommitRef、AC/BAC evidence、未决风险、manual evidence | 只开放 provider integration eligibility；不授权 merge/release/deploy，Issue completion 仍需 current IntegrationRef | implementation、commit、test、review、risk 或 required artifact 改变 |

每个 subject 使用独立决定。不得用 `final-acceptance` 倒推 Constitution、Architecture、ADR、Roadmap 或 Tasks 已接受。

## 4. Human gate、主动通知与决定路由

Gate owner 必须通过单一 HandoffRef 提供 subject、请求的 decision、project/work item/execution、current artifact IDs/revisions、actual diff、相关 evidence/测试/未验证项、选项与 tradeoffs、typed external actor refs，以及接受/拒绝/要求修订三种显式操作。`workflow-leader` 校验后才以原子 compare-and-set 记录 current `HumanApprovalRequestRef.v2`；无 Multica recording 权限的 execution Agent 不得自行创建 ledger ref。信息过长时可以附稳定链接，但 Human 无法访问链接即为 BLOCKED。

`workflow-leader` 必须先按 `project_ref + work_item_ref + execution_ref + subject + designation_ref + participation_plan_ref + sorted_input_revisions` 原子预留 current request 的 initial notification；只有 reservation 从 UNRESERVED 成功转为 RESERVED 的 run 才发送 exact designated Human member mention。发送后把 provider readback 和 reservation 更新为 `HumanNotificationReceipt`/SENT。该 notification comment 不得 mention Agent、Squad 或 `@all`，不得借 notification 改 assignment、dispatch、rerun、cancel 或视为 approval。

后续 reminder 只能由 plan 指定的 provider scheduler 触发，默认最多两次。每次发送前 readback current request、execution、designation、plan、decision、reservation、已有 receipt 与 work item state；已有决定、request stale、designation/plan 改变、work item terminal 或达到上限时停止。失败或未知 delivery 先 readback，禁止盲目重试。notification/receipt/timeout 只证明提醒尝试，绝不等于 consent 或 Human decision。

Leader 的 recording-only 接口只能持久化 designated Human 已作出的决定。写后校验 execution、designation ref、plan ref、email matching、subject、decision、exact input/evidence refs、time 与 supersedes；任一字段不匹配即 `HUMAN_APPROVAL_EVIDENCE_INVALID`。`ACCEPTED` 只开放 exact downstream gate；`REVISION_REQUESTED` 返回唯一 Producer/Maker；`REJECTED` 停止或按当前 workflow contract 返回。全部结果仍要求显式 resume/dispatch 和 current execution 去重，notification controller 不启动 Agent。

artifact、request、plan、designation 或 execution 变化后保留历史并标记 stale。无回复保持 BLOCKED。不同 Work Item 的 Human Gate 可并发等待，但 request/reservation/decision namespace 不能共享。

## 5. 职责分离

| Actor | 可以 | 不可以 |
| --- | --- | --- |
| Operator | 给出 `multica auth status` 所示 account email 并确认该 Human 的 explicit consent | 以 designation 代替各 subject 的实际决定 |
| Producer/Maker | 准备 artifact、diff、evidence 和建议 | 接受自己的产物；伪装 Human |
| Reviewer/Verifier | 提供独立 finding/verdict | 把 review PASS 当作 Human acceptance |
| `feature-loop-guard` | 完整呈现 Loop debt/risk，记录真实回复 | 替 Human sign off；覆盖 checker verdict |
| `workflow-leader` | 消费 current designation/participation plan、校验 revision、发送受控 exact Human mention/reminder、持久化 provider readback 和已发生决定 | 选择或改变 email/member、伪造 consent、broad mention、把通知/超时当作决定、assign/dispatch/rerun/cancel、作产品/治理/route/risk/final decision |
| CI | 验证记录、阻止缺失审批 | 推断意图或自动生成 Human decision |
| Designated Human | 对每个 subject 作独立决定 | 通过泛化 approval 绕过其他 subject |

## 6. Human designation 与 participation plan

每个 target Project 在首个 Feature/Fix producer 前有一个 current `HumanDesignationRef` 和一个 current `HumanParticipationPlanRef`。operator 提供 selected Multica profile 的 authenticated account email，Human 明确同意；仅此两项为 designation 前提。work-item override 必须由替代登录账号新近同意。

tracked template 由 `multica-orchestrator-nail-down` 的 `templates/human-participation-plan.template.yaml` 提供。它只保存 portable schema 和占位值；填写后的 plan、email、member ref、scheduler ref 与 receipts 保持 operator-local。notification recipient 只是 current designation 的投递映射，不得成为第二套 Human selector。

designation 或 plan 被撤销、替换，或 Brief/work type/scope 改变时，pending request 为 BLOCKED。账号/recipient 不匹配、无回复、notification、timeout 或外部 provider 记录都不能替代 consent 或 Human decision。

## 7. Governance 人工参与闭环

```text
current Human designation
  → Human governance-input
  → Agent draft
  → actual diff + evidence
  → Human ACCEPTED / REJECTED / REVISION_REQUESTED
  → accepted exact revision 或返回修订
```

## 8. Final acceptance 与未授权动作

Final acceptance 只开放 provider integration eligibility；它不授权 merge、release、deployment、数据迁移、secret/permission 或 workspace schema 变更，也不在缺少 current IntegrationRef 时允许 Leader 记录 Issue 完成。

## 9. 首次 dispatch/readback 验收

首次 dispatch 前，安装者必须证明：

1. 每个 target Project 有一个由 `multica auth status` 确认的 current Human account email、该 Human 的 explicit consent 和一个 current participation plan；
2. plan 的 member recipient 确实解析到 designation email，且 provider scheduler、interval、上限与 stop conditions 可 readback；
3. record store 支持 execution-bound immutable history、compare-and-set、exact refs、email matching、consent、request/reservation/notification/decision、supersedes 和 stale；
4. artifact、request、plan、designation 或 execution 更新会使依赖 decisions/pending requests stale；
5. PR/integration procedure 能读取 current decision records，且 final acceptance 不替代 integration approval；
6. 除 `workflow-leader` 的受控 Human notification 外，Agent 无创建/修改 designation、consent、notification route/reservation 或历史 Human decision 的权限；
7. first notification 先原子预留并使用 exact member mention；不能 mention Agent/Squad/`@all`，不能产生 assignment/dispatch/rerun/cancel；
8. Governance/Tasks/route/Loop/final acceptance 每一 subject 可分别阻止推进；
9. 未回复、notification delivery、REJECTED、REVISION_REQUESTED 和 stale 不会被判作通过，任何决定都不会自动启动 Agent；
10. 并发 Leader run 对同一 current request 只产生一次 initial notification。

本次 W8 不执行上述 live 安装或试跑。