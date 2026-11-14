# Preprocessing rollout and recovery

Use this reference when enabling or repairing preprocessing, changing worker
packaging, or recovering its scheduler. Follow the main Skill's release sequence
and existing user authorization. Discover all addresses, namespaces, resource
names and image identities afresh; previous incident values are not defaults.

## Diagnose the unavailable-node error

`No approved node applies to this dataset` is the aggregate fallback in
`src/backend/business/preprocess_options.py`. It does not identify a missing
environment variable. Check these boundaries in order:

1. Authenticate through the trusted proxy and inspect
   `GET /api/v1/preprocess/nodes` and
   `GET /api/v1/datasets/{dataset_id}/preprocess-options`.
   An empty `nodes` list directs investigation to registration and the poller;
   populated choices have individual `enabled`, `applicable` and `reason` fields.
   A missing generation or unreadable physical record is a separate source issue.
2. Compare `preprocess_node_definitions` in the actual selected SQL schema with
   the public catalog. Inspect `launcher/preprocess_service.py` and
   `business/preprocess_catalog.py` for registration settings and supported versions.
   Verify the actual poller service exists, is healthy and uses the intended pins.
3. Compare the explicit launcher environment with the rendered Compose model and
   actual recreated services. Include the enable flag, runner ID, selected node
   digest/version pairs and GPU runtime where applicable. Carry these values on
   retries too: the host owner does not derive its feature selection and all
   required inputs from dotenv interpolation.
4. Verify source readability and node-specific applicability using the selected
   published generation and actual read-only mounts. A generic representative
   file check does not prove that a node's required joints or high camera exist.

Enable only the requested nodes. Missing UMI artifacts do not block separately
authorized stationary/auto-label work. Preserve existing Pipeline/default pointers;
an empty default Pipeline does not prevent a valid manual run, and is not permission
to create a site-wide automatic policy.

## Prepare first-use service identities before release preflight

Private files, SQL roles and Mongo users are separate resources. A dormant profile
file can exist while its login does not. The current native branch of
`launcher/preprocess_roles.py` verifies credentials; it does not create missing
native roles or rotate them. The existing-site release preflight also checks
optional profiles before its normal writer stop and backup.

Inspect submission/finalizer SQL and content profiles; GPU mode additionally needs
the independent capacity-observer SQL profile. Inspect required signing/password
files without printing their values. Preserve existing secrets and supported
legacy usernames. For an authorized first enablement with missing identities:

1. Finish qualified builds and read-only inventory before downtime. Prepare only
   missing private inputs, with the main Skill's ownership and mode checks.
2. Stop/join all affected writers, including Web, indexer, preview, scheduler and
   any enabled preprocessing observers/callbacks. Preserve proxy and database
   availability, sources, media/preview approvals and execution epochs.
3. Run `launcher.native_refresh` in the actual immutable serving-compatible image
   for a fresh paired checkpoint and detached restore using the existing runtime
   SQL profiles. Bind its reported image revision to the container's actual image;
   an operations helper must not impersonate that image. Retain the READY proof.
4. After that process releases its lease, provision the missing optional identities
   in a maintenance container under `runtime_admission.controlled_maintenance`
   with a retained operation UUID. Use the selected authority's grant policy
   (`CurrentSchemaAuthority.provision_grants` for the current implementation) and
   the exact `ContentBootstrap`/`ContentAuthorityPolicy` service capabilities.
   Create only absent identities; validate existing roles and original passwords
   without resetting them. Do not run frozen legacy grant lists on a native schema.
5. Qualify the exact schema and real restricted SQL/content logins before releasing
   maintenance. Preserve the original fence/operation if any step fails. Then run
   the normal release owner, which must perform its own fresh paired qualification
   including all enabled profiles before reopening writers. The preparatory READY
   record is recovery evidence, not a reusable release permit.

If the selected revision lacks a supported compatible provisioning path, stop at
that concrete gate and prepare a reviewed repair. Do not grant owner privileges
to application services or rewrite authority inventories to pass preflight.

## Align Compose ownership and retained proxy networking

`release_preflight._content_owner` checks the exact ordered Compose file list,
project, service and primary working-directory labels. Enabling an overlay can
therefore reject an otherwise healthy Mongo container created with the old list.
Render through the same `Release` selection used for the rollout; do not hand-build
a subtly different file order or omit an existing dataset override.

If this ownership change requires Mongo recreation, do it under the stopped-writer
boundary after preserving recovery evidence. Compare image, authenticated command,
secret mounts, private network and both persistent data/config volume identities
before and after. Recreate only that service with the selected model, retaining its
volumes; wait for writable-primary health and verify the original authority again.
Compare mounts by destination and identity, not Docker's returned list order.
Do not patch labels, bypass the owner check or replace data with empty volumes.

The launcher can retain an existing proxy ID while enabling new console/gateway
routes. A configuration reload alone does not attach it to a newly declared
network. Check the selected model and actual enabled proxies' memberships. When
needed for the authorized mode, let Compose create the declared gateway/network
without starting writers, then connect only the declared private network to the
retained proxies. Verify their IDs, CA and published bindings remain unchanged.
Current Compose supports `up --no-start --no-deps --no-build`; do not assume
`create --no-deps` exists. Confirm installed syntax before relying on it.

## Qualify and transfer the actual worker artifacts

- Build the complete worker entrypoint and transitive imports. Previous packaging
  failures involved the PostgreSQL pool, Mongo `bson`, media dependencies and partial
  backend copies. Import the actual modules named in the Dockerfile/entrypoint;
  do not diagnose packaging with a guessed module path. Inspect models/readability
  under the configured non-root UID. A successful image build alone is insufficient.
- Verify base-image provenance, architecture and digest type. A Docker configuration
  ID is not a registry manifest digest accepted by `FROM ...@sha256:`. Use the
  selected approved artifact, keeping transient build proxies out of image ENV.
  A loopback build proxy may require host build networking; domestic package mirrors
  must remain direct. Do not change these inputs merely to avoid inspecting a failure.
- Record host manifest/index identity and the image/config ID actually resolved by
  private DinD after load. They can differ. Worker pins must resolve in that private
  daemon; the GPU runtime image belongs to host Docker. If reproducible worker
  identities are required and no attestation policy requires provenance, an approved
  `--provenance=false` build can avoid varying index metadata. In every case inspect
  the final artifacts instead of predicting IDs or copying a host index ID into the
  node catalog. Rebuild/inspect after source integration before activation.
- Plan storage and time for large model images: a compressed archive, unpacked layers
  and two daemon stores can occupy different filesystems. Stream standard
  `docker image save` to private `docker ... load` when an archive is unnecessary;
  check both process exit codes and inspect the loaded image. Retain the execution
  session and private log across long transfers. Do not treat a quiet load as failure
  or repeatedly import the same large artifact without evidence.
- Preserve the upstream `dockerd-entrypoint.sh dockerd` path when a wrapper
  computes the runner cgroup. Executing `dockerd` directly skips stale PID cleanup
  and init handling. Verify startup with a reused PID file and an unclean restart
  in an isolated daemon; a cold start alone does not exercise this failure.
- If a task-owned qualification daemon populates the production daemon volume,
  record that volume's identity and data root. Never run both daemons against the
  same store concurrently. Stop/remove the qualification daemon before starting
  production, then inspect the pins again through production DinD. Retain the
  production volume/cache and active artifacts during task cleanup.

## Recover storage incidents without silently resetting history

After ENOSPC, check actual Mongo and Kestra readiness and logs. A missing container
does not prove its volume is absent or disposable. Restore services from the
canonical selected model with their original volumes and private inputs.

If Kestra H2 cannot open, stop its process and preserve hashes and copies of the
original database/trace files. Run version-compatible H2 recovery attempts on
copies only, and verify that recovered candidates actually open; a repair command's
exit status alone is insufficient. Keep this distinct from SQL/Mongo business
authority recovery. A fresh scheduler store discards active scheduler history and
requires explicit authorization for that consequence. Reuse an authorization
already given; otherwise present the preserved evidence and concrete choice.
Do not delete the old volume, reuse a corrupt candidate, or report history restored
when only a fresh scheduler has started. Check retained business-run bindings before
resubmitting anything and report any history that remains archived/unavailable.

## Verify execution, then clean up

Check the authenticated catalog and generation-specific options, the Pipeline
editor and protected dataset/run pages through the trusted proxy. For an authorized
processing repair, use a suitable existing small readable dataset with read-only
source mounts and a manual run; do not register new sources or rewrite accepted
annotations to manufacture acceptance. Submit through
`POST /api/v1/datasets/{dataset_id}/preprocess-runs` with the current generation,
supported nodes and a retained valid `Idempotency-Key`. On an uncertain response,
reconcile that request/run before submitting another.

Follow `GET /api/v1/preprocess-runs/{run_id}` through terminal execution and each
node's validated artifact. Match the frozen node versions/image pins, actual nested
worker image and result digests; read result files through their authorized API.
Kestra task completion can precede finalizer acceptance. Container health, a 202
submission or `SUBMITTED` is not successful processing. GPU acceptance additionally
requires fresh trusted capacity and real model inference; do not forge admission,
relax resource policy or stop unrelated GPU jobs to force a passing result.

Verify protected `/kestra/` access, and authenticated-success/anonymous-rejection
against the private scheduler API. Preserve the site's existing authentication
boundary. Save terminal-result/browser evidence, revoke the temporary session and
remove its private state. Record real limitations if inference or source access
remains blocked.

Remove task helpers, the qualification daemon/network, obsolete unreferenced worker
builds in both daemons and disposable transfer archives. Check catalog/Pipeline/run
references as well as running-container consumers before deleting images. Preserve
active worker artifacts, production volumes/networks, compatible rollback images,
shared bases and paired/H2 recovery evidence. Inspect actual absence after cleanup.
