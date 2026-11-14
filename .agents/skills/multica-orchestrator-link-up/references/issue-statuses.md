# Issue Status definitions

When supplied, validate these definitions in Multica Web under Workspace
Settings → Issue Statuses: `needs_triage/backlog`,
`needs_information/blocked`, `ready_for_agent/backlog`,
`ready_for_human/todo`, and `wontfix/cancelled`.

The CLI may use a known key but cannot administer definitions. Do not call a
private API and do not mutate a real Issue as a probe. Missing or conflicting
Human attestation does not block `WorkspaceFoundationRef.v6`; emit
`status_contract.state=HUMAN_CONFIRMATION_REQUIRED` and list the five mappings as
the final Human reminder.
