---
name: multica-orchestrator-cli
description: Provide the sole stage-qualified operational CLI, shared state core, and support scripts for Multica orchestrator lifecycle Skills.
---

# Multica Orchestrator CLI

`multica-orchestrator-cli` is the sole distributed physical owner of the shared
state core, operational CLI modules, and prompt/report scripts used by
`multica-orchestrator-link-up`, `multica-orchestrator-kick-off`,
`multica-orchestrator-nail-down`, `multica-orchestrator-migrate`,
`multica-orchestrator-dispatch`, and `multica-orchestrator-relocate`.

`multica-migrate-server` is not a consumer. This Skill does not own Dispatch
control SQLite, Runtime-local activation state, lifecycle policy, Agent or Squad
configuration, or Human authorization and notification flows.

## Mandatory raw prompt and report capture

Every direct invocation must archive its exact prompt before work and its exact
final report before completion using this installed Skill's
`scripts/prompt_and_report_capture.py` helper. Run `start` with this Skill name
and the invocation working directory, provide the complete prompt on standard
input, retain the returned capture ID, then run `finish` with the same ID and
the exact final report on standard input. The resulting `.prompt-and-report/`
archive is local-only, owner-protected, never committed, copied, bundled, or
reported.

## Installation and Imports

The repository distributes this Skill through the standard copied-Skill flow.
Lifecycle contracts resolve this installed sibling package from the selected
Agent Skill root; they MUST NOT rely on a globally installed Python package or
retain a per-Skill compatibility copy of its helpers.

The stable state and handoff import namespace remains
`cli/multica_state_bundle/`. The stage modules are in
`cli/multica_orchestrator_cli/stages/`; they retain their existing lifecycle
policy, mode maps, typed failures, and Human/Agent/Squad boundaries.

## Stage-qualified invocation

Invoke a lifecycle stage through the central runner:

```text
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py \
  <link-up|orchestrator|nail-down|migrate|dispatch|relocate> <mode> [arguments]
```

The runner rejects missing, unknown, or cross-stage modes before a lifecycle
operation. A missing or incompatible package fails before lifecycle or live
service mutation and names `multica-orchestrator-cli` as the corrective
installation.

The `orchestrator` route includes `verify-integrity`; a publishable Server
generation requires its `--phase full` report together with the final Server
verification report. It is not interchangeable with a partial inspection.

## Operator diagnostics

State diagnostics remain available in the `state` namespace:

```text
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py state inspect \
  --repository <credential-free-github-url> --subpath <repository-relative-path> \
  [--workspace-key <sha256-digest>] --format json

python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py state validate \
  --repository <credential-free-github-url> --subpath <repository-relative-path> \
  [--workspace-key <sha256-digest>] --format json

python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py state recover \
  --repository <credential-free-github-url> --subpath <repository-relative-path> \
  [--workspace-key <sha256-digest>] --format json
```

`inspect` and `validate` are read-only. `recover` can clear only a proven stale
project claim after confirming that the prior writer is inactive and retained
state is complete and valid. It never migrates legacy state, repairs an
incomplete generation, or overrides an active claim.

## Invariants

- Project selection derives from workspace identity, credential-free repository
  identity, and repository-relative subpath only.
- Readers observe a prior verified generation or a new verified generation,
  never temporary publication material.
- Same-project competing mutations return an immediate typed blocker without
  state changes. Different projects remain independent.
- Legacy shared state is rejected without deletion, migration, or
  reinterpretation.
- Secret-bearing private material is owner-readable only and never enters
  bundles, hashes, reports, package trees, or inspection output.
