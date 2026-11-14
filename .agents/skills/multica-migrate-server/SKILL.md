---
name: multica-migrate-server
description: "Migrate or disaster-restore one Docker Compose Multica self-hosted service onto a replacement server, including PostgreSQL state, uploaded files, deployment configuration and required encryption keys, with verified snapshots, an explicit traffic cutover, and a bounded rollback path. Use when a Multica service host is being replaced or recovered; do not use for Runtime-host Project activation."
compatibility: Requires two SSH-accessible service hosts or one verified migration bundle, Docker Engine, Docker Compose v2, Git, Python 3, tar, sufficient protected staging space, and a maintenance window.
metadata:
  author: multica-speckit
  source: project-maintained
---

# Multica Migrate Server

Move the service plane created by `multica-deploy` to a replacement host without changing the Multica release during the move. Preserve the database, uploads, deployment secrets, and every classified deployment-owned persistent mount. Restore and verify the replacement before an explicit routing cutover.

This Skill is explicit-invocation only. It can stop a production service, copy sensitive state, restore a database, and recreate containers. Default to `mode=inspect`; no invocation implicitly authorizes downtime, DNS, firewall, reverse-proxy, certificate, source deletion, or an application upgrade.

This is not `multica-orchestrator-migrate`. That Skill activates one Project binding on Runtime hosts. This Skill migrates the central Web/API/PostgreSQL service. It never copies `~/.multica`, browser state, PATs from client profiles, daemon state, repositories on Runtime hosts, or coding-agent credentials. Cutover does own reconnecting explicitly declared existing Runtime hosts through their machine-local profiles and proving that their existing Runtime records return online.

## Mandatory raw prompt and report capture

This section takes precedence over every lower-level instruction to redact,
omit, or avoid saving invocation or report content. Every direct invocation
must create an exact local record before reading any source or taking another
action.

1. Resolve this installed Skill package's `scripts/prompt_and_report_capture.py`.
   Before proceeding, run its `start` command with this Skill's frontmatter
   `name` and `--cwd "$PWD"`. Supply the complete triggering user instruction
   to standard input as exact bytes, never as a command-line argument.
2. Preserve the returned `capture_id`. The helper writes
   `./.prompt-and-report/<capture_id>.prompt.md`; it creates the directory with
   mode `0700`, the file with mode `0600`, and adds `/.prompt-and-report/` to
   local Git `info/exclude` when the invocation directory is a Git worktree.
3. Do not redact, summarize, normalize, reformat, replace, or omit any prompt
   or report content in this archive. Keep the archive local: never commit it,
   include it in a migration bundle, copy it into a repository artifact, or
   send it to Multica, GitHub, chat, Issue, PR, or ordinary logs.
4. On every terminal path—`complete`, `partial`, `blocked`, error, or
   interruption—before replying to the user, run the helper's `finish` command
   with the same `capture_id` and `--cwd "$PWD"`. Supply the exact final report
   bytes on standard input. It writes the paired
   `./.prompt-and-report/<capture_id>.report.md` without overwriting any record.
5. Do not claim the invocation completed if either archive operation fails;
   report the capture failure directly.

This private raw archive is the sole exception to the Skill's requirements not
to persist sensitive information. It does not permit exposing sensitive
information outside the archive or placing it in generated deliverables.

## Invocation contract

Planned migration from a live source:

```text
/multica-migrate-server mode=<inspect|plan|apply|cutover|reconnect-runtimes|rollback> \
  source_host=<named-ssh-host> target_host=<named-ssh-host> \
  [source_dir=/opt/app/multica] [target_dir=/opt/app/multica] \
  [transfer_dir=<absolute-private-path>] \
  [origin=<preserve|change>] [authorization_ref=<non-secret-change-ref>]
```

Disaster restore when the source is unavailable:

```text
/multica-migrate-server mode=<inspect|plan|restore> \
  backup_path=<absolute-path-to-verified-bundle> \
  target_host=<named-ssh-host> [target_dir=/opt/app/multica] \
  [origin=<preserve|change>] [authorization_ref=<non-secret-change-ref>]
```

Post-cutover Runtime recovery:

```text
/multica-migrate-server mode=reconnect-runtimes \
  target_host=<named-ssh-host> \
  runtime_host=<named-ssh-host>/<profile> [...] \
  authorization_ref=<non-secret-change-ref>
```

Machine-readable handoff after Runtime recovery:

```text
/multica-migrate-server mode=emit-receipt \
  evidence=<private-server-migration-evidence.json> \
  plan=<reviewed-migration-plan.json> \
  target_readback=<exact-authoritative-target-readback.json> \
  output=<new-private-server-migration-receipt.json>
```

Defaults are `mode=inspect`, both install directories `/opt/app/multica`, and `origin=preserve`. A named SSH host must come from reviewed SSH configuration and use strict host-key checking. Never put passwords, private keys, tokens, `.env` values, cookies, verification codes, or database content in invocation arguments.

Mode behavior:

- `inspect`: read-only inventory of source, target, deployment, dependencies, capacity, listeners, route ownership, and declared Runtime hosts.
- `plan`: read-only plan with the exact release, image digests, data set, staging sizes, target changes, verification matrix, cutover mechanism, Runtime reconnection set, and rollback boundary.
- `apply`: requires `authorization_ref`; quiesces the source, creates and verifies a protected snapshot, transfers it, restores the target, and stops at `TARGET_READY`. It does not change public traffic.
- `restore`: requires `authorization_ref`; restores a previously verified bundle and stops at `TARGET_READY`. It cannot claim point-in-time freshness that the bundle does not prove.
- `cutover`: requires separate explicit routing authorization and a `TARGET_READY` readback from the same plan. It moves only the declared route or DNS record, reconnects required existing Runtime hosts, verifies clients and Runtimes, and leaves the source service stopped.
- `reconnect-runtimes`: requires `authorization_ref` and an authoritative target readback. It repairs machine-local endpoint/profile/daemon connectivity for declared existing Runtime hosts after cutover without changing service-plane data or routes.
- `rollback`: allowed only before the target has accepted writes. It restores the prior route and resumes the unchanged source. After target writes, recovery is fix-forward or a new reverse migration.
- `emit-receipt`: validates a completed target-authoritative migration and writes
  `ServerMigrationReceipt.v1`. It is read-only with respect to both servers and
  requires `source_service_state=stopped`, `runtime_state=RUNTIMES_READY`, and
  `final_state=RUNTIMES_READY|OBSERVING`.

Never infer routing ownership, an outage window, an alternate port, a replacement address, or permission to delete the old host. If either host requires interactive SSH authentication, request the password or key path only in the interactive terminal; never accept or retain it in chat.

## Source-of-truth data set

The reviewed upstream Compose deployment currently persists:

- PostgreSQL at the `postgres` service mount `/var/lib/postgresql/data`;
- backend-managed uploads at `/app/data/uploads`;
- `.env`, including the PostgreSQL password, JWT signing secret, integration encryption keys, mail/OAuth settings, and endpoint configuration;
- deployment-owned Compose overlays and proxy configuration;
- optional proxy volumes such as Caddy data/config when the proxy is part of the deployment.

That list is evidence, not an allowlist for all future releases. Read the source's exact pinned checkout and rendered Compose model. Inspect every service mount and classify every writable named volume and bind mount as one of:

1. `database-logical`: export with `pg_dump`; never copy a live PostgreSQL data directory;
2. `deployment-data`: quiesce its writer, archive it, checksum it, and restore it;
3. `deployment-config`: copy as a protected file, then apply only reviewed target-specific edits;
4. `external-service`: do not copy; prove the target can reach the same authorized dependency;
5. `ephemeral`: exclude only with evidence that recreation is safe;
6. `unknown`: stop planning until the operator classifies it.

A current default migration therefore includes a logical PostgreSQL dump and the complete `backend_uploads` volume. Database rows may contain encrypted integration credentials; the matching deployment encryption keys in `.env` are required to recover them. Copying only `pgdata`, only `.env`, or only the Git checkout is incomplete.

External S3/object storage, Redis, database replicas, SMTP/Resend, OAuth, GitHub App, Lark, Slack, VCS, WeCom, DNS, and external reverse proxies remain external. Preserve their references without printing values, verify target reachability, and obtain separate authorization for provider-side callback, allowlist, DNS, certificate, or secret changes.

## Non-negotiable invariants

1. **Same release first.** Record source tag, commit, rendered Compose files, platform, container image IDs, and registry digests. Restore the same application release and PostgreSQL major version. Upgrade only after migration acceptance and a new backup.
2. **One writer.** Before the final snapshot, stop every service that can mutate PostgreSQL or persistent files. Keep public traffic away from the target until restore verification succeeds. Never run source and target as writable peers.
3. **Logical database backup.** Use `pg_dump --format=custom` from the source PostgreSQL container and require its own zero exit status. Never archive a mounted live PostgreSQL data directory and never hide `pg_dump` failure behind a compression pipeline.
4. **Protected artifacts.** Snapshot and transfer directories are mode `0700`; dumps, archives, `.env`, manifests containing sensitive paths, and the final bundle are mode `0600`. Transfer only through authenticated, encrypted transport. Store them only on an approved encrypted filesystem; if a bundle leaves that boundary or is retained offline, envelope-encrypt it with an operator-approved key and tool. File modes are not encryption. Never invent a passphrase, place one in command arguments, or commit, upload, chat, or log these artifacts.
5. **Hash every byte.** Hash each payload before packaging, hash the package on source and target, and require exact equality before restore. A successful copy command alone is not verification.
6. **Fresh target state.** Refuse any target directory, Compose project, volume, database, or relevant listener that contains unknown or user-owned state. Never restore with `docker compose down -v` as cleanup.
7. **No hidden host changes.** Do not modify Docker daemon settings, firewall, NAT, DNS, reverse proxy, registry mirror, certificate store, or unrelated services without explicit scope.
8. **Rollback is time-bounded.** Source restart is safe only while the restored target has accepted no writes. Backend startup, automatic migrations, schedulers, outbound integrations, Runtime reconnects, and health-related persistence all count as possible writes—not only public user traffic. Unless a release-supported read-only mode proves otherwise, starting the target backend makes the target authoritative.
9. **No source retirement.** Successful cutover does not authorize deleting the snapshot, volumes, checkout, or old server. Retention and destruction are separate operator actions.
10. **No secret readback.** Report file names, modes, sizes, hashes, key names, and presence only. Never print complete `.env` lines or database rows.
11. **Existing Runtime identity.** Never copy Runtime-host profiles or tokens and never replace offline rows with duplicate registrations. Inventory the machine-local profile, daemon ID, Runtime IDs, providers, Workspace, endpoint, and launcher `PATH`; reconnect the same daemon and require the same Runtime rows online. A host that also contains the retired source service may run its Runtime daemon, but must not restart the old service containers.

## Migration state machine

Use these exact states in the plan and handoff:

```text
DISCOVERED
  -> PLANNED
  -> SOURCE_QUIESCED
  -> SNAPSHOT_VERIFIED
  -> TRANSFER_VERIFIED
  -> TARGET_RESTORED
  -> TARGET_WRITER_STARTED
  -> TARGET_READY
  -> CUTOVER_APPROVED
  -> CUTOVER_VERIFIED
  -> RUNTIME_RECONNECTING
  -> RUNTIMES_READY
  -> OBSERVING
```

`apply` may advance only through `TARGET_READY`. `cutover` begins only from a matching `TARGET_READY` plan and may enter `OBSERVING` only after `RUNTIMES_READY`. When the reviewed plan declares no required Runtime hosts, record an explicit `not_applicable` Runtime set before `RUNTIMES_READY`; an uninspected or offline Runtime fleet is not `not_applicable`. `reconnect-runtimes` resumes a target-authoritative migration at `RUNTIME_RECONNECTING`.

`TARGET_WRITER_STARTED` marks the conservative authority boundary unless a release-supported read-only mode proves that no target write is possible. Record `SOURCE_RESUMED` only for a rollback completed before that boundary. Record `FIX_FORWARD_REQUIRED` if target writes may have occurred; never label that condition rollback-safe.

Each state transition must have evidence: command exit status, exact plan identifier, host identity, release/image readback, payload hashes, Compose status, readiness response, or client/Runtime readback. Any changed host identity, source release, mount inventory, bundle hash, target contents, routing record, or plan input invalidates the plan.

## 1. Read-only discovery

Inspect source and target before creating a snapshot. Use [`references/migration-runbook.md`](references/migration-runbook.md) for reviewed command shapes.

On the source, capture without secrets:

- host identity, architecture, free disk/inodes, clock, Docker and Compose versions;
- install directory identity, Git origin, exact tag/commit, clean/dirty status, and deployment-owned local files;
- Compose project name, config file set, profiles, services, container IDs, health, image references, image IDs/digests, and published bindings;
- every named volume and bind mount, its writer, size, ownership requirements, and classification;
- PostgreSQL server major version, database name/user names, database size, extension list, and dump compatibility—never passwords or rows;
- non-empty external-integration key names only, plus target reachability requirements;
- current Web/API/WebSocket origins, DNS/proxy owner, TTL, certificate strategy, and whether the source host also runs an unrelated daemon or proxy.
- on every declared Runtime host, its pinned SSH alias, machine-local profile name, current API/App endpoints, account/Workspace readback, daemon status and ID, existing Runtime IDs/providers/status, and the exact `PATH` or service environment that resolves each working provider launcher. Record these values without profile tokens or environment secrets.

On the target, prove Docker/Compose prerequisites, capacity for the checkout plus at least two protected bundle copies and restored volumes, source/registry reachability, free listeners, intended bind address, and absence of conflicting directory/project/volumes. Inventory unrelated services before proposing any change.

For `backup_path`, verify its manifest, file modes, whole-bundle hash, per-file hashes, source release, PostgreSQL major, snapshot completion marker, and data-set classifications before trusting it. A directory containing plausible files without a valid manifest is not a migration bundle.

## 2. Produce a deterministic plan

The plan is operator-local and contains no secret values. Record:

- a plan identifier derived from the canonical plan bytes;
- source and target SSH host aliases plus non-secret host fingerprints/identities;
- exact release tag/commit and source image digests;
- Compose project/config set and target-specific config edits;
- every included/excluded volume and bind mount with its classification and writer;
- database export/restore commands, expected PostgreSQL major, estimated sizes, and free-space margin;
- bundle staging locations, modes, hashes to collect, transfer route, and cleanup/retention policy;
- maintenance start, source quiesce order, target restore order, and maximum acceptable outage;
- origin strategy, route owner, TTL state, TLS strategy, exact separately authorized cutover action, and per-Runtime-host endpoint change;
- verification from target host, a separate client, an authenticated existing client, and each required Runtime/daemon;
- the required existing Runtime ID set, owning daemon IDs, provider version probes, machine-local profiles, and expected post-cutover status;
- the last rollback-safe transition and the condition that makes the target authoritative.

Prefer `origin=preserve`: keep the canonical Web/API hostnames and move routing after target verification. This preserves browser/API/daemon configuration and most provider callbacks. If origins change, list every `.env` URL, OAuth callback, webhook, CORS, cookie, plugin surface, daemon profile, certificate, and external allowlist requiring an explicit update; do not silently rewrite them.

When Skill-owned Caddy is detected, require one explicit TLS choice:

- `external`: target uses separately managed proxy/certificates; exclude Caddy volumes;
- `reissue`: recreate certificates on the target after routing prerequisites are satisfied;
- `migrate`: include Caddy data/config as secrets, restore them while Caddy is stopped, and verify ownership and certificate names.

## 3. Quiesce and snapshot

Immediately before stopping writes, re-read the source plan preconditions. If they changed, stop and re-plan.

1. Record the maintenance start and, if separately authorized, make the existing proxy serve a maintenance response.
2. Stop frontend, backend, workers, and every discovered writer. Stop unknown services rather than guessing. Start only PostgreSQL if needed for the dump.
3. Confirm no application writer is running.
4. Create a custom-format database dump inside the PostgreSQL container. Copy it into the protected snapshot directory only after `pg_dump` succeeds.
5. Stop PostgreSQL. Archive every `deployment-data` volume while all writers are stopped. Never archive the raw PostgreSQL volume.
6. Copy `.env` and each approved deployment config with mode `0600`. Do not copy Git metadata as the source of release identity; materialize the exact tag/commit independently on target.
7. Write a non-secret manifest with release, image, Compose, database-version, classification, file-size, and SHA-256 evidence. It may name secret files but never include their contents.
8. Hash all payloads, create the protected bundle, hash the bundle, and verify it can be listed/read without errors.

Leave the source quiesced after the final snapshot. Restarting it before cutover decision invalidates the one-writer proof and requires a new final snapshot.

## 4. Transfer and restore

Use pinned SSH host aliases with strict host-key checking. A direct `scp -3` or an approved equivalent may transfer the protected bundle through the coordinator without persisting a second coordinator copy. If local staging is required, use a private directory and remove it after target hash verification according to the plan.

On the target:

1. Recheck host identity, capacity, directory/project/volume absence, ports, and unrelated services.
2. Materialize the exact source release tag and commit. Pull the exact source image references and verify platform plus image digests. Do not substitute `latest` or upgrade.
3. Transfer the bundle into a mode-`0700` directory, set the file mode to `0600`, and verify the whole-bundle and per-file hashes before reading secrets or restoring data.
4. Install the approved deployment files. Preserve `.env` exactly, then change only plan-listed host-specific non-secret settings. Never regenerate JWT, PostgreSQL, VCS, Lark, Slack, WeCom, plugin, or other encryption keys.
5. Validate rendered Compose configuration without printing it. Create the intended empty project volumes and containers; prove every restore target is empty.
6. Restore each non-database volume while its writers are stopped.
7. Start PostgreSQL alone on a fresh target volume. Recreate the application database and run `pg_restore --exit-on-error --no-owner` as the configured application database user.
8. Start backend, wait for automatic migrations, then start frontend and any classified auxiliary services. Because the application release is unchanged, unexpected new migrations are a mismatch requiring investigation.
9. Keep the target isolated from public writes until verification completes.

Do not copy or restore container writable layers, logs, Docker networks, stale container IDs, host SSH keys, client Multica profiles, or Runtime daemon state.

## 5. Verify restored state

`TARGET_READY` requires all of the following:

- source tag/commit, image IDs/digests, Compose project/config set, PostgreSQL major, and classified mount set match the plan;
- transferred bundle and payload hashes match the source or verified backup manifest;
- `pg_restore` succeeded with `--exit-on-error`; table/sequence counts, extension list, and database size are plausible against the source snapshot;
- every restored deployment-data volume has the planned archive hash and expected ownership;
- PostgreSQL is healthy; backend and frontend are running; `/health` reports liveness; `/readyz` reports both database and migrations `ok`;
- `/api/config` reports the intended daemon and app URLs without exposing secrets;
- login returns HTTP `200` through the exact target binding;
- an operator performs an authenticated read-only check of an existing account, Workspace, Project, Issue, and uploaded file appropriate to the instance;
- external S3/Redis/SMTP/OAuth/provider dependencies required by the non-empty configuration are reachable or explicitly recorded as unverified blockers;
- no public route sends writes to the target yet, and the source remains quiesced.

For HTTPS before DNS cutover, verify the intended hostname against the target with an approved `--resolve` or equivalent client override. This proves target routing/TLS only; it does not prove public DNS.

## 6. Cut over, reconnect Runtimes, and observe

Require separate authorization naming the exact DNS, load-balancer, NAT, or reverse-proxy change. Re-read `TARGET_READY`, source quiescence, target readiness, current route owner/value, plan identifier, and required Runtime set immediately before mutation.

Change only the authorized route. Then verify from a separate client with all proxy variables cleared:

- canonical Web login and API `/health` and `/readyz`;
- `/api/config` URLs;
- browser and daemon WebSocket routes;
- authenticated Workspace/Project/Issue/upload readback.

After `CUTOVER_VERIFIED`, enter `RUNTIME_RECONNECTING`. For every required existing Runtime host:

1. Read its machine-local profile, `auth status`, Workspace list, daemon status, provider versions, launcher `PATH`, daemon ID, and exact Runtime IDs. A daemon process reported as `running` is still disconnected when its `server_url` points at the retired service or its Runtime rows are offline.
2. If the deployment origin changed, stop only that Runtime daemon, update only its local profile `server_url` and `app_url`, then run `auth status` and `workspace list --output json` against the authoritative target with all proxy variables cleared. Preserve the local token. If it is invalid, invoke `multica-login` on that Runtime host; never copy a token from another client.
3. Re-probe every previously working provider using the captured daemon `PATH`. Do not install, upgrade, or silently drop a provider during reconnection.
4. Start the daemon with the same profile, daemon ID, device/runtime name, Workspace, and provider set. Pass an explicit `--daemon-id` when supported and use `--no-auto-update` when supported so recovery does not create a replacement daemon or upgrade tooling.
5. Require `daemon status --output json` to report `running`, the authoritative target `server_url`, the expected daemon ID, and the intended Workspace. Then query the authoritative server with an explicit Workspace and require every pre-recorded Runtime ID to retain its provider/daemon ownership and become `online`.

Do not create replacement Runtime rows merely because the originals are offline. If a required Runtime cannot reconnect after the target became authoritative, remain in `RUNTIME_RECONNECTING`, report `partial`, and fix forward. Do not restart the retired source service.

Advance to `RUNTIMES_READY` only when every required Runtime is online, or when the reviewed plan explicitly recorded an empty required set. Then enter `OBSERVING`; keep the source service stopped and retain the verified bundle plus source volumes for the approved period.

Mark the target authoritative when its first write-capable backend or auxiliary service starts, not only when public traffic changes. Runtime reconnection can also write target state and never reopens the rollback window.

## Failure and rollback

- Before `SOURCE_QUIESCED`: make no changes; fix discovery and re-plan.
- From `SOURCE_QUIESCED` through `TARGET_RESTORED`, if the target has run no write-capable service: stop target services, restore the prior route if it changed, restart the unchanged source, verify readiness and clients, and record `SOURCE_RESUMED`.
- If source was restarted or mutated after the snapshot: invalidate that snapshot for cutover and create a new final snapshot.
- From `TARGET_WRITER_STARTED` onward, or whenever target writes cannot be disproved: never restart source as a writable rollback. Mark `FIX_FORWARD_REQUIRED`; repair target or perform a new quiesced reverse migration from target to source/replacement.
- A required Runtime that remains offline, changes daemon/Runtime identity, loses a provider, or still targets the retired endpoint blocks `RUNTIMES_READY`. After `TARGET_WRITER_STARTED`, repair it forward; do not restart the old service plane.
- Failed checksum, incomplete dump, `pg_restore` warning/error, release/image mismatch, unknown mount, target conflict, readiness failure, or external dependency failure stops progression.
- An unavailable source can be restored only from a verified bundle. Report its recorded snapshot time and unprovable recovery-point gap; never claim zero data loss.
- Do not run `docker compose down -v`, prune Docker, delete source volumes, delete the bundle, or decommission the old host as rollback.

## Machine-readable relocation handoff

After `RUNTIMES_READY`, create an exact typed plan matching
[`contracts/server-migration-plan.schema.json`](contracts/server-migration-plan.schema.json),
an authoritative target readback matching
[`contracts/server-migration-target-readback.schema.json`](contracts/server-migration-target-readback.schema.json),
and private evidence matching
[`contracts/server-migration-receipt.schema.json`](contracts/server-migration-receipt.schema.json)
except for `receipt_digest`, then run:

```bash
python3 scripts/emit_server_migration_receipt.py \
  --evidence '<private-evidence.json>' \
  --plan '<reviewed-migration-plan.json>' \
  --target-readback '<exact-target-readback.json>' \
  --output '<new-private-receipt.json>'
```

The emitter parses both typed companions, verifies that their exact bytes match
the evidence digests, and cross-checks the origin strategy, application commit,
image-set digest, Workspace ref, four complete identity-set digests,
authoritative target state, stopped source service, ready Runtime fleet, final
state, and observation time. It computes `receipt_digest` over the canonical
receipt without that field and creates the result mode `0600` without replacing
an existing file. This receipt is the only supported machine input to
`multica-orchestrator-relocate`; a chat report, digest string without its source
file, or raw log is not equivalent. `receipt_digest` proves byte integrity, not
independent authorship or a cryptographic signature. Retain the protected
source files and operator approval as the provenance chain.

The final report must include this invocation's exact prompt/report capture ID,
the absolute receipt path, and `receipt_digest`. This triple is the
caller-facing relocation selector: `multica-orchestrator-relocate` resolves the
restricted report by capture ID and then revalidates the referenced receipt.
Do not tell callers to locate a receipt by filename pattern or modification
time.

Keep the plan, target readback, evidence, and receipt in an existing mode-`0700` operator directory. They may
contain live refs and endpoints but never secrets, profile contents, database
rows, absolute credential paths, or raw logs.

## Handoff format

Return a concise migration handoff containing no secrets:

- final state and plan identifier;
- source/target SSH aliases and non-secret host identity evidence;
- release tag/commit, image digests, Compose project/config set, and PostgreSQL major;
- included/excluded data items and classification, bundle hash, snapshot time, and sizes;
- source quiesce status, target service/health/binding state, and exact readiness responses;
- target-host, separate-client, authenticated application, upload, and per-Runtime-host verification, including profile endpoint, provider versions, daemon ID/status, exact Runtime IDs/status, and any explicit `not_applicable` set;
- origin/TLS/cutover action and current route readback;
- authoritative writer (`source`, `target`, or `none`) and whether rollback remains safe;
- retention location/deadline and every unresolved external dependency or blocker.

Never include `.env` contents, database rows, passwords, JWTs, PATs, cookies, OAuth credentials, provider secrets, verification codes, private keys, certificate private material, or raw logs.
