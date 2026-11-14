---
name: multica-deploy
description: Deploy and verify the latest stable Multica self-hosted instance with safe localhost defaults and explicit host-service preservation.
compatibility: Requires Docker Engine, Docker Compose v2, Git, Make, curl, OpenSSL, Python 3, and SSH access to the service host.
metadata:
  author: multica-speckit
  source: project-maintained
---

# Multica Deploy

Deploy the upstream Multica self-hosted stack on the host named by the operator.
This Skill is explicit-invocation only because it clones source, generates
secrets, creates persistent volumes, and starts containers. Invoking it
authorizes the default deployment writes described below.

This Skill covers service-host deployment and readback. It does not create a
Multica account or Workspace, authenticate a CLI profile, register a Runtime,
configure a Desktop client, expose a public address, configure router NAT, or
modify an unrelated reverse proxy unless the operator separately authorizes
that work.

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
   include it in a bundle, copy it into a repository artifact, or send it to
   Multica, GitHub, chat, Issue, PR, or ordinary logs.
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

The only required input is the service host:

```text
/multica-deploy host=<service-host>
```

Optional overrides are only needed for a non-default deployment:

```text
/multica-deploy host=<service-host> [user=<ssh-user>] \
  [mode=<inspect|plan|apply>] [install_dir=<absolute-path>] \
  [exposure=<localhost|lan|https>] [bind_ip=<host-ip>] \
  [backend_port=<host-port>] [frontend_port=<host-port>] \
  [release=<concrete-v-tag>]
```

Defaults are `mode=apply`, the SSH account selected by SSH configuration,
`install_dir=/opt/app/multica`, `exposure=localhost`, backend port `8080`,
frontend port `3000`, and the newest stable upstream `vX.Y.Z` release. The
Skill resolves that release to a tag and commit before cloning; it never
deploys a floating branch. The invocation itself authorizes checkout, `.env`
generation, Docker volumes, containers, and Compose recreation. It does not
authorize changes to unrelated services, firewalls, NAT, reverse proxies,
Docker daemon settings, or registry mirrors.
## Packaged support files

The Skill is self-contained. Read the relevant reference before applying it:

- [`references/compose-deployment.md`](references/compose-deployment.md) covers the
  loopback bootstrap, single-interface Caddy overlay, and operations.
- [`references/private-domain.md`](references/private-domain.md) is required for
  private hostnames, split DNS, internal Caddy TLS, client trust, and
  `--resolve` verification.
- [`references/docker-compose.caddy.yml`](references/docker-compose.caddy.yml)
  binds Caddy to one explicit interface.
- [`references/docker-compose.caddy-private-dual.yml`](references/docker-compose.caddy-private-dual.yml)
  binds Caddy to separate authorized LAN and VPN interfaces.
- [`references/Caddyfile.single-origin.example`](references/Caddyfile.single-origin.example)
  is the public-certificate single-origin route template.
- [`references/Caddyfile.private-domain.example`](references/Caddyfile.private-domain.example)
  is the split-DNS `tls internal` route template.
- [`scripts/deploy.sh`](scripts/deploy.sh) is the reviewed release-pinned
  loopback bootstrap. It rejects floating branch names.

Do not execute support scripts from a copied global Skill. Run them from the
target project's installed Skill package or review and copy the exact file into
the authorized deployment checkout.

## Private-domain HTTPS

Private-domain deployment is a separate exposure mode from public HTTPS. Use
the dual-interface overlay only when LAN and VPN bind addresses, split-DNS
ownership, certificate trust, and host-service preservation are explicitly
authorized. A successful `curl --resolve` test proves routing and TLS to one
address; it does not prove that DNS works for clients. Do not report the
deployment as reachable until each client DNS view resolves the canonical
hostname and the client trusts the approved internal CA.

The private-domain reference also records the required `/ws` and
`/api/daemon/ws` routes, the distinction between unauthenticated WebSocket
responses and successful sessions, and why an `/etc/hosts` entry is only a
temporary one-client workaround.

- `inspect` is read-only and inventories prerequisites, directory state,
  listeners, Docker state, proxy state, and existing Multica resources.
- `plan` is read-only and returns the resolved release, file changes,
  host-service risks, commands, and verification matrix.
- `apply` is the default and deploys the resolved release after discovery and
  finishes with target-host readback. Separate-client readback is required only
  for an explicitly selected LAN or HTTPS exposure.

Use default localhost deployment unless the operator selects LAN or HTTPS.
Do not infer a public IP, LAN address, proxy configuration, or existing
service ownership.
## Optional operator GitHub and Lark tooling

GitHub and Lark tooling is an operator-workstation concern, not a prerequisite
for deploying the Multica service. Do not install, authenticate, or configure
either tool as part of `inspect`, `plan`, or `apply` unless the operator
explicitly requests GitHub or Lark work.

When the operator needs reusable GitHub CLI support, first verify the local
CLI and its active account without exposing the token:

```bash
gh --version
gh skill --help
gh auth status
```

Install the official `gh` Skill only from `cli/cli`; do not copy or maintain
its `SKILL.md` manually. Install it at user scope for the active supported
coding agent:

```bash
gh skill install cli/cli gh --agent claude-code --scope user
gh skill install cli/cli gh --agent codex --scope user
gh skill install cli/cli gh --agent github-copilot --scope user
gh skill install cli/cli gh --agent cursor --scope user
gh skill list
```

The installer writes source metadata for later updates. Before any GitHub
write, read the installed `gh` Skill and obtain explicit intent for the target
repository and mutation.

When the operator needs Feishu/Lark access, install the official CLI and
official Skills, then verify the executable:

```bash
npm install -g @larksuite/cli
npx -y skills add https://open.feishu.cn --skill '*' --global -y
lark-cli --version
```

Review package-manager warnings before allowing lifecycle scripts. Do not run
`lark-cli config init --new` or any login command without operator intent:
both require browser or Feishu-client interaction. For user authorization,
request only the needed scope with `lark-cli auth login --no-wait --json`,
present the returned verification URL and a QR code generated with
`lark-cli auth qrcode`, then wait for the operator to confirm completion
before submitting the returned device code. Never print or retain an app
secret, access token, device code, Open ID, or complete granted-scope list.

Read the relevant installed `lark-*` Skill and its references before every
Lark operation. Use explicit `--as user` or `--as bot` when identity matters;
never treat an empty bot result as proof that a user resource does not exist.


## Inputs and interactive access

Require only `host` before beginning. `user` is optional; when omitted, let
SSH select the configured account. For an SSH connection that needs
authentication, prompt in the interactive terminal for either the SSH password
or the path to the private key. Pass a chosen key with `ssh -i <path>` and let
SSH request its passphrase when needed. Never request, copy, write, log, or
place passwords, private keys, or passphrases in chat, repository files, or
command arguments.

Use these defaults unless the operator provides an override:

- install directory: `/opt/app/multica`;
- exposure: loopback-only localhost;
- backend and frontend ports: `8080` and `3000`;
- source: `https://github.com/multica-ai/multica.git`;
- release: newest stable upstream `vX.Y.Z` tag;
- authorization: allowed by this explicit Skill invocation for the default
  deployment writes.

Before writing, discover the target directory, listeners, Docker state, proxy
state, and existing Multica resources. If either default port is occupied,
report its owner and interactively ask for a replacement port; use no
replacement unless the operator provides it. Never take over the listener,
select a port silently, or broaden the bind address.

Ask for an explicit override only when it is necessary:

- LAN requires its physical `bind_ip`; HTTPS requires the intended origin and
  separate authorization for the proxy work;
- a non-default directory must be declared as a new destination or an existing
  Multica checkout to upgrade;
- a specific release tag overrides the latest-stable selection;
- Docker daemon proxy corrections, registry mirrors, firewall, NAT, Caddy, or
  nginx changes require their own explicit authorization.

If an override remains unavailable, continue only with the safe default or
report the specific blocker. A LAN deployment normally uses the physical
private address in all client URLs. Never substitute a Docker bridge, overlay,
VPN, loopback, public address, or stale profile value without explicit
selection.

## Non-negotiable safety rules

1. **Read before writing.** If `install_dir` is nonempty and is not an
   identified Multica checkout, stop and inventory it. Never overwrite unknown
   files.
2. **Pin source and images.** Resolve the latest stable `vX.Y.Z` tag by
   default (or use the supplied concrete tag), record its commit, and use the
   matching image tag. Never mix an unpinned branch with release images.
3. **Preserve secrets.** Let the upstream initializer generate `.env` secrets;
   preserve them across edits and never print complete values. Do not enable a
   fixed verification code on a shared or exposed instance.
4. **Bind narrowly.** For direct LAN exposure, bind exactly to the selected
   physical IP. Never replace it with `0.0.0.0`. Do not publish PostgreSQL.
5. **Preserve unrelated services.** Inventory listeners first. Do not stop,
   reconfigure, or take over Caddy, nginx, an existing Multica deployment, or
   an occupied port. A plan that says port `8080` is occupied is not evidence
   that it is still occupied at apply time; read the current owner back.
6. **Re-read `.env`.** After environment edits, recreate the Compose project
   with `docker compose ... up -d`; `restart` alone is insufficient.
7. **Verify from two locations.** A target-host loopback check is not a LAN
   check. Test the exact bound address from a separate reachable client with
   proxy variables cleared.
8. **Keep deployments separate.** Never copy PATs, cookies, CLI profiles,
   database files, Compose volumes, or credentials from another instance.
9. **Do not report a partial deployment as complete.** Separate created,
   running, healthy, reachable, and client-verified states.

## 1. Read-only target discovery

Run discovery on the service host before cloning or changing files. Capture
facts without exposing secrets:

```bash
python3 -c 'import os,json; p="<install_dir>"; print(json.dumps({"exists":os.path.exists(p),"entries":sorted(os.listdir(p)) if os.path.isdir(p) else None}))'
ss -ltnp
systemctl is-active docker
DockerComposeVersion="$(docker compose version --short)"
docker info --format 'server={{.ServerVersion}} arch={{.Architecture}} containers={{.Containers}}'
```

Also inventory:

- existing containers, Compose projects, named volumes, and published ports;
- the actual owner and command for every relevant listener;
- Docker daemon proxy settings and whether the configured proxy is reachable;
- direct reachability to the upstream Git host and image registries;
- available disk space, architecture, and whether Docker has permission to use
  the requested install directory.

Do not use a failed proxy response as service evidence. A proxy can return a
valid-looking HTTP `503` from the wrong service; direct probes must clear
`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` and their lowercase variants.

If SSH authentication fails, ask interactively for a retry using an SSH
password or a private-key path. Do not accept either secret in chat or retain
it after the session.

If a default port is occupied, report the owning process and ask interactively
for a replacement port. Do not take over the listener, choose a port silently,
or bind more broadly.

## 2. Materialize a reviewed release

From `https://github.com/multica-ai/multica.git`, discover the newest stable
`vX.Y.Z` tag by default. Use a supplied `release` only when the operator
overrides that default:

```bash
git ls-remote --tags --refs https://github.com/multica-ai/multica.git 'refs/tags/v*'
```

Resolve the tag to its commit and record both values. Then clone into the
verified empty destination and check out that tag:

```bash
cd <parent-of-install-dir>
git clone https://github.com/multica-ai/multica.git <install_dir>
cd <install_dir>
git fetch --tags --force
git checkout --detach <release-tag>
git rev-parse HEAD
git describe --tags --exact-match HEAD
```

If the host cannot reach the source repository but the operator authorizes a
transfer fallback, clone and verify the exact tag on a connected machine,
transfer the checkout over the authorized channel, then read back the commit,
tag, and clean status on the service host. Do not copy a working tree from an
unknown branch or silently continue with a partial clone. Remove only a
partial clone created by this Skill after recording that cleanup.

## 3. Initialize self-host state

Read the upstream `Makefile`, self-host documentation, and Compose file before
running the initializer. Confirm the target uses Compose v2 and that the
initializer creates `.env` and random secrets.

Run the supported target with the selected host ports and matching image tag:

```bash
cd <install_dir>
PORT=<backend_port> FRONTEND_PORT=<frontend_port> \
  MULTICA_IMAGE_TAG=<release-tag> make selfhost
```

The initializer may create `.env` before image pulls fail. Treat that as a
partial result, not a successful deployment. Never print `.env` or run a full
`docker compose config` into an unprotected log.

### Registry and Docker proxy failures

Always try the pinned original image references first. A mirror used for an
earlier deployment is not an implicit permanent policy: each fresh install and
upgrade must start with the upstream Compose pull unless the operator explicitly
selected a persistent mirror policy. Do not preconfigure a global Docker mirror
or rewrite Compose image names merely because the host is in a region where an
upstream registry might be slow.

If the original pull fails, separate the failure classes before changing
anything:

- a Git clone failure is a source-transfer problem, not an image-registry
  problem;
- a refused Docker daemon proxy is a host-service problem;
- a registry timeout may leave complete images or reusable layers in the local
  cache; and
- a mirror `403` can mean that the repository is not allowlisted, not that the
  upstream image or local credentials are invalid.

Inspect every pinned image with `docker image inspect`, then retry only missing
original references one at a time. This avoids discarding completed downloads
when one image caused an aggregate Compose pull to fail.

If Docker reports a refused local proxy, inspect the daemon's effective proxy
and the proxy process before changing anything. A stale proxy at a loopback
port is a host prerequisite failure, not a reason to expose ports publicly.

A temporary correction or image accelerator is allowed only in `apply` with
explicit host-service and mirror authorization:

1. preserve the original Docker systemd drop-in and Compose files;
2. retry each missing pinned image from its original registry;
3. use an approved per-image mirror only for references that still fail;
4. compare the mirror manifest digest with the approved source-registry digest
   for the same tag and target platform;
5. retag the verified local image to the original Compose reference;
6. start with `docker compose ... up -d --pull never`, so Compose cannot
   silently contact a different registry after verification;
7. remove temporary mirror overrides, restore any Docker proxy change, and read
   back the effective proxy, image IDs, Compose services, and health.

Never substitute an untrusted registry mirror merely because it is reachable.
Never compare only tag text or image configuration IDs when a manifest digest
is available. See
[`references/compose-deployment.md`](references/compose-deployment.md) for the
reviewed original-first fallback sequence and concrete mirror address forms.

## 4. Configure exposure and URLs

Edit only the intended `backend.ports` and `frontend.ports` entries in
`docker-compose.selfhost.yml`. Containers keep their internal ports `8080` and
`3000`:

```yaml
backend:
  ports:
    - "<bind_ip>:<backend_port>:8080"
frontend:
  ports:
    - "<bind_ip>:<frontend_port>:3000"
```

For direct LAN exposure, set the corresponding non-secret `.env` values:

```dotenv
PORT=<backend_port>
FRONTEND_PORT=<frontend_port>
FRONTEND_ORIGIN=http://<bind_ip>:<frontend_port>
MULTICA_APP_URL=http://<bind_ip>:<frontend_port>
MULTICA_DAEMON_SERVER_URL=http://<bind_ip>:<backend_port>
CORS_ALLOWED_ORIGINS=http://<bind_ip>:<frontend_port>
MULTICA_PUBLIC_URL=
COOKIE_DOMAIN=
MULTICA_IMAGE_TAG=<release-tag>
```

Preserve every generated secret and unrelated setting. Do not expose
PostgreSQL, set a public webhook URL for a LAN-only deployment, or set a cookie
domain unnecessarily. HTTPS and reverse-proxy deployments use the explicitly
authorized origin and must separately verify WebSocket routes.

Read back the rendered structure without printing secret values:

```bash
docker compose -f docker-compose.selfhost.yml config --quiet
```

The quiet validation must succeed. Confirm the backend and frontend host IPs
and published ports with a filtered JSON readback, and confirm the selected URL
values in the service environment without printing secret variables.

## 5. Recreate and verify the stack

Recreate the stack after all `.env` and Compose edits:

```bash
docker compose -f docker-compose.selfhost.yml up -d
docker compose -f docker-compose.selfhost.yml ps
```

Expected state:

- `postgres` is `healthy`;
- `backend` and `frontend` are running;
- published ports match the selected physical bind IP and host ports;
- existing unrelated services remain present;
- named volumes are the intended new project volumes.

From the target host, probe the actual bound address for a LAN deployment:

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  -u http_proxy -u https_proxy -u all_proxy \
  curl -fsS http://<bind_ip>:<backend_port>/health

env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  -u http_proxy -u https_proxy -u all_proxy \
  curl -fsS http://<bind_ip>:<backend_port>/readyz

env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  -u http_proxy -u https_proxy -u all_proxy \
  curl -fsS http://<bind_ip>:<backend_port>/api/config

env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  -u http_proxy -u https_proxy -u all_proxy \
  curl -fsS http://<bind_ip>:<frontend_port>/login -o /dev/null -w '%{http_code}\n'
```

`/health` must report `status=ok`; `/readyz` must report database and
migration checks as `ok`; `/login` must return HTTP `200`; `/api/config` must
report the selected daemon server and app URLs. Read backend environment values
by key and never print secret variables.

A `127.0.0.1` probe is valid only when the service was intentionally bound to
loopback. With a physical-IP-only bind, loopback refusal is expected; verify the
selected bound address instead.

From a separate LAN client, not the service host, repeat `/health`, `/readyz`,
and `/login` with all proxy variables cleared. If the client receives `503`
while the target-host probe passes, first determine whether the response came
from the client's proxy. Then inspect host firewall and LAN routing. Do not
switch to `0.0.0.0`, public-IP exposure, NAT, or an overlay as a workaround.

## 6. Existing service and upgrade boundaries

Read back current listeners after deployment. If an existing Caddy or nginx
service is still present, report its actual port and process. Do not assume the
planned port is still occupied or still belongs to the same service. Never stop
or rewrite it as part of a direct LAN deployment.

For later upgrades, back up PostgreSQL first, use `git pull --ff-only` only on a
reviewed checkout, pin the desired release, recreate the stack, and rerun the
full verification matrix. Never use `docker compose down -v` unless destroying
the database and uploaded files is intentional.

## Failure handling

- **Nonempty install directory:** stop and inventory; never overwrite unknown
  contents.
- **Occupied default port:** report its owner and ask interactively for a
  replacement; do not take over the listener or auto-select a port.
- **SSH authentication failure:** retry only after the terminal prompts for an
  SSH password or private-key path; never accept either secret in chat.
- **No release tag:** stop; do not mix unpinned source with images.
- **Source clone timeout:** verify partial state and clean only the
  Skill-created partial clone. Image acceleration does not repair Git access;
  use an authorized exact-tag, exact-commit checkout transfer fallback.
- **Docker daemon down:** inspect service status and existing containers; do not
  restart blindly when unrelated workloads are running.
- **Stale Docker proxy:** preserve, temporarily override only with approval,
  restore after image staging, and verify the effective setting.
- **Aggregate image-pull timeout:** inspect every pinned image before retrying;
  completed images and cached layers may remain even when the aggregate command
  exits nonzero. Retry only missing original references, one at a time.
- **Mirror `403`:** treat it as a mirror availability or allowlist failure.
  Do not weaken authentication, change the release tag, or assume the upstream
  image is private.
- **Image pull or mirror mismatch:** stop unless the exact source release,
  target-platform manifest digest, and local retag are verified.
- **Health/readiness failure:** inspect backend and postgres logs without
  exposing secrets; do not report the stack as ready.
- **LAN-only reachability failure:** inspect firewall, routing, and client proxy
  state; never broaden the bind address.
- **Authentication testing without SMTP:** an authorized operator may inspect a
  controlled backend log for the immediate one-time code. Never report or retain
  the code, and never enable a fixed code on a shared instance.

## Handoff format

Return a concise deployment handoff containing:

- source tag and commit;
- install directory and Compose project name, but no secrets;
- service names, health states, and exact published bindings;
- Web/Desktop, API/CLI, and WebSocket URLs;
- target-host and separate-client verification results;
- actual existing Caddy/nginx/listener state;
- any temporary proxy or registry remediation and confirmation that it was
  restored;
- unresolved limitations, especially missing SMTP, firewall access, or
  unverified external routing.

Never include `.env` contents, JWTs, database passwords, PATs, cookies,
verification codes, private keys, or complete command-line credentials.
