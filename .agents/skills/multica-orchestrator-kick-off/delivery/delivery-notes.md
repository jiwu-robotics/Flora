# Multica Orchestrator delivery notes

## Package state

- Package: `multica-super-individual-orchestration`
- Version: `8.0.0`
- Scope: reusable workspace Runtime/Skills/Agents/Squads and worktree execution contracts
- Live application: not implied by repository content
- Project/repository association: excluded
- Dispatch: excluded

## Delivered reusable layer

- [`../manifests/orchestration-package.yaml`](../manifests/orchestration-package.yaml)
- [`../agents/agent-instructions.md`](../agents/agent-instructions.md) and sixteen role files
- [`../squads/feature-squad.md`](../squads/feature-squad.md)
- [`../squads/fix-squad.md`](../squads/fix-squad.md)
- [`../contracts/handoff-gate-contracts.md`](../contracts/handoff-gate-contracts.md)
- [`../contracts/branch-and-commit-policy.md`](../contracts/branch-and-commit-policy.md)
- [`../contracts/server-orchestration-ref.schema.json`](../contracts/server-orchestration-ref.schema.json)
- deterministic Skill archive, integrity, plan, single-operation apply, readback,
  verification, and handoff helpers under `../cli/`
- `ExecutionContextRef.v1`, `ArtifactRef.v2`, `GateRecord.v2`, `HandoffRef.v3`,
  `LeaderDispatchRef.v1`, `WorkItemExecutionRef.v4`, `WorkItemBranchRef.v1`,
  `RunCheckoutRef.v1`, `CheckoutRef.v5`, exact role/operation keys, typed external actors, single-consumer handoffs, and native Leader-first routing

Historical W1–W8 evidence remains under `../analysis/` and `../requirements/`.
It is design provenance, not a project binding or live readback.

## Completion

A current full Skill/Agent/Squad/runtime/status readback may produce:

```text
state=ORCHESTRATOR_LAYER_VERIFIED
dispatch_state=BLOCKED_PROJECT_BINDING
```

Project and repository resources, Runtime `local-worktree-v1` capability,
worktree binding, target commands, Spec Kit compatibility, dual branch/run
checkout controls, workflow ledger, scope/lease controls, CI, Human participation,
and integration readback are owned by `multica-orchestrator-nail-down`. A successful server-layer application never
creates a test Issue or starts a run.
