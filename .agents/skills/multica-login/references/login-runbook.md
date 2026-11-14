# Multica login runbook

Use only after `login-plan.json` is `PLANNED`. Replace placeholders with values
from the plan. Do not concatenate untrusted values into shell fragments.

## 1. Endpoint proof

Cloud:

```bash
curl -fsS https://api.multica.ai/health
```

Self-hosted service host:

```bash
curl -fsS <server-url>/health || curl -fsS <server-url>/ready
```

A Web page, reverse-proxy default page, TCP connect, or callback endpoint is not
API proof. Record a non-secret result file and advance to `endpoint_verified`.

## 2. Proxy-cleared Multica wrapper

Every Multica call uses the equivalent of:

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
    -u http_proxy -u https_proxy -u all_proxy \
    multica <arguments>
```

For a remote host, run the same command through the pinned SSH host alias. Do
not clear proxies for SSH itself.

## 3. CLI callback modes

### Direct loopback callback

Use only when the browser and CLI can reach the same loopback listener:

```bash
multica --profile <profile> auth login --endpoint <server-url>
```

Open exactly the URL printed by that CLI process in the isolated Agent Browser
session. Preserve its `cli_callback` and `cli_state` parameters byte-for-byte.

### SSH tunnel loopback callback

For an operator-owned remote CLI, prefer a local tunnel over changing server
firewall rules. Start the remote login with a callback host the browser machine
can reach through SSH; use the exact callback port printed by the CLI. Keep the
login process and tunnel supervised until the same CLI prints completion.

Do not infer tunnel syntax from the service URL. The callback listener and
service API are separate flows. Bind the tunnel to loopback where possible,
verify the listening socket, and remove the tunnel after the login process
finishes.

### Direct callback probe

Use only when the plan selects `direct_callback_probe_required`. Before login:

1. verify the CLI callback bind address and port;
2. prove the browser host can reach that exact callback endpoint;
3. verify host firewall and cloud security-group behavior;
4. stop if any hop is ambiguous.

Do not open a new public port merely to make login easier.

### Private PAT prompt

Use only when the plan selects `private_prompt_pat`. Read the PAT through hidden
input/stdin or a mode-0600 prompt file and remove that file immediately after
login. Never place the PAT in process arguments, typed artifacts, or reports.

## 4. Browser authentication

After `browser_preflight.py` succeeds:

```bash
agent-browser --session <unique-id> open '<exact-cli-login-url>'
agent-browser --session <unique-id> snapshot -i
```

Inspect the rendered account identity before authorizing. Use only element refs
from the latest snapshot. Never rewrite callback query parameters. Close the
isolated session after CLI completion:

```bash
agent-browser --session <unique-id> close
```

Browser authorization is evidence only for `browser_authenticated`.

## 5. CLI completion and readback

Wait for the initiating process to print both:

```text
Authenticated as ...
Token saved to config
```

Then, through the plan's API transport:

```bash
multica --profile <profile> auth status
multica --profile <profile> workspace list --output json
```

A successful browser page without those CLI lines and readbacks is blocked.
Advance to `cli_authenticated` only after both checks.

Resolve the single selected Workspace by `id`, `name`, or `slug`; ambiguous or
missing results block. Then run Workspace-scoped readbacks with the resolved ID
and advance to `workspace_selected`.

## 6. Desktop

Configure the Desktop service URL explicitly. Complete its application callback
and verify the account and Workspace inside Desktop. Do not reuse a CLI profile
token as Desktop evidence, and do not treat Desktop success as CLI success.

## 7. API transport

### Direct API

Run all CLI readbacks directly against the configured profile/endpoint.

### SSH API tunnel

When the browser can reach the service but the CLI cannot, establish an
operator-owned local forward to the authoritative service endpoint. Point the
CLI profile at that local forward for the session, verify `auth status` and
Workspace readback through it, then remove the tunnel. Do not report the tunnel
address as the deployed server URL.

## 8. Runtime execution, only when requested

Verify each required launcher before starting the daemon:

```bash
command -v bun
command -v codex
command -v claude
```

Use only providers requested by the operator. Start or restart the daemon with
proxy variables cleared and a `PATH` containing Bun and the selected launchers.
Then read back:

```bash
multica --profile <profile> --workspace-id <workspace-id> daemon status
multica --profile <profile> --workspace-id <workspace-id> runtime list --output json
```

`multica daemon` performs provider version probes and registers only successful
providers. Runtime names are machine-scoped; rename only when the operator asks:

```bash
multica --profile <profile> --workspace-id <workspace-id> \
  runtime rename <runtime-id> <name> --machine
```

Advance to `runtime_ready` only when every requested provider and Runtime is
present and healthy.

## 9. Failure handling

- Callback failure: preserve the originating CLI output privately, close the
  browser session/tunnel, and create a new plan if the route changes.
- Wrong browser account: stop before authorization.
- CLI timeout after browser success: do not retry authorization blindly; inspect
  callback reachability and initiating process state.
- Workspace mismatch: stop without selecting a substitute.
- Provider probe failure: report the exact launcher/version failure; do not
  claim the Runtime exists.
