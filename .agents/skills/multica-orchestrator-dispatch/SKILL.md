---
name: multica-orchestrator-dispatch
description: Admit and control one Work Item execution against an ACTIVE Multica orchestrator Project release, with exact-revision integration and provider evidence.
---

# Multica Orchestrator Dispatch

Own the live, per-Work-Item execution boundary. Admit one canonical Multica Issue against one ACTIVE Project release, bind the selected runtime capability and Agent/Squad contract, maintain the operator-local control store, and prove integration against exact source, target, and proposed merge revisions.

This Skill does not create Workspace resources, configure reusable Skills/Agents/Squads, bind a repository to a Project, activate a Project bundle on a runtime host, or mutate immutable bundles. Those responsibilities remain with Link Up, Orchestrator, Nail Down, and Migrate respectively.

## Dependencies

Read `multica-cli`, `multica-orchestrator-kick-off`, `multica-orchestrator-nail-down`, and `multica-orchestrator-migrate` before the first operation. Require:

- a current `ProjectBindingRef` from Nail Down;
- a matching `ProjectReleaseCandidate` activated by Migrate;
- an `ACTIVE` Project release with verified runtime activation receipts;
- the selected Runtime alias and required capability revision;
- a canonical Multica Issue UUID and routable Issue key;
- the immutable Server Agent/Squad generation named by the Project release.

Never infer readiness from a working-tree path, branch name, uncommitted file, or operator assertion. Read back every durable prerequisite.

## Central operational runner

Before any lifecycle action, resolve the installed
`multica-orchestrator-cli` package from the selected Agent Skill root. Invoke
Dispatch only through:

```text
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py \
  dispatch <inspect|admit-or-resume|control|record-human-decision|capture-control-evidence|check|capture-provider|refresh-provider-evidence|verify-provider|schedule-notifications> [arguments]
```

An unavailable or incompatible central package is a pre-mutation blocker; install
`multica-orchestrator-cli` rather than looking for a Dispatch-local command or
script asset.

## Mandatory raw prompt and report capture

Every direct invocation must create an exact local record before reading any source or taking another action.

1. Resolve
   `<agent-skill-root>/multica-orchestrator-cli/scripts/prompt_and_report_capture.py`
   and run `start` with Skill name `multica-orchestrator-dispatch` and `--cwd "$PWD"`. Supply the complete triggering instruction on standard input.
2. Preserve the returned `capture_id`. The helper writes under `./.prompt-and-report/` with private permissions and excludes the directory from the local Git worktree.
3. Never redact, rewrite, commit, bundle, upload, or publish the captured prompt or report.
4. On every terminal path, run `finish` with the same `capture_id`; supply the exact final report on standard input.
5. A capture failure blocks a completion claim.

## State boundary

The operator-local control store is separate mutable state. Its schema is versioned independently from Foundation, Server, and Project bundles.

- Bundle generations are immutable and retained.
- A changed Server Agent/Squad contract produces a new Server generation.
- A changed Project binding produces a new Project generation and release candidate.
- Activating a new candidate produces new runtime activation receipts and one new ACTIVE Project release.
- Existing active control-store executions whose binding/release contract is superseded become `STALE`; never rewrite them to appear current.

Runtime discovery and authority state are private, Runtime-local:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/multica-orchestrator-dispatch/
```

Migrate publishes an exact Project binding registry and fenced target ACTIVE
release; Dispatch never derives identity from cwd, profile aliases, branch, or
worktree. One daemon/deployment authority database is shared by its active
Projects. Registry, SQLite, admission artifacts and outbox remain mode-`0600`
below mode-`0700` directories.

## Leader admission

The workflow-leader uses only profile, optional Workspace selector and canonical
Issue identity:

```text
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py dispatch inspect --profile <profile> [--workspace <selector>] --issue <UUID|KEY-N>
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py dispatch admit-or-resume --profile <profile> [--workspace <selector>] --issue <UUID|KEY-N> [--run-ref <native-leader-run-ref>] [--restart]
```

`inspect` is authoritative read-only and never creates a directory, WAL sidecar,
pointer, database or admission. `admit-or-resume` resolves the ACTIVE target
release, exact Project, Runtime, assigned Feature/Fix Squad, immutable Leader
ref and exactly one running Leader task, then creates/reuses `RunAdmissionRef.v1`.
It never mentions, assigns, reruns, creates a checkout, mutates Git or executes
CI. A changed active contract blocks rather than ending/replacing an execution.

Admission does not itself dispatch an agent. The workflow leader performs explicit Multica dispatch only after admission, and must pass the Issue, selected Project/Runtime, exact immutable Agent/Squad refs, and the admission digest. Never use a branch or repository-local file as authority for Issue identity.

## Runtime and branch ownership

All checkout, branch, scope, lease, queue, notification, and Human-decision controls are dispatch-time state:

- one active writer checkout per execution;
- one Work Item integration branch bound to the execution;
- runtime branch and checkout root distinct from another live run;
- scope overlap and leases enforced with compare-and-swap revisions;
- notification delivery through restricted workflow-leader outbox only;
- Human designation is an explicit operator action; decision recording never designates or replaces a Human implicitly.

Use `control readback` after each state transition. Never bypass a rejected transition by editing SQLite directly.

## Exact-revision integration

Every integration attempt binds three lowercase 40-character revisions:

1. `source_revision`: current Work Item branch head;
2. `target_revision`: target branch head used to construct the proposal;
3. `merge_revision`: the proposed/accepted merge result on which project checks and provider checks run.

`capture-control-evidence` requires the active `RunAdmissionRef`, the current queue attempt, exact checkout/branch state, Human approval, scopes, leases, ledger, and all three revisions. It emits `IntegrationCheckEvidence.v1`.

`check` validates control evidence against all three revisions. With `--execute-project-command`, repository `HEAD` must equal `merge_revision`; source-head execution is invalid.

`capture-provider` queries GitHub check-runs for `merge_revision`, not the source head. `verify-provider` accepts evidence only when:

- the PR source equals `source_revision`;
- the recorded target-before-merge equals `target_revision`;
- the merged target and current target equal `merge_revision`;
- `checks_revision` equals `merge_revision`;
- every required control and project check has exactly one passing check-run.

Target movement, source movement, merge-result replacement, duplicate/missing checks, stale Human approval, or changed Project release invalidates the attempt. Enter a new queue revision and recapture evidence.

```text
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py dispatch inspect --profile <profile> [--workspace <selector>] --issue <UUID|KEY-N>
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py dispatch admit-or-resume --profile <profile> [--workspace <selector>] --issue <UUID|KEY-N> [--run-ref <native-leader-run-ref>] [--restart]
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py dispatch control --db <bound-store.sqlite> <branch|checkout|scope|lease|queue|ledger|notification|human-decision command>
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py dispatch record-human-decision --profile <profile> --workspace <workspace> \
  --db <bound-store.sqlite> --project-ref <project-ref> --repository-ref <repository-ref> \
  --target-ref <target> --attempt <attempt-ref> --source-revision <sha> \
  --target-revision <sha> --decision APPROVED|REJECTED --authorization-ref <ref>
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py dispatch capture-control-evidence --db <bound-store.sqlite> \
  --project-ref <project-ref> --repository-ref <repository-ref> --target-ref <target> \
  --attempt <attempt-ref> --source-revision <sha> --target-revision <sha> \
  --merge-revision <sha> --run-admission <run-admission.json> --output <evidence.json>
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py dispatch check --check <name> --evidence <evidence.json> \
  --source <sha> --target <sha> --merge <sha>
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py dispatch capture-provider --repository <owner/repository> \
  --pull-request <number> --merge-revision <sha> --output <provider-evidence.json>
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py dispatch verify-provider --evidence <provider-evidence.json> \
  --source <sha> --target <sha> --merge-head <sha> --output <verification.json>
```

The central `dispatch` stage route is the only stable runner.
`refresh-provider-evidence` is an alias of `capture-provider`; it always performs fresh provider readback.

## Terminal report

Report:

- `dispatch_state` and `RunAdmissionRef` digest;
- Project key, Project binding digest, ACTIVE release digest, runtime alias;
- Issue UUID/key, work type, Squad and leader refs;
- source, target, and merge revisions;
- control-store schema/revision and provider verification digest;
- blockers and all side effects not executed.

Never claim dispatch, integration, or completion from admission alone.

## Shared state package

This Skill resolves the central `multica-orchestrator-cli` package for the
preserved `multica_state_bundle` namespace. Its separate Dispatch control store
remains the sole owner of execution admission and queue state.
