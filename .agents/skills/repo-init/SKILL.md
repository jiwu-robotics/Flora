---
name: repo-init
description: 'Initialize a repository with a conservative, reproducible Python and/or C++ quality baseline: formatting, linting, type checking, tests, pre-commit hygiene, static analysis, and Conventional Commit validation. Use when a user asks to add or standardize foundational development configuration; it intentionally excludes CMakeLists.txt and CMake formatting.'
compatibility: Requires a writable Git working tree and the target project’s approved Python and C++ toolchains. Python support requires Python 3.10+; C++ static analysis requires clang-format, clang-tidy, and cppcheck when C++ is selected.
metadata:
  author: multica-speckit
  source: project-maintained
---

# Repository Initializer

## Goal

Add a small, coherent, language-aware quality baseline and a container-development
policy to one explicit target repository. The baseline covers Python and C++ source
formatting, static analysis, Python type checking and tests, repository hygiene hooks,
and a Conventional Commit message contract.

This Skill owns only developer-quality configuration and the target repository's
`AGENTS.md` container-development instructions. It does **not** create containers,
modify `Dockerfile`s, modify CMake configuration, configure CMake formatting, choose a
build system, create CI workflows, change application code, install tools on the host,
or replace a repository’s existing engineering policy.

## Invocation

```text
/repo-init mode=inspect target=<repository> languages=<python|cpp|python,cpp>
/repo-init mode=apply target=<repository> languages=<python|cpp|python,cpp>
```

`inspect` is read-only and is the default. `apply` may write only the approved
baseline files from this package's templates and the target `AGENTS.md` policy after
the inspection records their current state. The target must be an explicit repository
path; never select a directory by guessing.

## Packaged templates

This package distributes reviewed, reusable templates. Treat them as the only starting
point for a newly created baseline file; do not reconstruct equivalent configuration
from memory. Templates are inputs, not blind copies: render discovered Python roots and
versions, preserve compatible target policy, and stop on a conflict.

| Target artifact | Template | Application rule |
| --- | --- | --- |
| managed `AGENTS.md` sections | `templates/AGENTS.md` | Add or replace only the two managed sections. |
| `ruff.toml` | `templates/python/ruff.toml` | Render the discovered Python target version. |
| `pyproject.toml` quality sections | `templates/python/pyproject-quality.toml` | Merge the named TOML tables; never replace a project manifest. |
| fallback quality dependencies | `templates/python/quality-requirements.txt` | Use only when the target has no dependency convention. |
| `.clang-format` | `templates/cpp/.clang-format` | Copy only when no compatible formatter exists. |
| `.clang-tidy` | `templates/cpp/.clang-tidy` | Copy only when no compatible analyzer policy exists. |
| `cppcheck/suppressions.txt` | `templates/cpp/cppcheck-suppressions.txt` | Create only when absent. |
| `tools/pre_commit_hygiene.py` | `templates/pre-commit/repository_hygiene.py` | Copy only when the target lacks an equivalent compatible local check. |
| `.pre-commit-config.yaml` | `templates/pre-commit/python.yaml`<br>`templates/pre-commit/cpp.yaml`<br>`templates/pre-commit/python-cpp.yaml` | Choose the selected language variant; merge hooks into an existing configuration. |

The pre-commit templates are complete candidate files for a repository without a hook
configuration. For an existing configuration, retain its repository and version policy,
then merge only missing local hooks. The hygiene helper validates final newlines,
trailing whitespace, YAML/JSON/TOML syntax, and private-key markers. Its Python imports
require the conditional `PyYAML==6.0.3` and `tomli==2.4.1` fallback dependencies on
Python versions without `tomllib`.

## Safety and idempotency

1. Read the target’s active agent guidance, contributor documentation, package
   manifests, CI configuration, and local quality configuration before deciding
   anything. Its container, task runner, operating-system, proxy, and
   credential rules take precedence.
2. In a Git repository, read `git status --short` before mutation. Preserve
   every unrelated tracked, staged, and untracked change.
3. Detect existing `pyproject.toml`, `ruff.toml`, `.pre-commit-config.yaml`,
   `.clang-format`, `.clang-tidy`, `cppcheck/suppressions.txt`, test settings,
   and commit hooks. Extend a compatible configuration; do not overwrite a
   working alternative or introduce a second formatter, linter, type checker,
   or commit convention.
4. If an existing configuration conflicts with this baseline, report the exact
   files and rule differences. Stop before replacing it unless the Human
   explicitly authorizes that replacement.
5. Re-running `apply` must be idempotent: reuse identical files and update only
   missing or intentionally changed values. Never duplicate hooks, dependency
   entries, or TOML sections.
6. Do not add `Black`, `isort`, `flake8`, `cpplint`, or CMake configuration when
   Ruff, clang-format, clang-tidy, cppcheck, and the project’s current build
   system already cover the same responsibility.

## Target `AGENTS.md` policy

In `apply` mode, create `AGENTS.md` from `templates/AGENTS.md` when it is absent.
When it exists, preserve every unrelated instruction and add or update only the
idempotent `## Containerized development` and `## Coding agent integration` sections
from that template. The container-development section MUST require:

1. All development work, including code generation, builds, formatting, linting,
   testing, and debugging, occurs in the repository's Docker environment; host-based
   development tools and dependency installation are prohibited. Coding-agent-specific
   Skills, commands, plugins, and their supporting files are exempt from this
   requirement.
2. A dependency needed during development is installed first in the existing approved
   development container. After the development work is complete, update the relevant
   `Dockerfile` so the image reproducibly contains that dependency; do not use a
   container-only installation as the final state.
3. Ubuntu APT and Python package installers, including `uv` and `pip`, prefer
   compatible domestic mirrors. Provide these usable reference values unless a stricter
   repository or organization policy applies:
   - Ubuntu APT: `https://mirrors.tuna.tsinghua.edu.cn/ubuntu/`. Preserve the release
     codename and the approved security-update source.
   - Python Simple API for both `pip` and `uv`:
     `https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple`.
   - Supported Docker Hub base images:
     `m.daocloud.io/docker.io/library/<image>:<tag>`, for example,
     `m.daocloud.io/docker.io/library/ubuntu:24.04`. Use it only when DaoCloud lists
     the upstream image as supported.
   Installing APT or Python packages from a domestic mirror MUST NOT configure or
   require an HTTP(S) proxy; access the mirror directly. Preserve security, provenance,
   image digest pinning, and any stricter repository or organization source policy.
4. Dockerfiles MUST NOT set proxy variables with `ENV`. When a build requires a proxy,
   pass transient values at build time with `--build-arg HTTP_PROXY=...`,
   `--build-arg HTTPS_PROXY=...`, and, when needed, `--build-arg NO_PROXY=...`; obtain
   available values from the build machine's `~/.zshrc.local`. Do not persist proxy
   values in the image configuration.

The coding-agent-integration section MUST require:

1. Coding-agent-specific Skills, commands, plugins, and their supporting files are
   exempt from repository formatting, linting, type-checking, testing, and validation
   requirements.
2. Coding-agent-specific Skills, commands, plugins, their supporting files, and
   documentation MUST use English. Coding-agent conversations with users MUST use
   Chinese. Code, API/schema identifiers, CLI parameters, and machine-executable
   examples remain in English.
3. Code comments MUST follow Google style. Code MUST include those comments for public
   interfaces and non-obvious behavior, invariants, and side effects; do not add
   redundant line-by-line restatements.

If the repository has no approved Docker environment, report that as a blocker rather
than substituting host tooling for work governed by the container-development policy.
This policy governs future development; initialization itself still MUST NOT create
containers or modify `Dockerfile`s.

## Discovery and decisions

Before generating files, determine:

- selected language(s), source roots, test roots, and first-party Python package
  names from existing manifests and source layout;
- supported Python version from `.python-version`, `pyproject.toml`, CI, or the
  runtime image. If no evidence exists, use `py310` and state that default;
- the existing dependency-manager and task-runner convention. Reuse it rather
  than adding a parallel manager;
- whether `compile_commands.json` is generated by the existing C++ build. Never
  create a handwritten compilation database;
- whether a protected container or remote development environment owns the
  toolchain. Run checks there rather than substituting host tools.

If the user chooses neither language, ask which language baseline to apply. If
an existing formatter, linter, type checker, or hook cannot be safely merged,
report the conflict and do not write its replacement.

## Python baseline

When Python is selected, render `templates/python/ruff.toml` with the discovered Python
version and configure **Ruff** as the only formatter, import sorter, and style/error
linter. Prefer a standalone `ruff.toml` so formatting policy stays focused and
discoverable.

```toml
line-length = 120
indent-width = 4
target-version = "py310"
extend-exclude = ["build", "dist", "install", "log"]

[lint]
select = ["E", "F", "I", "B", "UP", "SIM"]

[lint.pydocstyle]
convention = "google"

[format]
quote-style = "double"
indent-style = "space"
line-ending = "lf"
docstring-code-format = true
```

Replace `py310` only with the Python version discovered above. Keep exclusions
narrow: generated or build-artifact directories only. Do not globally exclude
source, tests, or an entire package to silence violations.

Merge the named tables from `templates/python/pyproject-quality.toml`, adjusting roots
to evidence from the target. Never replace an existing project manifest:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.pyright]
include = ["src", "tests"]
typeCheckingMode = "basic"

[tool.commitizen]
name = "cz_customize"
version = "0.0.0"
tag_format = "v$version"
update_changelog_on_bump = false

[tool.commitizen.customize]
example = "feat(api): add health endpoint\n\n- Return the service health state."
schema = "<type>(<scope>)[!]: <description>, followed by at least one detail"
schema_pattern = "^(?:feat|fix|docs|style|refactor|test|build|ci|chore|perf|revert)\\((?:[a-z]|[0-9])+(?:-(?:[a-z]|[0-9])+)*\\)(?:!)?: \\S[^\\r\\n]{0,71}\\n\\n- \\S(?:(?!\\\\n)[^\\r\\n])*(?:\\n- \\S(?:(?!\\\\n)[^\\r\\n])*)*\\n?$"
```

`include` must contain all real first-party Python roots. If a target uses a
flat package layout, replace `src` with that package root. Do not claim that
basic Pyright enforces strict typing.

When no project dependency convention exists, add
`templates/python/quality-requirements.txt` as a dedicated, reproducible quality
dependency file, then install it only through the target’s approved environment:

```text
commitizen==4.18.0
pre-commit==4.6.2
pyright==1.1.411
pytest==9.1.1
ruff==0.16.4
```

Existing lockfiles, approved dependency groups, or pinned tool images are
stronger evidence than this fallback. Add `PyYAML==6.0.3` and `tomli==2.4.1`
only if the chosen pre-commit hook implementation imports them.

## C++ baseline

When C++ is selected, add `templates/cpp/.clang-format` as the only C++ formatting
policy:

```yaml
---
BasedOnStyle: Google
ColumnLimit: 120
...
```

Add `templates/cpp/.clang-tidy` with focused correctness and maintainability checks.
Keep warnings separate from compiler errors; do not globally promote warnings unless the
target already has that policy.

```yaml
---
Checks: >
  -*,
  bugprone-*,
  performance-*,
  modernize-*,
  readability-*
WarningsAsErrors: ''
...
```

Create `cppcheck/suppressions.txt` from
`templates/cpp/cppcheck-suppressions.txt` only when absent. It begins with this policy,
not an empty global suppression:

```text
# Add narrowly scoped, documented cppcheck suppressions here when a verified
# false positive cannot be resolved in source. No project-wide suppressions.
```

Every future suppression must name the cppcheck rule, affected file or narrow
scope, and the verified false-positive reason. Never add a project-wide
suppression merely to make a gate pass.

Run static analysis against the build-generated compilation database when it is
available:

```bash
clang-format --dry-run --Werror <changed-cpp-files>
cppcheck --enable=warning,performance,portability --error-exitcode=1 \
  --suppressions-list=cppcheck/suppressions.txt <cpp-files>
clang-tidy -p <build-directory> <cpp-files>
```

`clang-tidy` is conditional on `<build-directory>/compile_commands.json`. Report
its absence as skipped; do not construct a substitute database or weaken the
other checks.

## Shared pre-commit baseline

Choose the matching complete candidate from `templates/pre-commit/` and create or merge
`.pre-commit-config.yaml` with fast, offline checks only:

- file-ending newline and trailing-whitespace validation;
- YAML, JSON, and TOML syntax validation;
- private-key detection;
- `ruff format --check` and `ruff check` for Python repositories;
- `clang-format --dry-run --Werror` for C++ repositories.

The selected hooks must match installed tool availability and exclude generated
assets only by narrow, documented paths. Do not run Docker, download
dependencies, contact production systems, execute whole-project tests, or run
`clang-tidy`/`cppcheck` from commit hooks. Put expensive C++ analysis in the
project’s existing lint task or CI after the normal build has produced a
compilation database.

Use the target’s existing pre-commit dependency source and version policy. If
it has none, use pinned `pre-commit` plus local `language: system` hooks so the
approved project environment owns Ruff and clang-format. Do not mix system
hooks with remote hook repositories that provide the same checks.

## Commit-message baseline

Use the Commitizen configuration above to require:

```text
<type>(<kebab-case scope>)[!]: <description>

- <detail>
```

Accepted types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `build`,
`ci`, `chore`, `perf`, and `revert`. Require a lowercase kebab-case scope, a
subject of at most 72 characters, and one or more physical `- <detail>` body
lines. A breaking change uses `!` and needs a final
`BREAKING CHANGE: <description>` footer.

Only install a `commit-msg` hook through the repository’s current hook manager
or documented task. Never overwrite custom hooks, bypass validation with
`--no-verify`, or impose a repository-specific work-item footer.

## Verification

After `apply`, run only the checks supported by the target’s approved
environment and report exact commands and outcomes:

```bash
ruff format --check <python-roots>
ruff check <python-roots>
pyright
python -m pytest
pre-commit run --all-files
```

For C++, run clang-format and cppcheck only when C++ files exist; run
clang-tidy only after a normal build has generated a compilation database. A
missing compiler database is a reported skip, not a pass. Re-read the changed
configuration files and verify that no out-of-scope CMake files, build-system
files, containers, CI workflows, application sources, or user changes were
modified.

## Report

Report the selected languages; discovered source/test roots and Python version;
created, merged, reused, skipped, and conflicted files; the exact commands and
results; and every intentionally deferred check. State any unresolved conflict
or unavailable toolchain as a blocker rather than calling initialization
complete.
