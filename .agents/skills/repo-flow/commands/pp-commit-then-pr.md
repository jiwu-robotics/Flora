请使用 `$repo-flow` 完成当前 repository 的 commit、PR、合并和本地 `develop` 更新。

先读取并严格遵循 `conventional-commit` 与 `git-workflow`；`repo-flow` 不替代它们。

## 输入

- 使用当前 repository root。
- 当前 worktree 已在非受保护的私有分支时，直接使用该 worktree/branch；不得创建新 worktree 或替换分支。仅当前 branch 为 `main`、`develop`、detached 或不可用时，才先执行 `git fetch origin develop`，再从 `origin/develop` 创建 `feature/<owner>/<work-item>-<slug>`。
- 复用现有 Work Item；无法确定时分配下一个 `MANUAL-NNN`。

## 执行步骤

1. 读取 branch、`develop`、remote、worktree、变更和 untracked files；保留无关用户改动。
2. 复用可用私有 branch，否则按上述规则创建手动 feature branch；不得直接修改 `main` 或 `develop`。
3. stage exact files、检查 staged diff、运行适用验证，并按 `conventional-commit` 创建 commit。
4. push 后读取远端 branch head，创建到 `develop` 的 PR；checks 通过且取得 Human/provider 授权后合并并读取 merge commit。
5. 仅在 PR 成功合并且 merge commit readback 成功后，执行 `git fetch origin develop`；本地 `develop` 已存在则执行 `git switch develop && git merge --ff-only origin/develop`，否则执行 `git switch --track -c develop origin/develop`；确认本地 HEAD 等于 `origin/develop`。未提交改动阻止操作时停止，不 stash、覆盖或丢弃用户改动。
6. 在确认本地 HEAD 等于 `origin/develop` 后，执行 `git fetch --prune origin`；仅使用 `git branch -d` 删除已合并至 `origin/develop` 的所有本地 branch（排除 `main`、`develop` 与其他 worktree 正在使用的 branch），并 read back 确认无可删除 ref。不得删除 remote 或未合并 branch；任何候选 branch 删除受阻时停止并报告。

## 停止条件

Work Item、branch、policy、required checks、授权或远端 readback 不明确，或 hook/checks 失败、PR 不可合并时停止。

## 安全边界

- 不使用 `--no-verify`、`--amend`、force push、reset、shared-branch rebase 或自动冲突规避。
- 不提交无关 staged/untracked 文件，不直接 commit、push 或 merge `main`、`develop`，不创建测试 Issue、Run 或业务资源。

## 输出

报告 Work Item、实际使用或创建的 branch、commit、PR/checks/merge readback、最终本地 `develop` HEAD、已清理或阻塞的 merged local branches，以及保留的用户改动。