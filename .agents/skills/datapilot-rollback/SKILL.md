---
name: datapilot-rollback
description: Reset or recover an approved isolated local DataPilot instance, renew its media budget, and use the Node.js CLI for authorized account setup and source re-registration.
user-invocable: true
disable-model-invocation: false
---

# DataPilot Rollback

This file contains the complete operational workflow and fixed budget proposal.
No companion reference, asset, other Skill or external manual is a prerequisite.
Repository and user instructions still apply. Commands need the actual repository
executables, deployment configuration, credentials and runtime; these are inputs,
not additional instruction files. Inspect live configuration and executable
contracts when their behavior differs from this Skill. Never reuse another run's
addresses, image IDs, namespaces, resource names or approval digests.

## Scope and completion order

Use this Skill for an explicitly requested complete developer-start reset of an
approved, isolated local test instance. Never apply it to production/shared data.
Updating this Skill or requesting a dry-run does not authorize a destructive reset.
Reuse authorization already given for the same concrete target and consequences.
Account/password replacement, source restoration, website publication, unrelated
container removal and HTTPS authority changes must fit the user's task scope.
A reset request alone does not authorize registering every discovered candidate.

For a full authorized reset-and-restore request, perform:

1. Inventory the exact target, capture the selected source registrations and
   preserve a verified paired backup.
2. Run read-only preflight, obtain any missing destructive authorization, and
   apply or recover the exact approved reset.
3. Require verified reset completion, then renew the default media budget while
   application writers remain stopped, unless renewal was explicitly skipped.
4. Provide a restricted local HTTPS bootstrap endpoint and use the Node.js CLI
   to finish all four preset accounts' initial password changes.
5. Complete the authorized committed-primary release and trusted HTTPS checks.
6. Use the CLI to restore only the selected sources/datasets and verify progress.
7. Revoke task sessions, clean task-owned temporary resources and report actual
   outcomes separately for reset, accounts, budgets, release and registration.

Stop at the boundary of the authorized task. Never rerun reset to repair a later
password, budget, registration or release failure.

## 1. Inventory, backups and execution environment

- Identify the canonical primary checkout, branch, committed revision, dirty and
  staged paths, local Docker context, Compose project, services, configured image
  references and IDs, actual container IDs, mounts, networks, volumes and HTTPS binds.
  Read only selected Docker fields; do not dump full environments or credentials.
- Use the exact tracked effective Compose model: `docker-compose.yml`, shared
  `docker-compose.kestra.yml`, enabled feature overlays, tracked
  `docker-compose.release.yml` and any already approved dataset override. Use
  `--env-file .docker.env` and explicit project/working-directory arguments for
  Compose inspection. Parse dotenv as data; never source it as shell code.
- Carry the actual launcher mode explicitly: `LAN_HOST`, `WEB_BIND_HOST`,
  `WEB_PORT`, an existing `VPN_HOST`, `FEISHU_ENABLED` and `PREPROCESS_ENABLED`.
  Preserve enabled services and approved read-only dataset mounts. Discover the
  real SQL/content namespaces and selected baseline from the executable runtime;
  historical namespace names do not identify the schema version. A non-default
  pair uses both `DATAPILOT_BROWSE_TARGET_SQL_SCHEMA` and
  `DATAPILOT_BROWSE_TARGET_CONTENT_DATABASE`.
- The current complete-reset baseline is native41. Use a maintenance image whose
  immutable ID and backend source/resource digest match the selected committed
  implementation. Do not retag an older image or weaken qualification checks.
- Before destructive apply, retain a PostgreSQL/MongoDB common checkpoint with
  successful isolated restore, actual runtime-login qualification and verified
  reconciliation. Use the selected release's paired checkpoint/recovery owner;
  an untested dump or SQL-only archive is insufficient. Reset creates no backup.
  Save private copies of existing approved media profiles, or record absence.
- Record the original source/object-storage roots, derived-media/buffer roots,
  persistent CA and resources to preserve. The buffer must be a canonical
  `.datapilot-buffer` directory. Preview cache must be a writable canonical strict
  child of the prepared-media root; external, root-level or symlink mounts refuse.
- The coordinator inspects actual host processes and mounts. Resolve occupation
  refusals from evidence. Removing unrelated containers or interrupting training
  requires explicit authorization for those concrete effects; retain their data,
  volumes and images unless separately authorized. Do not disable a verifier to
  work around missing process visibility or Docker metadata incompatibility.
- Use deployment-owner-owned canonical private directories with mode `0700` and
  regular non-symlink private files with mode `0600`. Run as that owner. Preserve
  the exact existing service secrets and content-authority input inventory.
  Never print passwords, tokens, Cookies, hashes or private keys.
- Host Git, Docker and standard-library orchestration are allowed. Build, install,
  test or debug project code only inside approved Compose development containers.
  Name task helpers `robox-datapilot-dp<task-id>-<unique-four-character-suffix>`,
  inspect actual mounts and record every task-created resource for cleanup.

## 2. Prepare the Node.js CLI and source inventory

Prefer an installed trusted `datapilot`. The package is not published to npm.
Otherwise build the checkout's CLI in a task-owned approved Compose development
container with the intended checkout mounted at `/workspace`. With explicit
working directory `/workspace/src/cli`, run:

```sh
npm ci
npm run generate:api
npm run build
node dist/index.js --help
node dist/index.js --version
```

Use `node dist/index.js` in place of `datapilot` in the examples when operating
that build. Do not install a host project toolchain as a fallback. Check command
help for the actual installed version before relying on syntax.

- Set `DATAPILOT_URL` to the exact selected HTTPS origin and
  `DATAPILOT_CA_FILE` to its verified CA file, or pass `--url` and `--ca-file`.
  Origins have no application path, userinfo, query or fragment. TLS verification
  remains enabled; the CLI does not infer proxies or follow redirects.
- Give the task its own `XDG_CONFIG_HOME` on POSIX. The CLI stores origin-bound
  sessions under its `datapilot` configuration directory. Use owner-only
  directories/files and sequential account login/change/logout calls. Do not
  navigate or replace another task's session/configuration.
- Administrator writes require the Cookie saved by `auth login`. Unset
  `DATAPILOT_TOKEN_FILE` and omit `--token-file`; selecting a PAT cannot substitute
  for administrator Cookie authority. Flags override environment settings.
- Password login accepts hidden terminal input, `--password-stdin`, or a checked
  private `--password-file`. Never place a password in a command argument.
- Before reset, when source restoration is requested, use an authorized admin
  session to capture `storage-sources list --output json`,
  `datasets list --output json` and
  `datasets candidates --alias ALIAS --output json`, following pagination.
  Privately retain the requested storage configuration and exact
  alias/candidate/label selections, then `auth logout`. If the old API is already
  unavailable, use an independently retained approved inventory; do not invent
  candidates. New dataset/job/generation IDs must come from new registrations.

## 3. Preflight, apply and recover the complete reset

Explain the exact target and the following consequences before destructive
apply. The reset recreates the configured PostgreSQL, MongoDB and Redis stores,
clears Kestra state/storage and every entry under owned derived-media/buffer
roots, and removes business data, workflow/assignment history, accounts,
passwords, sessions, tokens, media approvals and cached artifacts. Original
source datasets, original object storage, the CA and retained backups are
protected. This is not a data-preserving upgrade.

It creates the selected native41 paired baseline and restricted runtime logins,
including the independent preview worker. Canonical presets are:

- `admin`, `tester`, `annotator`, `reviewer` with random initial passwords and
  required initial password changes; private output is
  `deployment/bootstrap-credentials.json` with mode `0600`.
- The default project, exactly one enabled default label group and the four
  stable labels `PICK`, `FORCE`, `LABEL`, `PUSH`; custom labels/groups do not survive.
- One enabled default-project assignment policy at revision 1, with the protected
  administrator at 100% in each role, empty counters/cursors/errors and no lease.
  Allocation plans/items/chunks, accepted receipts and current-round activity
  evidence must be empty, as must every other non-preset SQL table.

Run from the canonical primary checkout with the actual release environment and
matching maintenance image selected:

```sh
python3 tools/rollback_to_start.py --dry-run
```

Require exit `0` and inspect its secret-free target digest. A refusal needs actual
configuration/ownership correction and a new preflight, not a disabled check.
Custom Compose inputs, project names, maintenance image or buffer root must be
explicit supported command inputs inside the selected canonical repository.

After authorization of that concrete target, use interactive `--apply` and type
exactly `RESET ALL <digest>`, or use explicitly authorized automation:

```sh
python3 tools/rollback_to_start.py --apply --confirm-target <approved-digest>
```

Changed target digests require concrete review; do not silently substitute one.
The coordinator fences new writers, stops/joins them, resets the pinned stores,
installs the baseline/presets and verifies all postconditions. Require its
verified completion receipt before subsequent writes. Writers remain stopped.

An interrupted fenced operation must resume its original pinned plan, digest,
private inputs and staged credentials:

```sh
python3 tools/rollback_to_start.py --recover --confirm-target <original-digest>
```

Never delete `deployment/fresh-reset-state` or `deployment/fresh-reset-fence`, replace
staged credentials, initialize an occupied namespace or restart writers while
recovery is unresolved. Cancellation is allowed only in the original `planned`
phase with a ready fence, through `--cancel --confirm-target <original-digest>`;
it archives preparation evidence without clearing data. Exit codes are `0` for
verified completion or explicit cancellation, `3` for refusal before an active
operation, and `4` for interruption/unfinished recovery. A verified reset must
check the complete selected SQL/content baseline and presets, empty Redis with
persistence disabled, empty Kestra state and cleared owned media roots.

The explicit `--legacy-sql-only` adapter is frozen at native29 and cannot service
native41. Never select it to preserve accounts on a complete reset or substitute
it for a data-preserving operation the user requested.

## 4. Renew the fixed default media budget

Default budget renewal belongs in the combined reset consequence summary. Honor
an explicit instruction to skip it. When the combined operation is already
approved and current effective limits match this fixed policy, no additional
confirmation is needed. The reset executable and dry-run never approve budgets.

Keep application writers stopped from reset through renewal. Once budget or
account writes occur, the empty reset checkpoint no longer describes current
business state: do not run reset/recover again to verify or retry these steps.

The fixed proposal is 24 CPU permits, 64 GiB host memory, 16 GiB GPU memory and
512 GiB persistent-plus-hot disk combined, with a 32 GiB free-space floor. It
excludes original datasets, databases, Docker images and unrelated files. IO
ceilings are administrative maxima, not measured throughput. Materialize exactly
this inline JSON in a private per-run file and mount it read-only at
`/run/config/rollback-media-budget.json`; no bundled asset file is required:

```json
{
  "persistent_quota_bytes": 549755813888,
  "free_space_floor_bytes": 34359738368,
  "cpu_permits": 24,
  "host_memory_ceiling_bytes": 68719476736,
  "device_memory_ceiling_bytes": 17179869184,
  "source_readers": 24,
  "decoder_instances": 24,
  "writers": 12,
  "queue_frames": 512,
  "reorder_frames": 512,
  "queue_bytes": 12884901888,
  "reorder_bytes": 17179869184,
  "decoded_bytes": 4294967296,
  "grant_bytes": 4294967296,
  "read_bytes_per_second": 68719476736,
  "write_bytes_per_second": 34359738368,
  "read_burst_bytes": 8589934592,
  "write_burst_bytes": 2147483648,
  "playback_reads": 4,
  "playback_latency_ms": 600
}
```

1. Create a task-owned maintenance container from the exact committed deployed
   indexer image and canonical merged Compose configuration, retaining real
   dataset overrides. Match actual UID/GID, CPU, memory, memlock, GPU devices,
   output/cache roots and mounts. Inspect the resulting container before use.
2. Use direct `PGUSER=datapilot`, with the existing owner database secret mounted
   read-only and selected through `DATABASE_PASSWORD_FILE`; do not put secrets
   in environment values. Mount the existing approved-profile volume separately
   writable at `/run/media-budget-admin`, leaving `/run/media-preparation`
   read-only. The normal volume is `robox-datapilot_prepared-media-profile`;
   discover and preserve the actual deployment identity, never create a substitute.
3. Extract one genuine source JPEG inside the maintenance container from an
   approved read-only mount. Where present, the retained contiguous example is
   `/data/lab-collect/eval-contiguous/data/chunk-000/episode_000000.parquet`,
   column `observation.images.l_cam`, first image `bytes`. Read only the needed
   Arrow column/batch, validate the JPEG signature and save `/tmp/budget-probe.jpg`.
   Otherwise discover a real available source without modifying it.
4. Invoke the existing owner inside that maintenance container:

   ```sh
   /opt/venv/bin/python -m src.backend.dataset.media_acceleration.budget_admin \
     --profile-file /run/media-budget-admin/approved-profile.json \
     --gpu-probe-jpeg /tmp/budget-probe.jpg \
     preview --endpoints /run/config/rollback-media-budget.json \
     --principal <current-human-administrator>
   ```

5. Review effective limits and actual full codec qualification. Expected GPU
   capacity is two decoder contexts and two streams. A missing probe must not
   become a zero-GPU approval. If unchanged, use the same invocation with
   `approve` instead of `preview` and add `--confirm-digest <fresh-preview-digest>`.
   Changed compiler behavior, lower ceilings or different execution capacity
   requires a new concrete proposal and approval. Never fabricate observations.
6. Require successful SQL approval and atomic owner-private file publication.
   Verify SQL/profile state, version and digest agree using the existing
   `load_approved_profile_file` owner; the approved digest may differ from preview.
   The runtime file is `/run/media-preparation/approved-profile.json`.
7. If SQL committed but file publication failed, use that same maintenance owner
   with `install --profile-version <committed-version>
   --digest <committed-approved-digest>`. Never hand-write an approved JSON,
   restore a superseded approval, reuse a prior fingerprint/digest, rotate the
   execution epoch to bypass a refusal, or rerun destructive reset.
8. Remove the maintenance helper and probes after success; preserve the profile
   volume. If renewal remains incomplete, report reset separately and keep
   application writers stopped. This renewal does not approve the independent
   cover-preview budget or authorize retrying blocked preparation intents.

## 5. Initialize account passwords through the CLI

Reset already creates all four preset accounts. Use their fresh candidates from
`deployment/bootstrap-credentials.json` privately; do not register duplicate accounts.
Extract each candidate to an owner-private plain-text password file and generate
a distinct new password satisfying server policy (currently 12 to 1024 characters
in the CLI). Stage new secrets durably before mutation.

The CLI needs a running HTTPS API and does not start one. Before LAN/VPN password
exposure, provide a task-owned restricted local HTTPS bootstrap endpoint using
the selected exact application image and live baseline, only after reset and any
selected media renewal finish. Verify actual loopback-only host binding, source
network isolation, certificate identity and trusted CA. Only a proxy publishes
HTTPS; do not expose an unencrypted API or databases. Existing LAN/VPN routes
must not expose seed credentials. Container-local `localhost` is not the host
proxy. Preserve the existing CA and authorities unless a change was authorized;
do not invent a bootstrap flag unsupported by the deployment owner.

If no approved local HTTPS path is available, report the concrete bootstrap gap
and preserve verified reset state. Do not disable TLS, expose seeds remotely,
edit hashes or silently replace CLI operations with ad hoc HTTP/in-process calls.
A maintenance alternative within existing task authorization must retain native
authentication/password policy and be reported explicitly.

With the bootstrap origin/CA selected, run sequentially for each preset account:

```sh
datapilot auth login --username admin --password-file /private/admin.initial
datapilot auth change-password \
  --current-password-file /private/admin.initial \
  --new-password-file /private/admin.new
datapilot auth whoami --output json
datapilot auth logout
```

Repeat for `tester`, `annotator` and `reviewer`, confirming
`must_change_password=false`. Hidden terminal prompts are also supported.
Password change retains the current session and revokes its other sessions/PATs.
The CLI password input is plain text, not the aggregate bootstrap JSON.

The outer orchestrator owns password generation/extraction, per-account progress
and atomic publication of the final owner-private credential record. Preserve
each staged secret after a confirmed change; replace the aggregate file only
when it accurately contains all four final passwords. Preserve recovery inputs
on partial failure, without changing reset-coordinator staged credentials.
Reconcile uncertain writes through native authentication before another deliberate
change, with no blind retries. Log out and stop the task-owned bootstrap endpoint
after use. Authenticate afresh against the final origin after release; sessions
cannot cross origins.

## 6. Publish the authorized committed-primary release

A reset does not restart or publish the site. Release only when included in the
user's task. Build from the canonical primary checkout at a committed, integrated
revision. Record the selected remote tip if latest code was requested; do not
reset/stash unrelated changes or build from a worktree/uncommitted source.

After verified reset, recreate only `datapilot-content` under the complete
canonical Compose selection, excluding the private reset overlay, using
`up --detach --no-deps --force-recreate --wait datapilot-content`. Retain its
volumes and private inputs. This restores canonical ownership provenance without
resetting its data; never do it while reset is pending.

The release entry is `scripts/datapilot-frontend.sh start`, owned by
`src/backend/launcher/release.py`. Prepare its task-owned helper from the existing
approved `robox-datapilot-dev-recovery:local` image; it must run as the deployment
owner with canonical primary mounted at `/workspace` and that working directory.
Inspect these actual properties. Use the existing trusted runtime network and
no Docker-socket bind or published helper ports. If the recovery image is absent,
build its `dev-recovery` target from committed `docker/dev.Dockerfile`; never
impersonate it by retagging an unrelated image.

Set `DATAPILOT_DEV_CONTAINER` to that helper and `WEB_IMAGE_TAG` to a traceable
custom `repository:release-tag`, carry the exact mode/namespaces from section 1,
and invoke the release entry with the primary as explicit working directory.
Preserve private authority inputs, read-only dataset mounts, fixed LAN/VPN binds
and persistent CA. Set `PASSWORD_CLIENT_TRUST_VERIFIED=1` only after actual CA
trust is verified. An explicitly authorized authority/bind change additionally
requires `HTTPS_AUTHORITY_CUTOVER_VERIFIED=1`; do not set attestations blindly.
Use transient approved build proxies, never Dockerfile proxy `ENV` values.

Require the release owner to build/qualify the image, stop/join all writers,
create a fresh paired checkpoint, restore into owned isolated copies, qualify
runtime logins, reconcile, then recreate Web/indexer/preview and enabled scheduler
services. Keep the proxies available except for an authorized bind cutover.
Activate the qualified `repository:release-tag@sha256:manifest-digest`; compare
actual `.Config.Image` and `.Image` across all three writers to the qualified
reference/ID. Resolve repository digest metadata independently; an image ID alone
is not proof of its manifest digest. Read back the custom name in `docker ps -a`.
Retagging or restarting an existing container alone does not publish baked code.
Persist only the plain build tag in the existing non-secret image setting.

Verify Web/indexer/preview, enabled scheduler and both enabled proxies are healthy.
Through the selected CA-trusted proxy, check `/api/v1/health` and `/demo/`. Either
LAN or VPN browser acceptance is sufficient; default to LAN. In a fresh host
browser session, load the protected datasets page, inspect it, save a private
screenshot and check browser errors. For host `agent-browser`, use
`--session UNIQUE --ca-cert ABSOLUTE_CA_PATH`, remove proxy variables from its
startup environment and use its `--help` if needed. Use `--no-sandbox` only when
this host demonstrably requires it; never bypass TLS. Login must use native
authentication and private credentials; revoke the temporary session, close the
browser and remove auth state afterward. A public health page/login screen alone
is not protected-page proof. Do not claim a rollout when any release gate fails.

## 7. Restore the selected source registrations through the CLI

Once the final site is ready, set its exact origin/CA and log in as the completed
administrator with its final private password file. Read current source/dataset
inventories first, including on partial-restoration resume.

Create each selected storage source with a command input, not its entire saved
GET response. Preserve alias, kind, layout, label, description and discoverability.
For a local source, map `location.container_path` to `root` and use an approved
read-only mount already present in the deployment; registration adds no mounts.
A local example for `/private/source.json` is:

```json
{
  "alias": "lab-drag",
  "kind": "local",
  "layout": "lerobot_parent",
  "root": "/data/lab-drag-10h",
  "label": "Lab Drag",
  "description": "",
  "discoverable": true
}
```

Supported layouts currently include `oxe_parent`, `lerobot_parent`,
`single_dataset`, `hifi_umi`, `yam_abc`. For S3, supply the actual approved
`endpoint`, `bucket` and optional `prefix` instead of `root`; preserve supported
layout constraints. Never invent source credentials or locations.

```sh
datapilot storage-sources create --input-file /private/source.json --output json
datapilot datasets candidates --alias lab-drag --output json
datapilot datasets register-batch --input-file /private/datasets.json --output json
```

Batch input has this shape, with exact currently discoverable candidate keys
from the retained selection:

```json
{
  "items": [
    {
      "alias": "lab-drag",
      "candidate": "EXACT_DISCOVERED_CANDIDATE",
      "label": "Saved label"
    }
  ]
}
```

Use `datasets register --input-file FILE` for one candidate. Split batches to
the installed limit (currently 57 unique alias/candidate pairs) and inspect each
item independently; batch acceptance is not an all-or-nothing restore. Preserve
selected enabled state through supported source updates and its fresh revision
when needed; `enabled` is not a create input. Do not reuse an old resource revision.

Save returned dataset/job IDs privately and inspect authoritative progress:

```sh
datapilot index-jobs show JOB_ID --output json
datapilot datasets show DATASET_ID --output json
datapilot storage-sources list --output json
datapilot datasets list --output json
datapilot auth logout
```

Verify exact requested membership, scan state/errors and media-preparation state;
a registration acknowledgement alone is insufficient. Recording datasets can
still await segmentation/publication after scans and media complete. Report
Task/Episode readiness and independently unapproved cover previews separately.
Do not create artificial workflow data or approve extra budgets to manufacture
acceptance. Missing candidates/mounts need an explicit diagnosis, not silent
substitution of unrelated datasets.

CLI exit codes: `0` success; `2` local arguments/private files; `3` auth/permission;
`4` missing resource; `5` conflict/precondition; `6` validation; `7` throttling,
unavailability or failed read transport; `8` uncertain write outcome/damaged
successful response; `130` interruption. On `5`, refresh authoritative state.
On `8`, inspect current lists/history and completed private outputs before a
new deliberate request. Do not blindly replay password changes or registrations.

## 8. Cleanup and completion evidence

- Remove only recorded task-owned helpers, probes, disposable images, networks
  and disposable volumes. Check image consumers first. Remove Docker bridges
  through their owning Docker networks, never by deleting host interfaces.
  Do not use global prune or `docker compose down --volumes` for cleanup.
- Preserve serving images, compatible rollback images, shared/base/recovery
  images, active replacement data volumes, media/profile volumes, source data,
  object storage, persistent CA, backups and unrelated containers/worktrees.
  A reset-owned label does not make a newly serving data volume disposable.
- Log out task CLI/browser sessions. Remove temporary password extracts, staged
  secrets after final credential publication, and private session/auth state.
  Preserve final credentials and recovery inputs still needed after a failure.
- Reinspect Docker to prove temporary containers/networks/volumes were removed.
  Record any retained recovery helper or cleanup failure and its concrete reason.
- Keep a non-secret per-run record under owner-only `deployment/ops/<run>/`: full
  revision, exact target digest/operation receipt, backup/recovery verification,
  budget limits/version/digest, account setup status and private credential path,
  source/candidate counts and new job outcomes, image tag/ID/immutable reference,
  actual health and HTTPS/browser proof, cleanup and remaining limitations.
  Never put credential contents or Cookie/token hashes in that record.

Report in Chinese. Distinguish verified reset completion from later account,
budget, release, registration and publication states. A completed scan, empty
protected page or healthy process alone does not prove playable media, previews
or published Tasks/Episodes.
