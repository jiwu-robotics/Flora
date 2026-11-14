---
name: multica-orchestrator-kick-off
description: Configure and verify project-independent Multica workspace Skills, Agents, Squads, and reusable orchestration contracts from a verified workspace foundation.
---

# Multica Orchestrator Kick Off

Configure the reusable orchestration layer in one explicitly selected Multica
workspace. This Skill consumes a verified portable Foundation bundle containing
`WorkspaceFoundationRef.v6` (while accepting v5 during a clean upgrade), resolves it by manifest digest from the local
content-addressed bundle store, and owns only workspace Skill, Agent, Squad, and
per-role Runtime placement desired state. It never creates or repairs the
workspace foundation, associates a repository or Project, or dispatches work.

## Required dependencies

Read `multica-orchestrator-link-up` and the installed `multica-cli` Skill before
the first operation. A current restricted Foundation handoff bundle and its
independently received manifest digest are mandatory. Use `multica-login` when
authentication is absent. Never request or expose tokens, cookies, verification
codes, API keys, or custom environment secrets.

Agents, Squads, and Skills are workspace-scoped resources. Runtime lifecycle,
canonical labels, and Issue Status definitions belong exclusively to
`multica-orchestrator-link-up`.

## Central operational runner

Before any lifecycle action, resolve the installed
`multica-orchestrator-cli` package from the selected Agent Skill root. Invoke
the Server Orchestrator stage only through:

```text
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py \
  orchestrator <prepare|inspect|plan|apply|verify|emit> [arguments]
```

An unavailable or incompatible central package is a pre-mutation blocker; install
`multica-orchestrator-cli` rather than looking for a Server Orchestrator-local
command or script asset.

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
   For review, use the central
   `<agent-skill-root>/multica-orchestrator-cli/scripts/render_prompt_and_report.py`
   helper to render the immutable pair as one private two-section document; the raw files
   remain authoritative.
5. Do not claim the invocation completed if either archive operation fails;
   report the capture failure directly.

This private raw archive is the sole exception to the Skill's requirements not
to persist sensitive information. It does not permit exposing sensitive
information outside the archive or placing it in generated deliverables.

## Invocation

```text
/multica-orchestrator-kick-off mode=materialize-profile profile=<multica-profile> \
  workspace=<optional-id-name-or-slug> runtime_alias=<foundation-runtime-alias> \
  tier=<Lite|Pro|Max>
/multica-orchestrator-kick-off mode=prepare profile=<multica-profile> \
  workspace=<optional-id-name-or-slug> \
  orchestration_profile=<materialized-private-orchestration-profile.v1.json>
/multica-orchestrator-kick-off mode=build-archives \
  manifest=<package-manifest> source_root=<clean-package-source> \
  state_dir=<materialization-run-directory>
Use `--fallback-skill-root <installed-skill-root>` for any required manifest
dependency not distributed in the clean package source, or
`--skill-source multica-cli=<installed-package-directory>` for a one-package
override. The archive records external package content digests instead of
inheriting the package-source revision.
/multica-orchestrator-kick-off mode=materialize-integrity-lock \
  manifest=<package-manifest> archive_plan=<skill-archive-plan.json> \
  skill_list_readback=<readback/skill-list.json> skill_readback_dir=<readback/skills> \
  agent_list_readback=<readback/agent-list.json> agent_readback_dir=<readback/agents> \
  output=<skill-integrity-lock.json>



/multica-orchestrator-kick-off mode=inspect manifest=<package-manifest> \
  input=<server-application-input.v7.json> state_dir=<new-private-directory>
/multica-orchestrator-kick-off mode=plan manifest=<package-manifest> \
/multica-orchestrator-kick-off mode=apply --apply manifest=<package-manifest> \
  input=<server-application-input.v7.json> readback_dir=<captured-readback> \
  skill_archive_plan=<skill-archive-plan.json> plan=<reviewed-plan.json> \
  plan_digest=<digest> operation=<exact-operation-id> authorization_ref=<approval-ref>
/multica-orchestrator-kick-off mode=verify-integrity \
  manifest=<package-manifest> input=<server-application-input.v7.json> \
  readback_dir=<captured-readback> skill_archive_plan=<skill-archive-plan.json> \
  skill_integrity_lock=<skill-integrity-lock.json> phase=full output=<report.json>
/multica-orchestrator-kick-off mode=verify manifest=<package-manifest> \
  input=<server-application-input.v7.json> readback_dir=<captured-readback>
/multica-orchestrator-kick-off mode=emit manifest=<package-manifest> \
  application_input=<server-application-input.v7.json> readback_dir=<captured-readback> \
  verification_report=<server-verification.json> skill_integrity_report=<report.json> \
  skill_integrity_lock=<lock.json> package_version=<version> \
  state_root=<operator-state-root/bundle-store> pointer_state_root=<operator-state-root> \
  output=<server-orchestration-ref.v10.json> output_bundle=<new-export-directory>
```

The central `orchestrator` stage route exposes `materialize-profile`,
`build-archives`, `materialize-integrity-lock`, `prepare`, `inspect`, `plan`,
`apply`, `verify-integrity`, `verify`, and `emit`.
`materialize-profile` first
validates the current Foundation pointer and CAS closure, confirms the named
online OMP Runtime alias, and reads `omp models --json` to bind each family to
one exact selector. It writes a private `OrchestrationProfile.v1` and
resolution evidence. `prepare` then combines that profile with the same
Foundation closure to produce the complete v7 input and `ResolutionManifest.v2`.
Other mode arguments map directly to the selected helper; typed input remains
authoritative.

Do not pass a Server bundle or Foundation digest in the prompt. The deployment
index and stage pointer are the only operator-local selectors.

## Test-prompt input materialization

The canonical `pp-multica-orchestrator-kick-off-test` prompt accepts semantic
`profile`, Workspace, collaboration Runtime alias, and a Human-selected role
tier: `Lite`, `Pro`, or `Max`. It presents the complete sixteen-role
model/thinking matrix. A new Server generation defaults to `Pro` only when the
caller omits the tier; an existing generation reuses its exact digest-bound
policy unless the caller explicitly selects another tier. The prompt must not
require the caller to create or name an orchestration-profile file.

After validating the current Foundation pointer and CAS closure,
`materialize-profile` resolves the selected tier's Luna, Terra, and Sol entries
to unique exact model selectors from the named Foundation Runtime's live
`omp models --json` readback. It validates every requested thinking level
against that same catalog; OMP's machine spelling is `medium`, not `median`.
It never derives selectors from prose, names, or an outdated catalog. Create a
new mode-0600 `OrchestrationProfile.v1` inside the run's mode-0700 directory
from [`controls/orchestration-profile.template.json`](controls/orchestration-profile.template.json).
The generated profile path is an internal argument to the central `orchestrator
prepare` invocation, not a prompt input. Record its digest and model-catalog
digest in the materialization resolution. A missing or ambiguous Human choice,
tier, model-family mapping, Runtime, or thinking capability produces
`ORCHESTRATION_POLICY_INPUT_REQUIRED` before inspect, plan, or live mutation.

## Authoritative package

Read these package resources before planning:

- [manifest](manifests/orchestration-package.yaml)
- [Agent index](agents/agent-instructions.md)
- [Feature Squad](squads/feature-squad.md)
- [Fix Squad](squads/fix-squad.md)
- [execution contracts](contracts/handoff-gate-contracts.md)
- [branch and commit policy](contracts/branch-and-commit-policy.md)
- [server application input schema](contracts/server-application-input.schema.json)
- [server handoff schema](contracts/server-orchestration-ref.schema.json)
- [server setup guide](guide-to-setup-multica.md)

The manifest declares sixteen stable Agent roles and two Squads. Agent identity
is reusable across projects; every admitted run materializes one
`ExecutionContextRef.v1` bound to one manifest role/operation, current
`ProjectBindingRef.v12`, `ActiveProjectReleaseRef.v2`, `RunAdmissionRef.v1`,
`WorkItemExecutionRef.v4`, `WorkItemBranchRef.v1`, `RunCheckoutRef.v1`,
`CheckoutRef.v5`, and single-consumer `HandoffRef.v3`. Native Squad
assignment/mention/reply triggers only wake the Leader or exact member for
evaluation; they do not replace Dispatch admission, current Gate/Human
decisions, scope/lease checks, or run dedupe.

## Scope

This Skill may:

1. validate a current Foundation bundle and its `WorkspaceFoundationRef.v5` or
   `WorkspaceFoundationRef.v6`
   artifact against digest-bound identity, workspace, status contract, verified
   native Squad routing capabilities, and complete Runtime-fleet readback;
2. import and content-verify the exact workspace Skills required by the
   manifest;
3. create or reconcile the sixteen manifest Agents;
4. set each Agent's exact Skill set, selected Runtime alias, model,
   instructions, permission, and conservative concurrency;
5. create or reconcile the `feature` and `fix` Squads and exact membership; and
6. publish `ServerOrchestrationRef.v10`, `ServerVerificationSpec.v3`, and
   `ServerReissueSpec.v1` in a parent-linked immutable bundle after complete readback.

This Skill must not:

- create or select a workspace, create or update labels, administer Issue
  Status definitions, create a runtime profile, or start/rename/replace a daemon;
- call `repo add`, `project create`, or `project resource add`;
- inspect or modify a target product repository;
- create a Project binding, activate Runtime-local resources, initialize a
  Dispatch control store, admit a Work Item, or dispatch an execution run;
- store repository URLs, Project IDs, local absolute repository paths, Work
  Item IDs, or checkout roots in the package or server handoff;
- create Issues, tasks, runs, assignments, mentions, notifications, checkouts,
  branches, commits, PRs, or integrations; or
- claim a project is dispatch-ready.

## Runtime fleet and Skill profile

Runtime identity and capability come from the verified workspace Foundation
fleet. Every role names exactly one declared Runtime alias; aliases are resolved
to live Runtime and daemon refs only after the Foundation bundle is validated.
Model, thinking level, service tier, and per-role concurrency remain Human
choices. `null` means the Human explicitly selected the Runtime-managed default;
an omitted or rejected value is not `null`.

The execution Skills form a pinned workspace profile. Import complete packages
from an authorized canonical source, retain support files, and compare canonical
content digests. Never copy an arbitrary target project's generated
`speckit-*` directory into the workspace. A project with an incompatible Spec
Kit profile is blocked later by `multica-orchestrator-nail-down` rather than
causing a workspace-wide overwrite.

## Procedure

Start with
`python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py orchestrator prepare --profile <profile> [--workspace <selector>]`
`--orchestration-profile <private-profile.json>`. Review the generated request,
v7 input, and resolution manifest; do not paste Foundation digests or role
matrices into the prompt.

1. Resolve the Foundation manifest digest from the configured local bundle
   store. Reject a missing, stale, blocked, wrong-workspace,
   non-online-Runtime-fleet, unverified-status, unexpected-file, symlink, or
   digest-invalid bundle; never repair the Foundation in this Skill.
2. Build deterministic archives for every required manifest Skill and the
   operator-local `skill-archive-plan.json`. Capture Skill, Agent, Squad,
   workspace, and complete Runtime-fleet state with
   `python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py orchestrator inspect`; the
   snapshot includes full `skill get --with-content` artifacts and closing
   workspace/Runtime anchors.
3. Plan against the immutable input, manifest, archive plan, and readback
   snapshot digests. A missing Skill produces a `skill-import`; an identity or
   canonical-content mismatch produces a `skill-update`. Resolve these Skill
   operations before planning any Agent or Squad operation.
4. Apply one reviewed digest-bound operation with the prompt-run authorization
   reference. Before mutation, compare live resource identity with the plan.
   After mutation, independently list/get the resource and reject a failed
   postcondition. Re-inspect and re-plan before the next operation.
5. Reconcile Agents by exact role name, Skill set, Runtime alias placement,
   model, thinking, permission, and concurrency. Treat empty thinking-level
   readback as Runtime-managed `null`; never silently omit an unsupported reset
   from an explicit value to `null`.
6. Reconcile both Squads, shared Leader, instructions, and exact execution
   membership. Provider leader metadata is not an additional execution member.
7. Once all operations are empty, materialize a lock from complete Skill and
   all sixteen Agent list/detail readbacks, then run central `orchestrator
   verify-integrity --phase full`; do not treat a partial check as publishable.
8. Run central `orchestrator verify`, then publish a parent-linked
   `ServerOrchestrationRef.v10` bundle with the full `ServerVerificationSpec.v3`
   and portable `ServerReissueSpec.v1`. Pass paired bundle/pointer roots to
   `emit` to atomically update the workspace-scoped Server pointer and
   `WorkspaceDeploymentIndex.v1`. The emitter rejects stale reports and records
   exact input, snapshot, verification, placement, membership, and integrity
   digests.

Inputs, plans, snapshots, archives, live IDs, verification reports, and handoff
bundles remain in mode-0700 operator state directories and must not be committed.

## Completion

Success is:

```text
state=ORCHESTRATOR_LAYER_VERIFIED
dispatch_state=BLOCKED_PROJECT_BINDING
```

It proves the reusable workspace layer matches the pinned package. It does not
prove any repository, provider controls, Human participation plan, checkout,
CI, or integration path is configured. Continue with
`multica-orchestrator-nail-down` for each target project.

## Shared state package

This Skill resolves the central `multica-orchestrator-cli` package for the
preserved `multica_state_bundle` import namespace. If that namespace is absent
or incompatible, the central runner fails closed before lifecycle mutation and
names `multica-orchestrator-cli` as the corrective installation.
