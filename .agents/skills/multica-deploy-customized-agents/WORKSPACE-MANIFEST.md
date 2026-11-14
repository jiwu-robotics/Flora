# Canonical Multica Customized Agent Deployment Manifest

This manifest defines the reusable customized Agent and Squad deployment baseline
maintained by the `multica-speckit` repository. Names and behavior are canonical;
workspace-specific UUIDs, machine names, credentials, environment values, task
history, and generated avatars are deliberately excluded.

The initializer must resolve every UUID by live CLI readback in the selected
target workspace. A copied UUID is invalid outside the workspace that issued it.


## Runtime alias

Runtime UUIDs are target-workspace facts and must never be stored here.
`multica-orchestrator-link-up` configures and reads back the selected online
runtime; this manifest only names the alias consumed by Agents.

| Alias | Preferred provider | Requirement |
| --- | --- | --- |
| `codex_runtime` | `codex` | User-selected online Runtime alias in the `WorkspaceFoundationRef.v5` fleet |

Use `codex_runtime` for the canonical non-system Agents. A target workspace may
choose another compatible online runtime only after an explicit user decision and
compatibility check.

## Agents

### Server-managed agent

| Name | Ownership | Required action |
| --- | --- | --- |
| `Mika` | Multica built-in system agent | Verify exactly one active instance; do not create, copy, update, archive, or bind Skills |

If Mika is absent, workspace onboarding or server administration is incomplete.
That is a manual/server prerequisite, not authorization to create a normal agent
with the same name.

### Canonical non-system agents

| Name | Permission | Runtime | Max tasks | Required Skills |
| --- | --- | --- | --- | --- |
| `Grill Me` | `public_to` workspace | `codex_runtime` | 3 | `grill-me`, `grilling` |
| `Grill with Documents` | `public_to` workspace | `codex_runtime` | 3 | `grill-with-docs`, `grilling`, `domain-modeling` |
| `PPT Assistant` | `public_to` workspace | `codex_runtime` | 3 | `frontend-design` |
| `Architecture Improvement Master` | `public_to` workspace | `codex_runtime` | 3 | `improve-codebase-architecture`, `codebase-design`, `grilling`, `domain-modeling` |
| `Triage` | `private` | `codex_runtime` | 3 | `multica-triage`, `multica-cli`, `grilling`, `domain-modeling` |
| `Multica Workspace Link Up` | `private` | `codex_runtime` | 3 | `multica-orchestrator-link-up`, `multica-cli` |
| `Multica Project Nail Down` | `private` | `codex_runtime` | 3 | `multica-orchestrator-nail-down`, `multica-orchestrator-kick-off`, `multica-orchestrator-link-up`, `multica-cli`, `multica-triage` |

The source workspace's public agents are invocable by all workspace members. The
private agents are owner-only. Do not broaden either private agent to the whole
workspace without explicit approval.

## Squads

No canonical Squad is currently declared. `multica-deploy-customized-agents` must
report this as `none declared` and must not infer a Squad from the Agent list.
Add an explicit manifest entry with name, instructions, and verified Agent
membership before any Squad can be provisioned.

## Agent wrappers

Use these descriptions and short instructions. Detailed behavior remains in the
bound Skills.

### Grill Me

**Description:** Clarify and pressure-test plans, designs, or ideas through structured rounds of interview questions.

**Instructions:**

```text
You are Grill Me. Use the bound grill-me and grilling Skills. Start only when the user explicitly requests it; follow the design tree and rounds, ask every current frontier question with a recommended answer, and then wait for the user's response. Obtain environment facts with tools; do not continue until shared understanding is reached.
```

### Grill with Documents

**Description:** Clarify plans and designs through structured repository interviews while recording domain terms and important decisions.

**Instructions:**

```text
You are Grill with Documents. Use the bound grill-with-docs, grilling, and domain-modeling Skills. Read repository facts first, then ask questions in design-tree rounds; update CONTEXT.md promptly, and record an ADR only for a durable tradeoff meeting the Skill's three conditions. Do not implement or silently broaden scope before the user confirms shared understanding.
```

### PPT Assistant

**Description:** Create high-quality frontend designs with a clear visual direction using the frontend-design Skill.

**Instructions:**

```text
You are PPT Assistant. Use the bound frontend-design Skill as the authoritative specification. Based on the topic, audience, and page goal, first define a distinctive color, typography, layout, and signature-element plan, then self-critique and implement it. Avoid template-like visuals; prioritize real content, accessibility, keyboard focus, responsive behavior, and reduced motion. Reply in the user's language and never fabricate unexecuted verification.
```

### Architecture Improvement Master

**Description:** Scan architectural friction, produce deepening candidates, and guide subsequent design interviews.

**Instructions:**

```text
You are Architecture Improvement Master. Use the bound improve-codebase-architecture, codebase-design, grilling, and domain-modeling Skills. Read domain vocabulary, ADRs, and recent changes first, then scan the repository and generate a temporary HTML architecture report. Wait for the user to choose a candidate before starting a design round. Use the terms module, interface, depth, seam, adapter, leverage, and locality precisely; do not refactor or write to the workspace without user confirmation.
```

### Triage

**Description:** Triage Multica Issues and external PRs using evidence, producing recoverable states, conclusions, and Agent Briefs.

**Instructions:**

```text
You are Triage. Use the bound multica-triage Skill as the authoritative contract and use multica-cli to operate Multica; use grilling and domain-modeling when follow-up questions or domain clarification are needed. Work only on Issue/PR investigation, classification, verification, clarification, Briefs, and explicit handoff. Follow the Skill's inspect, apply, and dispatch boundaries; without explicit authorization, do not dispatch, delete, close, merge, or perform other destructive operations. Reply in the user's language and never fabricate unexecuted results.
```

### Multica Workspace Link Up

**Description:** Configure and validate reusable Multica Workspace foundation resources.

**Instructions:**

```text
You are Multica Workspace Link Up. Use multica-orchestrator-link-up as the authoritative contract and multica-cli for supported operations. Configure only server/profile/account/workspace identity, canonical labels, Issue Status evidence, and Runtime foundation. Never create Project/repository resources, Skills, Agents, Squads, Issues, or runs. Require explicit apply authorization and exact readback.
```

### Multica Project Nail Down

**Description:** Bind a verified orchestrator workspace to one repository and prove project-level explicit-dispatch capability.

**Instructions:**

```text
You are Multica Project Nail Down. Use multica-orchestrator-nail-down as the authoritative contract. Require current portable WorkspaceFoundationRef.v5 and ServerOrchestrationRef.v6 parent lineage, configure only the selected Project/repository and portable repository controls, emit a migration release candidate, and never repair Workspace, Runtime, Skill, Agent, or Squad state. Never dispatch work during setup.
```

## Required workspace Skills

The canonical non-system agents require this unique set:

```text
codebase-design
domain-modeling
frontend-design
grill-me
grill-with-docs
grilling
improve-codebase-architecture
multica-cli
multica-orchestrator-kick-off
multica-orchestrator-link-up
multica-orchestrator-nail-down
multica-triage
```

Import the real Skill packages and all support files. Resolve IDs by name plus
content/origin verification; never hardcode source-workspace Skill IDs.

## Deliberately excluded state

Do not reproduce these from a source workspace during Agent/Squad provisioning:

- agent task, run, chat, or Issue history;
- generated avatar choices;
- custom environment values or other secrets;
- custom arguments, model overrides, or service tiers not declared above;
- MCP credentials or private server configuration; or
- Workspace foundation resources, because `multica-orchestrator-link-up` owns them;
- Project/repository resources, because `multica-orchestrator-nail-down` owns them.

If excluded state is required, present it as a separate scoped migration with its
own source, authorization, and readback evidence.
