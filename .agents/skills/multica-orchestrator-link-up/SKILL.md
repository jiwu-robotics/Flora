---
name: multica-orchestrator-link-up
description: Configure and verify the reusable Multica workspace foundation before orchestration resources are provisioned.
---

# Multica Orchestrator Link Up

Configure one explicitly selected Multica workspace foundation directly from an
authenticated CLI profile and current Multica readback. This Skill owns
server/profile/account/workspace identity, canonical labels, Runtime readiness,
and an explicitly selected online Runtime fleet. It never imports workspace
Skills, creates Agents or Squads, associates a Project or repository, or
dispatches work.

Read the installed `multica-cli` and `multica-login` Skills before the first CLI
command. Check `auth status` first. If the requested profile is already
authenticated, never repeat login. Otherwise complete `multica-login`, then
resume Link Up. Never request or expose tokens, cookies, verification codes, API
keys, or custom environment secrets.


## Central operational runner

Before any lifecycle action, resolve the installed
`multica-orchestrator-cli` package from the selected Agent Skill root. Invoke
Link Up only through its stage-qualified runner:

```text
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py \
  link-up <prepare|inspect|plan|apply|verify> [arguments]
```

An unavailable or incompatible central package is a pre-mutation blocker; install
`multica-orchestrator-cli` rather than looking for a Link Up-local command or
script asset.

## Invocation

```text
/multica-orchestrator-link-up mode=prepare \
  profile=<multica-profile> workspace=<optional-id-name-or-slug> \
  runtime=<alias=provider> state_root=<optional-private-state-root> \
  status_attestation=<optional-typed-json>
/multica-orchestrator-link-up mode=inspect \
  server_kind=<cloud|self-hosted> server_ref=<server-url> profile=<profile> \
  account_ref=<account-ref> workspace_ref=<workspace-id> \
  runtime=<alias=runtime-id> runtime=<alias=runtime-id> \
  status_attestation=<optional-typed-json> state_dir=<new-private-directory> \
  input=<state-dir/foundation-input.json>
/multica-orchestrator-link-up mode=plan input=<foundation-input.json> \
  readback_snapshot=<state-dir/snapshot.json> plan=<new-plan.json>
/multica-orchestrator-link-up mode=apply --apply input=<foundation-input.json> \
  readback_snapshot=<state-dir/snapshot.json> plan=<reviewed-plan.json> \
  --plan-digest <exact-plan-digest> --operation <exact-operation-id> \
  --authorization-ref <prompt-run-authorization-ref>
/multica-orchestrator-link-up mode=verify input=<foundation-input.json> \
  readback_snapshot=<state-dir/snapshot.json> \
  --state-root <absolute-private-state-root/bundle-store> \
  --pointer-state-root <absolute-private-state-root> \
  --output-bundle <optional-new-export-directory>
```

The central `link-up` stage route exposes only `prepare`, `inspect`, `plan`,
`apply`, and `verify`. `prepare` resolves server, account, default Workspace,
Runtime and daemon identity from the named CLI profile and writes input, snapshot,
and a
profile-bound `FoundationResolutionManifest.v2`. It does not read an Operator
Context. Other mode arguments map directly to each helper's `--help`; typed
input and snapshot define desired and observed state.
`ohmypi` is the sole accepted legacy spelling for the OMP provider. `prepare`
canonicalizes `alias=ohmypi` to `alias=omp` before daemon, launcher, and Runtime
readback checks; published Foundation records always use `omp`.


Reject `repository`, `project`, `local_path`, `checkout`, and Work Item arguments
with `PROJECT_SCOPE_NOT_ALLOWED`.

- `inspect` and `plan` are read-only.
- `prepare` performs no login when `auth status` succeeds. It may start a stopped
  daemon or restart an idle daemon only when a requested local provider Runtime
  is not registered. It must skip daemon mutation when the exact provider and
  daemon Runtime are already online.
- One explicit Link Up prompt invocation is the bounded Human authorization for
  the stage. It authorizes only `workspace-create`, `label-create`,
  `runtime-profile-create`, and `runtime-daemon-start` operations from the
  current digest-bound plan. Pass one prompt-run authorization ref, the exact
  plan digest, and one operation id to each `apply`; re-capture and re-plan
  after every successful operation. Ambiguous identities, stale plans,
  unsupported actions, and out-of-contract mutations stop immediately.
- Final `verify` always receives the input-bound pair
  `<state-root>/bundle-store` and `<pointer-state-root>`. It atomically publishes
  the Foundation CAS bundle, workspace pointer, and
  `WorkspaceDeploymentIndex.v1`.

## Scope

This Skill may:

1. verify Multica CLI compatibility, server, profile, account, Workspace, and permissions;
2. discover or explicitly create the selected Workspace;
3. create missing canonical `bug` (`#ef4444`) and `enhancement` (`#3b82f6`) labels;
4. report the five canonical Issue Status definitions as a final Human confirmation reminder;
5. select every Human-approved online Runtime needed by the reusable orchestration fleet;
6. create explicitly requested supported Runtime profiles;
7. register a missing requested local provider by starting a stopped daemon or
   restarting an idle daemon; and
8. publish a restricted portable bundle containing `WorkspaceFoundationRef.v6`.

This Skill must not import or overwrite workspace Skills; create, update, archive,
delete, or bind Agents or Squads; create Projects or repository resources; inspect
or modify a target product repository; or create Issues, runs, assignments,
mentions, branches, checkouts, commits, or pull requests.

## Canonical workspace resources

Labels:

| Name | Color |
| --- | --- |
| `bug` | `#ef4444` |
| `enhancement` | `#3b82f6` |

Issue Status definitions:

| Display name | Key | Category |
| --- | --- | --- |
| Pending Triage | `needs_triage` | `backlog` |
| Needs Information | `needs_information` | `blocked` |
| Ready for Agent | `ready_for_agent` | `backlog` |
| Ready for Human | `ready_for_human` | `todo` |
| Won't Fix | `wontfix` | `cancelled` |

Do not infer status-administration support from a version number. When a current
Human attestation is supplied, validate it against **Multica Web → Workspace
Settings → Issue Statuses** and record `status-contract-attestation.v1`. When it
is absent or conflicts, Foundation verification continues with
`status_contract.state=HUMAN_CONFIRMATION_REQUIRED` and the final report must
remind the Human to confirm the five definitions. Never call a private API or
mutate a real Issue as a probe.

## Process

Start with
`python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py link-up prepare --profile <name> [--workspace <selector>]`
[--runtime <alias=provider>] [--status-attestation <path>]`. The default Runtime
request is `primary-runtime=omp`. Review its request, resolved input, snapshot,
Runtime action, and resolution manifest before planning. Live Workspace,
Runtime, daemon, member, and label refs come only from current CLI readback.

1. Run `auth status` for the exact profile. If authenticated, continue without
   login. Otherwise use `multica-login`, verify CLI completion and Workspace
   readback, then resume.
2. Read the profile's server and default Workspace from `config show`, then
   resolve the current account, Workspace, member, label, Runtime and daemon
   identities from CLI readback. Clear the six proxy variables for every
   `multica` process and never change `NO_PROXY`.
3. For every requested `alias=provider`, require an online Runtime on the local
   daemon. If it already exists, record `skipped-already-ready`. If it is
   missing, verify the launcher exists and the daemon has no active tasks, then
   start or restart the daemon and require post-registration Runtime readback.
   Never create a duplicate row, restart a busy daemon, or treat an online
   Runtime on a different daemon as the requested local Runtime.
4. Require the central `link-up prepare` capability evidence to report
   `cli-capabilities.v2`, `compatible=true`, and every
   `native_squad_routing` surface true.
5. Capture auth, config, Workspace/member, label, Runtime-fleet, and
   orchestration-capability evidence; keep Runtime and daemon identities
   separate; and anchor the complete Runtime set again after capture. A missing
   status attestation produces a reminder, not a blocker.
6. Produce a deterministic plan from the captured typed input and snapshot.
   Apply exactly one prompt-authorized operation at a time with its exact
   `plan_digest` and prompt-run `authorization_ref`; then re-run `prepare`,
   inspect, and plan. Never patch old readback JSON or pause for a second Human
   authorization.
7. When the plan has no operations or blockers, run `verify` with
   `--state-root <private-state-root>/bundle-store` and
   `--pointer-state-root <private-state-root>`. Verification publishes the
   immutable bundle, workspace-scoped Foundation pointer, and deployment-index
   entry. Its manifest digest, not an operator path, is the downstream identity.
   Live IDs and account refs remain restricted.

`skill_sync=latest` is optional tooling bootstrap, not workspace state. It is
allowed only in approved `apply` for the project-local locked `multica-cli`
package at an explicit tooling root. Run the central Link Up provenance helper
at
`<agent-skill-root>/multica-orchestrator-cli/cli/multica_orchestrator_cli/stages/link_up/check_skill_provenance.py`
before and after the refresh, reload the coding agent, and re-read the installed Skill.
Never install globally or refresh unrelated Skills.

## Completion

Success is:

```text
state=WORKSPACE_FOUNDATION_VERIFIED
dispatch_state=BLOCKED_ORCHESTRATOR_LAYER
```

Unresolved identity, Workspace, label, Runtime, permission, capability, or
readback items are blockers. Issue Status confirmation is never a Foundation
blocker; report `HUMAN_STATUS_CONFIRMATION_REQUIRED` until Human attestation is
available. Continue with `multica-orchestrator-kick-off`, which consumes this handoff
through `WorkspaceDeploymentIndex.v1` and owns orchestration policy, workspace
Skills, Agents, and Squads.

## Shared state package

This Skill resolves the central `multica-orchestrator-cli` package for the
preserved `multica_state_bundle` import namespace. If that namespace is absent
or incompatible, the central runner fails closed before lifecycle mutation and
names `multica-orchestrator-cli` as the corrective installation.
