# Multica server migration runbook

This runbook supplies command shapes for the lifecycle in [`../SKILL.md`](../SKILL.md). Replace every angle-bracket placeholder only with values recorded in the reviewed plan. Run commands on the named host indicated by the section; do not concatenate untrusted input into a remote shell command.

The current upstream Compose stack has `postgres`, `backend`, and `frontend`; `multica-deploy` may also add Caddy. Never assume those are the complete services or mounts for the source release. Render and inspect first.

## 1. Safe discovery

Run from each install directory. Do not print the rendered Compose model because it resolves `.env` secrets into service environments.

```bash
pwd -P
git remote get-url origin
git rev-parse HEAD
git describe --tags --exact-match HEAD
git status --short
docker compose version
docker compose -f docker-compose.selfhost.yml config --quiet
docker compose -f docker-compose.selfhost.yml config --services
docker compose -f docker-compose.selfhost.yml config --volumes
docker compose -f docker-compose.selfhost.yml ps --format json
docker compose -f docker-compose.selfhost.yml images --format json
df -Pk .
df -Pi .
```

If overlays are used, repeat every Compose command with the exact ordered file set, for example:

```bash
docker compose \
  -f docker-compose.selfhost.yml \
  -f docker-compose.caddy.yml \
  config --quiet
```

Record the effective project name and container IDs. Inspect mounts structurally; the output includes paths and volume names but not volume contents:

```bash
COMPOSE=(docker compose -f docker-compose.selfhost.yml)
PROJECT_NAME="$("${COMPOSE[@]}" ps --all --format json | python3 -c \
  'import json,sys; rows=json.load(sys.stdin); names={row["Project"] for row in rows}; assert len(names)==1, names; print(names.pop())')"

DISCOVERY_DIR="$(mktemp -d "${TMPDIR:-/tmp}/multica-discovery.XXXXXX")"
chmod 0700 "$DISCOVERY_DIR"
trap 'rm -rf -- "$DISCOVERY_DIR"' EXIT
"${COMPOSE[@]}" ps --all -q > "$DISCOVERY_DIR/container-ids"
python3 - "$DISCOVERY_DIR/container-ids" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

ids = [line.strip() for line in Path(sys.argv[1]).read_text().splitlines() if line.strip()]
for container_id in ids:
    data = json.loads(subprocess.check_output(["docker", "inspect", container_id], text=True))[0]
    print(json.dumps({
        "container": data["Name"].lstrip("/"),
        "image": data["Config"]["Image"],
        "mounts": [
            {
                "type": mount["Type"],
                "source": mount["Source"],
                "destination": mount["Destination"],
                "rw": mount["RW"],
                "name": mount.get("Name", ""),
            }
            for mount in data["Mounts"]
        ],
    }, sort_keys=True))
PY
rm -rf -- "$DISCOVERY_DIR"
trap - EXIT
```

For each named volume, record its Docker name, mount destination, writing service, size, and classification. `docker volume ls` alone is insufficient because external volumes may not carry Compose labels.

Read only non-secret database metadata from the running PostgreSQL container:

```bash
COMPOSE=(docker compose -f docker-compose.selfhost.yml)
DB_USER="$(${COMPOSE[@]} exec -T postgres printenv POSTGRES_USER)"
DB_NAME="$(${COMPOSE[@]} exec -T postgres printenv POSTGRES_DB)"
${COMPOSE[@]} exec -T postgres postgres --version
${COMPOSE[@]} exec -T postgres psql \
  --username="$DB_USER" --dbname="$DB_NAME" --tuples-only --no-align \
  --command='select current_database(), pg_database_size(current_database());'
${COMPOSE[@]} exec -T postgres psql \
  --username="$DB_USER" --dbname="$DB_NAME" --tuples-only --no-align \
  --command="select extname || ':' || extversion from pg_extension order by extname;"
```

List configured `.env` key names without values. Treat even key presence as operational metadata; keep this output in the private plan, not a public log:

```bash
python3 - .env <<'PY'
import re
import sys
from pathlib import Path

key = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    name, value = line.split("=", 1)
    if key.fullmatch(name.strip()) and value.strip():
        print(name.strip())
PY
```

Never run `cat .env`, `docker compose config` without `--quiet`, `docker inspect` over the full `Config.Env`, or an unfiltered log capture.

## 2. Target conflict and capacity checks

On the target, inspect before cloning or creating volumes:

```bash
python3 - '<target-install-dir>' <<'PY'
import json
import os
import sys

path = os.path.abspath(sys.argv[1])
print(json.dumps({
    "path": path,
    "exists": os.path.exists(path),
    "entries": sorted(os.listdir(path)) if os.path.isdir(path) else None,
}, sort_keys=True))
PY

docker info --format 'server={{.ServerVersion}} arch={{.Architecture}} containers={{.Containers}}'
docker compose version
docker volume ls --format '{{.Name}}'
docker ps -a --format '{{.Names}} {{.Image}} {{.Ports}}'
df -Pk '<target-parent-dir>'
df -Pi '<target-parent-dir>'
```

A nonempty unknown directory, existing target Compose project, named-volume collision, occupied planned listener, incompatible architecture, or insufficient space blocks restore. Budget for the compressed bundle, unpacked bundle, restored volumes, checkout, images, and operational headroom at the same time.

## 3. Quiesce the source

Run only after the plan and outage authorization are current. Use the complete ordered Compose file set in every command.

```bash
COMPOSE=(docker compose -f docker-compose.selfhost.yml)
${COMPOSE[@]} ps
${COMPOSE[@]} stop <all-writer-services-except-postgres>
${COMPOSE[@]} up -d postgres
${COMPOSE[@]} ps
```

The discovered writer list normally includes `backend`; include workers or customized services that write database or file state. Stop `frontend` and the deployment-owned proxy as well if they can still admit requests. Verify from process/container state that no application writer remains. Do not rely on a maintenance page as write exclusion.

Capture the container and image references before stopping PostgreSQL:

```bash
POSTGRES_CID="$(${COMPOSE[@]} ps -q postgres)"
POSTGRES_IMAGE="$(docker inspect --format '{{.Config.Image}}' "$POSTGRES_CID")"
DB_USER="$(${COMPOSE[@]} exec -T postgres printenv POSTGRES_USER)"
DB_NAME="$(${COMPOSE[@]} exec -T postgres printenv POSTGRES_DB)"
```

## 4. Create the final protected snapshot

Use a source-local filesystem with enough space. The directory and all sensitive files must remain outside the checkout and any synced or backed-up public location.

```bash
umask 077
SNAPSHOT='<absolute-private-snapshot-dir>'
install -d -m 0700 "$SNAPSHOT"
```

Create the custom-format dump inside the container so `pg_dump` has a direct exit status. Do not pipe it into compression:

```bash
REMOTE_DUMP='/tmp/multica-server-migration.dump'
${COMPOSE[@]} exec -T postgres pg_dump \
  --format=custom --no-owner \
  --username="$DB_USER" --dbname="$DB_NAME" \
  --file="$REMOTE_DUMP"
${COMPOSE[@]} exec -T postgres pg_restore --list "$REMOTE_DUMP" > /dev/null
docker cp "$POSTGRES_CID:$REMOTE_DUMP" "$SNAPSHOT/postgres.dump"
${COMPOSE[@]} exec -T postgres rm -f "$REMOTE_DUMP"
chmod 0600 "$SNAPSHOT/postgres.dump"
```

A nonzero `pg_dump`, archive-list, `docker cp`, or cleanup result stops snapshot
creation. The dump is validated while it is still a seekable container file.

Stop PostgreSQL after the successful dump:

```bash
${COMPOSE[@]} stop postgres
${COMPOSE[@]} ps
```

Archive each classified non-database volume while all writers are stopped. Resolve `<docker-volume-name>` from container mount inspection, not from an assumed project prefix. Use the already reviewed PostgreSQL image as a tar helper so migration does not introduce an unrelated image:

```bash
docker run --rm --user 0 --entrypoint tar \
  --volume '<docker-volume-name>:/volume:ro' \
  --volume "$SNAPSHOT:/snapshot" \
  "$POSTGRES_IMAGE" \
  -C /volume -cpf '/snapshot/<logical-volume-name>.tar' .
chmod 0600 "$SNAPSHOT/<logical-volume-name>.tar"
```

Do this for `backend_uploads` and every other `deployment-data` volume. Never do it for the PostgreSQL data volume. For Skill-owned Caddy, archive its data/config volumes only when the plan's TLS strategy is `migrate`.

Copy exact deployment configuration from a reviewed allowlist:

```bash
install -m 0600 .env "$SNAPSHOT/dot-env"
install -m 0600 docker-compose.selfhost.yml "$SNAPSHOT/docker-compose.selfhost.yml"
install -m 0600 '<approved-overlay-or-config>' "$SNAPSHOT/<approved-name>"
```

Do not recursively copy the checkout. Do not include `.git`, logs, `.prompt-and-report`, SSH material, CLI profiles, browser state, or undeclared host files.

Create `manifest.json` with no secret values. It must contain at least:

- schema identifier and snapshot UTC timestamp;
- source host identity, install directory, Compose project and ordered config files;
- Git source URL, exact release tag and commit;
- architecture, service image references, image IDs, and registry digests;
- PostgreSQL server major, safe database name/user identifiers, dump format;
- every payload path, byte size, SHA-256, classification, writer, and restore destination;
- every intentionally excluded persistent object and reason;
- source quiescence evidence and plan identifier.

Hash payloads with Python so the process is portable and each file is read directly:

```bash
python3 - "$SNAPSHOT" <<'PY'
import hashlib
import json
import os
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
rows = []
for path in sorted(item for item in root.iterdir() if item.is_file()):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    rows.append({"name": path.name, "bytes": path.stat().st_size, "sha256": digest.hexdigest()})
print(json.dumps(rows, indent=2, sort_keys=True))
PY
```

Store those digests in the manifest, then hash the final manifest too. Package from the snapshot parent so no absolute paths enter the archive:

```bash
BUNDLE='<absolute-private-bundle.tar.gz>'
tar -C "$SNAPSHOT" -czpf "$BUNDLE" .
chmod 0600 "$BUNDLE"
tar -tzf "$BUNDLE" > /dev/null
python3 - "$BUNDLE" <<'PY'
import hashlib
import sys
from pathlib import Path

path = Path(sys.argv[1])
digest = hashlib.sha256()
with path.open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
```

Record the printed whole-bundle digest in the private plan/receipt. Keep the source stopped.

## 5. Transfer and verify

From the coordinator, use reviewed named SSH hosts. `scp -3` keeps transport encrypted on both legs and need not create a coordinator copy:

```bash
scp -3 -p \
  -o BatchMode=yes \
  -o StrictHostKeyChecking=yes \
  '<source-ssh-host>:<absolute-private-bundle.tar.gz>' \
  '<target-ssh-host>:<absolute-private-incoming-dir>/'
```

If the path or SSH implementation cannot safely support remote-to-remote copy, stage under a coordinator-local mode-`0700` directory, verify the source hash, send to target, verify the target hash, then remove the local copy according to the plan. Never change SSH transport or disable host-key checking after a failure.

On target, set protected modes and recompute SHA-256 before extraction:

```bash
chmod 0700 '<absolute-private-incoming-dir>'
chmod 0600 '<absolute-private-incoming-dir>/<bundle-name>.tar.gz'
python3 - '<absolute-private-incoming-dir>/<bundle-name>.tar.gz' <<'PY'
import hashlib
import sys
from pathlib import Path

path = Path(sys.argv[1])
digest = hashlib.sha256()
with path.open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
```

Require exact equality with the source bundle hash. Extract into a new mode-`0700` directory and validate every per-file digest against `manifest.json` before restore.

## 6. Materialize the target release

Clone the exact source release into a verified empty destination. Never use a floating branch or `latest` substitution:

```bash
git clone https://github.com/multica-ai/multica.git '<target-install-dir>'
git -C '<target-install-dir>' fetch --tags --force
git -C '<target-install-dir>' checkout --detach '<source-release-tag>'
git -C '<target-install-dir>' rev-parse HEAD
git -C '<target-install-dir>' describe --tags --exact-match HEAD
```

The commit and tag must match the bundle manifest. Install the exact approved Compose/config files and protected `.env`:

```bash
install -m 0600 '<extracted>/dot-env' '<target-install-dir>/.env'
install -m 0644 '<extracted>/docker-compose.selfhost.yml' \
  '<target-install-dir>/docker-compose.selfhost.yml'
install -m 0644 '<extracted>/<approved-config>' '<target-approved-path>'
```

Apply only the target-specific non-secret edits listed in the plan—for example a physical bind address when the canonical origin is preserved but the host interface changes. Never globally replace addresses inside `.env`; update named keys and validate the result without printing secrets.

From the target install directory:

```bash
docker compose -f docker-compose.selfhost.yml config --quiet
docker compose -f docker-compose.selfhost.yml pull
docker compose -f docker-compose.selfhost.yml create
```

Read back image IDs/digests and require the plan values. If the registry no longer serves an exact required image, use only the digest-verified image transfer procedure authorized by `multica-deploy`; do not silently use another tag or mirror.

## 7. Restore non-database volumes

Before extraction, prove each target volume is the planned newly created empty volume. Then restore with the same reviewed helper image:

```bash
docker run --rm --user 0 --entrypoint tar \
  --volume '<target-docker-volume-name>:/volume' \
  --volume '<absolute-extracted-dir>:/snapshot:ro' \
  '<exact-postgres-image-reference>' \
  -C /volume -xpf '/snapshot/<logical-volume-name>.tar'
```

Restore every planned deployment-data archive while its writer remains stopped. Read back file count, total bytes, and ownership mode without printing file contents or names that contain user data.

## 8. Restore PostgreSQL

Start PostgreSQL alone. It initializes a fresh target data volume using the preserved `.env` credentials:

```bash
COMPOSE=(docker compose -f docker-compose.selfhost.yml)
${COMPOSE[@]} up -d postgres
${COMPOSE[@]} ps postgres
TARGET_PG_CID="$(${COMPOSE[@]} ps -q postgres)"
TARGET_DB_USER="$(${COMPOSE[@]} exec -T postgres printenv POSTGRES_USER)"
TARGET_DB_NAME="$(${COMPOSE[@]} exec -T postgres printenv POSTGRES_DB)"
${COMPOSE[@]} exec -T postgres postgres --version
```

The target PostgreSQL major must satisfy the plan before restore. Copy and validate the dump inside the target container:

```bash
docker cp '<absolute-extracted-dir>/postgres.dump' \
  "$TARGET_PG_CID:/tmp/multica-server-migration.dump"
${COMPOSE[@]} exec -T postgres pg_restore \
  --list /tmp/multica-server-migration.dump > /dev/null
```

With all application services still stopped, recreate only the application database and restore it:

```bash
${COMPOSE[@]} exec -T postgres dropdb \
  --if-exists --force --username="$TARGET_DB_USER" "$TARGET_DB_NAME"
${COMPOSE[@]} exec -T postgres createdb \
  --username="$TARGET_DB_USER" "$TARGET_DB_NAME"
${COMPOSE[@]} exec -T postgres pg_restore \
  --exit-on-error --no-owner \
  --username="$TARGET_DB_USER" --dbname="$TARGET_DB_NAME" \
  /tmp/multica-server-migration.dump
${COMPOSE[@]} exec -T postgres rm -f /tmp/multica-server-migration.dump
```

Any restore warning or error requires inspection before proceeding; do not retry with weaker flags. Read back safe database metadata and compare it with the snapshot:

```bash
${COMPOSE[@]} exec -T postgres psql \
  --username="$TARGET_DB_USER" --dbname="$TARGET_DB_NAME" \
  --tuples-only --no-align \
  --command='select count(*) from pg_catalog.pg_tables where schemaname not in ('\''pg_catalog'\'', '\''information_schema'\'');'
${COMPOSE[@]} exec -T postgres psql \
  --username="$TARGET_DB_USER" --dbname="$TARGET_DB_NAME" \
  --tuples-only --no-align \
  --command='select count(*) from information_schema.sequences where sequence_schema not in ('\''pg_catalog'\'', '\''information_schema'\'');'
${COMPOSE[@]} exec -T postgres psql \
  --username="$TARGET_DB_USER" --dbname="$TARGET_DB_NAME" \
  --tuples-only --no-align \
  --command='select pg_database_size(current_database());'
```

Counts and size are plausibility checks, not substitutes for the successful dump, transfer hashes, archive validation, and `pg_restore --exit-on-error`.

## 9. Start and verify the target

Starting the backend may run automatic migrations, schedulers, outbound integrations, Runtime reconnect handling, or other database writes. Unless this exact release provides and verifies a supported read-only mode, record `TARGET_WRITER_STARTED` and make the target authoritative before starting it. From that transition onward, failure handling is fix-forward or a new reverse migration—not source restart. Then start backend and inspect readiness before frontend/proxy:

```bash
${COMPOSE[@]} up -d backend
${COMPOSE[@]} ps
${COMPOSE[@]} logs --since '<maintenance-start-utc>' backend postgres
```

Review logs interactively; do not save unfiltered logs because they may contain user content, callback data, or verification codes. Then start remaining services:

```bash
${COMPOSE[@]} up -d frontend <approved-auxiliary-services>
${COMPOSE[@]} ps
```

Probe the exact target binding with all proxies cleared:

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  -u http_proxy -u https_proxy -u all_proxy \
  curl -fsS 'http://<target-bind-ip>:<backend-port>/health'
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  -u http_proxy -u https_proxy -u all_proxy \
  curl -fsS 'http://<target-bind-ip>:<backend-port>/readyz'
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  -u http_proxy -u https_proxy -u all_proxy \
  curl -fsS 'http://<target-bind-ip>:<backend-port>/api/config'
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  -u http_proxy -u https_proxy -u all_proxy \
  curl -fsS -o /dev/null -w '%{http_code}\n' \
  'http://<target-bind-ip>:<frontend-port>/login'
```

For pre-cutover HTTPS, use the canonical hostname against the exact target address:

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  -u http_proxy -u https_proxy -u all_proxy \
  curl --resolve '<canonical-host>:443:<target-ip>' \
  -fsS 'https://<canonical-host>/readyz'
```

Repeat target checks from a separate reachable client. Perform an authenticated
read-only check of existing Workspace, Project, Issue, and upload state without
exporting tokens or rows.

Before cutover, capture the required Runtime set from the migrated Workspace and
each Runtime host. Use proxy-free Multica commands and preserve only non-secret
identity/readback:

```bash
# Authoritative target readback client
env HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= \
  http_proxy= https_proxy= all_proxy= \
  multica --profile '<target-profile>' --workspace-id '<workspace-id>' \
  runtime list --output json

# Each declared Runtime host
env HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= \
  http_proxy= https_proxy= all_proxy= \
  multica --profile '<runtime-profile>' config show
env HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= \
  http_proxy= https_proxy= all_proxy= \
  multica --profile '<runtime-profile>' auth status
env HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= \
  http_proxy= https_proxy= all_proxy= \
  multica --profile '<runtime-profile>' daemon status --output json
```

Record the profile endpoint, Workspace, daemon ID, device/runtime name, exact
Runtime IDs/providers/status, and the `PATH` that resolves every working
provider. Do not print or copy the profile token. Before route change, Runtime
reconnection may remain pending because canonical traffic still targets the
stopped source. Record that distinction without calling it a target restore
failure.

## 10. Cutover, Runtime reconnection, and rollback boundary

Immediately before cutover, verify:

- target remains ready and isolated;
- source application remains stopped;
- plan and bundle identifiers still match;
- the current DNS/load-balancer/proxy value still matches the captured precondition;
- the required Runtime set and per-host profiles are recorded;
- the exact route mutation has separate authorization.

Apply only that route mutation, then repeat exact-host client, authenticated
application, upload, and WebSocket checks. Record when target traffic can first
write. From that instant the target is authoritative.

For an unchanged canonical origin, wait for every required Runtime to reconnect
and verify exact IDs. When the origin changed, repair each Runtime host without
copying credentials or creating replacement rows:

```bash
# On the Runtime host; preserve the captured launcher PATH.
env HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= \
  http_proxy= https_proxy= all_proxy= \
  multica --profile '<runtime-profile>' daemon stop
env HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= \
  http_proxy= https_proxy= all_proxy= \
  multica --profile '<runtime-profile>' config set server_url '<target-server-url>'
env HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= \
  http_proxy= https_proxy= all_proxy= \
  multica --profile '<runtime-profile>' config set app_url '<target-app-url>'
env HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= \
  http_proxy= https_proxy= all_proxy= \
  multica --profile '<runtime-profile>' auth status
env HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= \
  http_proxy= https_proxy= all_proxy= \
  multica --profile '<runtime-profile>' workspace list --output json

# Inspect daemon start --help first; pass identity/update flags only when supported.
env HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= \
  http_proxy= https_proxy= all_proxy= \
  multica --profile '<runtime-profile>' daemon start \
  --daemon-id '<existing-daemon-id>' \
  --runtime-name '<existing-runtime-name>' \
  --no-auto-update

env HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= \
  http_proxy= https_proxy= all_proxy= \
  multica --profile '<runtime-profile>' daemon status --output json
env HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= \
  http_proxy= https_proxy= all_proxy= \
  multica --profile '<target-profile>' --workspace-id '<workspace-id>' \
  runtime list --output json
```

Before restarting, probe every previously working provider using the captured
daemon `PATH`. If the local token is invalid, run `multica-login` on that host;
never copy a token from the target or another client. A daemon is restored only
when it reports the target endpoint and expected daemon ID, and every required
existing Runtime ID retains its provider/daemon ownership and is `online`.

If a Runtime host is also the retired source service host, start only its
Runtime daemon—never the old Compose service. Remain in `RUNTIME_RECONNECTING`
and fix forward while any required Runtime is offline. Enter `OBSERVING` only
after `RUNTIMES_READY` or an explicitly reviewed empty Runtime set.

If failure occurs before target writes, stop target application services, restore the prior route if needed, and restart the unchanged source:

```bash
# Target
${COMPOSE[@]} stop <all-target-application-services>

# Source, from its install directory and exact Compose file set
SOURCE_COMPOSE=(docker compose -f docker-compose.selfhost.yml)
${SOURCE_COMPOSE[@]} up -d
${SOURCE_COMPOSE[@]} ps
```

Verify source `/readyz`, login, authenticated state, uploads, and Runtime reconnection. If target writes may have occurred, do not run the source restart sequence: fix target forward or create a new reverse-migration snapshot with target quiesced.

## 11. Emit the orchestrator relocation receipt

After `RUNTIMES_READY`, create three private, immutable JSON objects:

1. a reviewed plan matching
   [`../contracts/server-migration-plan.schema.json`](../contracts/server-migration-plan.schema.json);
2. an authoritative target readback matching
   [`../contracts/server-migration-target-readback.schema.json`](../contracts/server-migration-target-readback.schema.json);
3. receipt evidence matching
   [`../contracts/server-migration-receipt.schema.json`](../contracts/server-migration-receipt.schema.json)
   except that `receipt_digest` is omitted.

The target readback's `migration_plan_digest` is the SHA-256 of the exact plan
bytes. The receipt evidence carries the exact plan and target-readback byte
digests. Its source/target, origin strategy, Workspace, release, identity sets,
authority state, source-service state, Runtime state, final state, and
observation time must equal the corresponding typed companion fields.

Create a dedicated current-user mode-`0700` output directory before running:

```bash
python3 '<multica-migrate-server-skill>/scripts/emit_server_migration_receipt.py' \
  --evidence '<absolute-private-evidence.json>' \
  --plan '<absolute-reviewed-migration-plan.json>' \
  --target-readback '<absolute-exact-target-readback.json>' \
  --output '<absolute-new-private-receipt.json>'
```

The emitter parses and validates both companion objects, verifies their exact
byte digests and cross-object identity/state equality, then writes the new
receipt without replacing an existing path. Keep all three source files
immutable with the receipt; a digest string alone is not provenance.

Do not hand-write `receipt_digest`. The emitter computes it over the canonical
receipt without that field. A relocation consumer must recompute and compare
that digest before trusting the receipt.

The four identity-set digests cover sorted, canonical readback of the Workspace,
all Projects, all orchestrator Skills/Agents/Squads, and the complete Runtime
fleet. They must be captured from the authoritative target after Runtime
reconnection. Raw CLI output stays beside the private evidence and is never
embedded in the receipt.

The receipt records `source_service_state=stopped` and
`runtime_state=RUNTIMES_READY`. If either statement cannot be proved, do not
emit a receipt and do not start orchestrator relocation.

## 12. Retention


Keep source volumes/checkouts stopped and keep at least one verified protected bundle for the approved observation and retention period. A successful migration does not authorize any of:

```text
docker compose down -v
docker volume rm ...
docker system prune ...
rm -rf <source-install-dir>
rm -rf <migration-bundle>
server decommission
```

Those are separate destructive operations. Before eventual retirement, take a new accepted backup from the authoritative target, verify its restore policy, confirm external callbacks and Runtime fleet are stable, and obtain explicit deletion authorization.
