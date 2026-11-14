---
name: multica-create-agent
description: Import a real network Skill and create a Multica agent only after the user selects an existing or newly registered runtime and its model.
compatibility: Requires Multica CLI v0.4.26 or newer and an authenticated Multica workspace.
metadata:
  author: multica-speckit
  source: project-maintained
---

# Multica Create Agent

Import a real Skill from a user-provided network source and create a Multica agent bound to that Skill.

## Core principles

1. **The Skill must be a real resource:** never copy an external `SKILL.md` in full into an agent system prompt as a fake Skill. Import it with `multica skill import`, then bind it with `multica agent skills add`.
2. **Pin the account and workspace explicitly:** confirm `auth status`, discover the profile, server, and workspace; pass `--profile` and `--workspace-id` explicitly instead of relying on implicit defaults.
3. **Runtime and model are a user decision:** before any Agent creation, require the user to choose either an existing online runtime plus one of its supported models, or a newly registered runtime plus a supported model. Do not select either on the user's behalf.
4. **Never guess execution configuration:** use only a runtime UUID returned by `runtime list` and a model identifier supported by that runtime. Do not silently inherit a local/default model. If a provider exposes no selectable model, require the user to explicitly accept its runtime-managed default policy.
5. **Keep system prompts lightweight:** agent instructions contain only the role, scope, execution boundaries, and the instruction to use the bound Skill as the authoritative contract. Keep the detailed workflow in the Skill file to avoid duplicated rules drifting apart.
6. **Do not expose credentials:** never output tokens, cookies, API keys, or complete secret environment values, or save them outside the mandatory private raw prompt/report archive. Reports may show the account, server address, resource IDs, selected model, and non-sensitive status only.
7. **Read back every write:** separately verify Skill imports, runtime registration when applicable, Agent creation including runtime/model, Skill binding, and environment-variable updates.

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

## Inputs

Confirm with the user or obtain from an explicit user instruction:

- Skill or repository network URL
- New agent name
- Which authenticated account to use; when the user specifies an account, use that account's active session
- Workspace visibility: private to the user or available to the whole workspace
- Required runtime path:
  - select an existing runtime; or
  - register a runtime on a user-specified machine
- Required model selection for the chosen runtime
- For a new runtime: machine, runtime display name, built-in AI coding tool or custom runtime profile, and authorization to install/authenticate tools and start or restart the daemon
- Optional thinking level, service tier, and environment variables

If visibility is unspecified, default to `private` and do not broaden workspace access. If the user explicitly requests workspace access, use `public_to` plus `--public-to-workspace`. Runtime and model are not optional defaults; creation remains `BLOCKED` until the user makes both decisions or explicitly accepts a runtime-managed model policy for a provider with no model picker.

## Standard procedure

### 1. Check the CLI, account, and configuration

```bash
multica version
multica auth status
multica config show
```

Requirements:

- CLI version must be `0.4.26` or newer; stop and request an upgrade for older versions.
- `auth status` must show an active session; if not logged in, stop. Do not fabricate credentials or log into another person's account.
- Record the current server URL, profile, and account; only confirm that a token exists, never print its complete value.

### 2. Require the runtime and model decision

```bash
multica --profile <profile> workspace list --output json
multica --profile <profile> --workspace-id <workspace-id> runtime list --output json
```

If more than one workspace exists, use the user's selection. If none was
provided, list the workspaces and ask; never guess.

From `runtime list`, present the eligible choices with:

- runtime name and exact UUID;
- `online`/`offline` status;
- owner/access, machine/device, provider or protocol family;
- capability constraints relevant to the Skill;
- the runtime's available model identifiers;
- supported thinking levels and service tiers when returned.

If the installed CLI returns runtime records without their model catalogs,
report that readback gap and use the selected runtime's model picker in Multica
Web to present the exact available values. Require the user to choose there or
provide that exact value back to the CLI flow. Do not infer model IDs from
provider documentation, another runtime, or local configuration.

Do not collapse this to “a suitable runtime was found.” Ask the user to choose
one of two paths:

1. **Use an existing runtime:** select one exact online runtime and one model
   from that runtime's catalog.
2. **Register a runtime:** specify the execution machine and AI coding tool or
   custom profile, register it, then select one model from the registered
   runtime's catalog.

Even when only one eligible runtime or model exists, show it and require the
user's explicit selection. A user-supplied model must still be checked against
the selected runtime. Never substitute a similar model, move the Agent to
another runtime, or omit `--model` because a local CLI has a default.

Some runtimes manage models internally and expose no model picker. For those
only, show `runtime-managed default` as the model policy and require the user to
accept it explicitly. Record that policy instead of fabricating a model ID.

The selected runtime must satisfy all of these conditions:

- `status` is `online`;
- `id` is the UUID returned by the current workspace-scoped readback;
- owner/access, provider, device, and capabilities match the Agent's needs;
- the selected model belongs to that runtime's current catalog, or the user
  explicitly accepted its runtime-managed default policy.

### 2.1 Use an existing runtime

After the user chooses the runtime/model pair, read `runtime list` again
immediately before Agent creation. If the runtime is offline, its catalog
changed, or the model is no longer available, stop and present the refreshed
choices. Do not fall back automatically.

### 2.2 Register a user-specified runtime

There is no `multica runtime create` command for an actual online runtime.
A runtime is registered by a daemon on the selected machine for a detected AI
coding tool or compatible custom runtime profile.

Before acting, require the user to specify:

- execution machine and whether it is the current machine;
- authenticated Multica profile and workspace;
- runtime display name;
- built-in AI coding tool, or custom profile display name, command, and
  compatible protocol family;
- intended model, to be verified after the runtime catalog is available;
- authorization to install or authenticate the tool and start/restart the
  daemon.

For a built-in tool on the current authorized machine, verify that the tool is
installed and authenticated, then start or restart the daemon:

```bash
multica --profile <profile> daemon start --runtime-name <runtime-name>
# If the daemon is already running and must re-detect a newly installed tool:
multica --profile <profile> daemon restart
multica --profile <profile> --workspace-id <workspace-id> runtime list --output json
```

For a compatible wrapper or version-pinned executable, a workspace owner/admin
may first create a custom profile:

```bash
multica --profile <profile> --workspace-id <workspace-id> \
  runtime profile create \
  --display-name <profile-name> \
  --command-name <executable> \
  --protocol-family <supported-family> \
  --output json
multica --profile <profile> daemon restart
multica --profile <profile> --workspace-id <workspace-id> runtime list --output json
```

A custom profile is not an online runtime: it does not install or authenticate
the command, and no runtime exists until the selected machine's daemon resolves
and registers it. On a remote machine, give the operator the scoped commands
and remain `BLOCKED`; never start a daemon on a different machine as a
substitute.

After registration, present the new current runtime and its model catalog.
Require the user to confirm the exact runtime/model pair. If the intended model
is unavailable, ask the user to choose another returned model or another
runtime; do not create the Agent with a fallback.

### 3. Locate the real Skill directory in the network source

Prefer a direct import:

```bash
multica --profile <profile> --workspace-id <workspace-id> \
  skill import --url <url> --output json
```

If the service reports that the root directory does not contain `SKILL.md`:

1. Read the network repository root and its plugin or marketplace manifests to locate the directory that actually contains `SKILL.md`.
2. For a multi-Skill repository, use a GitHub tree URL:

```text
https://github.com/<owner>/<repo>/tree/<ref>/<skill-directory>
```

3. Run `skill import --url` again. Do not assume from experience that the repository root is the Skill directory.

A typical repository may look like this:

```text
repo/
  .claude-plugin/marketplace.json
  plugins/<plugin>/skills/<skill>/SKILL.md
```

In that case import `plugins/<plugin>/skills/<skill>`, not the repository root or only the plugin directory.

### 3.1 Handle a selected sub-Skill and implicit dependencies

The user may provide an installation selection like this rather than a complete Skill URL:

```bash
npx skills add https://github.com/<owner>/<repo> --skill <skill-name>
```

This means “select the Skill named `<skill-name>` from the repository”; it does not mean to import the entire repository. Locate and import the corresponding directory, for example:

```text
https://github.com/<owner>/<repo>/tree/<ref>/skills/<category>/<skill-name>
```

After import, do not inspect only the Skill name. Read `SKILL.md` and check whether it is a thin entry point or explicitly depends on another Skill, for example:

```text
Call the Skill tool with "grilling".
```

When such a dependency exists:

1. Locate and import the called dependency from the same repository.
2. Bind both the entry Skill and the dependency Skill to the new Agent.
3. Describe the entry/dependency relationship in the final report.
4. Use `skill get` and `agent skills list` separately to confirm that both exist and have `enabled=true`.

Do not copy dependency content into Agent instructions and do not assume that binding an entry Skill automatically binds its dependencies. Reuse a dependency only when it already exists in the target workspace and has been confirmed usable.

Preserve the semantics of frontmatter such as `disable-model-invocation: true`: a Skill with that setting may be triggered only explicitly by the user, and its Agent wrapper must not make it implicit.

### 3.2 Preserve the source and support files

An import may include `agents/openai.yaml` or other support files. They are part of the Skill package; use the file list returned by `skill get` rather than verifying only `SKILL.md`. Preserve the repository, path, branch, and source URL in `config.origin` so later `skill refresh` operations remain possible.

If the user specifies `--skill <name>`, import only that Skill and its explicitly required runtime dependencies; do not import the whole repository indiscriminately.

### 4. Handle import failures

When an import fails:

- Retry once according to the CLI guidance; add `--debug` when the raw server error is needed.
- Record the exact command and error type. Distinguish an incorrect directory, missing Skill, TLS or network timeout, and server-side 5xx error.
- If the URL directory is confirmed correct but the server cannot fetch from GitHub repeatedly, create a temporary local archive in the current working directory. Keep only the target Skill directory so that `SKILL.md` is at the archive root, then use:

```bash
multica --profile <profile> --workspace-id <workspace-id> \
  skill import --file <relative-skill-archive.zip> --output json
```

- The local archive is only a fallback for network import. Delete the temporary source and archive after import; do not commit them.
- Do not call private Multica HTTP APIs to bypass the CLI.

### 5. Verify the Skill

Obtain the real Skill ID from the import result, then read it:

```bash
multica --profile <profile> --workspace-id <workspace-id> \
  skill get <skill-id> --output json
```

At minimum confirm:

- Skill name and description are correct
- `SKILL.md` exists and is non-empty
- support files were imported, such as templates, CSS, scripts, and reference documents
- the Skill ID was not guessed locally or fabricated manually

If a Skill with the same name already exists, do not overwrite it by default. Read and compare its source and content first; use the relevant conflict strategy or `skill refresh` only when the user explicitly requests refresh or replacement.

### 6. Create the agent

Create it with the user-selected runtime/model pair and keep instructions as a lightweight wrapper:

```bash
multica --profile <profile> --workspace-id <workspace-id> \
  agent create \
  --name '<agent-name>' \
  --description '<short-description>' \
  --instructions '<short-wrapper>' \
  --runtime-id <runtime-id> \
  --model '<model-id>' \
  --permission-mode private \
  --max-concurrent-tasks 3 \
  --output json
```

If the selected runtime exposes no model picker and the user explicitly accepted
`runtime-managed default`, omit `--model` and record that policy in the
operation ledger and delivery report. This is the only permitted omission.

Add `--thinking-level <level>` and `--service-tier <tier>` only when the user
selected values returned as supported for the runtime/model pair.

Immediately read the created Agent and compare its runtime and model fields with
the approved pair before binding Skills:

```bash
multica --profile <profile> --workspace-id <workspace-id> \
  agent get <agent-id> --output json
```

If readback differs, stop. Do not bind Skills or repair the mismatch by choosing
another runtime or model without returning the choices to the user.

For workspace visibility, use:

```bash
--permission-mode public_to --public-to-workspace
```

Recommended wrapper content:

```text
You are "<agent-name>". Use the bound `<skill-name>` Skill as the authoritative contract.

Scope: <scope>.
Follow the Skill's workflow, tool boundaries, and verification requirements; do not copy or maintain its long rules.
Reply in the user's language; never fabricate unexecuted results; do not publish, delete, or perform other destructive operations without explicit authorization.
```

Do not put `SKILL.md`, reference documents, or the complete command manual into `--instructions`.

### 7. Bind the Skill

```bash
multica --profile <profile> --workspace-id <workspace-id> \
  agent skills add <agent-id> \
  --skill-ids <skill-id> \
  --output json
```

Confirm that the response contains the target Skill and that `enabled` is `true`.

### 8. Set optional environment variables

Environment variables are replacement operations, not incremental merges. Prefer stdin or a file to avoid exposing values in shell history or the process list:

```bash
printf '%s' '{"KEY":"value"}' | \
  multica --profile <profile> --workspace-id <workspace-id> \
  agent env set <agent-id> --custom-env-stdin --output json
```

Read back after setting them:

```bash
multica --profile <profile> --workspace-id <workspace-id> \
  agent env get <agent-id> --output json
```

If existing variables must be preserved, read the current map first and submit the complete map; do not accidentally clear the environment with `{}`. The final report should list variable names only unless a value is clearly a non-sensitive local address.

### 9. Final verification

```bash
multica --profile <profile> --workspace-id <workspace-id> \
  agent get <agent-id> --output json
multica --profile <profile> --workspace-id <workspace-id> \
  agent skills list <agent-id> --output json
```

All of these relationships must hold:

```text
Selected account
  → Selected profile/server
  → Selected workspace
  → Agent
      ├── User-selected online runtime ID
      ├── User-selected supported model, or explicitly accepted runtime-managed default
      ├── Real Skill ID with enabled=true
      ├── Correct permission scope
      └── Optional environment variables
```

## Important failure experience

### Mistaking the repository root

A GitHub repository's documentation may describe a root `SKILL.md` as a conceptual entry point, while the Multica importer resolves the actual Skill directory. Inspect `.claude-plugin/marketplace.json` or the tree first; when a multi-level plugin layout exists, use the exact tree URL containing `SKILL.md`.

### Source fetch timeout

“service temporarily unavailable” does not necessarily mean that the directory is wrong. Use `--debug` to distinguish:

- `SKILL.md not found`: wrong import directory
- `TLS handshake timeout`: network problem while the server fetches the source
- other 5xx errors: record the raw response and use the local archive fallback

### Agent updates can affect permissions

Some CLI or server updates can recalculate invocation targets. After changing instructions, runtime, model, or another property, read the Agent again; if the runtime/model pair, `permission_mode`, or workspace target changed, explicitly restore the user-approved values and verify them again. Never substitute a new runtime or model merely to preserve availability:

```bash
multica --profile <profile> --workspace-id <workspace-id> \
  agent update <agent-id> \
  --permission-mode public_to --public-to-workspace --output json
```

### Do not confuse Skill binding with prompt content

The final Agent must satisfy all of these conditions:

- `agent get` reports the user-selected runtime ID;
- `agent get` reports the user-selected model; for an explicitly accepted runtime-managed default, its model override is empty and the operation ledger records the user's decision;
- `agent get` lists the target Skill in `skills`;
- `agent skills list` returns the target Skill and shows it enabled;
- instructions contain only a short role wrapper, not the full external Skill.

## Delivery report

Report in the user's language:

- authenticated account (redacted as appropriate) and profile/server URL
- workspace name and ID
- imported Skill name, ID, source, and verified file coverage
- agent name and ID
- runtime name/device, ID, registration path, and online readback
- selected model or explicitly accepted runtime-managed default policy
- selected thinking level and service tier when applicable
- visibility and concurrency limits
- environment-variable names and whether they were verified
- failed retries, fallback paths, and incomplete items

Never include tokens, cookies, API keys, or unnecessary secret content in the report.
