---
name: multica-coach
description: Analyze any readable local project's Skill set through accepted, evidence-based stages and generate portable Multica Agent, Squad, Issue, and control templates.
---

# Multica Coach

Turn a source project's existing Skills and engineering constraints into a
portable Multica orchestration package. Follow the reference's W1–W8 sequence
exactly:

```text
W1 inputs and capability inventory → W2 rationalization →
W3 artifact dependencies → W4 Feature/Bug DAGs →
W5 Agent responsibilities → W6 Skill bindings and permissions →
W7 Agent/Squad/Issue templates → W8 CI, provider controls, and Human approval
```

This Skill is explicit-invocation only. It generates repository files; it never
imports a Skill into Multica, provisions an Agent or Squad, creates an Issue,
dispatches work, mutates a live workspace, or claims a control is installed.

## Authoritative method

Read [`references/generate-squads.md`](references/generate-squads.md) in full
before starting. It defines the design vocabulary and the authoritative W1–W10
lifecycle. This Skill operationalizes its W1–W8 sequence only:

- W1 fixes the input baseline and inventories capabilities;
- W2 rationalizes duplicate, obsolete, and hidden dependencies;
- W3 defines artifact contracts and dependency graph;
- W4 defines separate Feature and Bug Fix DAGs;
- W5 derives the separated Agent responsibility matrix;
- W6 defines the Skill binding and permission matrix;
- W7 emits copyable Agent, Squad, and Issue templates;
- W8 emits proposed CI, provider-control, and Human-approval templates;
- W9 live trials and W10 evidence-driven revision/publication require separate,
  explicit authorization and are outside this Skill.

Do not add, collapse, reorder, or substitute stages. Do not replace the
reference with a shorter competing method.

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

## Invocation

```text
/multica-coach source_project=<required readable local project path> \
  requirements=<required file path or explicit user requirements> \
  output_dir=<required repository-local path> \
  skills_dir=<optional path relative to source_project>
```

`source_project` is a capability sample, not the product for which the reusable
templates are customized. It may be any readable local project root, expressed
as an absolute path or relative to the invocation directory; use
`source_project=.` when the current repository is the source. Resolve it before
inventory. Reject a missing, unreadable, or non-directory source path.
When `skills_dir` is omitted, use the first readable Skill root in this order:
`./skills`, `./.agents/skills`, then `./.claude/skills`. Resolve an explicit or
detected path relative to `source_project` and reject a missing, unreadable, or
non-directory Skill root; after symlink resolution, it must remain inside
`source_project`. Read the selected source only as capability evidence; never
write to it.

`requirements` supplies the intended orchestration scope and project-policy
decisions. It may reference a requirements artifact owned by the output
repository or the selected source project, or quote explicit user requirements.
Persist the accepted content at the relative path selected during W1 after
redacting source paths, credentials, live IDs, private addresses, account
names, and runtime snapshots. The mandatory raw prompt/report archive is local
only and must never substitute for this portable generated artifact.

A new design starts at W1. A later invocation reads the recorded provenance and
resumes at the earliest `DRAFT`, `STALE`, `BLOCKED`, or missing step; callers do
not choose a stage. A natural-language status request is read-only: report the
current step decisions and the one next step without generating anything.

If older W1–W8 files lack accepted provenance, report `STALE_LEGACY_OUTPUT`.
File presence is not stage acceptance. Resolve ownership and current W1 policy
before rewriting legacy output.

## Generation and write safety

Invocation directly starts or resumes generation at the current sequential step.
Read the required sources, derive the step's complete result, and write its
artifacts under `output_dir`; do not stop at an inspect-only recommendation.

All generated output paths must resolve inside the current repository. Source
inputs may resolve outside it only under the `source_project` and `skills_dir`
boundary above. Preserve unrelated files.
Before changing an existing generated file, compare its recorded input
revisions with current inputs:

- unchanged inputs and equivalent output: report `UNCHANGED`;
- changed inputs: show the affected decisions and replacement diff;
- missing provenance: treat the file as user-owned, show the replacement diff,
  and wait for explicit user confirmation;
- removed generated output: delete it only when the accepted clean cutover makes
  it obsolete and the user explicitly confirms deletion.

Never silently merge a new design into stale output.

## Output contract

This Skill defines logical deliverables, not filenames, file counts, numbering,
or a mandatory directory tree. During W1:

1. inspect the target repository's existing output and naming conventions;
2. derive only the artifacts required by the accepted scope;
3. propose an artifact index mapping each logical artifact ID to one
   repository-relative path under `output_dir`;
4. obtain acceptance of that index before writing later stages.

At minimum, the index must make the following logical groups discoverable when
they are applicable: stage analysis records, Agent Instructions, Squad
Instructions, Issue input contracts, shared handoff/gate schemas, package
manifests, delivery notes, requirements provenance, and enforcement proposals.
One file may contain multiple tightly coupled logical artifacts when ownership,
consumers, and revision lifecycle are identical. Split them when ownership,
permissions, invalidation, or reuse differs.

Never create an empty category, placeholder file, predetermined role file, or
fixed “standard package” merely to match an example. Filenames and paths are
outputs of W1 and remain stable through W8 unless an accepted revision explicitly
changes the artifact index.

Every analysis document starts with this provenance block:

```yaml
coach_stage: W<N>
decision: ACCEPTED | DRAFT | BLOCKED | STALE
source_project: <portable label, never an absolute path>
source_revision: <commit or deterministic tree digest>
requirements_revision: <commit, digest, or message reference>
input_artifacts:
  - <path>#<revision-or-digest>
decisions:
  default_worktree: true | false
  loop_eligible: true | false
  loop_isolation: none | worktree | not_applicable
open_blockers: []
supersedes: <prior revision or null>
```

Record `loop_isolation: not_applicable` when `loop_eligible: false`. When
`default_worktree: true` and `loop_eligible: true`, record
`loop_isolation: none`: the accepted worktree remains the Feature checkout and
Loop MUST NOT create nested iteration worktrees. A later stage
may consume only `ACCEPTED` upstream documents whose recorded revisions still
match. Editing an accepted requirement or upstream document marks every
dependent stage `STALE`; regenerate from the earliest affected stage.

## Analysis language

Every W1–W8 stage analysis record and its checkpoint summary MUST be written in
Chinese. This includes findings, decisions, evidence-card prose, matrix column
content, DAG annotations, blockers, invalidation notes, delivery analysis, and
enforcement analysis. Preserve machine-readable provenance keys, logical
artifact IDs, status keys, code, quoted source identifiers, and required
template schema fields exactly where their contracts prescribe them.

This requirement applies to intermediate analysis artifacts, not to copyable
Agent, Squad, Issue, manifest, or control templates. Their language follows
the accepted requirements and target repository convention.

## Non-negotiable design invariants

### Evidence and portability

1. Read actual `SKILL.md` files, their frontmatter, referenced support files,
   scripts, templates, and `agents/openai.yaml`. Do not infer capability from a
   directory name.
2. A Skill is a method or integration; an Agent owns a stable class of judgment
   or artifact; a Squad routes Agents; CI/provider controls/Humans enforce hard
   constraints.
3. Every handoff has a stable reference, producer, consumers, objective check,
   immutable revision, and invalidation rule. Conversation memory is not an
   artifact locator.
4. A Producer cannot approve its own output. A Leader routes, joins, records
   gates, and escalates; it is never an implementation fallback.
5. Reusable output contains no source-project path, product fact, workspace UUID,
   credential, server address, account/profile, private IP, runtime name, or live
   deployment snapshot.

### Feature/Bug Agent separation

Feature and Bug Fix use different execution Agents. This is mandatory even when
the same runtime or engineering discipline could perform both:

- a Feature production/review/verification Skill may bind only to a
  `work_type: feature` Agent;
- a Bug assessment/fix/test Skill may bind only to a `work_type: bug` Agent;
- no Agent may own both Feature and Bug artifacts, implementation, review, or
  verification;
- shared Agents are limited to work-type-neutral intake, orchestration, and
  platform readback, and may not bind Feature or Bug execution Skills;
- the package manifests and Squad membership lists must make the separation
  mechanically visible.

Bug-to-Feature escalation closes the Bug execution route, preserves its evidence,
and returns to the shared intake Agent for a new current Feature Brief. A Bug
Agent never writes the Feature Spec or continues as the Feature Producer.

### Worktree/Loop policy

As the first action in W1, obtain a direct Human decision for
`default_worktree: true|false`. Repository configuration may inform the question
but cannot answer it on the Human's behalf.

- When `default_worktree: true`, use the accepted worktree route for Feature
  work and pass its resolved root to every downstream node. Do not exclude
  `speckit-loop-*` solely because the checkout is a worktree. Loop may remain a
  candidate only when its contract supports `isolation: none`; if selected,
  record `loop_isolation: none` and prohibit Loop-created iteration worktrees.
- When `default_worktree: false`, Loop also remains only a candidate. Its
  accepted `loop_isolation` may be `none` or `worktree`.
- In either case, set `loop_eligible: true` only when the Loop Skills are
  canonical, the implementation route is contract-compatible, shared state and
  budget are explicit, and an independent checker runtime/session plus Human
  guard are available.
- A Feature chooses exactly one implementation route before source mutation:
  Core Implement or Loop. Never run both routes for the same change or let them
  write the same checkout concurrently. `default_worktree` selects the checkout
  context; `loop_isolation` selects whether Loop creates additional iteration
  worktrees.

### Multica Issue status vocabulary

Inventory exact status keys and categories from the selected `multica-triage`
contract and accepted workspace mapping. Do not copy legacy names or infer
categories. Keep Multica Issue statuses separate from orchestration gate
decisions (`APPROVED`, `APPROVED_NA`, `REJECTED`, `BLOCKED`).

For the current maintained `multica-triage` contract, the expected vocabulary is:

| Meaning | Key | Category |
| --- | --- | --- |
| Needs maintainer evaluation | `needs_triage` | `backlog` |
| Waiting for actionable information | `needs_information` | `blocked` |
| Fully specified, awaiting explicit agent dispatch | `ready_for_agent` | `backlog` |
| Scoped Human implementation or decision | `ready_for_human` | `todo` |
| Explicitly rejected | `wontfix` | `cancelled` |

`ready_for_agent` is not a started run. `ready_for_human` is not the routine PR
review state. If the source Skill or verified mapping disagrees with this
baseline, record `STATUS_CONTRACT_DRIFT` and stop dependent template generation;
do not silently normalize the difference.


## Sequential checkpoints

At the end of every step:

1. persist or present the complete step result;
2. summarize the inputs and revisions, key findings, decisions, generated or
   changed artifacts, unresolved blockers, invalidated downstream work, and the
   proposed next step;
3. ask: **“是否需要修改本步骤？如果不需要，请回复继续。”**
4. stop and wait for the user's answer.

If the user requests a correction, revise the same step and present the summary
and question again. If the user says no modification is needed or says
`继续`, mark the current step `ACCEPTED` and proceed directly to the next
numbered step without asking for or requiring a stage argument. Never interpret
silence as acceptance and never skip a blocked authority, security, release,
data, or acceptance decision.

Do not ask for information available from repository files. The direct Human
worktree decision and other authority decisions still require an explicit
answer.

## Final acceptance

W8 local generation is complete only when:

- every selected Skill has an evidence-backed capability card and disposition;
- exact status keys/categories come from an accepted contract with no unresolved
  drift;
- W1 records the Human worktree decision and an explicit Loop eligibility and
  isolation decision; when default worktree and Loop coexist, Loop uses
  `isolation: none`, and each Feature still selects exactly one implementation
  route;
- Feature and Bug DAGs, execution Agents, Skill bindings, memberships, and
  manifests are separated;
- artifacts are revision-aware and invalidation is explicit;
- producers and verifiers are independent;
- Agent, Squad, Issue, manifest, and control templates are copyable and contain
  no source-project or live-environment facts;
- proposed controls are not represented as installed controls.

Stop after W8. Live Multica provisioning, W9 Feature/Bug trials, and W10
evidence-driven publication are separate operations.
