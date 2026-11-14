---
name: multica-orchestrator-relocate
description: Reissue and atomically rebind Multica orchestrator state after a verified self-hosted server relocation, preserving logical deployment lineage, Project activation history, and Runtime bundle closure without migrating service data or dispatching work.
---

# Multica Orchestrator Relocate

Rebind the operator-local Multica orchestrator deployment index after
`multica-migrate-server` has moved the authoritative service plane. This Skill
never edits an immutable bundle. It verifies the external server migration
receipt, fences dispatch, invokes the upstream stage contracts to reissue the
Foundation → Server → Project graph, collects fresh Runtime activation
receipts, and commits the new index only after the complete graph verifies.

This is an exceptional sibling of Runtime migration, not a normal fifth
orchestration stage. The handoff graph remains Foundation → Server → Project.

## Required dependencies

Read `multica-migrate-server`, `multica-orchestrator-link-up`,
`multica-orchestrator-kick-off`, `multica-orchestrator-nail-down`, `multica-login`, and
the installed `multica-cli` Skill before the first operation. Relocate does not
depend on `multica-orchestrator-migrate`; it consumes the same neutral Runtime
activation contracts. Require a digest-valid
`multica-migrate-server.server-migration-receipt.v1` whose
`runtime_state=RUNTIMES_READY`, `final_state` is `RUNTIMES_READY` or
`OBSERVING`, target is authoritative, and source service is stopped.

Use `multica-login` when the target profile is not authenticated. Never copy a
profile, token, cookie, verification code, provider credential, or browser
state. Clear all six proxy variables for every Multica command against a
self-hosted target.

## Central operational runner

Before any lifecycle action, resolve the installed
`multica-orchestrator-cli` package from the selected Agent Skill root. Invoke
Relocate only through:

```text
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py \
  relocate <prepare|readback|capture|plan|fence|receipt|aggregate|commit|verify|status|next> [arguments]
```

An unavailable or incompatible central package is a pre-mutation blocker; install
`multica-orchestrator-cli` rather than looking for a Relocate-local command or
script asset.

## Mandatory raw prompt and report capture

Every direct invocation must create the same private exact prompt/report archive
required by the other `multica-orchestrator-*` Skills.

1. Before reading source or taking another action, run
   `<agent-skill-root>/multica-orchestrator-cli/scripts/prompt_and_report_capture.py start --skill multica-orchestrator-relocate --cwd "$PWD"`
   and supply the complete triggering instruction on standard input.
2. Preserve the returned capture ID. Keep `.prompt-and-report` local, mode 0700,
   excluded from Git, and outside every bundle or receipt.
3. Before every terminal reply, run the matching `finish` command and supply the
   exact final report bytes on standard input.
4. Do not claim completion if either archive operation fails.

The archive is the sole exception to the rule against persisting sensitive
prompt/report content. It never permits disclosure elsewhere.

## Invocation

```text
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py relocate prepare \
  --state-root <absolute-private-state-root> \
  --migration-receipt <server-migration-receipt.json> \
  --target-profile <authenticated-target-profile> \
  --target-inventory <runtime-target-inventory.v1.json> \
  --project-scope <all|explicit|explicitly-empty> \
  --project <optional-repository-identity,subpath> \
  --output-dir <new-private-run-directory>
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py relocate readback \
  --input <relocation-input.json> --control-db <control-authority.sqlite3> \
  --output-dir <new-private-readback-directory>
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py relocate capture \
  --input <relocation-input.json> --live-readback <target-readback.json> \
  --snapshot <new-relocation-preflight.json>
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py relocate plan \
  --input <relocation-input.json> --snapshot <relocation-preflight.json> \
  --plan <new-relocation-plan.json>
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py relocate fence \
  --input <relocation-input.json> --snapshot <relocation-preflight.json> \
  --plan <reviewed-plan.json> --live-readback <fresh-target-readback.json> \
  --authorization <approval-ref>
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py relocate receipt \
  --state-root <absolute-private-state-root> \
  --evidence <project-relocation-evidence.json> \
  --runtime-receipt <runtime-activation-receipt.json> [...] \
  --output <project-relocation-receipt.json>
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py relocate aggregate \
  --input <relocation-input.json> --snapshot <relocation-preflight.json> \
  --plan <reviewed-plan.json> --intent <relocation-intent.json> \
  --foundation-manifest <foundation-bundle/manifest.json> \
  --server-manifest <server-bundle/manifest.json> \
  --project-receipt-dir <complete-project-receipt-directory> \
  --output <relocation-aggregate.json>
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py relocate commit \
  --input <relocation-input.json> --snapshot <relocation-preflight.json> \
  --plan <reviewed-plan.json> --aggregate <relocation-aggregate.json> \
  --live-readback <post-relocation-target-readback.json> \
  --authorization <separate-commit-approval-ref> --output <relocation-record.json>
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py relocate verify \
  --record <relocation-record.json> \
  --live-readback <fresh-target-readback.json>
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py relocate status --input <relocation-input.json>
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py relocate next --input <relocation-input.json>
```

The central `relocate` stage route is the stable runner. Its `readback` mode is
the sole producer of live target readback. Invoke Link Up, Orchestrator, and
Nail Down through their respective central stage-qualified routes under the
relocation intent to reissue their own artifacts. Relocate validates and commits
those outputs but does not synthesize them.

## Stable deployment identity

`server_ref` is a mutable connection location, not the durable Workspace
namespace. `WorkspaceDeploymentIndex.v1` carries an opaque
`deployment_key=sha256:<hex>` that survives server relocation. Workspace and
Project keys include that deployment key, so endpoint changes preserve logical
identity:

```text
WorkspaceKey = sha256(canonical(deployment_key, workspace_ref))
ProjectKey   = sha256(canonical(WorkspaceKey, repository_identity, project_subpath))
```

Relocation resolves the source index from the migration receipt's source
endpoint, verifies the target profile against the private Runtime inventory,
and republishes the same deployment key under the target endpoint selector.
Never generate another deployment key for the same restored database lineage.

## Test-prompt dependency materialization

The canonical `pp-multica-orchestrator-relocate-test` prompt identifies the
completed `multica-migrate-server` invocation by its exact prompt/report
capture ID and supplies one semantic target description per required Runtime
alias. It must not require the caller to name a receipt or inventory file.
Resolve only `.prompt-and-report/<capture-id>.report.md` in the authorized
invocation directory, extract the single emitted receipt path and digest, and
verify the receipt bytes and all migration postconditions. A missing report or
receipt is `SERVER_MIGRATION_RECEIPT_REQUIRED`; multiple paths/digests or an
identity mismatch is `SERVER_MIGRATION_RECEIPT_AMBIGUOUS`. Never choose a
receipt by modification time.

After receipt and active Project inventory validation, materialize a new
mode-0600 `RuntimeTargetInventory.v1` in the relocation run directory from
[`controls/runtime-target-inventory.template.json`](controls/runtime-target-inventory.template.json).
Require exact coverage of the active Projects' required Runtime aliases and
record the receipt and inventory digests in `RelocationInput.v2`. Missing
machine facts produce `RUNTIME_TARGET_CONFIGURATION_REQUIRED` before readback,
fence, reissue, or activation. The generated receipt and inventory paths are
internal `prepare` arguments.

## Lifecycle and ownership

Use these exact states:

```text
MIGRATION_RECEIPT_VERIFIED
  -> GRAPH_CAPTURED
  -> RELOCATION_PLANNED
  -> RELOCATION_FENCED
  -> REISSUE_OR_AGGREGATE_REQUIRED
  -> RELEASES_REACTIVATED
  -> INDEX_COMMITTED
  -> ORCHESTRATOR_RELOCATION_VERIFIED
```

1. `prepare` verifies the migration receipt, resolves the source
   `WorkspaceDeploymentIndex.v1`, validates the target ProfileSession and
   private `RuntimeTargetInventory.v1`, and writes `RelocationInput.v2`.
2. `capture` binds a current target readback, complete source graph, active
   Project inventory, mutation barrier, and exact required Runtime aliases.
3. `plan` binds the input, snapshot, Project set, Runtime set, target endpoint,
   and expected stable deployment identity by digest.
4. `fence` consumes a fresh readback, acquires the deployment lock, and creates
   an `IN_PROGRESS` fence under a separately reviewed approval.
5. Invoke Link Up through
   `python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py link-up ...`
   with the relocation intent to reissue `WorkspaceFoundationRef.v6`; it must
   carry `FoundationReissueSpec.v1` and publish the Foundation stage pointer.
6. Invoke Orchestrator through
   `python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py orchestrator ...`
   with the same intent to reissue `ServerOrchestrationRef.v9`; it must consume
   the new Foundation, carry `ServerReissueSpec.v1`, and publish the Server stage pointer.
7. Invoke Nail Down through
   `python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py nail-down ...`
   once per exact Project to reissue `ProjectBindingRef.v9`,
   `RuntimeTargetPolicy.v3`, `ProjectVerificationSpec.v6`, and
   `ProjectReissueSpec.v1`, then publish `ProjectReleaseCandidate.v6`.
8. Activate each candidate on every required target using the neutral
   `RuntimeActivationReceipt.v1`, `ActivationAggregate.v1`, and
   `ActiveProjectRelease.v1` contracts. This Skill does not depend on the
   Migrate implementation or create Runtime/daemon/repository rows.
9. `aggregate` validates the complete reissued graph and every active release.
10. `commit` requires a fresh readback and separate approval, verifies the
    stage pointers and target deployment index, records the mutation, and leaves
    dispatch blocked for post-commit verification.
11. `verify` consumes another fresh readback and proves
    `ORCHESTRATOR_RELOCATION_VERIFIED / ACTIVE / EXPLICIT_DISPATCH_REQUIRED`.

Detailed command and evidence requirements are in
[`references/relocation-runbook.md`](references/relocation-runbook.md).

## Non-negotiable invariants

- Old bundles, pointers, releases, and receipts remain immutable audit evidence.
- Server migration preserves the exact Workspace and all declared resource
  identities. Identity drift is not relocation and blocks.
- Repository identity, revision, project subpath, portable configuration digest,
  Runtime IDs, daemon IDs, providers, and Project resources remain exact.
- Every current active Project associated with the old Workspace is either in
  the plan or the plan is blocked.
- No pointer is exposed for dispatch while the fence is `IN_PROGRESS` or
  `BLOCKED`.
- A relocation-aware context `prepare` command may cross the fence only when
  its explicit `--relocation-intent-digest` matches the active transaction.
  Environment variables and generic dispatch commands never bypass it.
- A changed context, pointer, bundle, receipt, live identity set, repository
  revision, or Runtime status invalidates the plan.
- Once the migrated target is authoritative, failures are fix-forward. This
  Skill never restarts the retired source service.
- Successful relocation does not authorize deletion of the old service host,
  migration bundle, old state graph, or Runtime-local bundle objects.

## Completion

Success is:

```text
state=ORCHESTRATOR_RELOCATION_VERIFIED
activation_state=ACTIVE
dispatch_state=EXPLICIT_DISPATCH_REQUIRED
```

Relocation restores a verified active state but does not itself create or
dispatch a Work Item.

## Shared state package

This Skill resolves the central `multica-orchestrator-cli` package for the
preserved `multica_state_bundle` namespace. Relocation fences and migration
journals remain Relocate-owned state.
