---
name: multica-login
description: "Authenticate Multica Desktop or CLI clients against Cloud, LAN self-hosted, or public self-hosted deployments; verify the selected Workspace and provision requested Runtimes. Use for login, auth, profile, callback, endpoint, Workspace, and Runtime connectivity work."
compatibility: "Requires Multica CLI v0.4.26 or newer for CLI flows; browser authentication uses pinned agent-browser 0.37.1 with npm only for an explicitly authorized install."
metadata:
  author: multica-speckit
  source: project-maintained
allowed-tools: Bash(python3:*), Bash(multica:*), Bash(curl:*), Bash(ssh:*), Bash(agent-browser:*), Bash(npm:*)
---

# Multica Login

Authenticate exactly one Multica client at a time. Endpoint, browser account,
CLI/Desktop client, Workspace, Runtime, and daemon are independent facts. Never
infer one from another.

This Skill performs account authentication and readback. It does not deploy or
upgrade a Multica service, change DNS/TLS/firewall policy, create Workspace
resources, start a daemon unless Runtime execution is explicitly requested, or
move server/orchestrator state.

## Mandatory raw prompt and report capture

This section takes precedence over every lower-level instruction to redact,
omit, or avoid saving invocation or report content. Every direct invocation
must create an exact local record before reading any source or taking another
action.

1. Resolve this installed Skill package's
   `scripts/prompt_and_report_capture.py`. Before proceeding, run its `start`
   command with `--skill multica-login`, `--cwd "$PWD"`, and the exact user
   prompt supplied on standard input. Never place the prompt in command-line
   arguments.
2. Keep the returned `capture_id` available for this invocation.
3. As the final action before the final answer, pass the exact final answer on
   standard input to the same helper's `finish` command with that `capture_id`
   and `--cwd "$PWD"`.
4. If either capture command fails, stop. Do not proceed or report success.

The helper writes exact copies under `<cwd>/.prompt-and-report/`; it applies no
redaction or filtering. The directory and files are private and excluded from
Git by the helper. Never replace the exact raw capture with a summary.

## Required intake

Collect or derive every field in [`contracts/login-input.schema.json`](contracts/login-input.schema.json):

- target type and deployment scope (`cloud`, `public`, `lan`, or `local`);
- authoritative service/API URL and separate Web URL;
- client kind (`cli` or `desktop`) and where that client runs;
- explicit CLI profile, account reference, and exactly one Workspace selector;
- whether Runtime execution is requested;
- HTTP/API route observations and whether an operator-owned SSH path exists.

Account reference is an identity label, not a password, token, PAT, cookie,
verification code, callback state, or credential fragment. Do not put secrets
in typed JSON artifacts. Store typed artifacts only in a new private directory.

## Phase 0: deterministic plan

Create `login-input.json`, then run:

```bash
python3 <skill>/cli/login_workflow.py plan \
  --input <private-run-dir>/login-input.json \
  --output <private-run-dir>/login-plan.json
```

The planner selects exactly one callback mode and one API transport:

- browser-host CLI → direct loopback callback;
- remote CLI over an operator-owned SSH path → SSH callback tunnel first;
- remote CLI without SSH on public/LAN scope → explicit direct callback probe;
- remote CLI without a usable callback route → PAT through a private prompt;
- Desktop → application callback;
- direct API route when proven; otherwise SSH API tunnel when HTTP and SSH are
  available; otherwise `BLOCKED_API_ROUTE`.

Never improvise a second route after the plan. A blocked plan requires corrected
intake and a new plan.

Initialize an immutable session receipt:

```bash
python3 <skill>/cli/login_workflow.py start-session \
  --plan <private-run-dir>/login-plan.json \
  --output <private-run-dir>/session-00.json
```

Advance one state only after producing non-secret evidence and hashing its
exact bytes:

```bash
python3 <skill>/cli/login_workflow.py advance-session \
  --plan <private-run-dir>/login-plan.json \
  --receipt <private-run-dir>/session-00.json \
  --state endpoint_verified \
  --evidence-digest sha256:<64-hex> \
  --output <private-run-dir>/session-01.json
```

Valid states are strictly ordered:

```text
planned
  -> endpoint_verified
  -> browser_authenticated
  -> cli_authenticated
  -> workspace_selected
  -> runtime_ready       # only when execution_requested=true
```

Skipping, repeating, or reversing a state is rejected.

## Phase -1: browser capability preflight

Before every browser-authentication flow, inspect
[`browser-runtime.lock.json`](browser-runtime.lock.json) and run:

```bash
python3 <skill>/cli/browser_preflight.py \
  --cache-dir <private-cache-dir> \
  --output <private-run-dir>/browser-capability.json
```

The preflight requires pinned Agent Browser `0.37.1`, loads `skills get core
--full`, prefers an explicitly configured or discovered system Chrome/Chromium,
and performs a unique-session `about:blank` open/snapshot/close probe. It reuses
cached executable discovery only while version, path identity, and TTL still
match; every invocation still reloads the core workflow and performs the smoke
probe.

If Agent Browser or a browser is absent, installation is forbidden unless the
operator explicitly authorizes it. Then rerun with `--install`; npm installs
exactly `agent-browser@0.37.1`, and managed browser download occurs only when no
usable system browser exists. A npm success line is never capability proof.

## Execution rules

1. Follow [`references/login-runbook.md`](references/login-runbook.md) for exact
   route, callback, browser, CLI, Workspace, daemon, and Runtime commands.
2. Clear `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `http_proxy`, `https_proxy`,
   and `all_proxy` for every `multica` command. Do not clear them for SSH or npm.
3. `--endpoint` identifies the Multica service. A callback endpoint is separate
   and never substitutes for the service URL.
4. Keep browser, CLI, Desktop, Workspace, daemon, provider, and Runtime evidence
   separate. Browser-page success is insufficient for CLI login.
5. For CLI login, wait for the initiating process to print both
   `Authenticated as ...` and `Token saved to config`; then run `auth status`
   and `workspace list --output json` through the planned API transport.
6. Use `--workspace-id` for every Workspace-scoped readback after selection.
7. Do not start/restart a daemon or register a Runtime during login-only work.
8. If Runtime execution is requested, prove launcher/provider availability,
   start or restart the daemon with proxy variables cleared and the required
   `PATH`, then verify `runtime list --output json`.
9. Do not create test Projects, Skills, Agents, Squads, Issues, executions, or
   any other resource to validate authentication.

## Credential handling boundary

A CLI process may display a short-lived verification code and the raw capture
contract archives the exact prompt and final report. Follow the existing
operator-approved interaction policy for this Skill. Never write passwords,
PATs, cookies, JWTs, private keys, callback state, verification codes, or token
fragments to typed plans, receipts, evidence files, command-line arguments,
source files, or Git.

Use hidden terminal input, a private prompt file, or equivalent stdin for
passwords/PATs. Remove temporary prompt files immediately after the consuming
process exits. Never print `.env`, Multica config, browser storage, or complete
authentication logs.

## Blocking conditions

Stop with the exact next action when any of these holds:

- authoritative service URL, account, profile, or Workspace selector is
  ambiguous;
- service/API route is unavailable and no planned tunnel exists;
- callback route is unproven for a remote CLI;
- browser account differs from the intended account;
- initiating CLI never prints both completion lines;
- `auth status` or Workspace readback fails after browser success;
- Workspace selection is ambiguous;
- Runtime execution was requested but provider or daemon evidence is missing;
- browser capability preflight fails or differs from the pinned lock.

## Handoff

Report only observed facts:

- client kind/location, target deployment scope, service URL, and callback/API
  route actually used;
- browser, CLI/Desktop, Workspace, and optional Runtime state separately;
- profile and Workspace identity readback;
- Agent Browser version and capability receipt digest when browser auth ran;
- final session receipt state and digest;
- unresolved blocker and one exact next action.

Never report a client, Workspace, daemon, or Runtime as ready based on another
component's status.
