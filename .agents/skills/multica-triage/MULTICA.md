# Multica Platform Adapter

This file adapts the upstream triage method to Multica. The reusable workflow
lives in `SKILL.md`; project facts live in `.multica/agents/` and MUST NOT be
repeated here when they can drift.

## Required project configuration

This reusable skill contains no workspace UUID, project ID, repository URL,
label UUID, credential, or deployment value. Before triage, confirm that all
support files are readable from the target repository:

- `.multica/agents/issue-tracker.md`: portable project/repository, Issue
  identity, external Issue/PR policy, and parent/dependency conventions;
- `.multica/agents/triage-mapping.md`: canonical type label names/colors,
  custom status display-name/key/category, and authorized operations;
- `.multica/agents/domain.md`: target repository, vocabulary,
  architecture/specification/ADR pointers, and rejection knowledge-base path.

If legacy `docs/agents/` configuration, `.multica/agents/triage-labels.md`, or
both old and new mappings exist, stop for configuration migration; never choose
one silently. Use `multica-orchestrator-nail-down` to inspect or realign the
project.

If a required file/value is missing, contains a placeholder, or differs from
the authenticated live workspace and current binding handoff, stop and report
configuration drift. Never guess a label ID, status key/category, project,
source repository, or permission boundary. Live IDs and receipts stay in
operator-local handoffs; tokens, cookies, and CLI config secrets stay out of
both project files and reusable Skills.

## CLI baseline

Use the official `multica-cli` skill and the local authenticated CLI. Before a
write, verify the intended identity and workspace:

```bash
multica version
multica auth status
multica config show
multica workspace list --output json
multica workspace switch <workspace-id-or-slug>
```

The CLI MUST be at least `0.4.26`. Prefer `--output json` for reads and parse
the returned IDs rather than scraping tables. Use the configured server and
workspace; do not call private HTTP endpoints or use `curl` as a substitute for
CLI or Web operations.

Useful read operations include:

```bash
multica issue get <issue-id> --output json
multica issue comment list <issue-id> --roots-only --summary --compact --output json
multica issue comment list <issue-id> --thread <comment-id> --tail 30 --compact --output json
multica issue label list <issue-id> --output json
multica issue metadata list <issue-id> --output json
multica issue pull-requests <issue-id> --output json
multica issue runs <issue-id> --output json
multica label list --output json
```

## State and label operations

The type labels are mutually exclusive: the final item has exactly one of
`bug` or `enhancement`; preserve every non-type label. Before a write, run
`multica label list --output json` in the explicit workspace and require exactly
one live label whose name and color match the portable mapping. Use that
readback UUID; never use an ID committed in a repository or copied from another
workspace.

Before writing, read the Issue labels and workspace mapping. If the desired type
is absent, add it first; then remove the obsolete mapped type. This avoids
leaving the Issue untyped if the first write fails, though a failed removal may
temporarily leave a visible conflict. Read back after both writes. Report any
partial result and do not describe the classification as complete until exactly
one mapped type remains.

```bash
multica issue label list <issue-id> --output json
multica issue label add <issue-id> <desired-label-uuid>
multica issue label remove <issue-id> <obsolete-label-uuid>
multica issue label list <issue-id> --output json
```

Custom status definitions are administered in Multica Web. The CLI can consume
an existing custom status key but cannot list, create, or edit the definition.
The project's validated display name, key, and category are one contract. If the
live key or category differs from the mapping, do not silently adapt the skill;
require an authorized configuration decision and update the project mapping only
after the platform configuration is settled.

`needs_information` is a `blocked` checkpoint that waits for external evidence.
`ready_for_agent` is a `backlog` dispatch gate; only the authorized dispatch
transition to built-in `todo` starts the assigned agent. `ready_for_human` is a
`todo` status for a workspace member or no assignee; never assign an agent or
Squad while an Issue has that status.

Do not create a `triage_state` property or metadata key. Issue Status is the
only triage-state record. Formal execution statuses are `todo`, `in_progress`,
`in_review`, and `done`, plus applicable platform terminal/error states.

## Write modes and side-effect control

### `inspect`

Read-only. Do not modify Issues, comments, labels, metadata, properties,
subscribers, status, repository files, PRs/MRs, or execution state.

### `apply`

Apply only the maintainer-authorized classification and triage result. This may
write type labels, custom status, triage notes, a current Brief, or an authorized
out-of-scope record. It MUST NOT start an agent or implementation run.

List the intended writes before execution. Use `--no-start` for every
recording-only status, assignment, or update:

```bash
multica issue status <issue-id> <status-key> --no-start
multica issue assign <issue-id> --to-id <user-or-agent-id> --no-start
multica issue update <issue-id> --status <status-key> --no-start
```

Positive recording-only example:

```bash
multica issue runs MUL-42 --output json
multica issue status MUL-42 ready_for_agent --no-start
multica issue get MUL-42 --output json
multica issue runs MUL-42 --output json
```

Counterexample — this is not `apply` because the missing flag may enqueue work:

```bash
multica issue status MUL-42 ready_for_agent
```

Comments MUST be UTF-8 files inside the current working directory and MUST start
with the AI-generated disclaimer. When a comment triggered the work, reply with
`--parent <trigger-comment-id>`; do not attach to an unrelated thread merely to
satisfy the flag. Omit `--parent` only for a new top-level triage discussion.
Delete the temporary content file after a successful write.

Do not mention an agent, squad, member, or `@all` unless the resulting enqueue or
notification is explicitly authorized. External PR/MR close, merge, branch
write, and review actions are outside ordinary `apply` authorization.

After an apply batch, read back the Issue, labels, status, and relevant comment
thread. A status write without `--no-start` is a dispatch attempt, not a harmless
recording correction.

### `dispatch`

Before dispatching, verify:

- exactly one type label and the current complete Brief version;
- dependencies and required permissions;
- intended exact Squad identity;
- Issue status/assignee and all existing queued/running executions.

For a Workspace managed by Multica Orchestrator, authorized intake prebinds the
exact Feature/Fix Squad without starting it, then performs exactly one native
`todo` transition. The assignment wakes the Squad Leader. The Leader—not triage
and not relocation—resolves the ACTIVE local release and runs
`admit-or-resume`; that operation only creates/reuses local admission identity.

```bash
multica issue runs <issue-id> --output json
multica issue assign <issue-id> --to-id <exact-squad-id> --no-start
multica issue status <issue-id> todo
multica issue runs <issue-id> --output json
```

Do not invoke a `multica-orchestrator-relocate ... dispatch` command: it does
not exist. Do not start a second run by repeating assignment, status, update,
mention, rerun, or cancellation. The native Leader evaluation records the
admission only after its exact Issue/Squad/run/runtime readback succeeds.

Counterexample — two commands may each start work:

```bash
multica issue assign MUL-42 --to-id <agent-id>
multica issue status MUL-42 todo
```

Counterexample — a timeout does not authorize a blind second start:

```bash
multica issue status MUL-42 todo
multica issue status MUL-42 todo
```

After an ambiguous first result, read `issue runs` and the relevant
`run-messages`; retry only when evidence proves no run was enqueued and the
maintainer still authorizes dispatch.

Read back the Issue and run state after the start. If an equivalent run is
already queued or active, report its task ID and do not dispatch again. If the
start command errors or times out, inspect runs and run messages before any
retry; a transport error does not prove the server failed to enqueue work.

Changing Issue Status does not stop an existing run. `rerun` and `cancel-task`
are disruptive, separately authorized operations and are not dispatch recovery
shortcuts.

## Failure and partial-write reporting

Maintain an operation ledger for every write batch: planned operation, exact
command, success/error, and readback state. If only part of classification,
comment, status, repository, or dispatch work succeeds:

- report each successful and failed operation separately;
- state the actual remaining labels/status/comment/run state;
- do not roll forward blindly or describe the intended final state as achieved;
- inspect execution history before retrying anything that could start work; and
- finish every reachable non-duplicating repair, otherwise name the exact manual
  or permission prerequisite.

The CLI does not cover every Multica surface. Custom Issue Status definition
management belongs to Multica Web. When an operation is unavailable, state the
limitation and direct the maintainer to the supported Web surface; never call a
private API to make the result look complete.
