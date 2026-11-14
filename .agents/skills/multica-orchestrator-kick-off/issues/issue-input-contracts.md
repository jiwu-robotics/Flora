# Copyable Issue Input Contracts

> 模板状态：W9 ACCEPTED。以下模板只定义 intake 输入；从模板创建文件或 Issue 不会自动分类、派发、通知或授权实现。

## Feature Issue Template

<a id="feature-issue-template"></a>

```markdown
# Feature: <observable capability or outcome>

## Work type

`feature`

## Source

<!-- Choose exactly one: canonical external source URL/ref, or self-contained input below. Do not provide credentials. -->

- Source type: external | self-contained
- Source ref: <opaque URL/ref or N/A>
- Source revision/date: <immutable revision/date or N/A>
- Authorized scope from source: <specific facts/sections this Feature may use>

## Background

<Current situation and why this capability is needed. Separate observed facts from assumptions.>

## Goal

<One testable end state.>

## Scope and affected surfaces

- Repository/project ref: <opaque repository/project identity>
- Canonical work item ID: <provider-stable ID>
- Canonical work item URL: <HTTPS URL or N/A>
- Branch owner slug: <stable target-project owner slug; no email/UUID>
- Branch slug: <lowercase kebab-case identifier>
- In scope:
  - <surface/module/interface/user journey/data boundary>
- Affected surfaces:
  - product behavior: yes | no | unknown
  - API/interface contract: yes | no | unknown
  - UI/UX/visual: yes | no | unknown
  - data/storage/migration: yes | no | unknown
  - security/privacy/permissions: yes | no | unknown
  - architecture/ADR: yes | no | unknown
  - Constitution: yes | no | unknown
  - Roadmap: yes | no | unknown
  - CI/CD/deployment/release: yes | no | unknown

## Non-goals

- <explicitly excluded behavior or surface>

## Acceptance criteria

- [ ] AC-1: <observable condition, actor/input, expected result>
- [ ] AC-2: <boundary/failure condition and expected result>
- [ ] AC-3: <compatibility or regression condition>

## Constraints and references

- Existing contract/spec refs: <stable refs or N/A with reason>
- Constitution ref: <revision or N/A>
- Architecture ref: <revision or N/A>
- ADR refs: <revisions or N/A>
- Roadmap entry ref: <stable entry/revision or N/A>
- Technical/business constraints:
  - <constraint + source ref>

## Dependencies

- Depends on: <Issue/artifact/provider refs or none>
- External systems/owners: <named role/system, not credentials>
- Anticipated write paths/resources: <repository-relative paths, API/schema/dependency/config/migration resource keys, or unknown + owner>
- Potential overlap with active work items: <refs and relationship, or none/unknown + owner>
- Required environment/data: <what is needed and who provides it>

## Human governance impact

- Governance initialization/amendment required: yes | no | undecided
- Proposed governance scope: <Constitution / Architecture / ADR / Roadmap / none>
- Human approval subject: <governance-input / constitution / architecture / adr / roadmap>
- Evidence needed before decision: <diff/source/report>

## Human participation refs

- Human designation ref: <operator-local HumanDesignationRef or unresolved>
- Human participation plan ref: <operator-local HumanParticipationPlanRef or unresolved>
- Designation scope: project | this-work-item
- Work-item override reason: <none or concise reason>

These are opaque refs to the operator-local SSOT. Do not copy email, member ref, scheduler ref, consent record or notification receipt into the Issue. The designated Human still makes each later subject decision on exact diff/evidence; notification delivery is not approval.

## Verification expectations

- Required test levels/types: <unit/integration/system/manual/other>
- Required environment: <local/sandbox/real system/manual>
- Required evidence per AC: <command/scenario/report/artifact>
- Destructive/network/expensive checks: <none or explicit list requiring Human authorization>

## Permissions and risk

- Approved repository write scope: <paths/surfaces or pending>
- External write required: yes | no | unknown
- Cross-work-item scope disposition: pending | no-conflict | serialize-after:<work-item> | explicit-dependency:<work-item> | Human-decision-required
- Irreversible/destructive action: yes | no | unknown
- Security/data/release risk: <risk refs or none>
- Required Human approval subjects: <governance/tasks/route/risk/final acceptance>

## Open questions

- Q-1: <one actionable question + owner>

## Intake readiness

- [ ] Goal, scope and non-goals are distinguishable.
- [ ] Every AC is observable and independently decidable.
- [ ] Affected surfaces are answered; `unknown` items name an owner.
- [ ] Dependencies, environment and permission needs are explicit.
- [ ] Governance impact is explicit and does not assume AI approval.
- [ ] Designated Multica login account email is resolvable and explicit consent is confirmed.
- [ ] Canonical work item ID and branch owner/slug are resolvable; no private identity is embedded.
- [ ] Potential write-path/resource overlap is declared or names an owner.
- [ ] No credentials, live tokens or private machine paths are embedded.
```

### Feature intake gate

`FG0_BRIEF` remains `BLOCKED` when any of the following holds:

- source is neither resolvable nor self-contained;
- goal, scope, non-goal or acceptance criteria are not independently decidable;
- an affected surface is `unknown` without a named owner/resolution trigger;
- repository/project identity is ambiguous;
- permissions, dependencies or environment make the first stage unsafe;
- one request contains an independently actionable Fix and Feature without Human split/scope choice.

A complete template does not authorize dispatch. Shared Intake must still produce a current Feature Brief; `ready_for_agent/backlog` waits for explicit dispatch.

## Fix Issue Template

<a id="fix-issue-template"></a>

```markdown
# Fix: <existing behavior that is broken>

## Work type

`fix`

## GitFlow routing

- Requested route: fix | hotfix | undecided
- Existing production impact on `main`: yes | no | unknown
- Approved base/target ref: <provider readback; Fix must be develop/develop, Hotfix must be main/main>
- Release branch currently active: yes | no | unknown
- Hotfix justification: <production-blocking/security/severe-data-risk evidence or N/A>

## Source and environment

- Report/source ref: <Issue/PR/log/customer report ref or self-contained>
- Repository/project ref: <opaque identity>
- Canonical work item ID: <provider-stable ID>
- Canonical work item URL: <HTTPS URL or N/A>
- Branch owner slug: <stable target-project owner slug; no email/UUID>
- Branch slug: <lowercase kebab-case identifier>
- Version/revision/build: <immutable version>
- Environment: <OS/runtime/browser/device/service topology as relevant>
- Configuration/feature flags: <non-secret values relevant to reproduction>
- Test data prerequisites: <sanitized data and owner>

## Existing accepted contract

- Contract/spec/requirement/API ref: <stable ref proving expected behavior>
- Why this is a deviation, not a new capability: <evidence>

## Reproduction steps

1. <deterministic setup/input>
2. <action>
3. <observation point>

- Reproduction frequency: always | intermittent | unknown
- Minimal reproducer/artifact ref: <ref or missing owner>

## Expected behavior

<Observable result required by the existing contract.>

## Actual behavior

<Observed result, exact error/state/response and timestamp where relevant.>

## Impact and severity

- Affected users/systems/data: <scope>
- Severity: critical | high | medium | low
- Frequency/blast radius: <evidence>
- Security/data/integrity impact: yes | no | unknown
- Workaround: <verified workaround or none>

## Acceptance criteria

- [ ] FXAC-1: Original reproduction no longer fails on the fixed revision.
- [ ] FXAC-2: Existing related behavior passes regression checks.
- [ ] FXAC-3: <fix-specific boundary/failure condition>

## Evidence and references

- Logs/traces/screenshots: <redacted refs; no credentials>
- Related code/interface refs: <known refs or unknown>
- Related Issues/PRs: <refs or none>
- Last known good revision: <revision or unknown>
- First known bad revision: <revision or unknown>

## Scope and constraints

- Suspected local scope: <paths/modules/interfaces or unknown>
- Explicit non-goals: <unrelated refactor/new behavior>
- Required environment/tools: <requirements and owner>
- Destructive/network/expensive checks: <none or explicit list requiring Human authorization>
- Approved repository write scope: <paths or pending assessment>
- Anticipated shared resource keys: <API/schema/dependency/config/migration/provider resource keys, or none/unknown + owner>
- Potential overlap with active work items: <refs and relationship, or none/unknown + owner>

## Feature escalation screen

- Product/API semantics must change: yes | no | unknown
- Architecture/ADR amendment required: yes | no | unknown
- Cross-system impact not locally verifiable: yes | no | unknown
- Data migration required: yes | no | unknown
- Security/permission boundary changes: yes | no | unknown
- Irreversible release/operation required: yes | no | unknown

Any `yes`, or an unresolved `unknown` that prevents proving a local deviation, stops Fix execution and returns evidence to Shared Intake for Feature classification.

## Human/manual evidence

- Manual/target-only evidence owner: <named person/role/system ref>
- Manual/target-only verification required: yes | no
- Required evidence: <scenario/result/ref>

## Human participation refs

- Human designation ref: <operator-local HumanDesignationRef or unresolved>
- Human participation plan ref: <operator-local HumanParticipationPlanRef or unresolved>
- Designation scope: project | this-work-item
- Work-item override reason: <none or concise reason>

These are opaque refs to the operator-local SSOT. Do not copy email, member ref, scheduler ref, consent record or notification receipt into the Issue. The designated Human still makes each later subject decision on exact diff/evidence; notification delivery is not approval.

## Open questions

- FQ-1: <one actionable missing reproduction/contract/environment fact + owner>

## Intake readiness

- [ ] Existing accepted behavior is referenced.
- [ ] Environment, version, data and configuration are sufficient to reproduce.
- [ ] Reproduction steps and observation point are deterministic.
- [ ] Expected and actual behavior are distinct and observable.
- [ ] Impact and severity have evidence.
- [ ] Feature escalation questions are answered or have named owners.
- [ ] Designated Multica login account email is resolvable and explicit consent is confirmed.
- [ ] Canonical work item ID and branch owner/slug are resolvable; no private identity is embedded.
- [ ] Potential write-path/resource overlap is declared or names an owner.
- [ ] No credentials, live tokens or private machine paths are embedded.
```

### Fix intake gate

`XG0_BRIEF` is `BLOCKED` if environment, version, data, reproduction steps, expected contract or observation point is missing. Do not turn insufficient evidence into a guessed Fix assessment.

`hotfix` is not a third execution work type. It requires Human/provider confirmation of production-blocking, security or severe-data-risk evidence, then a `CheckoutRef(branch_role=hotfix,base_ref=main,target_ref=main)` and the mandatory GitFlow back-merge `PromotionRef`.

If the existing accepted contract is absent or any Feature escalation condition applies, Fix execution does not start. Shared Intake creates a new Feature Brief from the preserved evidence after Human classification.

A complete Fix template does not authorize dispatch. `ready_for_agent/backlog` remains an explicit authorization gate.

## Shared validation rules

- One Issue has exactly one work type after triage; `hotfix` is a GitFlow branch role, not an Agent work type.
- Stable IDs (`AC-*`, `FXAC-*`, question IDs and source refs) do not get silently renumbered after downstream use.
- `unknown`, `N/A` and `none` are distinct. `N/A` requires a reason; `unknown` requires an owner and resolution trigger.
- Attachments and external sources remain opaque refs until explicitly authorized; no Agent may infer missing content.
- Issue status is the accepted Multica status contract. Internal Gate outcomes never appear as Issue statuses.
- Input acceptance produces CURRENT_BRIEF; it does not produce a Human designation/participation plan, approval request/notification/decision, Spec, Assessment, checkout approval, implementation route or Human final acceptance.
