# Issue tracker: Multica

Multica stores Issues, assignees, statuses, discussions, parent/child structure,
stages, and execution history. The code host stores source, pull requests,
reviews, and merge state. The repository stores durable domain knowledge, ADRs,
shared Agent configuration, and `.multica/out-of-scope/` decisions.

Replace angle-bracket placeholders with portable project values. Live server,
workspace, Project, label, runtime, Agent, Squad, member, or resource identifiers
remain in operator-local handoffs and must not be committed here.

## Project association

- Project name: `<project-name>`
- Code repository: `<canonical-repository-url>`
- Code host: `<GitHub>`
- Project subpath: `<repository-relative-project-root>`

Authentication remains operator-local. Resolve the active server/profile/account/
workspace from the current `ProjectBindingRef.v12` lineage and verify it live;
never commit a token, cookie, PAT, CLI configuration secret, or live identifier.

## Identity and routing

Resolve both identities for every Multica Issue: the UUID is `work_item_ref`;
the canonical routable key (for example `MUL-42`) is `work_item_id` and the
source for branch/footer identity. A GitHub Issue or PR is identified by its full URL or an explicit repository plus number. Never resolve a bare number across systems.

Feature/Fix integration branches use
`feature|fix/<owner>/<branch-work-item-token>-<slug>`, where the token is the
lowercase branch-safe form of the canonical key, not a bare number or Multica
UUID. Runtime-managed `agent/<agent>/<issue>` task branches remain per-run
checkout evidence and are never used as the PR source.

Keep the Multica Issue as the operational work record. Store source request and
PR URLs in the Issue or Brief. Code-host close, merge, and review operations
remain separately authorized provider actions.

## Read and write boundary

Prefer JSON reads and explicit profile/workspace scope:

```bash
multica issue get <issue-id-or-key> --output json
multica issue list --project <project-ref-from-current-handoff> --output json
multica issue comment list <issue-id> --roots-only --summary --compact --output json
multica issue pull-requests <issue-id> --output json
multica issue runs <issue-id> --output json
```

Use UTF-8 files inside the approved checkout for long descriptions and comments.
Delete temporary content files after successful readback.

`inspect` is read-only. Recording changes use `--no-start`. `dispatch` performs
exactly one deliberate start after current Brief, dependency, permission,
execution-admission, scope, lease, checkout, and existing-run checks.

Assignment, status changes, mentions, Issue creation, reruns, cancellation, and
dispatch are side effects. Agent/Squad mentions enqueue work; member mentions
notify people. Never use them for acknowledgement or setup verification.

## Parent/child work

Stages order groups of siblings. They are not an arbitrary dependency graph.
When a required dependency cannot be represented by the supported provider,
record a visible `Blocked by: <issue-key>` fallback and verify every blocker
before claim or dispatch. Do not claim platform enforcement for this convention.

## External request policy

- Discover external PRs: `<yes-or-no>`
- External contributor rule: `<repository-policy>`
- Intake rule: `<create-or-link-a-Multica-Issue-before-triage>`
- Code-host writes: `<inspect-only-or-separately-authorized>`

The ProjectBindingRef and provider controls are authoritative for actual project,
repository, checkout, notification, CI, and integration identities.
