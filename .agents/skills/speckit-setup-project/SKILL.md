---
name: speckit-setup-project
description: 'Initialize a target project with the repository-supported Spec Kit CLI, project-local Git workflow and Conventional Commit Skills, bug, loop, worktree, roadmap, adrkit, and workflow-preset integrations. Use when creating or adopting a Spec Kit project, validating an incomplete setup, or reporting missing target, integration, governance, permission, or toolchain information before initialization can finish.'
compatibility: Requires a writable target project, Git 2.15+ and Bash for the worktree extension, uv, Node.js 22+ with npx and Bun for adrkit, and network access to the configured sources
metadata:
  author: multica-speckit
  source: project-maintained
---

# Spec Kit Setup Project

## Goal

Initialize one explicitly selected project with the complete Spec Kit stack defined
in this skill. The initializer installs the supported CLI and integrations,
initializes or adopts the target project, reconciles generated agent skills, verifies
the installed state, and reports every missing technical prerequisite.

This skill is self-contained. Use its baselines, commands, decision rules, failure
handling, and verification contract directly; do not require the caller to read
another repository document, skill, or setup guide.

This skill owns technical setup plus explicitly authorized refreshes of project-local
Git Skills, the Spec Kit CLI, and generated Spec Kit Skills. It does not start feature
implementation, create or modify project roadmap, architecture, or ADR artifacts,
invent a constitution, upgrade an extension or preset without explicit approval,
repair extension source code, remove integrations, or troubleshoot unrelated tooling.

## Supported baseline

Use this baseline unless the user explicitly selects and approves another compatible
revision:

| Component | Supported source or release | Role |
| --- | --- | --- |
| Spec Kit | `jiwu-robotics/spec-kit`, branch `develop` | Core CLI and SDD lifecycle |
| `git-workflow` | `affaan-m/ECC`, selected Skill `git-workflow` | Project-local Git workflow, commit, and collaboration guidance |
| `conventional-commit` | `jiwu-robotics/multica-speckit`, selected Skill `conventional-commit` | Project-local Conventional Commit message policy and commit workflow |
| `bug` | Bundled extension, repository baseline `1.0.0` | Assess, fix, and validate isolated defects |
| `spec-kit-loop` | `formin/spec-kit-loop`, release `v1.0.0` | Maker/checker loop and human sign-off |
| `speckit-roadmap` | `srobroek/speckit-roadmap`, release `v0.1.0` | Project roadmap and drift review |
| `spec-kit-worktree-parallel` | `jiwu-robotics/spec-kit-worktree-parallel`, branch `develop`, currently `1.3.2` | Git worktree isolation for parallel agents, manually created by default |
| adrkit CLI | `jiwu-robotics/adrkit`, branch `develop`, expected `0.12.0` | Git-native ADR operations |
| adrkit extension | Same adrkit checkout, expected `0.2.0` | Plan context/check/draft commands |
| `workflow-preset` | `jiwu-robotics/spec-kit-workflow-preset`, branch `develop`, currently `3.3.0` | Requirement Gate and X0-X4 planning artifacts |

Maintain this source chain in order: original parent `upstream/main` tree, Jiwu fork
`origin/main` tree, then Jiwu fork `origin/develop` with verified fork-specific
commits. Ordinary code contributions use the target repository's PR workflow.
For an explicitly Human-authorized mirror sync, maintainers may set the fork's
`main` SHA exactly to the verified parent `main` SHA with an exact
`--force-with-lease` after checking protections and the observed old SHA. Rebuild
`develop` from that `main` plus validated fork-specific functional changes; rewrite
the shared `develop` ref only when that exact ref is explicitly authorized, again
using an exact lease. Never update a parent ref or bypass provider-enforced gates.
Setup and refresh commands consume only the resulting Jiwu `develop` branches.

| Jiwu fork | Original parent |
| --- | --- |
| `jiwu-robotics/spec-kit` | `github/spec-kit` |
| `jiwu-robotics/adrkit` | `mbeacom/adrkit` |
| `jiwu-robotics/spec-kit-workflow-preset` | `bigsmartben/spec-kit-workflow-preset` |
| `jiwu-robotics/spec-kit-worktree-parallel` | `dango85/spec-kit-worktree-parallel` |

After the main-to-develop integration, carry only functional commits from the
migration sources below that are not represented by either branch. A source commit
already integrated upstream is not cherry-picked again.

The current migration inputs are Spec Kit `feat/workflow-run-lease`, adrkit
`adapt-spec-kit-current`, and `main` for workflow-preset and
spec-kit-worktree-parallel. These names identify migration sources only; callers must
clone and refresh the corresponding `develop` branches. A source-branch sync is not
evidence that either maintained fork `main` or `develop` has been updated.

These values are the supported project baseline, not a claim about the latest remote
release. Record the fetched commit for every branch-based source. If an observed
version differs, report drift and stop before accepting or replacing it, except for
the explicitly authorized project-local and `specify_sync=latest` refreshes below.

## GitHub transport

Resolve one GitHub transport for this setup. Honor an explicit Human choice;
otherwise inspect `git remote get-url origin` in the target: use SSH for
`git@github.com:...` or `ssh://git@github.com/...`, HTTPS for a GitHub HTTP(S)
origin, and HTTPS when no preference is observable. Each maintained repository
accepts both forms:

| Repository | HTTPS | SSH |
| --- | --- | --- |
| `jiwu-robotics/spec-kit` | `https://github.com/jiwu-robotics/spec-kit.git` | `git@github.com:jiwu-robotics/spec-kit.git` |
| `jiwu-robotics/spec-kit-worktree-parallel` | `https://github.com/jiwu-robotics/spec-kit-worktree-parallel.git` | `git@github.com:jiwu-robotics/spec-kit-worktree-parallel.git` |
| `jiwu-robotics/adrkit` | `https://github.com/jiwu-robotics/adrkit.git` | `git@github.com:jiwu-robotics/adrkit.git` |
| `jiwu-robotics/spec-kit-workflow-preset` | `https://github.com/jiwu-robotics/spec-kit-workflow-preset.git` | `git@github.com:jiwu-robotics/spec-kit-workflow-preset.git` |
| `affaan-m/ECC` | `https://github.com/affaan-m/ECC.git` | `git@github.com:affaan-m/ECC.git` |

Treat shorthand, HTTPS, SCP-style SSH, and `ssh://` forms as the same canonical
repository identity in `skills-lock.json`. Use only the selected URL. If access
fails, preserve the exact error and stop; never retry through the other transport
without Human approval, and never request or persist a private key, token, or
password.

## Required coding agents and controlled refreshes

Invoke this Skill explicitly with the target-wide required agent set and one default
Specify integration:

```text
/speckit-setup-project mode=inspect target=<target-project> \
  coding_agents=<claude-code,codex,github-copilot,cursor> \
  skill_sync=none specify_sync=none
/speckit-setup-project mode=apply target=<target-project> \
  coding_agents=<claude-code,codex,github-copilot,cursor> \
  integration=<default-integration-key> script=<sh|ps|py> \
  skill_sync=latest specify_sync=latest \
  authorization=<approved-writes-and-refreshes>
```

`coding_agents` is the required target-wide set. Its only accepted values are
`claude-code`, `codex`, `github-copilot`, and `cursor`; duplicates are ignored. An
explicit list is authoritative. `integration` is not an npx agent identifier: it is
the one requested default Specify integration and must map to a member of that set.

| Coding agent | Project-local policy Skill root | Specify key | Generated Skill root |
| --- | --- | --- | --- |
| Claude Code (`claude-code`) | `.claude/skills` | `claude` | `.claude/skills` |
| Codex (`codex`) | `.agents/skills` | `codex` | `.agents/skills` |
| GitHub Copilot (`github-copilot`) | `.agents/skills` | `copilot` | `.github/skills` |
| Cursor (`cursor`) | `.agents/skills` | `cursor-agent` | `.cursor/skills` |

When `coding_agents` is absent, infer only from target guidance that names a supported
agent, `.claude/` for Claude, `.cursor/` for Cursor, `.github/skills` or recorded
`copilot` integration state for Copilot, and recorded Specify integration state.
`.github/` alone and `.agents/skills` alone are not agent-identifying evidence. Empty,
contradictory, unsupported, or shared-root-ambiguous evidence requires the
missing-information block before every agent-scoped mutation. If exactly one required
agent is known, its mapped Specify key is the default when `integration` is omitted;
otherwise require one explicit default.

- `inspect` is read-only. It discovers the full per-agent matrix, runs toolchain and
  multi-root provenance checks, reads `skills-lock.json`, reports local-content and
  remote candidate-revision drift, and drafts every change.
- `apply` performs only reviewed, authorized setup actions. `skill_sync=none` and
  `specify_sync=none` are the defaults.
- `skill_sync=latest` requires explicit authorization and updates only
  project-local `git-workflow`; it never upgrades Spec Kit.
- `specify_sync=latest` requires separate explicit authorization to upgrade the
  globally installed `specify` CLI and refresh generated `speckit-*` Skills for every
  resolved required integration. It never upgrades extensions, presets, policy
  packages, or unselected extra integrations.

Before and after `skill_sync=latest`, run from the target root with every required
npx agent repeated:

```bash
SPECKIT_SETUP_SKILL_ROOT=<project-local-path-to-speckit-setup-project>
python3 "$SPECKIT_SETUP_SKILL_ROOT/cli/check_skill_provenance.py" \
  --project-root <target-project> \
  --agent <required-agent-1> [--agent <required-agent-N> ...] \
  --require-lock --require-remote
npx skills update git-workflow --project --yes
python3 "$SPECKIT_SETUP_SKILL_ROOT/cli/check_skill_provenance.py" \
  --project-root <target-project> \
  --agent <required-agent-1> [--agent <required-agent-N> ...] \
  --require-lock --require-remote --record
```

For `specify_sync=latest`, first record `specify --version` and
`specify integration status --json`. Then run `specify self upgrade` directly:
it has no confirmation prompt, and `--dry-run` is not completion evidence. Preserve
any dry-run transport error if one was requested, but an explicitly authorized actual
upgrade is the authoritative operation. Re-read the version, upgrade each resolved
required integration with `specify integration upgrade`, restore the requested
default with `specify integration use`, and read the status again. Honor proxy
environment variables already supplied by the target environment without printing
their values; never invent proxy settings.

The checker records each selected physical root only after every selected root passes.
Read each resulting `skill-provenance.json`, `skills-lock.json`, the combined diff,
and every required agent's catalog; reload and read both Git policy Skills for every
required agent. A missing, stale, or conflicting root is `partial`, never `complete`.

## Safety and ownership rules

1. Read the target project's active agent guidance and engineering policy before
   running tools. Use its container, task runner, proxy, and credential rules. Never
   move project tooling to the host merely because the required environment fails.
2. Detect whether the target is a Git repository. When it is, run
   `git status --short` before mutation and preserve all unrelated work. For a
   non-Git target, ask whether to proceed without a reviewable diff; never run
   `git init`, reset, clean, stash, commit, or overwrite user changes silently.
3. Existing-project initialization with `--force` may replace Spec Kit-managed paths.
   Require a clean, reviewable baseline and explicit approval for `--force`; otherwise
   stop before `specify init` and explain the conflict.
4. Keep Spec Kit, adrkit, preset, worktree-extension, and development-extension
   checkouts outside the target project, normally as siblings. Never copy their nested
   project state into the target.
5. Keep project-local policy Skills in the mapped roots above. Before mutation,
   inspect `skills-lock.json` and every distinct selected policy root for locked
   `jiwu-robotics/multica-speckit` packages and `affaan-m/ECC/git-workflow`. A
   same-name package from another source is a blocking conflict. Generated
   `speckit-*` Skills, integration prompts, extension registries, and preset
   `.composed/` files are generated artifacts: reconcile them only through
   `specify`; never patch or hand-copy them between roots.

   Install missing project-local policy Skills, or refresh matching-source packages
   only under explicit authorization, with one `--agent` for every required coding
   agent:

   ```bash
   npx --yes skills add "$MULTICA_SPECKIT_SOURCE" \
     --skill conventional-commit --skill speckit-setup-project \
     --agent <required-agent-1> [--agent <required-agent-N> ...] --copy --yes
   npx --yes skills add "$GIT_WORKFLOW_SOURCE" \
     --skill git-workflow \
     --agent <required-agent-1> [--agent <required-agent-N> ...] --copy --yes
   ```

   Deduplicate filesystem verification by physical policy root, but retain catalog,
   reload, and readback evidence for each required agent. Never install globally,
   substitute a global copy, or use these commands to overwrite a conflicting source.
   `conventional-commit` and `speckit-setup-project` must come from the same
   `jiwu-robotics/multica-speckit` source; `git-workflow` must lock
   `affaan-m/ECC` at `skills/git-workflow/SKILL.md`.
6. Never use unscoped `npx adrkit`. A missing `ADRKIT_CLI`, Node.js, Bun, or
   executable is an error.
8. Do not enter, print, or commit SSH keys, tokens, proxy credentials, absolute
   site-local secrets, or controller values. Authentication must already be arranged
   through the approved environment.
9. Initialization operates on setup configuration and generated integration files
   only. It must not access external production systems, change runtime deployment
   state, create a feature, assess a fake bug, draft a fake ADR, start an
   implementation loop, or create or modify project roadmap, architecture, or ADR
   artifacts merely to test installation.
10. Re-running this skill must be idempotent. Reuse matching clean installations;
    never create duplicate projects, checkouts, extension registrations, or presets.
11. Record every exact command, selected source revision, output status, and failure.
    Never claim an unavailable or partial check passed.
12. The setup invocation authorizes affirmative responses to every Spec Kit CLI
    confirmation for the actions selected by this procedure. On POSIX, prefix every
    mutating `specify` command with `yes |`; retain `--non-interactive` where it
    selects documented defaults. This does not select an ambiguous target or
    integration, permit unreviewed `--force`, invent governance facts, or bypass
    network policy.
13. After every extension and preset is installed and reconciled, delete only
    `.specify/.git`. It is nested generated Git metadata that would interfere with
    committing the target project. Never delete the target repository's root `.git`
    or any sibling checkout's `.git`.



## Missing-information contract

Discover facts from the target repository, current CLI output, and source checkouts
before asking. Do not ask for information those sources provide. When a required fact
is still missing, proactively tell the user before the affected mutation.

Use this format:

```text
Missing: <fact or authorization>
Why required: <decision or command it controls>
Evidence checked: <paths or commands already inspected>
Safe default: <default and consequence, or "none">
Work that can continue: <unblocked setup steps>
Blocked step: <exact setup step>
```

Batch related missing facts into one prompt. Distinguish:

- **hard blockers** — target path, target integration key, writable/compliant execution
  environment, reviewable baseline for `--force`, required source access, or permission
  to replace a conflicting installed CLI;
- **completion blockers** — a persistent way to provide `ADRKIT_CLI` in future
  sessions;
- **optional choices** — alternate checkout directories or development installs. Use
  the conservative defaults below when they do not overwrite or broaden scope.

Never silently choose:

- a target project when several candidates exist;
- a coding-agent integration when repository evidence supports more than one;
- `--force` against an unreviewed non-empty project;
- a different Spec Kit fork, extension release, preset branch, or compatibility range;
- a persistent environment file or shell profile for `ADRKIT_CLI`;

Conservative defaults that may be stated and used:

- current directory only when the invocation clearly names it as the target;
- `sh` scripts on POSIX and `ps` on Windows when the target has no documented script
  convention;
- sibling source checkouts beside the target project;
- the pinned releases and maintained branches in the baseline table;

## Required inputs and preflight

### 1. Resolve the target and mode

Determine:

- requested `mode`, `skill_sync`, absolute target, script variant, Git/reviewable
  baseline, target runner, and sibling-checkout parent;
- required `coding_agents` and the requested default `integration`;
- whether the target is new, existing, or already Spec Kit initialized; and
- current Specify integration status plus every mapped policy and generated root.

Validate the explicit agent list against the four supported identifiers, map it to
physical policy roots and Specify keys, and require that the requested default maps
back to a required agent. When the list is absent, use only the explicit-first
evidence rules above. An empty, contradictory, unsupported, or ambiguous result
emits the missing-information block and stops before all agent-scoped mutation.
Use `specify init --help` and `specify integration status --json` once available to
validate supported keys; never use `integration switch` to infer or simulate
coexistence.

### 2. Establish CLI availability and inspect the target

First determine whether the globally available `specify` command is installed:

```bash
command -v specify >/dev/null 2>&1 && specify --version
```

In `inspect` mode, record a missing command as the first planned `apply` action. In
`apply` mode, install the reviewed global CLI in initialization step 1 when the
command is absent. Do not run `specify init --help`, the packaged version checker, or
any target-scoped `specify` command until that command is available.

After the global CLI is available, run the packaged read-only checker and inspect
target state before mutation:

```bash
SPECKIT_SETUP_SKILL_ROOT=<project-local-path-to-speckit-setup-project>
python3 "$SPECKIT_SETUP_SKILL_ROOT/cli/check_speckit_versions.py"
specify integration status --json
python3 "$SPECKIT_SETUP_SKILL_ROOT/cli/check_skill_provenance.py" \
  --project-root <target-project> \
  --agent <required-agent-1> --agent <required-agent-N> \
  --require-lock --require-remote
npx skills list --project
```

Record the version JSON and, for every required agent, policy root, generated root,
catalog state, integration key, installed/missing/conflict state, and final planned
readback. Inspect `skills-lock.json`, `.specify/` registries, mapped generated
directories, each selected policy root, sibling checkouts, worktree configuration,
and target task-runner/environment conventions. The checker validates `specify`
`1.0.0+`, Node.js `22+`, Git `2.15+`, Bun, and Bash; after ADRKit configuration,
repeat it with `--adrkit-cli "$ADRKIT_CLI"`.

Require Node.js 22 or newer for adrkit and Git 2.15 or newer plus Bash for the
worktree extension. Verify that SSH access and network policy permit the maintained
organization repositories before relying on them. If a command or source is
unavailable, report the exact error and the installation step it blocks.

### 3. Present the setup plan

Before mutation, present one compact table with one row per required agent:

| Agent | Policy root | Specify key / generated root | State | Planned action |
| --- | --- | --- | --- | --- |
| `<required-agent>` | mapped project-local root | mapped key / root | installed / missing / conflict | reuse, install, reconcile, or stop |

Then include the Spec Kit CLI, extensions, preset, and governance-artifact rows.
The table must distinguish each shared-root agent's catalog/readback even when their
filesystem verification is deduplicated. Ask one bundled question for unresolved
agent set, default, conflict, or Copilot secondary-install authorization. Explicit
initialization authorizes normal generated files, not unrelated overwrites or
conflicting source replacement.
`inspect` stops after this draft. Run initialization only in `apply` after every
required authorization and any reviewed `--force` approval are established.

## Initialization procedure

Follow the order below. Skip only a step proven reusable by CLI readback.

### 1. Verify, install, or explicitly refresh the global Spec Kit CLI

Run `specify --version` first. Reuse a matching installed CLI. Only when the command
is absent, install the maintained branch as a global `uv` tool from a clean sibling
checkout using the selected transport:

```bash
SPEC_KIT_REPOSITORY=https://github.com/jiwu-robotics/spec-kit.git
# SSH: SPEC_KIT_REPOSITORY=git@github.com:jiwu-robotics/spec-kit.git
git clone --branch develop \
  "$SPEC_KIT_REPOSITORY" ../spec-kit
uv tool install specify-cli --from ../spec-kit
specify --version
```

`uv tool install` makes `specify` available globally to subsequent sessions. If a
different CLI or source is installed, show the observed version/source and obtain
approval before replacement. Do not replace the maintained fork with PyPI or upstream
merely because the selected GitHub transport, proxy, or registry access fails.

When `specify_sync=latest` is explicitly authorized, refresh only the maintained
fork's `develop` branch from its clean sibling checkout. Verify its origin and branch
against the selected transport, reject a dirty checkout, fast-forward the expected
branch, then reinstall the `uv` tool from that exact checkout:

```bash
git -C ../spec-kit remote get-url origin
git -C ../spec-kit status --porcelain
git -C ../spec-kit fetch origin develop
git -C ../spec-kit switch develop
git -C ../spec-kit merge --ff-only origin/develop
git -C ../spec-kit rev-parse HEAD
uv tool install specify-cli --force --from ../spec-kit
specify --version
```

`specify self upgrade` is prohibited here: it follows the installed CLI's own
upstream release channel and can replace the maintained Jiwu fork. An already
up-to-date fast-forward is a valid no-op. A dirty or mismatched checkout, failed
fetch, non-fast-forward branch, installer failure, or post-install readback failure
is `partial`; do not silently fall back to another installer, source, or transport.

### 2. Initialize or adopt the target and establish the policy Skill set

Resolve the full required set and default first. For a new target, initialize exactly
once with the default Specify key:

```bash
yes | specify init --here --integration <default-key> \
  --script <sh|ps|py> --non-interactive
```

For an existing non-empty target, require the reviewed `--force` authorization; for
an initialized target, inspect `specify integration status --json` and never rerun
init blindly. Then, before additional integration installation, inspect the lock and
every distinct required policy root. Install missing clean packages using the two
target-wide `npx skills add` commands in the ownership rules; reuse matching clean
packages; stop on a same-name different-source package. This project-local phase is
idempotent and never copies generated Spec Kit artifacts.

### 3. Reconcile project-local Git policy Skills

For `skill_sync=latest`, run the required multi-root provenance precheck, execute
`npx skills update git-workflow --project --yes` once against the lock-recorded
project installation, then require the multi-root postcheck and record. Review the
combined lock/diff; reload and read `git-workflow` and `conventional-commit` in every
required agent. Under `skill_sync=none`, do not refresh or write provenance. A
missing, stale, or conflicting required root is `partial`, never `complete`.

### 4. Install remaining required Specify integrations

After the primary initialization and policy Skill phase, reuse each installed matching
required key and install each remaining required key with:

```bash
yes | specify integration install <key> --script <sh|ps|py>
```

Use the mapped defaults for Claude, Codex, and Cursor. For Copilot, use
`--integration-options="--skills"`. When Copilot joins another integration, current
CLI metadata requires `--force` only for that multi-install admission:

```bash
yes | specify integration install copilot --script <sh|ps|py> \
  --integration-options="--skills" --force
```

Show that exact command and require authorization covering it. Never reuse that
authorization for modified-file replacement or integration upgrade. Preserve extra
pre-existing integrations, stop on unknown keys or baseline drift, and never use
`integration switch` or manual copying to simulate coexistence.

### 5. Refresh generated Skills for every required integration

After extensions and `workflow-preset` are installed once at project scope, refresh
each resolved required integration with the current CLI:

```bash
yes | specify integration upgrade <required-key> --script <sh|ps|py>
# repeat once for every resolved required key
yes | specify integration use <default-key>
specify integration status --json
```

`integration use` restores the requested default; it does not refresh generated
Skills. Do not add `--force`: if an upgrade reports modified managed files or shared
infrastructure that it did not update, preserve those paths, report the exact output,
and classify the refresh `partial` until a Human explicitly authorizes the reviewed
overwrite. If any unforced upgrade fails, preserve completed roots, restore the
original/default integration when safe, and report `partial` with the exact missing
agent/Skill matrix. Never treat another generated root as proof for a failed agent.

Current Spec Kit status metadata reports `unsafe-multi-install` and exits nonzero
after an explicitly authorized secondary Copilot installation, even when it lists all
installed keys, retains the requested default, and no managed file is missing or
modified. Record that warning and the status payload; verify each generated root
independently. It does not authorize further force operations or a claim that the
multi-install set is safe.

### 6. Install the bundled Bugfix extension

```bash
yes | specify extension add bug
specify extension list
```

Expect `speckit.bug.assess`, `speckit.bug.fix`, and `speckit.bug.test`. Do not run them
with fabricated data as an installation test.

### 7. Install spec-kit-loop

The setup invocation automatically approves this direct-URL trust prompt:

```bash
yes | specify extension add loop \
  --from https://github.com/formin/spec-kit-loop/archive/refs/tags/v1.0.0.zip
specify extension list
```

Expect `speckit.loop.define`, `speckit.loop.run`, `speckit.loop.check`,
`speckit.loop.guard`, and `speckit.loop.status`. Do not weaken checker
independence or human sign-off in generated artifacts.

### 8. Install spec-kit-worktree-parallel

No release archive is published for this extension. Install its maintained `develop`
checkout locally, then run its explicit post-install script:

```bash
WORKTREE_EXTENSION_REPOSITORY=https://github.com/jiwu-robotics/spec-kit-worktree-parallel.git
# SSH: WORKTREE_EXTENSION_REPOSITORY=git@github.com:jiwu-robotics/spec-kit-worktree-parallel.git
git clone --branch develop --single-branch \
  "$WORKTREE_EXTENSION_REPOSITORY" ../spec-kit-worktree-parallel
yes | specify extension add ../spec-kit-worktree-parallel --dev
bash .specify/extensions/worktrees/scripts/bash/post-install.sh
```

Before configuration, inspect
`.specify/extensions/worktrees/worktree-config.yml` when it exists. Preserve an
existing configuration; if its `layout` or `auto_create` values differ from the
baseline below, report drift and stop before changing it. When the file is absent,
create it with these defaults:

```bash
cat > .specify/extensions/worktrees/worktree-config.yml <<'EOF'
layout: "nested"
auto_create: false
EOF
specify extension list
```

The post-install script adds `.worktrees/` to the target's `.gitignore` if absent.
The configuration keeps that nested layout but prevents automatic worktree creation
after `/speckit.specify`; users create or reuse one explicitly with
`/speckit.worktrees.specify` or `/speckit.worktrees.create`. Expect `worktrees`
`1.3.2` with `speckit.worktrees.specify`, `speckit.worktrees.create`,
`speckit.worktrees.list`, and `speckit.worktrees.clean`.

Do not modify another extension's hooks during setup. A later workflow may explicitly
change `auto_create` or disable the Git extension's `speckit.git.feature` hook after
reviewing the target's chosen isolation model.

### 9. Install speckit-roadmap

Use the supported pinned release, then enable it:

```bash
yes | specify extension add \
  --from https://github.com/srobroek/speckit-roadmap/archive/refs/tags/v0.1.0.zip
yes | specify extension enable roadmap
specify extension list
```

Expect `speckit.roadmap.write`, `speckit.roadmap.brief`,
`speckit.roadmap.debrief`, and `speckit.roadmap.sync`, plus
`.specify/extensions/roadmap/roadmap-config.yml`. The default roadmap is
`.specify/memory/roadmap.md`.

If a local roadmap install is required, use a new sanitized copy outside the target;
do not mutate or delete the source checkout. Remove only the sanitized copy's nested
`.specify/` directory. With Spec Kit 1.0.x, if manifest validation rejects script IDs
ending in `.sh` or `.ps1`, change only the two `name:` values in the sanitized
`extension.yml` to `load-config` and `load-config-powershell`; retain the script
`file` paths and record the workaround.

### 10. Install the adrkit CLI and extension

Use a clean sibling checkout of the maintained branch:

```bash
ADRKIT_REPOSITORY=https://github.com/jiwu-robotics/adrkit.git
# SSH: ADRKIT_REPOSITORY=git@github.com:jiwu-robotics/adrkit.git
git clone --branch develop "$ADRKIT_REPOSITORY" ../adrkit
cd ../adrkit
bun install --frozen-lockfile
bun run build
cd -
export ADRKIT_CLI="$(realpath ../adrkit/packages/cli/dist/index.js)"
"$ADRKIT_CLI" --version
yes | specify extension add \
  --dev ../adrkit/packages/adapters/spec-kit \
  --force
specify extension list
```

Expect CLI `0.12.0`, extension `0.2.0`, three commands, and one optional
read-only `after_plan` hook. The commands are `speckit.adrkit.context`,
`speckit.adrkit.check`, and `speckit.adrkit.draft`.

Before completion, identify how future compliant sessions receive `ADRKIT_CLI`. Reuse
the target's existing task runner or ignored environment convention. If none exists,
ask the user; never write an absolute machine path into a committed file or edit a
shell profile silently.

The default corpus proposal is `docs/adr`; honor an existing `ADRKIT_DIR`. A missing
corpus is not a successful empty corpus. Do not create a fake ADR or invent rationale
to prove the CLI works.

### 11. Install workflow-preset

Use a clean sibling checkout of the maintained organization repository:

```bash
WORKFLOW_PRESET_REPOSITORY=https://github.com/jiwu-robotics/spec-kit-workflow-preset.git
# SSH: WORKFLOW_PRESET_REPOSITORY=git@github.com:jiwu-robotics/spec-kit-workflow-preset.git
git clone --branch develop "$WORKFLOW_PRESET_REPOSITORY" ../spec-kit-workflow-preset
yes | specify preset add --dev ../spec-kit-workflow-preset
specify preset list
specify preset info workflow-preset
```

Record the checkout commit and reported version. The baseline currently resolves to
`3.3.0`; a different version is drift requiring review, not implicit permission to
accept latest behavior.

After every extension and the preset is installed once at project scope, repeat the
Step 5 `specify integration upgrade` sequence for every resolved required key, then
restore the requested default with `yes | specify integration use <default-key>`.
Capture `specify integration status --json` after the final restore.

The final unforced upgrade must refresh every resolved generated Skill root. Do not
add `--force`; a modified managed/shared file or an omitted shared-infrastructure
warning remains a reviewed `partial` result. Require status to show every required
key and the requested default, preserve and report extras, and verify each mapped
root contains the expected core, bug, loop, worktree, roadmap, adrkit, and
workflow-preset generated Skill names. Never repair parity by copying templates or
generated Skills.

### 12. Remove nested Spec Kit Git metadata

After all extensions, presets, and the integration upgrade are complete, remove the
generated nested Git metadata before reviewing the target diff:

```bash
rm -rf -- .specify/.git
test ! -e .specify/.git && test ! -L .specify/.git
```

This cleanup is idempotent. It applies only to `.specify/.git`; never remove the
target repository's root `.git` or a sibling checkout's `.git`.

### 13. Defer project governance artifacts

Installation and project governance are separate concerns. Do not create or modify a
project roadmap, architecture artifact, ADR corpus, constitution, or any related
record during setup. Preserve and report any pre-existing artifacts without treating
their absence as a blocker.

The enabled roadmap extension may generate its own
`.specify/extensions/roadmap/roadmap-config.yml`; that is extension configuration,
not a project roadmap. Creation of project-owned roadmap, architecture, and ADR
artifacts is decided later by the applicable Spec Kit workflow from then-current,
approved project facts.

## Verification and readback

Read back actual target-wide installed state; file presence alone is insufficient:

```bash
specify --version
specify extension list
specify preset list
specify preset info workflow-preset
specify integration status --json
cat .specify/extensions/worktrees/worktree-config.yml
git check-ignore -q .worktrees/.keep
test ! -e .specify/.git && test ! -L .specify/.git
test -f skills-lock.json
printf '%s\n' "$ADRKIT_CLI"
"$ADRKIT_CLI" --version
SPECKIT_SETUP_SKILL_ROOT=<project-local-path-to-speckit-setup-project>
python3 "$SPECKIT_SETUP_SKILL_ROOT/cli/check_speckit_versions.py" \
  --adrkit-cli "$ADRKIT_CLI"
npx skills list --project
python3 "$SPECKIT_SETUP_SKILL_ROOT/cli/check_skill_provenance.py" \
  --project-root <target-project> \
  --agent <required-agent-1> --agent <required-agent-N> \
  --require-lock --require-remote
```

For every required agent, read back its catalog, reload and read both policy Skills,
and verify its mapped policy root plus its mapped generated root. Deduplicate only
the physical policy-root digest check: Codex, Copilot, and Cursor still each require
catalog/reload proof. Status must list every required integration and the requested
default; expected core, bug, loop, worktree, roadmap, adrkit, and workflow-preset
generated Skill names must exist in every mapped generated root. A missing or stale
root, modified managed file, failed integration cycle, or mismatched provenance is
`partial`; generated files for another agent are not substitute evidence.

For the current Copilot metadata warning, record the nonzero status and
`unsafe-multi-install` finding as a known compatibility risk, while separately
recording the installed/default keys and every generated-root file check. A missing
file, modified managed file, different status finding, or failed unforced use remains
`partial`.

For preset payload parity, when the checkout and installed payload use the documented
layout:

```bash
diff -qr --exclude=.git --exclude=.composed \
  ../spec-kit-workflow-preset .specify/presets/workflow-preset
```

No output means source payload parity. This does not replace CLI version, registry, or
resolved-skill verification.

Do not create a sample feature, bug, loop, roadmap change, or ADR solely for smoke
testing. Use read-only listings and existing real artifacts. If the target already has
an approved roadmap or ADR corpus, an applicable read-only command such as
`speckit.roadmap.sync`, `speckit.loop.status`, or adrkit `lint` may be exercised through
the target's actual agent/task-runner interface; report absence of prerequisites
instead of fabricating them.

## Failure handling

- **Required agent set is empty, contradictory, unsupported, or shared-root
  ambiguous:** emit one bundled missing-information block and stop before every
  agent-scoped mutation; never default from `.agents/skills` or `.github/` alone.
- **Default integration is absent or not mapped to a required agent:** show the
  resolved matrix and stop before initialization or reconciliation.
- **Policy package is missing, locked to another source, or divergent in a required
  root:** preserve it, report the exact root/package/lock entry, and stop for explicit
  replacement authorization. Never overwrite via multi-agent `npx skills add`.
- **Latest refresh fails, provenance fails, or a root is stale:** preserve installed
  Skills, report each root result, write no provenance state when eligibility fails,
  and classify setup `partial`.
- **Copilot secondary integration needs `--force`:** show only the reviewed
  multi-install command and request authorization; never force an upgrade or
  modified-file replacement.
- **Integration install, use, or upgrade fails, a key is unknown, or generated output
  differs:** preserve completed roots, restore the default when safe, report the exact
  agent/Skill matrix, and do not hand-copy generated artifacts.
- **Existing project is dirty or requires `--force`:** stop before mutation and ask
  for a reviewable baseline and explicit overwrite authorization.
- **CLI, source, network, toolchain, checkout, or ADRKit failure:** preserve the
  exact command/error, do not switch transport or replacement source silently, and
  continue only independent setup steps.
- **Worktree, governance, nested Git, or quality-gate condition:** preserve the
  documented existing behavior and report the exact blocking path or command.

## Completion report

Return one target-wide setup ledger:

| Area | Required evidence |
| --- | --- |
| Target | path, mode, `skill_sync`, `specify_sync`, Git/reviewable baseline, required agents, default integration, script |
| Agent matrix | every agent, policy root, Specify key/generated root, installed/missing/conflict state, catalog/reload/readback |
| Sources | repository, branch/tag, fetched commit, trust decision, policy lock hashes, and before/after Specify versions when refreshed |
| Generated files | every mapped root, owner integration, unforced upgrade result, restored default, and reviewed diff |
| Verification | version/status listings, multi-root provenance, exact commands/results, repository gates |
| Governance and failures | preserved/deferred artifacts plus exact unresolved fact, error, impact, and safe next action |

Use exactly one final state:

- **complete** — every required integration and mapped root is verified, the requested
  default is restored, policy provenance is valid, persistent adrkit resolution is
  established, and governance artifacts were preserved or deferred;
- **partial** — safe work completed but any required root, agent catalog, integration,
  generated Skill, or completion prerequisite remains missing or stale;
- **blocked** — a hard blocker prevented reliable target-wide mutation or verification.

Never report complete when only one agent's generated files exist, when status omits a
required/default key, when a physical policy root is unverified, when setup modifies
governance content, or when a required check was not run.
