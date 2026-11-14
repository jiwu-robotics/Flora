# Multica Compose deployment reference

`multica-deploy/scripts/deploy.sh` bootstraps a reviewed upstream release into a
new destination. It does not copy the upstream Compose file into this
repository and does not retain generated secrets.

## Prerequisites

The service host needs Docker Engine, Docker Compose v2, Git, Make, curl, and
OpenSSL. Docker must be running. Confirm the destination is absent or empty
according to the Skill's discovery rules, and inventory listeners before any
write.

The bootstrap intentionally uses loopback publication. It does not publish
PostgreSQL and never binds the application to `0.0.0.0`:

```bash
MULTICA_DEPLOY_SKILL_ROOT=<project-local-path-to-multica-deploy>
"$MULTICA_DEPLOY_SKILL_ROOT/scripts/deploy.sh"
```

Without options, the bootstrap installs the newest stable upstream `vX.Y.Z`
release in `/opt/app/multica`, uses matching image tags, and publishes the
backend and frontend only on loopback ports `8080` and `3000`. It resolves and
records the concrete tag and commit before cloning; it does not deploy a
floating branch. Use `--ref` only to select a concrete release, `--directory`
only to select a non-default destination, and `--backend-port` or
`--frontend-port` only after the default port is found occupied and the
operator selects a replacement.

The script generates `.env` secrets only on the target checkout and invokes the
upstream `make selfhost` target. It performs a `/readyz` check against the
selected loopback backend port. Never print `.env` or complete secret values.

## Original-first image acquisition

The normal path always uses the image references shipped by the reviewed
release:

```bash
cd <install-directory>
MULTICA_IMAGE_TAG=<reviewed-release-tag> \
  docker compose -f docker-compose.selfhost.yml pull
```

Include the reviewed Caddy overlay in that command when the deployment uses it.
Do not add a registry accelerator preemptively. Do not configure a Docker
daemon-wide mirror for one Multica deployment: that also changes image
resolution for unrelated Compose projects on the host.

If the original pull fails:

1. Record the failing registry, reference, tag, and error class.
2. Inspect every expected image locally before retrying. A timed-out aggregate
   pull can still leave complete images or reusable layers:

   ```bash
   docker image inspect \
     ghcr.io/multica-ai/multica-backend:<reviewed-release-tag> \
     ghcr.io/multica-ai/multica-web:<reviewed-release-tag> \
     pgvector/pgvector:pg17
   ```

3. Retry only missing original references, one image at a time. Do not move to
   an accelerator while the original registry is working.
4. If an original reference still fails and the operator authorized a mirror,
   use a per-image mirror rather than changing the daemon globally. For the
   image registries used by the current self-host Compose layout, reviewed
   address forms include:

   ```bash
   # GHCR: replace only the registry host.
   docker pull \
     ghcr.nju.edu.cn/multica-ai/multica-backend:<reviewed-release-tag>
   docker pull \
     ghcr.nju.edu.cn/multica-ai/multica-web:<reviewed-release-tag>

   # Docker Hub: prepend the complete original registry path.
   docker pull m.daocloud.io/docker.io/pgvector/pgvector:pg17
   docker pull m.daocloud.io/docker.io/library/caddy:<reviewed-caddy-tag>
   ```

   Read the selected release's Compose files first; image names and tags remain
   release-owned inputs. The examples above are address transformations, not a
   floating latest-version policy. DaoCloud's GHCR form
   `m.daocloud.io/ghcr.io/...` may return `403` for a repository outside its
   allowlist. Treat that as mirror unavailability and use another explicitly
   approved source; do not treat it as evidence that the original GHCR image is
   private. Provider syntax is documented by
   [NJU e-Science](https://doc.nju.edu.cn/books/e1654/page/ghcr) and
   [DaoCloud](https://github.com/DaoCloud/public-image-mirror).

5. Obtain the original manifest digest from the source registry or a connected,
   trusted verification machine. Compare it with the mirror's digest for the
   same tag and target platform. For a multi-platform image, compare the image
   index digest or the selected platform manifest digest consistently; do not
   compare one of those with the image configuration ID.
6. Retag only after the digest matches, then prove that both local tags resolve
   to the same image ID:

   ```bash
   docker tag <verified-mirror-reference> <original-compose-reference>
   docker image inspect <verified-mirror-reference> \
     <original-compose-reference> --format '{{.Id}} {{json .RepoDigests}}'
   ```

7. Preserve the release's original Compose image references and start from the
   verified local cache without another pull:

   ```bash
   docker compose -f docker-compose.selfhost.yml \
     <approved-overlays> up -d --pull never
   ```

Remove a temporary mirror overlay after staging. On the next fresh install or
upgrade, try the pinned original references first again. If direct source
checkout also fails, handle it separately with an authorized exact-tag,
exact-commit transfer; an image accelerator does not repair Git clone access.

## Single-interface HTTPS

Copy the packaged files into the upstream deployment checkout and choose a
single authorized interface:

```bash
MULTICA_DEPLOY_SKILL_ROOT=<project-local-path-to-multica-deploy>
cp "$MULTICA_DEPLOY_SKILL_ROOT/references/docker-compose.caddy.yml" \
  <install-directory>/docker-compose.caddy.yml
cp "$MULTICA_DEPLOY_SKILL_ROOT/references/Caddyfile.single-origin.example" \
  <install-directory>/Caddyfile

cd <install-directory>
export CADDY_BIND_IP=<authorized-bind-ip>
```

Replace the example hostname in `Caddyfile`. Set the same HTTPS origin in the
non-secret `.env` values, including `CORS_ALLOWED_ORIGINS`, then validate and
recreate:

```bash
docker compose -f docker-compose.selfhost.yml \
  -f docker-compose.caddy.yml config --quiet
docker compose -f docker-compose.selfhost.yml \
  -f docker-compose.caddy.yml up -d
docker compose -f docker-compose.selfhost.yml \
  -f docker-compose.caddy.yml ps
```

The Caddy template routes `/health`, `/readyz`, `/ws`, and
`/api/daemon/ws` to the backend and ordinary browser/API traffic to the
frontend. The daemon route is required; omitting it can silently degrade daemon
realtime behavior to polling.

## Operations and upgrades

Use the same overlay for every Compose operation on an HTTPS deployment:

```bash
docker compose -f docker-compose.selfhost.yml \
  -f docker-compose.caddy.yml logs --since 10m backend caddy
docker compose -f docker-compose.selfhost.yml \
  -f docker-compose.caddy.yml up -d
docker compose -f docker-compose.selfhost.yml \
  -f docker-compose.caddy.yml down
```

`up -d` is required after `.env` changes; `restart` does not reread the
rendered environment. Before an upgrade, export and verify a PostgreSQL backup,
fast-forward only to a reviewed release, pull the matching images, recreate,
and rerun the complete readiness and separate-client matrix. Never use
`docker compose down -v` unless deleting the database and uploaded files is
intentional.

For private names and LAN/VPN split DNS, use
[`private-domain.md`](private-domain.md) and the dual-interface overlay instead
of assuming public DNS or public certificate issuance.
