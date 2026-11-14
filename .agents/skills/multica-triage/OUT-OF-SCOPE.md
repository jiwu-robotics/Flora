# Out-of-Scope Knowledge Base

The target project's `.multica/out-of-scope/` directory stores durable,
concept-level records of enhancements that maintainers explicitly rejected. It
preserves reasoning and lets later triage surface the decision without treating
Multica comment history as the only institutional memory.

This skill file defines the rule. Actual records belong in the target
repository identified by `.multica/agents/domain.md`, never in the reusable
skill package and never as a parallel Multica metadata database.

## Directory structure

```text
.multica/out-of-scope/
├── dark-mode.md
├── plugin-system.md
└── graphql-api.md
```

Keep one kebab-case file per concept, not per Issue. Group later explicitly
rejected requests for the same concept under the active record.

## File format

Records are readable decision documents. Every source must have a canonical URL;
a bare Issue number, copied title, or Multica mention alone is insufficient.

Use relaxed explanatory prose rather than database-like fields alone. Diagrams,
code/configuration excerpts, and examples are welcome when they make the durable
reason understandable to someone who never saw the original discussion.

### Positive example

```markdown
# Dark Mode

**Decision status:** active rejection
**Decision owner:** product maintainer
**Decision date:** 2026-08-30

This project does not provide user-facing dark mode or runtime theming.

## Why this is out of scope

State the durable product, architectural, technical, or strategic reason. Do not
use temporary workload, staffing, access, or scheduling constraints as a
rejection rationale.

Strong reasons normally point to one or more of:

- an explicit project scope or product boundary;
- a technical constraint or conflict with the accepted architecture; or
- a durable strategic decision and its tradeoff.

“We do not want it,” “not now,” or “too much work” is not sufficient.

## Prior requests

- MUL-42 — https://multica.example/workspaces/acme/issues/MUL-42
- PR #314 — https://github.com/acme/product/pull/314
```

When a source is a linked PR/MR, record both its canonical code-host URL and the
Multica Issue URL that owns the triage decision.

### Counterexample

```markdown
# Dark Mode

We are too busy to do this right now.

## Requests

- #42
```

Do not write this record. It turns a temporary resource constraint into a
durable product rejection, omits decision status/owner/date, supplies no
canonical source URL, and does not explain a stable scope or architectural
reason. Close or defer the Issue according to the actual decision without
polluting `.multica/out-of-scope/`.

## When to check

During context gathering, read all active
`.multica/out-of-scope/*.md` records. Match by concept, not just keywords.
Surface a similar record, its durable reason, source links, and current decision
status to the maintainer before recommending an outcome.

A withdrawn record is historical evidence, not an active rejection. Do not use
it to classify a new request as `wontfix`.

When a new request resembles an active record, present three distinct decisions:

- **Confirm:** the maintainer explicitly confirms the same rejection still
  applies; append the complete new source URL and conclude the Issue.
- **Reconsider:** remove or withdraw the active record and continue normal
  triage under the new decision.
- **Distinct:** leave the record unchanged because the concepts differ, and
  continue normal triage for the new request.

Similarity alone never authorizes a record update or `wontfix`.

## When to write

Write or update a record only when all are true:

1. the item is an `enhancement`;
2. the maintainer explicitly rejects the concept rather than deferring it;
3. the target repository and canonical source URLs are known; and
4. the `wontfix` conclusion is authorized.

Do not create or update a rejection record for:

- bugs;
- behavior already implemented;
- a duplicate closed without a new rejection decision;
- work already tracked elsewhere;
- temporary lack of time, budget, access, staff, or deployment availability; or
- a request merely waiting for information.

For a new concept, create one record with decision owner/date, durable reason,
and complete source URLs. For an existing active concept, update it only when
the maintainer confirms the same rejection applies and the new source belongs in
its history. Post the AI-disclaimed Multica conclusion, reference the repository
path and canonical repository URL when available, then apply the authorized
`wontfix` status with recording-only semantics.

A local uncommitted path is not yet a durable external link. If the record will
be delivered through a commit or PR, say so and link the resulting repository
URL when it exists; do not claim the Issue already points to a readable record.

## Already implemented and rejected bugs

For already implemented behavior, point to the current implementation and close
with the authorized Multica status without writing
`.multica/out-of-scope/`. For a rejected bug report, explain why the claimed
defect is not accepted and record the Issue conclusion only; the rejection
knowledge base is enhancement-only.

## Withdrawing or changing a decision

When the maintainer reverses an active rejection:

- remove the file, relying on repository history for the old decision; or
- change `Decision status` to `withdrawn` when the project intentionally keeps a
  visible historical record, and state the replacement decision/date.

In both cases, update the Multica discussion with the repository change and let
the new request proceed through normal triage. Do not silently reopen or
dispatch old Issues. Ensure withdrawn records are excluded from active
prior-rejection matching.
