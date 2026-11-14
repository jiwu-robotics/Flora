## Containerized development

- All development work, including code generation, builds, formatting, linting, testing, and debugging, MUST occur in the repository's approved Docker environment. Host-based development tools and dependency installation are prohibited. Coding-agent-specific Skills, commands, plugins, and their supporting files are exempt.
- Install a dependency needed during development first in the existing approved development container. After development completes, update the relevant `Dockerfile` so the image reproducibly contains that dependency; a container-only installation is not a final state.
- Unless a stricter repository or organization policy applies, use these compatible domestic mirror references: Ubuntu APT `https://mirrors.tuna.tsinghua.edu.cn/ubuntu/`; Python Simple API for `pip` and `uv` `https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple`; and DaoCloud's supported Docker Hub base-image proxy `m.daocloud.io/docker.io/library/<image>:<tag>` (for example, `m.daocloud.io/docker.io/library/ubuntu:24.04`). Preserve each Ubuntu release codename, retain the approved security-update source, and use DaoCloud only for images listed as supported. Installing APT or Python packages from a domestic mirror MUST NOT configure or require an HTTP(S) proxy; access the mirror directly. Preserve security, provenance, image digest pinning, and any stricter source policy.

- Dockerfiles MUST NOT set proxy variables with `ENV`. When a build requires a proxy, pass transient values at build time with `--build-arg HTTP_PROXY=...`, `--build-arg HTTPS_PROXY=...`, and, when needed, `--build-arg NO_PROXY=...`; obtain available values from the build machine's `~/.zshrc.local`. Do not persist proxy values in the image configuration.

## Coding agent integration

- Coding-agent-specific Skills, commands, plugins, and their supporting files are exempt from repository formatting, linting, type-checking, testing, and validation requirements.
- Coding-agent-specific Skills, commands, plugins, their supporting files, and documentation MUST use English. Coding-agent conversations with users MUST use Chinese. Code, API/schema identifiers, CLI parameters, and machine-executable examples remain in English.

- Code comments MUST follow Google style. Code MUST include those comments for public interfaces and non-obvious behavior, invariants, and side effects; do not add redundant line-by-line restatements.
