---
name: multica-orchestrator-migrate
description: "Activate an already ACTIVE immutable Project release on explicitly selected optional Runtime hosts over pinned SSH. It never performs first activation or replaces the primary Runtime."
---

# Multica Orchestrator Migrate

Adapt an immutable ACTIVE Project release to selected additional Runtime hosts. This Skill changes only target-local state and target Project `local_directory` resources. It never creates first ACTIVE state, changes the primary Runtime binding, creates test Issues, or dispatches Agents or Squads.

## Central operational runner

Before any lifecycle action, resolve the installed
`multica-orchestrator-cli` package from the selected Agent Skill root. Invoke
Migrate only through:

```text
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py \
  migrate <prepare|capture|plan|apply|remote|aggregate|activate> [arguments]
```

An unavailable or incompatible central package is a pre-mutation blocker; install
`multica-orchestrator-cli` rather than looking for a Migrate-local command or
script asset.

## Mandatory raw prompt and report capture

This section takes precedence over every lower-level instruction to redact,
omit, or avoid saving invocation or report content. Every direct invocation
must create an exact local record before reading any source or taking another
action.

1. Resolve
   `<agent-skill-root>/multica-orchestrator-cli/scripts/prompt_and_report_capture.py`.
   Before proceeding, run its `start` command with this Skill's frontmatter
   `name` and `--cwd "$PWD"`. Supply the complete triggering user instruction
   to standard input as exact bytes, never as a command-line argument.
2. Preserve the returned `capture_id`. The helper writes
   `./.prompt-and-report/<capture_id>.prompt.md`; it creates the directory with
   mode `0700`, the file with mode `0600`, and adds `/.prompt-and-report/` to
   local Git `info/exclude` when the invocation directory is a Git worktree.
3. Do not redact, summarize, normalize, reformat, replace, or omit any prompt
   or report content in this archive. Keep the archive local: never commit it,
   include it in a bundle, copy it into a repository artifact, or send it to
   Multica, GitHub, chat, Issue, PR, or ordinary logs.
4. On every terminal path—`complete`, `partial`, `blocked`, error, or
   interruption—before replying to the user, run the helper's `finish` command
   with the same `capture_id` and `--cwd "$PWD"`. Supply the exact final report
   bytes on standard input. It writes the paired
   `./.prompt-and-report/<capture_id>.report.md` without overwriting any record.
   For private review,
   `<agent-skill-root>/multica-orchestrator-cli/scripts/render_prompt_and_report.py`
   may render the immutable pair; the raw files remain authoritative.
5. Do not claim completion if either archive operation fails.

This private raw archive is the sole exception to the Skill's requirements not
to persist sensitive information. It does not permit exposing sensitive
information outside the archive or placing it in generated deliverables.

## Prerequisites

- Read Link Up, Orchestrator, Nail Down, `multica-login`, and `multica-cli`; Nail Down must already have published and read back the primary ACTIVE release and primary Runtime binding.
- The coordinator has the ACTIVE Project bundle/candidate closure and the primary receipt/aggregate under its private release root.
- Targets are a non-empty explicit subset of `RuntimeTargetPolicy.v4.optional_runtimes`; the required primary alias is always rejected.
- Every target is reachable by a named SSH configuration host with strict host-key verification.
- Every target has its own authenticated Multica profile for the same `server_ref` and `workspace_ref`.
- Every target runs the declared local daemon, owns the selected online Runtime record, and reports the exact `local-worktree-v1` capability revision.
- The Runtime-owned base checkout has the canonical repository origin. Work Item commits are resolved later by provider-owned branches.
- All paths in the migration input are absolute machine-local paths. Do not put credentials in any input, bundle, receipt, or log.

## Contracts

- Input: `contracts/migration-input.schema.json`
- Read-only capture: `contracts/target-preflight.schema.json`
- Plan: `contracts/migration-plan.schema.json`
- Per-operation receipt: `contracts/migration-operation-receipt.schema.json`
- Per-target activation receipt: `contracts/runtime-activation-receipt.schema.json`
- Aggregate receipt: `contracts/activation-aggregate.schema.json`
- Active release: `contracts/active-project-release.schema.json`

The current `ProjectReleaseCandidate.v8` is resolved by repository identity and
project subpath through `WorkspaceDeploymentIndex.v1` and the project-scoped
candidate pointer. Its Runtime capability, Dispatch contract, and native Squad
dispatch digests must match the Project bundle and every `RuntimeActivationReceipt.v2`.
The Project bundle is addressed only by `sha256:<hex>` manifest digest; its
parent closure must be Project → Server → Foundation. Target-local profiles,
accounts, SSH hosts, repository roots, state roots, and resource refs come from
`RuntimeTargetInventory.v1` and stay outside shared bundles.

## Lifecycle

Use the central stage-qualified runner:

```bash
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py \
  migrate <prepare|capture|plan|apply|remote|aggregate|activate> ...
```

### 0. Resolve the current release

```bash
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py migrate prepare \
  --profile <coordinator-profile> \
  [--workspace <id-name-or-slug>] \
  --state-root <private-operator-state-root> \
  --target-inventory <runtime-target-inventory.v1.json> \
  --repository-root <root> \
  --project-subpath <subpath> \
  [--target <runtime-alias> ...]
```

`prepare` opens the coordinator ProfileSession, resolves the deployment/current candidate and requires the immutable current `ActiveProjectRelease.v2` plus primary Runtime binding to agree with it. It accepts a non-empty explicit subset of optional aliases (default: all optionals), rejects the required primary alias and writes `MigrationInput.v5` / `ResolutionManifest.v2`. Input binds the primary alias, source ACTIVE digest, source candidate/bundle digests, and exact target aliases.

### Test-prompt inventory materialization

The canonical prompt accepts one semantic target description per selected optional alias: SSH config host, consumer profile, absolute target state root, and absolute repository parent. It must not infer SSH hosts, profiles, absolute paths, or reuse inventory bytes with a different digest. Missing target facts produce `RUNTIME_TARGET_CONFIGURATION_REQUIRED` before SSH, transfer, or activation.

### 1. Capture every target read-only

```bash
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py migrate capture \
  --input <migration-input.json> \
  --snapshot <target-preflight.json>
```

Capture uses `ssh -o BatchMode=yes -o StrictHostKeyChecking=yes <ssh_config_host> ...`. It reads Multica version/auth/config/workspace/Runtime/daemon/Project-resource state plus repository origin. A target is not eligible merely because its Runtime appears in the shared workspace list: the local daemon must also be running, identifiers must agree, and the Runtime must report the candidate-bound `local-worktree-v1` capability revision.

### 2. Produce one deterministic plan

```bash
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py migrate plan \
  --input <migration-input.json> \
  --snapshot <target-preflight.json> \
  --plan <migration-plan.json>
```

Review the exact digest. Plans are bound to the migration input, release candidate, Project bundle, bundle closure, preflight snapshot, repository identity, SSH host, and target-local paths.

### 3. Apply one explicitly authorized operation

```bash
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py migrate apply \
  --apply \
  --input <migration-input.json> \
  --snapshot <target-preflight.json> \
  --plan <migration-plan.json> \
  --plan-digest sha256:<hex> \
  --operation <target-alias>/<operation> \
  --authorization-ref <human-authorization-ref> \
  --work-dir <private-local-directory> \
  --receipt <operation-receipt.json>
```

Operations are idempotent only when their exact postcondition already exists. Any conflicting repository origin, Runtime identity, bundle digest, Project resource, or changed plan precondition fails closed. Re-capture and re-plan after a legitimate state change.

`MigrationInput.source` binds both `operator_state_root` and the CAS
`state_root`; the latter must equal `<operator_state_root>/bundle-store`.
Every operation and activation uses the deployment lock under the bound
operator root and records a mutation-journal start and completion before
releasing it. A caller cannot substitute an unrelated unfenced state tree.

Operation order per target:

1. `install-receiver`
2. `transfer-bundle-pack`
3. `import-bundle-pack`
4. `checkout-repository`
5. `bind-local-directory`
6. `verify-activation`

The receiver and canonical bundle helpers are copied as reviewed files. The pack contains the exact Project/Server/Foundation closure. Repository checkout creates or reuses a Runtime-owned base checkout identified only by origin; `bind-local-directory` adds or updates only the declared Project resource on the declared local daemon, always with `execution_mode=worktree`; conflicting resource identity fails closed.

### 4. Verify targets and collect receipts

`verify-activation` writes a receipt on the target, then copies it to the coordinator receipt path. It re-reads:

- server/workspace/profile/account session identity;
- Runtime and daemon online/ownership evidence whose exact `local-worktree-v1`
  capability revision equals `RuntimeTargetPolicy.v4.required_capability_revision`;
- full immutable Foundation → Server → Project bundle closure and verification specs;
- repository origin and project subpath;
- Project GitHub resource and target-local `local_directory(execution_mode=worktree)` resource;
- selected Runtime command profile.

Project configuration and exact source/target commits are verified at explicit
Work Item dispatch after the provider-owned branch resolves; activation never
binds a repository snapshot.

The receipt records digests and opaque refs, never credentials.

### 5. Aggregate and activate

```bash
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py migrate aggregate \
  --input <migration-input.json> \
  --receipt <runtime-a.json> --receipt <runtime-b.json> \
  --output <activation-aggregate.json>

python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py migrate activate \
  --apply \
  --input <migration-input.json> \
  --aggregate <activation-aggregate.json> \
  --authorization-ref <human-activation-ref> \
  --output <active-project-release.json>
```

`aggregate` emits `ActivationAggregate.v2` for exactly the selected optional targets and binds the primary alias plus base ACTIVE digest. `activate` re-reads that source before and after all target readbacks. Each additional target receives byte-identical `ActiveProjectRelease.v2` bytes and its own exact Runtime binding. Existing matching target state is `ALREADY_ACTIVE`; any different target release, fence, or binding is a conflict. Migrate never writes coordinator `active.json`, creates a Project generation, replaces the primary Runtime binding, or mutates the primary `local_directory`.

## Failure and recovery

- Never continue from an invalid or stale plan.
- Never silently change SSH transport, profile, workspace, Runtime, repository root, or bundle digest.
- A failed additional target leaves the primary ACTIVE source and previously committed exact targets intact; re-capture only that target and generate a new plan.
- Re-running an exact additional-target activation is idempotent.
- No command in this Skill dispatches work. Explicit dispatch remains a later operator action after ACTIVE readback.

## Proxy and remote execution policy

Clear `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `http_proxy`, `https_proxy`, and `all_proxy` for every Multica command on self-hosted servers. Do not clear them for Git or SSH. Remote command shapes are fixed by the implementation; migration input values are shell-quoted and cannot supply arbitrary command fragments.

## Shared state package

This Skill resolves and transfers the reviewed central
`multica-orchestrator-cli` closure, which supplies the preserved
`multica_state_bundle` namespace. Runtime receivers checksum-verify that
central closure before importing shared lifecycle state.
