---
name: speckit-upgrade-refs
description: Inspect and synchronize maintained forks; preserve shared history by default and allow explicitly authorized exact-ref mirror updates with --force-with-lease.
---

# Spec Kit Upgrade Refs

Maintain the source topology used by project setup: the original parent `main` tree → maintained fork `main` → fork `develop` with verified fork-specific commits on top. Preserve shared history by default. An explicitly Human-authorized mirror sync may replace the maintained fork's exact `main` ref and rebuild `develop` with `--force-with-lease`; never rewrite the parent repository or unrelated refs.

## Invocation

```text
/speckit-upgrade-refs mode=inspect workspace=<parent-of-checkouts> repositories=all
/speckit-upgrade-refs mode=apply workspace=<parent-of-checkouts> repositories=all authorization=<approved-publish-action>
```

`inspect` fetches current refs, analyzes both synchronization stages, runs read-only checks, and returns a plan. `apply` prepares and validates updates in isolated checkouts. Without explicit authorization for the exact external refs, leave remote branches unchanged. Ordinary code contributions use the target repository's PR flow. For an explicitly authorized mirror sync, a direct ref update is allowed only on named maintained-fork refs, after verifying branch protection/rulesets and the observed old SHA. Use an exact `--force-with-lease=refs/heads/<branch>:<observed-old-sha>`; never use bare `--force`, update the parent repository, or bypass provider-enforced protections or required checks.

## Maintained repositories

`origin` identifies the maintained Jiwu Robotics fork. `upstream` identifies the fork's original parent, confirmed from GitHub fork metadata; never infer it from a repository name.

| Maintained fork | Original parent | Functional migration source | Purpose |
| --- | --- | --- | --- |
| `jiwu-robotics/spec-kit` | `github/spec-kit` | `feat/workflow-run-lease` | Core CLI and workflow lifecycle |
| `jiwu-robotics/adrkit` | `mbeacom/adrkit` | `adapt-spec-kit-current` | ADRKit CLI and Spec Kit adapter |
| `jiwu-robotics/spec-kit-workflow-preset` | `bigsmartben/spec-kit-workflow-preset` | `main` | Requirement Gate and planning artifacts |
| `jiwu-robotics/spec-kit-worktree-parallel` | `dango85/spec-kit-worktree-parallel` | `main` | Worktree isolation extension |

The functional source branch is only a migration input. Setup callers clone the maintained fork's `develop`, never the parent or migration branch.

## Safety rules

- Read each repository's `AGENTS.md`, contribution policy, branch-protection guidance, and open-PR limits before mutation. Verify both remote URLs and fork-parent identity. Select one GitHub transport; report its original error without silent fallback.
- Preserve dirty checkouts. Prepare candidates in disposable clones or isolated worktrees; never modify an existing user checkout to prepare updates.
- Fetch and record `upstream/main`, `origin/main`, and `origin/develop` (when present), plus the mapped migration source. Never trust stale local tracking refs.
- For an explicitly authorized mirror sync, set the candidate fork `main` to the exact fetched `upstream/main` commit. If the refs differ, update only `origin/main` with an exact lease against its observed SHA; if they already match, do not push. Do not create a merge commit when exact SHA identity is requested.
- Build `develop` from that parent-main commit plus only inspected, behaviorally required fork-specific changes. Validate the candidate before publishing. Rewriting shared `develop` requires explicit authorization for that exact ref; publish with an exact lease against the freshly observed `origin/develop` SHA.
- After each direct update, fetch again and verify remote SHA, tree, ancestry, and retained functional changes. If a provider rule blocks the direct update or the lease fails, stop instead of bypassing it.
- For a new `develop`, derive it from the updated fork `main`; carry only functional migration commits whose behavior is absent from both updated `main` and `develop`.
- Never cherry-pick the complete range `origin/main..source-branch` or every commit reported by `git cherry`. Inspect each proposed patch and its behavior. Patch equivalence is evidence, not proof.
- Preserve the newer parent implementation when resolving conflicts. Do not choose an entire file side merely to clear markers. If conflicts reveal incompatible or removed functionality whose intended replacement is unclear, abort the isolated candidate, list exact conflicts, and do not publish.
- Run repository-defined and behavior-specific regressions on every candidate. A passing test on the old fork `main` does not prove compatibility with current parent `main`.
- A ref synchronization is not approval to upgrade CLI, extension, preset, or package versions. Report version drift separately and stop before changing the reviewed baseline without explicit approval.

## Procedure

### 1. Inspect

For every requested repository:

1. Locate or create a disposable clone. Verify `origin` is the maintained fork and `upstream` is its GitHub parent.
2. Fetch the exact parent `main`, fork `main`, fork `develop` (if present), and migration-source refs. Record their SHAs and available protection, PR, and review requirements.
3. Compare fork `main` with parent `main`; classify fork-only commits and detect conflicts or incompatible changes before preparing a candidate.
4. Compare `develop` with the fetched fork `main`. Classify migration commits as already present, functionally represented, missing, unrelated, or unclear.
5. Identify required checks and provide a per-repository plan, exact target refs, old/new SHAs, and any blockers. `inspect` performs no branch creation, commit, push, PR, or merge.

### 2. Prepare and validate

In `apply`, work only in a disposable clone or isolated worktree:

1. Prepare the fork `main` candidate as described above. For mirror mode, it must be exactly the fetched parent `main` commit.
2. Prepare a separate `develop` candidate based on the new fork `main`, carrying only reviewed fork-specific functional changes. Use ordinary merge/PR flow unless the Human explicitly authorized rewriting that exact shared `develop` ref.
3. Run the repository's documented checks and feature regressions. At minimum:
   - Spec Kit: tests for affected workflow leases/remediation/state, workflow assets, path-only setup, and Copilot co-installation.
   - ADRKit: `bun install --frozen-lockfile`, `bun run build`, and `bun test packages/adapters/spec-kit/test` when the adapter changes.
   - Workflow preset and worktree extension: their repository-defined validation and tests for the affected behavior.
4. Read back each candidate's `HEAD`, merge parents, clean status, and test results. Do not publish a failed, dirty, or partially resolved candidate.

### 3. Publish and verify

- Without explicit publication authorization, return validated local candidates and exact target refs; remote refs remain unchanged.
- For ordinary contributions, use the target repository's PR flow. For explicitly authorized mirror sync, update only the named maintained-fork refs with exact `--force-with-lease` values; never update parent refs or bypass provider-enforced gates.
- Publish `main` first, fetch and verify its exact SHA, then publish `develop` if separately authorized; read back both remote refs after each push.
- Report per repository: parent `main` SHA, fork `main` SHA, fork `develop` SHA, retained/skipped functional changes, checks, force-with-lease expected values, and blockers.

## Completion criteria

Completion requires every requested fork's remote `main` SHA to equal its parent `main` SHA and every requested `develop` to be based on that exact commit plus verified functional fork-specific changes. A local candidate, pushed branch, or open PR is not proof of synchronization. Report only refs confirmed by a fresh remote readback.
