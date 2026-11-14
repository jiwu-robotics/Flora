---
name: conventional-commit
description: Create focused commits that satisfy this repository's Conventional Commit subject, scope, and required bullet-body policy.
metadata:
  author: multica-speckit
  source: adapted-from-github-awesome-copilot
---

# Conventional Commit

Create reviewable commits with a Conventional Commit subject and an evidence-bearing body. Use this Skill when the user asks to commit changes, prepare commit messages, split a change into commits, or verify commit history.

## Required format

Every commit message uses:

```text
<type>(<kebab-case-scope>)[!]: <imperative description>

- <concrete detail>
- <verification or second concrete detail>

Work-Item: <canonical-work-item-id-or-url>
```

Rules:

- `type` is one of `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `build`, `ci`, `chore`, `perf`, or `revert`.
- Scope is required and uses lowercase kebab case: `multica`, `speckit`, `commit-policy`, or `spec-002`.
- `!` is optional and marks a breaking change.
- The complete subject is at most 72 characters and uses imperative mood.
- One blank line separates the subject from the body.
- The body contains at least one non-empty Markdown bullet. Every body detail starts with `- ` on its own physical line.
- The final non-empty line is exactly one `Work-Item: <canonical-work-item-id-or-url>` footer. Use a canonical ID, or a credential-free HTTPS URL without query/fragment.

Examples:

```text
feat(multica): add reusable workspace initializer

- Add the workspace manifest and explicit reconciliation procedure.
- Preserve live workspace identifiers as CLI-read facts.

Work-Item: MULT-123
```

```text
fix(commit-policy)!: reject unscoped subjects

- Require lowercase kebab-case scope in every commit subject.

Work-Item: MULT-124
```

## Workflow

1. Read repository guidance and the complete current status.
2. Inspect unstaged and staged diffs. Preserve unrelated user work.
3. Split changes by responsibility so each commit is independently coherent.
4. Stage exact files or hunks for one responsibility.
5. Re-read the staged diff and check for missing callers, tests, docs, generated files, or secrets.
6. Construct a message in the required format, ending with the exact canonical Work-Item footer.
7. Run `python3 scripts/check_commit_message.py <message-file>` when the repository provides the validator.
8. Commit without bypassing hooks, then inspect the resulting commit before continuing with the next group.

Prefer a message file or multiple `-m` arguments so the blank line and physical bullet lines are preserved:

```bash
git commit \
  -m "feat(multica): add reusable workspace initializer" \
  -m "- Add the workspace manifest and reconciliation procedure." \
  -m "Work-Item: MULT-123"

Never combine unrelated changes merely to reduce commit count. Never use `--no-verify`, amend a commit the user did not authorize, rewrite shared history, or claim a commit or push succeeded without Git readback.
