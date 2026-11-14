---
name: datapilot-cli
description: Operate the repository's DataPilot HTTPS CLI and its supported /api/v1 workflows. Use for command selection, authentication, revisions, private output files, and failure recovery; not for CLI implementation or website deployment.
---

# DataPilot CLI

Use this skill to perform an authorized operation through `datapilot` or to explain how its command interface works. The CLI sends HTTPS requests under `/api/v1`. The server owns permissions, workflow transitions, source readiness, and revision checks.

## Start and discover commands

- Prefer an already installed, trusted `datapilot` executable. The package is not published to an npm registry; do not assume `npx @robox/datapilot-cli` can fetch it. For a checkout build, use the repository's Docker Compose development container with the current checkout mounted at `/workspace`. Set the command working directory to `/workspace/src/cli`, then run `npm ci`, `npm run generate:api`, `npm run build`, and `node dist/index.js --help`. Do not build or install dependencies with a host project toolchain.
- Run `datapilot --help`, `datapilot <group> --help`, and `datapilot --version` before relying on a binary's command syntax. `datapilot completion bash|zsh|fish` generates shell completion. Help and completion use the same registry as dispatch and require no credentials or network access.
- Unsupported options, repeated scalar options, and malformed structured input fail locally. The current command families are:

| Family | Supported work |
| --- | --- |
| `auth` | Methods, registration, login, password change, current profile, logout, PAT list/create/revoke/import |
| `datasets`, `storage-sources`, `index-jobs` | Dataset browsing, source candidates and registration, storage/source governance, rescan, media retry, index-job status |
| `projects`, `labels` | Project and label governance, membership, dataset binding, segmentation start, generation adoption |
| `segmentations` | Assigned roots, versions, boundaries, group signals, draft replacement, mode and attestation actions |
| `work-items` | Work-item/task reads, episode inventory and atomic assignment, exact stage submit/send-back, history and source correction |
| `assignments`, `annotations`, `episodes` | Assignment browsing, annotation edits/history, episode presence and source evidence |
| `episode-exports` | Reviewed manifest preparation and separate original-source save |
| `users`, `roles` | People, accounts, roles, Feishu binding, legacy identity resolution, one-time passwords |
| `robots`, `tasks`, `signals`, `robot-states`, `sections`, `poster`, `reports` | Bounded source browsing, downloads, approved sections, poster slots, source-coverage summary |

`datasets catalog` is retired; use `datasets list`. A generated API type does not imply that a CLI command exists.

## Connect and authenticate

- Determine the intended HTTPS origin and actor before a remote request. Use `--url` and, for a private CA, `--ca-file`. The origin must have no userinfo, application path, query, or fragment and must exactly match the selected credential's origin. The CLI verifies TLS and does not follow redirects, infer a proxy, bypass certificate checks, or replay requests.
- Explicit flags `--url`, `--ca-file`, `--token-file`, and `--output` override `DATAPILOT_URL`, `DATAPILOT_CA_FILE`, `DATAPILOT_TOKEN_FILE`, and `DATAPILOT_OUTPUT`. Non-secret `config.json` is the last fallback where supported; it may contain only URL, CA path, and output preference. On POSIX, its directory is `$XDG_CONFIG_HOME/datapilot` or `~/.config/datapilot`.
- `auth methods` and `auth register` use the public flow. `auth login --username USER --url https://HOST --ca-file /private/root.pem` prompts for a hidden password; automation may use `--password-stdin` or `--password-file`. A successful login stores an origin-bound Cookie session. Administrator governance, token management, full-inventory reviewed export, and source-save require that Cookie.
- A selected `--token-file` loads one origin-bound PAT and never falls back to the Cookie. PATs may perform server-authorized reads and annotation/review writes, but cannot replace Cookie authority for administrator operations. Import a PAT from stdin with `auth tokens import --token-stdin --token-output-file NEW_PRIVATE_FILE --url https://HOST`; do not put it in a command argument.
- On POSIX, private directories must be owned by the current user with mode `0700`; private files must be regular, user-owned, mode `0600`, and not symlinks. Windows uses current-profile ACL checks. Keep passwords, PATs, Cookies, one-time secrets, and export capabilities out of command history, stdout, and tracked files.

A read-only scripting pattern is:

```sh
datapilot datasets list --url https://HOST --ca-file /private/root.pem \
  --token-file /private/token.json --output json
```

## Use exact workflow state for writes

- Read the current owner resource before a mutation. Dataset binding and `projects start-segmentation` use the dataset-assignment revision in `--revision`; `0` is valid only before first binding. Storage-source, dataset-source, segmentation, annotation, and work-item revisions belong to different resources. Do not substitute one for another.
- Registration can enqueue an index job without making a dataset ready. Check `index-jobs show JOB_ID` and `datasets show DATASET_ID` before binding a generation. For a recording dataset, `segmentations save-draft` replaces the complete draft under the current configuration/work-item/stage identities; source cut ranges are half-open. Publish through `work-items submit --stage segmentation`. Adoption of a newer generation is an explicit `projects adopt-active-generation` action, not an automatic refresh.
- `work-items episodes PROJECT_ID` returns the exact per-episode assignment, source, work-item, and publication pins needed by `work-items assign-episodes`. Each `--entry` is a complete JSON object with `dataset_id`, `episode_id`, `annotator_id`, `reviewer_id`, `expected_assignment_revision`, `source_generation_id`, `source_fingerprint`, `work_item_id`, `expected_work_item_revision`, `segmentation_stage_revision_id`, and `segmentation_version_id`; preserve null-valued fields from inventory. A batch is atomic within one project, with no automatic retry.
- Stage submission and send-back use the work-item aggregate `--revision` and exact `--stage-revision-id`. Annotation/review stages also need `--task-id`. Review submission supplies an explicit `--segment-decision` for every pending annotation; a generic send-back is not a substitute. Annotation frame intervals are inclusive, unlike segmentation source cuts.
- `episode-exports prepare DATASET_ID --input-file SCOPE_JSON --output-file NEW_MANIFEST` saves verified original response bytes for a single, selected, or full-dataset scope. A requested source-save capability is a separate private file via `--save-token-output-file`; its absence means manifest-only success. `episode-exports save-source DATASET_ID EXPORT_ID --input-file MANIFEST --save-token-file CAPABILITY --yes` transmits the unchanged bytes and needs an independent current source-write grant. Never reconstruct the manifest from parsed JSON.

Remote mutations require the user's task authorization. Use `--yes` only where the registered command requires explicit destructive or source-save intent; a prompt flag does not replace backend permission or a current revision.

## Handle output and failures

- Default output is `table`; select `--output json` for automation. Requested data goes to stdout and sanitized diagnostics to stderr. Downloads and manifests must target new paths; the CLI publishes only complete files and never replaces an existing destination. One-time secrets go to checked private files, not normal output.
- Exit codes: `0` success; `2` local argument/private-file error; `3` authentication or permission (401/403); `4` missing resource (404); `5` conflict or precondition (409/412/428); `6` bad request or validation (400/422); `7` throttling, unavailability, or failed read transport; `8` unknown write outcome or damaged successful response; `130` interruption.
- After exit `5`, refresh the authoritative resource and prepare a new deliberate request. After exit `8`, inspect server list/history and any complete local output before deciding whether to write again: server success can precede local file failure. Never blindly replay an uncertain write. A source-save result of `denied` or `failed` is nonzero even if HTTP status is 200.

The CLI is not a generic HTTP shell. If a requested operation has no registered command, report that coverage gap and do not guess a path or bypass the API through database or dataset mounts. Use a direct HTTP API only when its exact contract and the user's authorization are available. Report the target origin, operation, returned identity/revision, and outcome without exposing private values.
