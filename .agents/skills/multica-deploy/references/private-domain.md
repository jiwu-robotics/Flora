# Private-domain HTTPS deployment

A private hostname is not a public deployment. A Caddy container can terminate
HTTPS on a LAN or VPN interface without public DNS, router NAT, or a public-IP
listener, but the name-resolution and trust steps must be explicit.

## Boundary and naming

Choose one canonical HTTPS origin, for example:

```text
https://multica.internal.example
```

Use that same origin for `FRONTEND_ORIGIN`, `MULTICA_APP_URL`,
`MULTICA_PUBLIC_URL`, `MULTICA_DAEMON_SERVER_URL`, and
`CORS_ALLOWED_ORIGINS`. Browser, CLI, and daemon clients must not alternate
between an IP URL and the private hostname; doing so splits cookies, origins,
and WebSocket policy.

Keep the backend and frontend published only on their approved service-host
interfaces, or keep them loopback-bound when Caddy is the only entry point.
Bind Caddy with `docker-compose.caddy-private-dual.yml` when LAN and VPN DNS
views resolve to different physical addresses. Every port mapping must name an
explicit interface. Never replace the mappings with `0.0.0.0`.

Do not add public DNS, router NAT, or a public-IP URL unless that exposure is a
separate approved change. Preserve unrelated services and verify port owners
again immediately before Compose starts.

## Split DNS

Create records in the DNS views used by each client network:

```text
LAN view:  multica.internal.example -> <lan-bind-ip>
VPN view:  multica.internal.example -> <vpn-bind-ip>
```

Do not publish an unreachable `AAAA` record. A public resolver returning
`NXDOMAIN` is expected when the name exists only in split DNS; it is not proof
that Caddy or the application is down. If the organization has no DNS service
for a temporary one-client check, an `/etc/hosts` entry is an operator-local
workaround, not a deployment solution.

## Certificate trust

For a private name, use `Caddyfile.private-domain.example` with `tls internal`
unless an authorized DNS-01 certificate workflow is available. After Caddy
starts, obtain its local root certificate from the Caddy data volume through an
authorized channel and install it in every client trust store. Never commit the
certificate, key material, or generated Caddy data to this repository.

On macOS, a user-scoped trust installation avoids changing unrelated system
trust settings:

```bash
security add-trusted-cert \
  -r trustRoot \
  -k "$HOME/Library/Keychains/login.keychain-db" \
  <caddy-root.crt>
```

A system-wide trust installation requires local administrator authorization.
Do not put that password in a Skill, script, shell history, issue, or log.

## Verification order

First verify the service host and Caddy configuration without printing secrets:

```bash
docker compose -f docker-compose.selfhost.yml \
  -f docker-compose.caddy-private-dual.yml config --quiet
docker compose -f docker-compose.selfhost.yml \
  -f docker-compose.caddy-private-dual.yml ps
```

Then verify the exact binding from a separate client. `--resolve` is useful when
split DNS has not propagated yet because it preserves the TLS hostname while
selecting a specific test address:

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  -u http_proxy -u https_proxy -u all_proxy \
  curl --cacert <caddy-root.crt> \
  --resolve multica.internal.example:443:<test-bind-ip> \
  -fsS https://multica.internal.example/health
```

Use `/health` for liveness and `/readyz` for database/migration readiness. Also
check `/login` and `/api/config`; the latter must return the selected daemon and
app URLs. Verify both `/ws` and `/api/daemon/ws`. An unauthenticated `400` or
`401` can prove that the request reached the backend, but it is not a successful
authenticated WebSocket session; record that distinction.

Only after DNS is configured should you repeat the same checks without
`--resolve`. A successful `--resolve` probe does not prove that clients can
resolve the private name.

## Failure boundaries

- DNS failure: fix the LAN/VPN DNS view; do not broaden Caddy to `0.0.0.0`.
- Certificate warning: install the approved internal root CA; do not use `-k` as
  the permanent client configuration.
- HTTP `503` from a client: clear proxy variables, then inspect routing and
  firewall policy before changing service bindings.
- WebSocket `404` or `502`: inspect the Caddy route and backend logs; retain the
  explicit `/ws` and `/api/daemon/ws` handlers.
- Port conflict: identify the current owner and stop; never stop or rewrite an
  unrelated reverse proxy or service automatically.
