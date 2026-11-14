# Runtime fleet foundation

Select every Human-approved Runtime required by the orchestration topology.
Each live readback must be uniquely `online`; aliases and Runtime refs must be
unique. A Runtime profile describes an executable/protocol mapping and does not
register an online Runtime. Create a profile only when explicitly requested and
supported.

Only approved `apply` on an intended Runtime machine may start its daemon. Never
start a duplicate daemon, bind an offline Runtime, guess a Runtime UUID, or start
a daemon during `inspect` or `plan`. Re-read the complete
`runtime list --output json` after every Runtime operation. The Foundation
membership digest covers sorted aliases, Runtime refs, daemon refs, provider,
status, and capability revision so downstream placement cannot silently drift.
`capability_revision` is the SHA-256 of
`multica-orchestrator.runtime-capability-evidence.v1`: Runtime ref, daemon ref,
provider, optional mode/version, and the sorted capability set. Heartbeat,
timestamps, display names, and unrelated Runtime metadata are deliberately
excluded. Conflicting top-level and `metadata.capabilities` readbacks are
ambiguous and block publication.
