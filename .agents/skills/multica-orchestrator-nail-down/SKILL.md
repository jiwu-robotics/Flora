---
name: multica-orchestrator-nail-down
description: Bind a verified reusable Multica orchestrator workspace to one repository and prove project-level explicit-dispatch capability.
---

# Multica Orchestrator Nail Down

Bind one repository and project subpath to an already verified reusable Multica orchestration layer. This Skill owns only Project/repository association, portable repository policy/configuration, the immutable Project bundle, and a release candidate.

It never owns Runtime-local checkout paths, `local_directory` resource mutation, execution control stores, Work Item admission, branch/worktree state, Human decisions, CI/provider evidence, or dispatch. Migrate owns Runtime activation; Dispatch owns every per-Work-Item execution control.

## Dependencies

Read `multica-orchestrator-kick-off`, `multica-orchestrator-link-up`, `multica-login`, and `multica-cli`. Require a current content-addressed Server bundle containing `ServerOrchestrationRef.v10`, `ServerVerificationSpec.v3`, and `ServerReissueSpec.v1`, parent-linked to verified `WorkspaceFoundationRef.v6`.

Resolve the Server bundle through the live ProfileSession and `WorkspaceDeploymentIndex.v1`. No mode may synthesize or repair Workspace, label, status, Runtime, Skill, Agent, or Squad facts.

## Central operational runner

Before any lifecycle action, resolve the installed
`multica-orchestrator-cli` package from the selected Agent Skill root. Invoke
Nail Down only through:

```text
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py \
  nail-down <prepare|plan|apply|verify> [arguments]
```

An unavailable or incompatible central package is a pre-mutation blocker; install
`multica-orchestrator-cli` rather than looking for a Nail Down-local command or
script asset.

## Mandatory raw prompt and report capture

Every direct invocation must create an exact private local record before reading source or taking another action.

1. Run
   `<agent-skill-root>/multica-orchestrator-cli/scripts/prompt_and_report_capture.py start`
   with Skill name `multica-orchestrator-nail-down` and `--cwd "$PWD"`; send the complete triggering instruction on standard input.
2. Preserve `capture_id`. The helper writes below `./.prompt-and-report/` with private permissions and excludes it from the Git worktree.
3. Never redact, rewrite, commit, bundle, upload, or publish the capture.
4. On every terminal path, run `finish` with the same ID and exact final report bytes.
5. A capture failure blocks a completion claim.

## Contracts

- request: `ProjectBindingRequest.v6`
- read-only snapshot: `ProjectBindingSnapshot.v6`
- application input: `ProjectBindingInput.v12`
- binding: `ProjectBindingRef.v12`
- plan: `ProjectBindingPlan.v11`
- Runtime policy: `RuntimeTargetPolicy.v4`
- verification: `ProjectVerificationSpec.v8`
- reissue: `ProjectReissueSpec.v3`
- candidate: `ProjectReleaseCandidate.v8`

`RuntimeTargetPolicy.v4` has exactly one required collaboration Runtime and zero or more unique optional Runtime targets. Nail Down activates that required Runtime on the current machine. `ProjectBindingRef.v12` stays portable and binds the Dispatch contract digest, but never includes a machine-local path, profile/account, resource ref, receipt, or control-store locator.

## Invocation

```text
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py nail-down prepare \
  --profile <profile> --workspace <workspace> \
  --repository-root <repository-root> --project-subpath <relative-subpath> \
  --runtime-alias <required-runtime-alias> [--request <request.v6.json>]
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py nail-down plan \
  --input <project-binding-input.v12.json> \
  --binding-content <portable-yaml> \
  --issue-tracker-content <portable-markdown> \
  --triage-mapping-content <portable-markdown> \
  --domain-content <portable-markdown> --plan <new-plan.json>
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py nail-down apply --apply \
  --input <project-binding-input.v12.json> --plan <reviewed-plan.json> \
  --plan-digest <digest> --operation <exact-operation-id> \
  --authorization-ref <approval-ref>
python3 <agent-skill-root>/multica-orchestrator-cli/cli/run.py nail-down verify \
  --input <project-binding-input.v12.json> \
  --binding-manifest <repository/.multica/agents/orchestrator-binding.yaml> \
  --output <project-binding-ref.v12.json> --output-bundle <new-export-directory> \
  --release-candidate <project-release-candidate.v8.json> \
  --authorization-ref <approval-ref> --activation-receipt <receipt.json> \
  --activation-aggregate <aggregate.json> --active-release <release.json> \
  --pointer-state-root <operator-state-root>
```

The central `nail-down` stage route exposes only `prepare`, `plan`, `apply`,
and `verify`.

## Prepare

`prepare` performs read-only resolution:

1. resolve one authenticated ProfileSession and Workspace;
2. resolve current Foundation → Server CAS closure;
3. derive repository identity from credential-free GitHub origin and project subpath;
4. materialize or validate one portable request;
5. read the repository registry, Project, Project GitHub resource, and selected primary local-directory resource;
6. read the selected Runtime and verify its live capability revision equals the Server fleet and request requirement;
7. write private request/snapshot/input/resolution files under the operator run directory.

Do not inspect repository HEAD or require a clean worktree. Project binding is configuration identity, not a commit snapshot.

## Plan and apply

The deterministic plan may contain only:

- repository registration;
- Project creation;
- Project GitHub repository resource addition;
- one `project/bind-primary-local-directory` operation when the exact primary resource is absent or has the wrong mode;
- writes of exactly four portable repository files:
  - `.multica/agents/orchestrator-binding.yaml`
  - `.multica/agents/issue-tracker.md`
  - `.multica/agents/triage-mapping.md`
  - `.multica/agents/domain.md`

Ambiguous or path/daemon-conflicting local-directory resources are blockers. Apply exactly one reviewed operation with stale-plan verification and postcondition readback. Re-plan after every observed-state change.

## Verify and publish

Verify:

- parent Foundation/Server identity, lineage, state, package contract, Skill/Agent/Squad placement, and Runtime capability revision;
- exact repository registry, Project, GitHub, and primary worktree local-directory resource identity;
- all four portable files and their digests;
- binding manifest policy and command profiles;
- selected primary Runtime, daemon, receipt, aggregate, and Dispatch contract digest.

Any blocker stops before candidate/ACTIVE pointer publication or Runtime binding. On success Nail Down publishes the immutable Project bundle and candidate, one primary `RuntimeActivationReceipt.v2`, a one-receipt `ActivationAggregate.v1`, immutable `ActiveProjectRelease.v2`, the coordinator ACTIVE pointer, and the exact primary Runtime binding. The activation fence is cleared only after matching readbacks.

## Portability and secrets

Shared artifacts may contain repository identity, project subpath, policy, immutable bundle digests, Runtime aliases/capability digests, and reusable Agent/Squad refs. They must not contain profile/account refs, workspace credentials, absolute paths, SSH hosts, local resource refs, repository HEAD, control-store paths, Human identity, or provider receipts.

Operator inputs, snapshots, resolution manifests, activation inventories, and execution evidence remain private mode-`0600` artifacts below mode-`0700` roots.

## Completion

Nail Down completion means:

- `PROJECT_BOUND`;
- `activation_state=ACTIVE`;
- a portable immutable Project bundle/candidate plus primary receipt/aggregate/release;
- a readable current-machine Runtime binding and ACTIVE pointer;
- no Dispatch admission, Work Item, run, or worktree creation.

Report exact bundle/candidate/receipt/aggregate/release digests, generation, primary Runtime, pointers updated, blockers, and side effects not executed.

## Shared state package

This Skill resolves the central `multica-orchestrator-cli` package for the
preserved `multica_state_bundle` import namespace. If that namespace is absent
or incompatible, the central runner fails closed before lifecycle mutation and
names `multica-orchestrator-cli` as the corrective installation.
