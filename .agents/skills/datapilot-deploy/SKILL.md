---
name: datapilot-deploy
description: Build and deploy the latest approved DataPilot code to an existing Docker Compose website, verify named immutable images and trusted HTTPS/browser behavior, and clean up historical release images, their attributable build caches, and task-owned resources. Use for site release, rebuild, or redeployment requests.
---

# DataPilot Deploy

Deploy a freshly fetched, approved Git revision through the existing DataPilot
release owner. Complete the build, paired recovery qualification, container
recreation, browser verification and scoped cleanup before reporting success.

This file contains the operational procedure. No other Skill, README, runbook or
external document is a prerequisite. Use live Git/Docker state, configuration and
the executable owners below to resolve environment or version differences;
existing repository and user instructions still apply. Keep source paths relative
to the discovered checkout; never reuse a previous run's host IP, namespace,
container name, image ID or private operation directory.

## Scope and authorization

- A request to deploy/rebuild/redeploy authorizes that agreed rollout. Reuse
  explicit authorization already present in the conversation; do not ask again
  merely because the site is production-facing. Creation or inspection of this
  Skill does not authorize deployment. If rollout is not authorized, finish the
  read-only inventory and concrete rollout/recovery plan before requesting it.
- Refresh an existing single-host Compose site. Default to the latest fetched
  `origin/develop` commit unless the user selected another integration branch,
  tag or revision. Define "latest" as the fetched tip recorded for this run;
  do not silently deploy an older local HEAD or chase new tips during cutover.
- GitHub release publication, PR merges, database upgrades/resets, credential
  rotation, budget changes, source registration and HTTPS authority changes are
  separate operations. Perform them only within explicit task authorization.
  An ordinary deploy never invents a semantic version or changes business data
  to manufacture an acceptance example.
- Documentation/Skill-only changes need no rollout unless the user explicitly
  asks to rebuild/redeploy. An explicit rebuild still runs the real build and
  recreation when application bytes are unchanged; cached layers are valid.
- A rollout includes the post-verification historical release image and build
  cache cleanup below. Explicit retention requirements and repository recovery
  rules still apply; never extend cleanup to unrelated projects or data.

## 1. Select the committed primary revision

1. Inspect `git status --short`, remotes, the current branch, and
   `git worktree list --porcelain`; identify the absolute primary checkout.
   Fetch the selected remote branch and read its exact SHA. Record the starting
   revision and dirty/staged paths before any change.
2. Integrate pending feature/worktree work through its authorized commit/PR
   workflow first. Deploying latest committed code alone does not authorize
   committing unrelated work or merging an unreviewed branch. Provider mutation
   needs remote head/check/merge readback; do not bypass hooks or protections.
3. In the primary checkout, select the intended integration branch and update
   it with a fast-forward only. Verify its HEAD equals the fetched approved tip.
   Stop on divergence or a blocked checkout; do not reset, stash, force-push,
   rewrite shared history or overwrite another task's files to make it work.
4. Build only from that committed primary revision. Never use a feature worktree
   as production context, source mount, release-script source or copied overlay.
   Preserve unrelated changes only when inspection proves they do not affect
   Docker COPY inputs, Compose, release owners, scripts or dependencies. Otherwise
   resolve the exact blocking changes before building; a dirty image input is
   not the recorded commit.

Host Git and standard-library deployment orchestration are allowed. Application
development, dependencies, compilation, tests and debugging use approved Docker
containers; do not install a host project toolchain as a fallback. Communicate
progress in Chinese and keep credential values out of messages and artifacts.

## 2. Discover and preserve the deployment

Inspect selected fields rather than dumping full container environments or
private configuration. Record container IDs, image references/IDs, health,
Compose project/config-file labels, mount identities, published proxy bindings,
network IDs and persistent volumes. Match them to the intended primary checkout.
Before replacing images, inventory their named tags, IDs and consumers, and record
available build provenance and builder/cache relationships. This evidence helps
identify obsolete releases and their cache after cutover; creation time alone
does not prove ownership or exclusive use.

The current executable entry is `scripts/datapilot-frontend.sh start`, forwarding
to `src/backend/launcher/release.py`. Its phase owners are
`release_preflight.py`, `release_backup.py`, and `native_refresh.py` in that
package. Docker builds use `docker/dev.Dockerfile`; the image includes backend,
built frontend and recovery tools. Inspect these executable contracts if their
behavior differs from this Skill; do not substitute a second deployment engine.

- The base composition is `docker-compose.yml`, followed by shared
  `docker-compose.kestra.yml`, enabled Feishu/preprocessing overlays, and tracked
  `docker-compose.release.yml`. Preserve an already approved read-only dataset
  override. A new local override is not an implicit production input.
- `.docker.env` provides machine-specific path/image interpolation. Use
  `--env-file .docker.env` and the exact selected overlays for manual Compose
  inspection. Parse the rendered model in memory and retain only needed fields;
  do not source an arbitrary dotenv file as executable shell code or log its
  entire rendered configuration.
- Discover and explicitly carry the existing launcher mode into its environment:
  `LAN_HOST`, `WEB_BIND_HOST`, `WEB_PORT`, an existing `VPN_HOST`,
  `FEISHU_ENABLED` and `PREPROCESS_ENABLED`. Retain enabled GPU/preprocessing
  inputs where present. Do not infer current addresses from examples, omit an
  existing VPN endpoint, enable dormant services, or disable authentication to
  pass a gate. Dotenv interpolation alone does not ensure the host launcher has
  selected the same feature mode.
- Preserve the persistent Caddy CA and fixed HTTPS authorities. Only Caddy
  publishes the website; do not expose Web, SQL, Redis, Mongo or storage ports.
  Trust `deployment/caddy-root.crt` and verify its actual origin. Set a client-trust
  attestation only after verifying it. An authority/bind change requires explicit
  scope and `HTTPS_AUTHORITY_CUTOVER_VERIFIED=1`; it may briefly interrupt HTTPS.
- Discover the actual SQL/content namespaces and live admission, never a version
  inferred from their names or an old receipt. Read the selected version from
  `src/backend/infrastructure/schema_authority.py` and the selected image; do not
  retain a historical native version as the deployment default.
  For a non-default pair, supply both `DATAPILOT_BROWSE_TARGET_SQL_SCHEMA` and
  `DATAPILOT_BROWSE_TARGET_CONTENT_DATABASE` in the launcher environment. Leave
  both unset for the standard pair. Their historical names do not authorize a
  retired migration. Do not inject arbitrary libpq options.
- Private `deployment/` directories must be canonical, deployment-owner-owned mode
  `0700`; private files are regular owner-owned `0600` files, not symlinks.
  Run as that deployment owner. The declared `CONTENT_*_CONFIG_HOST_FILE`,
  `CONTENT_*_PASSWORD_HOST_FILE` and replica-key inputs must form the single
  exact authority-directory inventory required by the owner. Preserve original
  service usernames/passwords, including supported older-version names. Dormant
  profile files do not authorize creating their service identities.
- Existing media/preview budget approvals and execution epochs remain intact.
  Missing approval, incompatible authority, an active open-loop writer, or a
  pending maintenance/reset fence needs its explicit resolution; do not rotate
  an epoch, approve a budget, clear a fence, rename namespaces or retry an old
  migration as an automatic deployment repair. Ordinary start refuses occupied
  older authorities. Fresh-install bootstrap is outside this existing-site flow.
- Check free bytes and inodes on the root filesystem, Docker storage and selected
  data/backup filesystems before large builds or imports. Include layer unpacking,
  duplicate daemon stores and paired restores in the estimate. An ENOSPC incident
  can leave persistent services damaged after space is freed. Identify disposable
  caches precisely and reuse any existing cleanup authorization; never substitute
  global Docker pruning or deletion of business data for scoped cleanup.

### Media and preview budget acceptance

Check budgets before cutover and again after startup. Healthy containers and an
HTTP health response do not prove that media preparation or registration previews
can run. Inspect the active SQL `media_budget_profiles` approval, its matching
serving profile file and current resource compatibility; independently inspect
the approved SQL `preview_profiles` row and actual preview worker caps. Record
missing, superseded or incompatible approvals as a functional acceptance failure.
A retained JSON file is not authority when SQL was reset or has no approved row.

If renewal is needed, reuse explicit budget authorization from the conversation.
Without it, prepare a read-only proposal with concrete finite limits before asking
for approval; never infer budget authorization from an ordinary deployment request.
With authorization, complete renewal using the existing budget owners:

- Use the committed serving-compatible image in maintenance containers. Preserve
  a freshly verified paired backup and a private copy of any existing profile;
  stop and join affected writers before approval. Keep proxy, sources and volumes.
- For media, use `src.backend.dataset.media_acceleration.budget_admin` with the
  indexer's actual UID, CPU/memory/memlock/device caps and output/cache mounts.
  Mount the existing profile volume at a separate writable maintenance alias;
  leave the serving path read-only. Use direct administrator SQL credentials
  through a private read-only mount, never elevate a serving role.
- Preview finite endpoints against actual free space, retained byte debt and
  resource limits. The checked-in production endpoints are a proposal, not a
  machine-independent approval. Do not blindly allocate 512 GiB. GPU credits
  require successful current complete-path qualification; otherwise report zero.
  Approve the exact freshly previewed digest, never a remembered one. If SQL
  committed but file publication failed, use the owner's `install` operation for
  that exact approved version/digest rather than approving again blindly.
- Registration previews use the independent `PreviewBudgetAdministration` owner
  in `src.backend.dataset.previews.budget_admin`, with the preview service's
  actual output root and finite CPU/memory/process caps. Preview and approve its
  exact digest separately; a media approval does not approve preview jobs.
- Recreate affected services through the normal approved release lifecycle and
  read back effective approvals. Verify preparation/preview behavior through the
  trusted proxy when authorized input exists. Existing blocked media intents need
  an explicitly authorized administrator retry; do not silently retry all jobs.
  Report missing input or outstanding retries instead of claiming playback works.

### Preprocessing image and environment inventory

When preprocessing is enabled, compare the site's `.docker.env`, the explicit
launcher environment, the selected Compose model and the existing node catalog.
Carry the selected values into the launcher process: it chooses the GPU overlay
from `PREPROCESS_AUTO_LABEL_IMAGE_DIGEST` or `PREPROCESS_UMI_POST_PROC_IMAGE_DIGEST`,
not from Compose interpolation. Preserve `PREPROCESS_ENABLED`, `PREPROCESS_RUNNER_ID`,
`FEISHU_ENABLED`, `DATAPILOT_DATASET_OVERRIDE`, source mounts and existing mode inputs.

| Setting | Consumer and release check |
| --- | --- |
| `WEB_IMAGE_TAG` | Host services use the qualified Web image; persist its plain custom build tag after verification. |
| `PREPROCESS_STATIONARY_IMAGE_DIGEST` / `PREPROCESS_STATIONARY_NODE_VERSION` | Private DinD worker and immutable catalog version; current Compose defaults the version to 4 when absent. |
| `PREPROCESS_AUTO_LABEL_IMAGE_DIGEST` / `PREPROCESS_AUTO_LABEL_NODE_VERSION` | Private DinD worker and supported catalog/adapter version; qualify the pair together and check the selected revision's supported versions. |
| `PREPROCESS_UMI_POST_PROC_IMAGE_DIGEST` / `PREPROCESS_UMI_POST_PROC_NODE_VERSION` | Private DinD worker and its supported catalog/adapter version; qualify the pair together. |
| `PREPROCESS_GPU_RUNTIME_IMAGE` | Host Docker image for the private GPU DinD service, not an algorithm worker. |
| `PREPROCESS_UMI_VIEWER_IMAGE` | Host Docker viewer service; inspect the effective Compose default when the site omits this key and verify compatibility with worker visualization output. |

Resolve current supported versions and defaults from `preprocess_service.py`,
`business/preprocess_catalog.py`, and the selected preprocessing Compose overlays.
Do not turn a missing optional key into permission to enable a service. Preserve
unchanged image pins; a Web-only release does not require rebuilding every worker.
Verify every configured worker pin in the actual private daemon. A documented pin
or previous deployment record is not evidence that its artifact is available;
report missing artifacts without silently clearing an enabled node's setting.

For first enablement, missing approved nodes, changed worker packaging, or scheduler
recovery, read [Preprocessing rollout and recovery](references/preprocessing-rollout.md).
It covers applicability diagnosis, missing service identities, Compose ownership,
private-daemon handoff and execution acceptance. An unchanged preprocessing rollout
needs the inventory and verification checks here without loading that reference.

## 3. Prepare a task-owned operations container

The launcher needs its approved container for policy rendering, private-file
checks and trusted network probes. Prefer a dedicated Compose helper named
`robox-datapilot-dp<task-id>-<unique-four-character-suffix>`. Record every created
resource and use a unique Compose project. For an explicit helper, current
`prepare_dev_container()` requires all of these actual inspection results:

- `.Config.Image` is exactly `robox-datapilot-dev-recovery:local`;
- the container is running and mounts the canonical primary checkout at
  `/workspace`, with that working directory and the deployment owner's UID/GID;
- `DATAPILOT_DEV_CONTAINER` names this container.

Reuse the approved recovery image; do not retag an unrelated image to impersonate
it. If absent, build the `dev-recovery` target from the committed primary
`docker/dev.Dockerfile` with the approved build configuration. Record ownership
of a newly built image; preserve a pre-existing shared one. Inspect mounts before
running project commands. Do not bind the Docker socket or publish helper ports.

A helper composition under a private `deployment/ops/<run>/` directory can use the
following template after its parameters have been discovered. The external
network must be the existing site's network that permits the required HTTPS
probes; add another existing private network only when an owner needs it.

```yaml
services:
  deploy-operations:
    image: robox-datapilot-dev-recovery:local
    container_name: ${DP_DEPLOY_OPS_CONTAINER:?}
    user: "${HOST_UID:?}:${HOST_GID:?}"
    working_dir: /workspace
    init: true
    entrypoint: ["/bin/sleep"]
    command: ["infinity"]
    cpus: 1
    mem_limit: 4g
    pids_limit: 128
    environment:
      PYTHONPATH: /workspace
      PYTHONDONTWRITEBYTECODE: "1"
    volumes:
      - type: bind
        source: ${DP_DEPLOY_PRIMARY_ROOT:?}
        target: /workspace
        bind:
          create_host_path: false
    networks: [runtime]
networks:
  runtime:
    external: true
    name: ${DP_DEPLOY_RUNTIME_NETWORK:?}
```

Set the template's non-secret parameters, run Compose with an explicit unique
project and file, then inspect the actual container. A correct helper mount
allows operations; it does not authorize developing uncommitted application code
in the primary checkout. Policy-supplied worktree isolation remains applicable
to separate development work.

## 4. Build, qualify and recreate

### Qualify changed preprocessing artifacts

For a rollout that changes node images, identify each affected build entrypoint
under `docker/preprocess/` and its approved base artifact. Build repository-owned
adapters from the committed primary revision. Record the distribution location or
archive identity, platform, immutable image identity and compatible node version.
Load worker artifacts into the actual private DinD daemon; load GPU runtime and
viewer artifacts into host Docker. Inspect each configured reference in its owning
daemon and distinguish image/config IDs from registry manifest digests. Kestra's
Docker Runner uses `pullPolicy: NEVER`; a host-only worker image cannot execute.

The poller registers configured nodes through `preprocess_catalog.py` using
`ON CONFLICT (node_key, version) DO NOTHING`. Changing a digest in `.docker.env`
does not replace the image already stored for that version. Inspect the exact row:
an empty catalog can register a qualified image under a supported version; an
occupied version retains its original digest. Replacing an occupied pin requires
a supported new immutable version and corresponding code, or an explicitly
reviewed compatible migration. Resolve supported versions from the selected source,
including auto-label; do not assume its registration is fixed to version 1.
Do not invent unsupported settings, overwrite catalog
rows, or rewrite existing Pipeline/run snapshots. Determine which manual selection
or new Pipeline revision will consume the qualified pin before cutover.

Include updated `.docker.env.example` pins and affected image/build instructions
in the approved source change when worker or GPU runtime artifacts change. Include
viewer configuration changes when needed for output compatibility. Do not edit
tracked release inputs after selecting the committed build revision.

Before activation, retain a private permission-preserving copy of the site's
configuration and record the exact keys being changed. Apply only qualified image
and version changes to `.docker.env` and the launcher inputs together, before the
affected services are recreated through the existing release owner. Preserve
unrelated settings, comments and file permissions; never source dotenv as shell
code. Re-render the selected model and inspect only the needed non-secret fields.
If activation fails, record whether configuration, services and catalog changed;
do not claim rollback or blindly restore old settings after new work may have run.

### Run the existing release owner

Record the full selected SHA and choose a traceable custom build tag, such as
`jiwu.robotics/robox-datapilot/robox-datapilot-web:release-<12-char-sha>`.
Add a run/time suffix for a separately recorded rebuild when useful. Configure
all discovered authority, mode and helper variables before the invocation:

```sh
WEB_IMAGE_TAG="${DP_DEPLOY_IMAGE:?}" \
DATAPILOT_DEV_CONTAINER="${DP_DEPLOY_OPS_CONTAINER:?}" \
  ./scripts/datapilot-frontend.sh start
```

For an enabled optional mode, carry its complete non-secret configuration into
every launcher invocation and retry. Updating `.docker.env` alone does not supply
the host owner's required stationary digest or select its GPU overlay. Keep a
private invocation record or construct the process environment from an explicit
allowlist; never execute dotenv text or publish secret environment values.

Run with the primary checkout as explicit working directory. The shell entry
only invokes the existing standard-library owner. Let it load the operator's
approved transient build proxy from `~/.zshrc.local`; do not expose those values,
persist proxy ENV in images, or turn off approved build networking to fix a
browser probe. Package mirrors are accessed directly where configured.

The existing owner must complete this order:

1. Check startup fences, actual authority, private inputs and old HTTPS identity.
2. Build Web and Kestra while the old compatible Web still serves. Qualify the
   exact baked schema/ACL resources, restricted content/SQL credentials and
   `pg_dump`, `pg_restore`, `psql`, `mongodump`, `mongorestore` availability.
3. Stop/join Web, indexer, preview and enabled scheduler/preprocessing writers.
   An open-loop writer needs an explicit compatible stop/drain plan. Keep the
   original proxy, databases, volumes, source mounts and CA available.
4. Take a fresh common SQL/Mongo checkpoint. Restore into owned isolated copies,
   qualify actual runtime logins, reconcile and verify the retained proof. Only
   this invocation's successful selected-authority refresh permits startup;
   an old READY file or SQL-only archive is insufficient.
5. Activate the qualified `repository:release-tag@sha256:manifest-digest` and
   recreate Web, indexer and preview with health checks, then the enabled
   scheduler/services. Verify the unchanged proxy identities, or the exact
   explicitly approved authority cutover.

Named immutable activation reads repository digests through the qualified image
ID and verifies the selected named digest resolves locally to that same ID.
Do not assume an image ID is a manifest digest. A bare hash loses the custom
name in Docker inventory; a mutable tag alone cannot prevent concurrent retag
from changing the selected image. Missing/mismatched digest metadata must fail
closed. Do not bypass the owner with a manual Compose restart or bare-tag up.

A stopped-Web recovery is admissible only when the owner verifies the explicit
current SQL/content pair and original retained TLS authority, then performs a
fresh paired qualification. A stopped backend does not authorize remote first
bootstrap or clearing an unfinished operation.

## 5. Verify the actual deployment

- Verify media and preview budget acceptance as described above. Report each
  effective version/digest and compatibility independently of container health.
- Verify Web, indexer, preview, enabled scheduler and both enabled proxy container
  health checks. Read `.Config.Image`, `.Image` and container IDs for the actual
  three writers; compare them with the qualified reference/ID and confirm they
  were recreated. Read back the custom release name in `docker ps -a`. Merely
  tagging an image cannot change an existing container's configured reference.
- Use CA-trusted HTTPS through the selected proxy for `/api/v1/health` and
  `/demo/`. Expect the current authority and ready state. Either LAN or VPN is
  sufficient for browser acceptance; default to LAN. Check additional enabled
  endpoint health without inventing a requirement for two browser sessions.
- Load the changed protected page in a real browser. Use a host browser tool,
  such as host-provided `agent-browser`, with a fresh named session, trusted CA
  and proxy variables removed from the browser process's startup environment.
  Do not install browser-agent tools into project images or disable certificate
  checks. No pre-existing shared browser session may be navigated for this task.
- With `agent-browser`, start with `--session UNIQUE --ca-cert ABSOLUTE_CA_PATH`,
  open the selected HTTPS URL, inspect `snapshot -i`, save a screenshot in the
  private run directory and check `errors`. When that host demonstrably requires
  it, set `AGENT_BROWSER_ARGS=--no-sandbox` only for that fresh browser startup;
  this is not a TLS bypass. CLI `--help` can resolve
  installed syntax differences without loading another Skill or document.
- Prefer an already authorized session. If actual login is needed, use an approved
  private credential candidate without printing it; a stored value is not proof
  it is current. One verified login attempt is sufficient to establish success;
  do not reset accounts or repeatedly guess. Existing local inventory may include
  `deployment/bootstrap-credentials.json` keys `admin` and `tester`. Authenticate only
  through the exact trusted HTTPS origin. The current login route is
  `/api/v1/auth/login`, same-origin POST, JSON `username`/`password`; sensitive
  Cookie values must never appear in tool arguments or output.
- If loading browser state, create a private owner-only file (`0600` under a
  `0700` directory), then pass its path with `--state`. Store credentials/state
  only through checked private files or in-memory handling. Preserve existing
  business data: an empty dataset page proves rendering/readiness, not live
  preview generation or playback. Capture the actual limitation.
- Revoke the temporary session with same-origin POST `/api/v1/auth/logout`,
  close the task browser, and remove its private authentication state. A 200
  unauthenticated health page or a login screen alone is not protected-page proof.

After successful verification, persist the plain custom build tag in the existing
`WEB_IMAGE_TAG` setting in `.docker.env` so the next release builds the intended
named image.
Record the runtime digest binding separately; do not replace a build-tag input
with a bare hash or blindly overwrite the rest of `.docker.env`.

For enabled preprocessing, compare effective recreated-service settings, daemon
image resolution and the authenticated node catalog with the selected pins. For
changed workers, check the Pipeline editor and a new run's frozen version/image
binding, then perform isolated processing acceptance within the authorized scope.
Inspect the actual nested task image and terminal output; service health, catalog
registration or a visible button alone does not prove successful node execution.
For UMI output changes, verify the compatible viewer through the selected proxy.
If suitable isolated input is unavailable, report execution acceptance as incomplete
without modifying existing business data to manufacture a successful run.
Read back the final changed `.docker.env` keys without exposing private settings.

## Failure handling and cleanup

Stop on a failed release gate. Inspect the owner's reported phase, actual
containers/admission and this run's private checkpoint/proof before retrying.
Keep original operation IDs, input digests, namespaces and maintenance fences.
A lost startup acknowledgement may already have allowed target writes. Do not
blindly rerun a migration, reset the database, force-clear markers or start an
incompatible old image. Prefer compatible forward repair; schema/data rollback
requires a verified paired restore, reconciled accepted post-checkpoint writes
and its explicitly approved recovery decision. Image-only rollback is not a
substitute for paired-authority compatibility. State the concrete unresolved gate.

### Historical release images and build caches

After the release and its required health, trusted HTTPS and browser checks
succeed, inventory historical images in the deployed Web release repository and
identify the superseded release tags and exact image IDs. Inspect all containers,
including stopped ones, configured Compose references, other tags on each ID,
and the recorded recovery plan before deleting anything. Remove each confirmed
obsolete, unreferenced release by its exact tag or ID; recheck the ID and its
consumers immediately before removal. Preserve the activated tag/digest and ID,
all container-consumed images, qualified rollback images required by the recovery
rules, other retained pins, shared/base and unrelated images. Do not assume that
removing one tag deletes its image or frees its full reported size. For changed
preprocessing images, follow the private-daemon, catalog and historical-run
reference checks in the preprocessing reference; never treat an idle worker as
unreferenced solely because no container is running.

Inspect the actual builder and its cache records, for example with
`docker buildx ls` and `docker buildx du --verbose`. Correlate cache IDs and
dependency chains with the removed releases using recorded provenance and actual
builder state. Remove confirmed obsolete, attributable cache records by exact ID
using the selected builder's supported ID filter, for example
`docker buildx prune --builder BUILDER --filter 'id=CACHE_ID' --force`.
Check each candidate's consumers and dependencies immediately before deletion;
preserve cache used by active builds, retained images, other releases or projects,
and cache whose ownership or exclusive disposability cannot be established.
Cache descriptions, age, `Shared` status or a single timestamp alone do not prove
that it belongs exclusively to a removed image. Do not use unfiltered or global
prune commands, remove shared builder resources, or disrupt concurrent builds.

Reinspect images, consumers and selected cache IDs after cleanup. Record the
removed tags/IDs and cache IDs, actual reclaimed space when available, and any
retained or unidentifiable candidates with reasons. Treat failed deletion or
unverifiable cleanup as an explicit incomplete cleanup outcome, not a completed
cleanup; report deployment verification separately. If a release gate fails,
retain historical images and caches needed for recovery and apply the failure
handling above rather than carrying out post-success history cleanup.

### Task-owned resources

After success, remove the task helper and temporary probe/test containers,
task-built disposable images, owned networks and disposable volumes. Use exact
recorded names/IDs or task project labels, and check image consumers first.
External production networks are retained. Removing an owned Docker network
removes its bridge; do not manually delete host interfaces. Never use global
prune or `docker compose down --volumes`. Preserve serving images, compatible
rollback images, pre-existing/shared base and development images, production
volumes, media/profile caches, source data, persistent CA, backups and unrelated
containers/worktrees. Preserve old worker artifacts in private DinD, catalog versions
and outputs still referenced by retained Pipelines or historical runs; an image
without a currently running container is not necessarily disposable. On failure,
retain resources needed to recover the original
operation and explain them; delete only independently proven disposable resources.
Branch/worktree removal, especially remote branch deletion, requires its own task
scope and merged-state evidence. Verify cleanup by inspecting Docker again.

## Completion evidence

Store a non-secret per-run record under owner-only `deployment/ops/<run>/` containing:
full Git SHA and selected remote tip; build tag; qualified image ID and named
manifest-digest reference; actual writer IDs/configured references; authority;
checkpoint/recovery-proof paths and verification; selected HTTPS origin/health;
protected-page screenshot/outcome; removed resource names/IDs; retained resources
and reasons; historical release image and build-cache cleanup evidence and any
incomplete cleanup. Never record passwords, Cookies, private keys or browser state.
Include media/preview approval versions, digests, effective finite limits and
resource compatibility, plus actual preparation/playback evidence or its limitation.
For preprocessing changes, also record the changed non-secret configuration keys,
artifact distribution identities and owning daemons, node versions/catalog pins,
Pipeline/run bindings, viewer compatibility and actual execution acceptance outcome.

Report in Chinese: deployed revision/tag, real service health, trusted-proxy and
browser results, cleanup outcome and concrete limitations. A PR merge, successful
build, tag update or container start alone is not completed deployment. Do not
claim deployment when this task only created the Skill or updated documentation.
