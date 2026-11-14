# Workspace and labels

Read identity and workspace state before every plan. Match a workspace by exact
UUID when supplied; a same-name object with incompatible server/account identity
is a conflict. Creation requires explicit `apply` authorization and must be read
back before any workspace-scoped operation is planned.

Preserve unrelated labels. Reuse `bug` only at `#ef4444` and `enhancement` only
at `#3b82f6`. A same-name wrong-color label is a conflict requiring a separately
approved update; never create a suffixed duplicate or delete a label to converge.

Every workspace-scoped CLI command must include the selected profile and explicit
workspace UUID. Live UUIDs remain in restricted operator-local state.
