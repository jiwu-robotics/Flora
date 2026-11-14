请使用 `$repo-flow` 创建或复用人工分支，并提交本次更新。

先读取并严格遵循 `conventional-commit` 与 `git-workflow`；`repo-flow` 不替代它们。

## 输入

- 使用当前 repository root 和当前 worktree；不得创建、删除或替换 worktree。
- 当前 worktree 已在非受保护的私有 `feature/*` 或 `fix/*` branch 时直接复用该 branch；否则在当前 worktree 先执行 `git fetch origin develop`，再从 `origin/develop` 创建 `feature/<owner>/<work-item>-<slug>`。
- 复用现有 Work Item；无法确定时分配下一个 `MANUAL-NNN`。

## 执行步骤

1. 读取 branch、`develop`、remote、worktree、变更、staged diff 和 untracked files；保留无关用户改动。
2. 复用可用私有 branch，否则按上述规则在当前 worktree 创建并切换手动 feature branch；不得直接修改 `main` 或 `develop`。
3. stage 仅属于本次 Work Item 的 exact files，检查 staged diff，运行适用验证。
4. 按 `conventional-commit` 创建 commit，不绕过 hook；读取并确认 commit SHA、message 和 Work-Item footer。

## 停止条件

Work Item、policy 或 branch name 不明确，无法安全复用或创建 branch，存在无法归属的 staged 变更，或 hook/验证失败时停止。

## 安全边界

- 不创建、删除或替换 worktree；除必要的 branch 创建或切换外，不进行其他 branch mutation；不 push、创建 PR 或 merge。
- 不使用 `--no-verify`、`--amend`、force push、reset、rebase 或自动冲突规避。
- 不提交无关 staged/untracked 文件，不创建测试 Issue、Run 或业务资源。

## 输出

报告 Work Item、实际复用或创建的 branch、commit SHA/message、验证结果和保留的用户改动。
