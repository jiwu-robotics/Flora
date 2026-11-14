# Multica triage mapping

This portable file maps triage concepts to canonical workspace resource names.
Live label UUIDs, workspace IDs, and evidence receipts belong to the current
operator-local `WorkspaceFoundationRef.v6` and `ProjectBindingRef.v12`; they must
not be committed here.

## Type labels

A completed triage has exactly one type label. Preserve unrelated module, risk,
source, and ownership labels.

| Canonical type | Workspace label | Color |
| --- | --- | --- |
| `bug` | `bug` | `#ef4444` |
| `enhancement` | `enhancement` | `#3b82f6` |

At execution time, list labels in the explicitly selected workspace and require
exactly one name/color match before using its live UUID. Never trust an ID copied
from another workspace and never create a duplicate because resolution failed.

## Triage statuses

| Canonical role | Display name | Status key | Category |
| --- | --- | --- | --- |
| `needs-triage` | Pending Triage | `needs_triage` | `backlog` |
| `needs-information` | Needs Information | `needs_information` | `blocked` |
| `ready-for-agent` | Ready for Agent | `ready_for_agent` | `backlog` |
| `ready-for-human` | Ready for Human | `ready_for_human` | `todo` |
| `wontfix` | Won't Fix | `wontfix` | `cancelled` |

The current Foundation handoff must prove these definitions were verified in
Multica Web. A same-key wrong-category definition is a conflict. Do not create
`triage_state` metadata; Issue Status is the triage-state source of truth.

## Operational authorization

| Mode | Allowed | Not allowed |
| --- | --- | --- |
| `inspect` | Read Issues, comments, labels, metadata, PRs, repository context, and runs | Any Multica or repository write |
| `apply` | Explicitly authorized classification, status, comments, Briefs, and durable rejection records | Workspace administration, implementation starts, reruns, cancellations, external PR close/merge |
| `dispatch` | One deliberate start after all current gates | Duplicate starts, blind retries, unauthorized run interruption |

Use `--no-start` for status, assignment, and update operations that only record
work already underway.
