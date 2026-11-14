# Multica orchestrator relocation runbook

Use only after `multica-migrate-server` emits a valid
`ServerMigrationReceipt.v1`. Every run/evidence directory is private mode 0700;
files are mode 0600. Never synthesize evidence JSON or identity/count values.

Relocate is a sibling of `multica-orchestrator-migrate`. It depends on Link Up,
Orchestrator, Nail Down, the external server migration receipt, and the neutral
activation contracts; it does not invoke or depend on Migrate.

## 1. Prepare

```bash
python3 '<skill>/cli/run.py' prepare \
  --state-root '<absolute-private-state-root>' \
  --migration-receipt '<absolute-server-migration-receipt.json>' \
  --target-profile '<authenticated-target-profile>' \
  --target-inventory '<absolute-runtime-target-inventory.v1.json>' \
  --project-scope all \
  --output-dir '<new-private-run-directory>'
```

`prepare` resolves the source `WorkspaceDeploymentIndex.v1` from the receipt's
source endpoint selector. It preserves the deployment key and stable
Workspace/Project keys, verifies the target ProfileSession, and binds the exact
mode-0600 `RuntimeTargetInventory.v1` bytes.

At any point, inspect durable state and the exact next command:

```bash
python3 '<skill>/cli/run.py' status \
  --input '<run>/relocation-input.json'
```

`next` is an alias for `status`. Pass explicit `--snapshot`, `--plan`,
`--aggregate`, or `--record` only when those files are outside the run directory.

## 2. Capture authoritative target readback

Run the packaged producer against the target-authenticated profile and the
operator-local control-authority SQLite database:

```bash
python3 '<skill>/cli/capture_target_readback.py' \
  --input '<run>/relocation-input.json' \
  --control-db '<absolute-control-authority.sqlite3>' \
  --output-dir '<new-private-readback-directory>'

python3 '<skill>/cli/run.py' capture \
  --input '<run>/relocation-input.json' \
  --live-readback '<readback>/target-readback.json' \
  --snapshot '<run>/relocation-preflight.json'
```

The producer invokes real Multica list commands with all six proxy variables
removed, compares Workspace/resource identities to the migration receipt,
resolves every Runtime alias from the private inventory, queries live work from
the control authority, binds raw evidence bytes, and captures the mutation
barrier. Drift, unready Runtime state, active work, missing evidence, or a
barrier mismatch blocks.

## 3. Plan and fence

```bash
python3 '<skill>/cli/run.py' plan \
  --input '<run>/relocation-input.json' \
  --snapshot '<run>/relocation-preflight.json' \
  --plan '<run>/relocation-plan.json'
```

Review the exact plan digest and operations. Capture a newer target readback,
then fence with a separate approval:

```bash
python3 '<skill>/cli/run.py' fence \
  --input '<run>/relocation-input.json' \
  --snapshot '<run>/relocation-preflight.json' \
  --plan '<run>/relocation-plan.json' \
  --live-readback '<fence-readback>/target-readback.json' \
  --authorization 'approval:<fence-approval>'
```

The fence is compare-and-swap and idempotent only for the same transaction.
Every mutation after capture must hold the deployment lock and write
`mutation-journal.v2` with the relocation intent. Unrelated mutations invalidate
the transaction.

## 4. Reissue the complete graph through owning stages

While fenced, pass the exact relocation intent to each stage:

1. Link Up reissues `WorkspaceFoundationRef.v6` and
   `FoundationReissueSpec.v1`, then publishes the Foundation pointer and target
   deployment selector.
2. Orchestrator consumes that Foundation and reissues
   `ServerOrchestrationRef.v9`, `ServerVerificationSpec.v3`, and
   `ServerReissueSpec.v1`, then publishes the Server pointer.
3. Nail Down consumes that Server once per captured Project and reissues
   `ProjectBindingRef.v9`, `RuntimeTargetPolicy.v3`,
   `ProjectVerificationSpec.v6`, `ProjectReissueSpec.v1`, and
   `ProjectReleaseCandidate.v6`.
4. Activate every candidate on all required targets using
   `RuntimeActivationReceipt.v1`, `ActivationAggregate.v1`, and
   `ActiveProjectRelease.v1`. Relocate validates these neutral contracts; it
   does not depend on a particular activation implementation.
5. Produce one Project relocation receipt for every Project.

Observed drift blocks. Do not patch snapshots, receipts, manifests, digests, or
the deployment index. Remediate through the owning stage under separate
authorization, then recapture and replan.

## 5. Emit Project receipts and aggregate

```bash
python3 '<skill>/cli/run.py' receipt \
  --evidence '<private-project-evidence.json>' \
  --state-root '<absolute-private-state-root>' \
  --runtime-receipt '<runtime-activation-receipt.v1.json>' \
  --output '<project-receipt-dir>/<project-key>.json'

python3 '<skill>/cli/run.py' aggregate \
  --input '<run>/relocation-input.json' \
  --snapshot '<run>/relocation-preflight.json' \
  --plan '<run>/relocation-plan.json' \
  --intent '<state-root>/relocations/objects/<intent-digest>.json' \
  --foundation-manifest '<foundation-bundle>/manifest.json' \
  --server-manifest '<server-bundle>/manifest.json' \
  --project-receipt-dir '<project-receipt-dir>' \
  --output '<run>/relocation-aggregate.json'
```

`aggregate` computes manifest digests from exact bytes, discovers the complete
Project receipt set, validates Runtime receipt closure and active-release
lineage, and rejects duplicates, extras, or missing Projects.

## 6. Commit and verify

Capture another target readback after reissue. Commit requires an approval
different from the fence approval:

```bash
python3 '<skill>/cli/run.py' commit \
  --input '<run>/relocation-input.json' \
  --snapshot '<run>/relocation-preflight.json' \
  --plan '<run>/relocation-plan.json' \
  --aggregate '<run>/relocation-aggregate.json' \
  --live-readback '<commit-readback>/target-readback.json' \
  --authorization 'approval:<cutover-approval>' \
  --output '<run>/relocation-record.json'
```

Commit revalidates the reissued bundles, Project candidates, Runtime receipts,
active releases, stage pointers, target `WorkspaceDeploymentIndex.v1`,
quiescence, and mutation barrier. It records `RelocationRecord.v3` and the actual
commit time, then leaves dispatch blocked for verification.

Capture a fresh readback after commit:

```bash
python3 '<skill>/cli/capture_target_readback.py' \
  --input '<run>/relocation-input.json' \
  --control-db '<absolute-control-authority.sqlite3>' \
  --output-dir '<new-post-commit-readback-directory>'

python3 '<skill>/cli/run.py' verify \
  --record '<run>/relocation-record.json' \
  --live-readback '<new-post-commit-readback-directory>/target-readback.json'
```

Only successful verification changes the fence to `COMMITTED` and returns
`ORCHESTRATOR_RELOCATION_VERIFIED / ACTIVE / EXPLICIT_DISPATCH_REQUIRED`.
Relocate has no dispatch command. Later Work Item starts use the normal
per-dispatch admission path and separate Human authorization.
