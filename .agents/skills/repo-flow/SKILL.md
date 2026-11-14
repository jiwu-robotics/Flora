---
name: repo-flow
description: Coordinate repository commits, GitFlow branches, pull requests, merges, and releases while following the conventional-commit and git-workflow Skills.
compatibility: Requires Git, the repository's configured commit hooks, and provider CLI access for pull requests, merges, tags, and releases.
metadata:
  author: multica-speckit
  source: project-maintained
---

# Repo Flow

`repo-flow` is the repository-provider workflow Skill and command catalog for
the project. It does not replace either required policy Skill:

- Read and follow `conventional-commit` before staging or creating any commit.
  Every ordinary commit must use the repository's scoped Conventional Commit
  format and exactly one final `Work-Item` footer.
- Read and follow `git-workflow` before changing branches, opening a pull
  request, merging, creating a release branch, tagging, or publishing a
  release. The target project must use the configured external `git-workflow`
  source; this package must not vendor or replace that Skill.

The package owns the complete `pp-*.md` project command catalog, including
Multica login, deployment, upgrade, and orchestrator commands. Commands that
operate a specialized Multica subsystem continue to delegate to that named
Skill; packaging them here keeps one release artifact and one generated command
catalog without changing their execution ownership.

## Workflow boundary

This Skill operates only after the Human explicitly requests the corresponding
workflow. It may use the repository provider CLI for the requested branch, pull
request, merge, tag, and release operations, but it must read back every remote
result before reporting success.

Use the repository's GitFlow contract:

- `feature/<owner>/<branch-work-item-token>-<slug>` and
  `fix/<owner>/<branch-work-item-token>-<slug>` start from current
  `origin/develop` and target `develop`.
- `release/<version>` starts from `develop` and targets `main`.
- After a release reaches `main`, back-merge `main` into `develop`.
- Manual work items use the next sequential `MANUAL-NNN` identifier when no
  canonical work item was supplied.

## Required gates

1. Confirm the repository root, current branch, remote, and worktree state.
2. Preserve unrelated user changes, including staged and untracked files.
3. Read current branch heads and provider state before branch or PR mutation.
4. Stage exact files, inspect the staged diff, and run the required checks.
5. Never commit directly to `main` or `develop`.
6. Never use `--no-verify`, `--amend`, reset, rebase of shared branches,
   cherry-pick, force-push, or an automatic conflict workaround for this
   repository's ordinary branch workflow. The sole external-ref exception is an
   explicitly authorized `speckit-upgrade-refs` mirror sync of named Jiwu fork
   refs, using an exact `--force-with-lease` after protection and old-SHA checks;
   it never applies to this repository's `main`/`develop` or parent refs.
7. Stop when policy, work item, version, required checks, or remote readback is
   missing or ambiguous.

A failed check is a blocker, not permission to bypass policy. A successful local
command is not remote evidence; read back the branch head, pull request state,
merge commit, tag, and release after each provider operation.

## Release gates

A release requires all of the following in order:

1. A reviewed release branch from current `develop`.
2. An incremental changelog generated with the repository release helper.
3. A release PR targeting `main` with passing checks.
4. An annotated version tag pointing at the merged `main` release commit.
5. A published provider release for the exact tag.
6. A back-merge PR from `main` to `develop` with passing checks.

Do not infer a release version when more than one semantic version is valid;
stop with `RELEASE_VERSION_REQUIRED` and report the candidates.
