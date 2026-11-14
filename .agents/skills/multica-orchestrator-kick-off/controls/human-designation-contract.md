# Human designation and decision contract

## Purpose

Multica Projects have a Lead but no Project Owner permission role. This portable contract therefore does not require a Multica `project-owner`, approval-provider role binding, quorum, delegation, notification route, or authorization receipt.

For each target Project, an operator designates the email of the Human authenticated to Multica and obtains that Human's explicit consent. The actual email and consent record remain operator-local; this repository contains only placeholders and no live account data.

## Human designation

The operator maintains one current designation:

```yaml
schema: multica-coach.human-designation-ref.v1
designation_id: "designation:<opaque-project-ref>:<sequence>"
project_ref: "<opaque target Project ref>"
scope: project | work-item
work_item_ref: "<opaque work item ref or null for project scope>"
human_email: "<authenticated Multica account email from multica auth status>"
consent: true
consented_at: "<UTC RFC3339>"
state: CURRENT | REVOKED | SUPERSEDED
supersedes: "<designation_id or null>"
```

`human_email` is the authenticated Multica account email and the sole Human selector. Before designation, `multica auth status` must show that email for the selected profile; the account check plus explicit consent are the only designation prerequisites. It does not grant Multica workspace, Project, repository, runtime, Squad, Agent, merge, release, or deployment permission. A Multica Project Lead may be a Human or an Agent but is not this approval mechanism.

The designation must be current before a Feature's governance input or Specify stage and before a Fix Assess stage. A work-item designation overrides a current project designation only after the replacement authenticated account explicitly consents. A revoked or superseded designation blocks new Human decisions; historical decisions remain historical.

## Human decisions

The designated Human decides each subject independently after seeing the exact input revisions and actual diff/evidence. The Human may `ACCEPT`, `REJECT`, or `REQUEST REVISION`; silence and timeout remain `BLOCKED`.

```yaml
schema: multica-coach.human-decision-ref.v4
decision_id: "human:<work_item_ref>:<subject>:<sequence>"
work_item_ref: "<opaque work item ref>"
execution_ref: "<current WorkItemExecutionRef>"
subject: governance-input | constitution | architecture | adr | roadmap | tasks | implementation-route | loop-signoff | final-acceptance | risk-override
human_designation_ref: "<current HumanDesignationRef>"
human_participation_plan_ref: "<current HumanParticipationPlanRef>"
human_email: "<authenticated Multica account email matching the designation>"
input_refs:
  - "<ArtifactRef artifact_id@revision>"
diff_or_evidence_refs:
  - "<actual diff/report/evidence ref>"
decision: ACCEPTED | REJECTED | REVISION_REQUESTED
reason: "<non-empty Human reason or acceptance scope>"
decided_at: "<UTC RFC3339>"
supersedes: "<decision_id or null>"
```

A decision is valid only when its execution, designation and participation plan are current, its email matches the authenticated Multica account in the designation at `decided_at`, its input revisions match the gate, and the Human had the presented diff/evidence. A new artifact or execution revision makes dependent decisions stale; it does not overwrite history.

## Recording and notification

The workflow ledger records designation, participation plan, approval request, notification reservation/receipt, and decisions append-only with compare-and-set. `workflow-leader` may read current state, atomically reserve and send the exact designated-Human notification authorized by that plan, persist provider readback, and record a decision already made by the designated Human. It may not invent consent, change email/member mapping, duplicate a reserved initial notification, use a broad mention, treat delivery/timeout as a decision, or approve on the Human's behalf.

The tracked `multica-orchestrator-nail-down/templates/human-participation-plan.template.yaml` contains placeholders only. The operator-local copy maps the designation email to one exact Multica member recipient and a provider scheduler. This address is not a second Human selector. One initial notification and at most two scheduled reminders are allowed per current execution-bound request; every send requires atomic reservation/current-state readback and cannot assign, dispatch, rerun, cancel, or resume an Agent.

## First-producer readback

Passive Agent/Squad application does not require a designation, participation plan, consent, or decision ledger. Before the first Feature governance-input/Specify producer or Fix Assess producer, the operator confirms:

1. `multica auth status` for the selected profile shows the one current operator-local designation email;
2. that authenticated account's Human explicitly consented;
3. the current participation plan maps that designation to one exact member recipient and a readback-capable provider scheduler with bounded reminders and stop conditions;
4. the ledger can persist/read `HumanDesignationRef`, `HumanParticipationPlanRef`, `HumanApprovalRequestRef`, `HumanNotificationReceipt`, and `HumanDecisionRef` with exact revisions, supersession, and invalidation;
5. the workflow rejects absent, revoked, mismatched-email/member, stale-designation/plan/request/revision, non-Human decisions, and notification-as-decision;
6. Agents, Squads, bots, CI, and runtime identities cannot create a designation, consent, or Human decision; only `workflow-leader` has the bounded notification permission.

This contract does not authorize a live Issue, dispatch, trial run, merge, release, or deployment.
