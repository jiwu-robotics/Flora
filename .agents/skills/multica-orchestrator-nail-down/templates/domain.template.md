# Project domain guidance for Multica agents

This file tells Multica-backed engineering Skills where the target repository
keeps vocabulary, architecture, specifications, decisions, and rejection
memory. It is configuration, not the domain model itself. Replace placeholders
with existing project sources; do not create a parallel documentation system.

## Target repository

- Repository: `<canonical-repository-url>`
- Default revision or branch: `<default-branch>`
- Project name: `<project-name>`
- Project root: `<repository-relative-project-root>`

The Multica Issue stores live work state and discussion. The target repository
stores durable domain knowledge, ADRs, specifications, shared configuration,
and `.multica/out-of-scope/` records. Live server, workspace, Project, runtime,
Agent, Squad, member, resource, or label identifiers remain operator-local.

## Before exploring or implementing

Record actual sources and read the relevant subset in this order:

1. `<project-governance-path>` for non-negotiable rules.
2. `<architecture-or-context-path>` for boundaries and ownership.
3. `<roadmap-or-product-scope-path>` for outcomes and dependencies.
4. `<feature-specification-path-or-pattern>` for behavior contracts.
5. `<adr-directory-or-pattern>` for governing decisions.
6. `<domain-reference-directory>` for delivered or external interface evidence.

If an optional context, glossary, or ADR source does not exist, proceed without
fabricating it and without scaffolding empty files. Point to an existing
constitution, architecture memory, specification lifecycle, or ADR contract
instead of introducing another system.

## Vocabulary

Record only terms whose ambiguity can change triage or implementation:

- **`<term>`:** `<project-specific-meaning-and-boundary>`

Use established names and surface conflicts as decisions rather than silently
overriding project language.

## Evidence boundaries

State which facts are repository contracts and which require customer,
deployment, controller, or external-system evidence. Mark unverified external
facts unresolved rather than promoting examples or historical observations.

## Rejection knowledge base

`.multica/out-of-scope/` stores concept-level records only for explicitly
rejected enhancements. It is created lazily on the first eligible decision.
Bugs, implemented requests, duplicates, and temporary resource constraints do
not create rejection records. Each record retains source Issue or PR URLs.
