---
name: multica-deploy-customized-agents
description: Import canonical Skills and deploy the declared customized Multica Agents and Squads in an already configured workspace.
---

# Multica Deploy Customized Agents

Provision the reusable agent layer of a specified Multica workspace. This Skill
imports the real Skill packages, then creates or reconciles the canonical
non-system Agents and any Squads declared in
[WORKSPACE-MANIFEST.md](WORKSPACE-MANIFEST.md).

`multica-orchestrator-link-up` owns server/profile identity checks, workspace
selection or creation, labels, custom Issue Status definitions, runtime
registration, and daemon startup. This Skill consumes its verified portable
Foundation bundle containing `WorkspaceFoundationRef.v5` and never configures those resources itself.

This Skill is explicit-invocation only and never starts implementation work.
Read the official `multica-cli` Skill before running any command. Its identity,
workspace-selection, secret-handling, recording-only, and failure rules remain
authoritative. Never call private Multica APIs to fill a CLI gap.

## Mandatory raw prompt and report capture

This section takes precedence over every lower-level instruction to redact,
omit, or avoid saving invocation or report content. Every direct invocation
must create an exact local record before reading any source or taking another
action.

1. Resolve this installed Skill package's `scripts/prompt_and_report_capture.py`.
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
5. Do not claim the invocation completed if either archive operation fails;
   report the capture failure directly.

This private raw archive is the sole exception to the Skill's requirements not
to persist sensitive information. It does not permit exposing sensitive
information outside the archive or placing it in generated deliverables.

## Invocation contract

```text
/multica-deploy-customized-agents mode=inspect \
  workspace_handoff_bundle=<local-imported-bundle-directory> \
  manifest_digest=<sha256-digest>
/multica-deploy-customized-agents mode=plan \
  workspace_handoff_bundle=<local-imported-bundle-directory> \
  manifest_digest=<sha256-digest>
/multica-deploy-customized-agents mode=apply \
  workspace_handoff_bundle=<local-imported-bundle-directory> \
  manifest_digest=<sha256-digest> \
  authorization=<approved-skill-agent-and-squad-writes>
```

Resolve and validate the imported Foundation bundle and independently received
manifest digest before a write. `inspect` may report unresolved evidence;
`plan` and `apply` require the exact server, profile, authenticated account,
workspace UUID, verified status contract, and online Runtime from that bundle.
This Skill must not create, update, or start a Runtime to make the evidence
appear.

For self-hosted Multica, clear `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`,
`http_proxy`, `https_proxy`, and `all_proxy` for every `multica` process. For
Multica Cloud, retain the inherited proxy environment. Do not change
`NO_PROXY`.

If authentication is missing, direct the operator to authenticate locally with
`multica login` or `multica setup`; never request or accept a token in chat,
a repository, or command arguments. This Skill neither logs in nor starts a
daemon. `multica-orchestrator-link-up` handles those configuration actions.

## Modes and authorization

- `inspect`: read-only inventory of required Skills, Agents, Squads, and their
  bindings.
- `plan`: read-only inventory plus an ordered, exact provisioning plan.
- `apply`: perform only approved imports, Agent changes, and Squad changes, then
  read them back.

A discovery request is not authorization to import a Skill, create an Agent,
change an Agent binding or visibility, or create or update a Squad. Creation of
a missing resource is allowed only in `apply`. Updating, replacing, deleting,
archiving, changing visibility, or overwriting an imported Skill requires a
separately stated diff and approval.

## Scope

This Skill can:

- import and verify the real Skill packages required by the manifest;
- create or reconcile every non-system Agent declared by the manifest;
- bind verified workspace Skill UUIDs to those Agents; and
- create or reconcile manifest-declared Squads and their verified Agent
  memberships.

The current manifest declares canonical Agents but no canonical Squad. Report
that fact; do not invent a Squad from a collection of Agents. A future manifest
entry is the only authority to provision one.

This Skill does not configure profiles, authenticate users, select or create a
workspace, create labels, administer Issue Status definitions, register or
start runtimes, create projects or repository resources, write repository
configuration, create Issues/tasks/runs, or configure environment secrets or
MCP.

## Safety and idempotency

1. Pass `--profile <profile>` and `--workspace-id <workspace-uuid>` on every
   workspace-scoped command. Verify the returned workspace UUID after every
   import, create, or update.
2. Read before writing. Match Skills, Agents, and Squads by exact name; compare
   relevant fields before proposing a change. Never create a duplicate to avoid
   resolving a conflict.
3. An Agent or Squad mention, assignment, Issue change, or start entry point is
   forbidden during provisioning. Binding a Skill must not enqueue work.
4. Credentials, cookies, PATs, custom environment values, and MCP secrets never
   enter the manifest or command line.
5. A partial result is partial. Report created, reconciled, unchanged, skipped,
   conflicted, blocked, failed, and manual resources separately.

## Procedure

### 1. Verify target and provisioning prerequisites

Require `multica` v0.4.26 or newer and run the supported reads:

```bash
multica version
multica --profile <profile> auth status
multica --profile <profile> config show
multica --profile <profile> workspace list --output json
multica --profile <profile> --workspace-id <workspace-uuid> \
  workspace get <workspace-uuid> --output json
multica --profile <profile> --workspace-id <workspace-uuid> \
  runtime list --output json
```

Confirm the server, authenticated account, selected workspace name and UUID.
Never silently switch a server, identity, profile, or workspace. Resolve the
manifest's `codex_runtime` only to an already verified `online` runtime UUID.
If none exists, stop Agent provisioning and direct the operator to
`multica-orchestrator-link-up`; do not start a daemon or bind an offline runtime.

### 2. Inventory agent-layer resources

Read all supported resources before planning:

```bash
multica --profile <profile> --workspace-id <workspace-uuid> \
  skill list --output json
multica --profile <profile> --workspace-id <workspace-uuid> \
  agent list --output json
multica --profile <profile> --workspace-id <workspace-uuid> \
  squad list --output json
```

Build a reconciliation table with desired state, live state, action, side
effect, and evidence. Same-name resources with incompatible fields are
conflicts, not missing resources.

### 3. Resolve and import required Skills

Collect the unique Skill names from the Agent and Squad manifest. For each name:

1. reuse an exact-name workspace Skill only after `skill get` confirms its
   content and support files;
2. otherwise resolve the real source from the target project's active
   project-local `.agents/skills/<name>/` or `.claude/skills/<name>/` directory,
   or from its `skills-lock.json` origin;
3. import a network source with `skill import --url`, or package the complete
   local Skill directory with `SKILL.md` at the archive root and use
   `skill import --file`; and
4. read the imported Skill back and retain its workspace-specific UUID.

The default conflict strategy is `fail`. `skill import --on-conflict overwrite`
requires explicit approval after comparing existing and desired contents or
origins. Never paste a Skill body into Agent instructions as a substitute for
importing it. Import support files, preserve explicit-invocation semantics, and
remove temporary archives after successful verification.

### 4. Reconcile canonical Agents

Read [WORKSPACE-MANIFEST.md](WORKSPACE-MANIFEST.md) for names, descriptions,
instructions, visibility, concurrency, runtime aliases, and required Skills.

- `Mika` is server-managed: verify exactly one active system Agent exists. If it
  is absent, stop and direct the workspace administrator to complete server
  onboarding; never fabricate a replacement.
- For every non-system Agent, match by exact name. No match may be created in
  approved `apply`; one match is compared; multiple matches are a conflict.
- Resolve runtime aliases to verified online UUIDs and Skill names to verified
  Skill UUIDs before Agent creation.
- Public Agents use `--permission-mode public_to` and
  `--public-to-workspace`; private Agents use `--permission-mode private`.
- Preserve `max_concurrent_tasks: 3`; leave the model empty unless the user
  explicitly selects a runtime-supported model.

```bash
multica --profile <profile> --workspace-id <workspace-uuid> agent create \
  --name <name> --description <description> --instructions <short-wrapper> \
  --runtime-id <verified-runtime-uuid> \
  --permission-mode <private-or-public_to> [--public-to-workspace] \
  --max-concurrent-tasks 3 --output json
multica --profile <profile> --workspace-id <workspace-uuid> agent skills add \
  <agent-uuid> --skill-ids <comma-separated-verified-skill-uuids> --output json
```

Detailed workflows remain in bound Skills. Never copy source-Agent environment
values, custom arguments, MCP secrets, or task history.

### 5. Reconcile manifest-declared Squads

For each explicit Squad entry, match by exact name, resolve every member to a
verified Agent UUID, compare membership and instructions, then propose the
narrowest create or update supported by the installed CLI. Read the Squad back
after every approved write. Do not infer membership from Agent names or create
an empty Squad. If the CLI lacks a required Squad operation, report the exact
manual procedure instead of using a private API.

At present, the canonical manifest has no Squad entries, so this step records
`none declared` without a write.

### 6. Verify and report

After all reachable writes, read back:

```bash
multica --profile <profile> --workspace-id <workspace-uuid> skill list --output json
multica --profile <profile> --workspace-id <workspace-uuid> agent list --output json
multica --profile <profile> --workspace-id <workspace-uuid> agent get <agent-uuid> --output json
multica --profile <profile> --workspace-id <workspace-uuid> \
  agent skills list <agent-uuid> --output json
multica --profile <profile> --workspace-id <workspace-uuid> squad list --output json
```

Verify workspace UUID, unique Agent names, selected online runtime, permission
mode, workspace target, concurrency, wrapper, enabled Skills, and every
manifest-declared Squad membership. Return an agent-layer provisioning handoff:
server, account, profile, workspace UUID, runtime mapping, Skill and Agent
UUIDs, Squad state, Foundation digest, and all unresolved items. Never include
secrets or report a partial result as complete.
