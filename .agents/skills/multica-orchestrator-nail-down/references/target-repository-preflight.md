# Target repository binding preflight

Before any write, read the real repository root/origin, project subpath, existing `.multica/agents/` files, and current user changes. Preserve unrelated work.

Nail Down must resolve and verify:

- credential-free GitHub SSH/HTTPS origin;
- unique repository registry, Project, and Project GitHub resource identities;
- `main`/`develop`, canonical Multica Issue-key source, dual branch-authority policy, and repository command profile;
- one Human-selected collaboration Runtime alias;
- current live Runtime capability revision matching the Server fleet and `RuntimeTargetPolicy.v4`;
- native Squad routing and immutable Agent/Squad generation;
- portable constitution/architecture/roadmap/ADR/Feature/Fix mappings;
- exactly four portable repository binding files with no live IDs, credentials, absolute paths, or revisions;
- current Dispatch contract digest.

Do not require a clean worktree or bind repository HEAD. Do not inspect/create/update a Project `local_directory` resource. Migrate performs machine-local preflight and activation after a release candidate exists. Dispatch performs Work Item branch/worktree/scope/lease/queue/provider checks after ACTIVE release.

Any unknown identity, stale bundle/capability, missing configuration, or contract drift blocks before publishing a Project bundle or release candidate.
