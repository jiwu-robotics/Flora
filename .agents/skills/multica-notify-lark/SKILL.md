---
name: multica-notify-lark
description: Publish evidence-backed engineering change updates to a Lark group or person with explicit recipient, content, and sender-identity approval.
compatibility: Requires the installed lark-im Skill and lark-cli. Resolving a person by name or email also requires lark-contact.
metadata:
  author: multica-speckit
  source: project-maintained
---

# Multica Notify Lark

Use this Skill when a Human asks to publish an engineering change, release note,
incident update, migration result, verification result, or other technical update
to a Lark/Feishu group or person.

This Skill owns notification preparation, recipient resolution, approval, delivery,
and delivery readback. It does not implement the change, create a Lark group,
change Lark permissions, send credentials, or decide that an unverified change is
complete.

## Required dependencies

Before any Lark operation, read and follow `lark-im` and its required
`lark-shared` instructions. When resolving a person from a name or email, also
read and follow `lark-contact`.

## Mandatory raw prompt and report capture

Every direct invocation must create an exact local record before reading any
source or taking another action.

1. Resolve this installed package's `scripts/prompt_and_report_capture.py` and
   run `start` with Skill name `multica-notify-lark` and `--cwd "$PWD"`. Supply
   the complete triggering user instruction on standard input as exact bytes.
2. Preserve the returned `capture_id`. The helper writes below
   `./.prompt-and-report/` with private permissions and excludes that directory
   from the local Git worktree.
3. Never redact, normalize, commit, bundle, upload, or publish the captured
   prompt or report. In particular, never send the capture archive to Lark.
4. On every terminal path, run `finish` with the same `capture_id`; supply the
   exact final report on standard input before replying to the user.
5. A capture failure blocks any completion claim.


Use `lark-cli` shortcuts rather than constructing raw OpenAPI calls. Never print,
store, or place access tokens, app secrets, cookies, or authorization URLs in the
notification.

## Inputs

Obtain all of the following before delivery:

- **Recipient**: a group name or `oc_...` chat ID, or a person name/email or
  `ou_...` open ID.
- **Message source**: the exact Human-supplied text, or repository evidence from
  the requested change.
- **Repository HTTPS URL**: the exact credential-free `https://...` link for
  the repository associated with the notification.
- **Content type**: exactly one of `code-change`, `milestone`,
  `design-change`, `architecture-change`, or `new-project`.
- **Sender identity**: `user` or `bot`.

If any input is missing or ambiguous, resolve what tools can resolve and ask the
Human only for the remaining decision. Do not infer a recipient from a repository
name, previous chat, or the first search result.

## Workflow

### 1. Select a content template

Select exactly one package template before drafting:

| Content type | Required template |
| --- | --- |
| `code-change` | [`templates/code-change.md`](templates/code-change.md) |
| `milestone` | [`templates/milestone.md`](templates/milestone.md) |
| `design-change` | [`templates/design-change.md`](templates/design-change.md) |
| `architecture-change` | [`templates/architecture-change.md`](templates/architecture-change.md) |
| `new-project` | [`templates/new-project.md`](templates/new-project.md) |

Use the Human's explicit type. If it is absent, classify only when the requested
publication is unambiguous; otherwise ask the Human to choose. Do not publish
another content type with the closest template. A new category requires a
reviewed package template before it can be used for delivery.

### 2. Collect only publishable evidence

For a Human-supplied summary, preserve its facts and intent. For a repository
summary, read the relevant changelog, commits, changed files, and executed
verification output before drafting.

Resolve the repository URL from a published HTTPS remote or obtain it from the
Human. Every template requires this exact credential-free HTTPS URL in its
`仓库` field. Never substitute a local path, an SSH clone URL, a URL with
credentials, or a guessed repository link; if the URL is unavailable, block the
draft.

State only observed facts:

- what changed, in plain language;
- the exact change range and a concise 3–5 point thematic summary drawn from its commits; never enumerate commits.
- user-visible or operational impact;
- verification actually run and its result;
- known risks, blockers, or intentionally unperformed actions.

Do not claim deployment, release, test success, delivery, or completion from a
branch name, file existence, planned work, or a command that was not run. Do not
include private paths, credentials, workspace IDs, Runtime IDs, access tokens, or
unredacted logs unless the Human explicitly provides and approves them for this
recipient.

### 3. Render the selected template exactly

Read the selected template from this package and replace its brace-delimited
fields using only publishable evidence. Preserve its title, field names, order,
and Markdown list format; do not omit, rename, merge, or add fields. Write
`无` only when the evidence establishes that the field has no applicable
content. If a mandatory field is unknown, the draft is blocked until the Human
supplies it or explicitly changes the notification scope.

Keep the rendered message readable to non-specialists. Translate internal
component names into their purpose on first use, while retaining exact
identifiers only when they help recipients act.

### 4. Resolve exactly one recipient

- A supplied `oc_...` chat ID is a group recipient.
- For a group name, run `lark-cli im +chat-search --query <name>` with the chosen
  identity when possible. Search returns only chats visible to that identity.
  Zero results is a blocker; multiple candidates require Human selection.
- A supplied `ou_...` is a personal recipient.
- For a person name or email, use `lark-contact` as the user identity to resolve
  a person. Multiple candidates require Human selection. A bot send may still
  fail if the bot cannot message that person; report that failure without silently
  switching to user identity.

Read back the resolved group name and `chat_id`, or the resolved person display
name and `open_id`, before presenting the delivery request.

### 5. Require explicit delivery approval

Before every send, show the Human all three exact values:

1. recipient: resolved group/person name and stable ID;
2. message: final rendered Markdown or exact text;
3. sender identity: `user` or `bot`.

Send only after the Human explicitly approves that recipient, content, and
identity. This gate applies even when the Human provided an earlier draft. A
request to "send the above" is not approval to choose a missing sender identity
or an ambiguous search result.

If `lark-cli` returns a high-risk-write confirmation gate, present its action,
risk, and key parameters to the Human and wait for explicit approval before
retrying with the CLI-provided confirmation flag.

### 6. Send and read back delivery

Use the resolved endpoint and chosen identity:

```bash
# Group update
lark-cli im +messages-send --as <user|bot> --chat-id <oc_...> \
  --markdown "$MESSAGE" --idempotency-key <unique-key> --format json

# Personal update
lark-cli im +messages-send --as <user|bot> --user-id <ou_...> \
  --markdown "$MESSAGE" --idempotency-key <unique-key> --format json
```

Use one unique idempotency key per intended message so a retry cannot create a
duplicate within Lark's idempotency window. Do not use `--dry-run` as delivery
evidence. Success requires `ok: true` and a returned `message_id`; report the
actual sender identity, recipient, and message ID. If the send fails, report the
returned error and do not claim publication.

## Boundaries

- Never send without the explicit approval gate above.
- Never choose the first matching group or person.
- Never silently fall back from bot to user, from one recipient to another, or
  from Markdown to a different message body.
- Never mark an engineering change as complete merely because its notification
  was delivered.
- Do not create groups, add members, alter permissions, send urgent alerts, or
  attach files unless separately requested and approved.

## Completion report

Report one of:

- `delivered`: sender identity, recipient name and ID, and returned `message_id`;
- `blocked`: unresolved recipient, missing approval, unavailable identity, or
  exact Lark error;
- `not-sent`: draft prepared but the Human declined or changed the request.
