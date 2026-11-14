请在当前项目根目录通过 `jiwu-robotics/multica-speckit` 的 [`install.sh`](http://install.sh) 安装全部 Agent Skills 和受支持的原生项目 commands，使用 project scope 和 `--copy`。

安装输入可指定 `branch=<branch>`；未指定时必须安装 `main`。`branch` 只接受可验证的远程 branch，不接受 tag、commit SHA 或任意 repository source。

先读取 `git remote get-url origin`：Human 指定 transport 时严格遵从；否则 SSH origin 用 SSH，其他情况用 HTTPS。先验证所选 transport 上存在目标 branch。HTTPS 使用 `https://github.com/jiwu-robotics/multica-speckit/tree/<branch>` 作为 `install.sh --repository` source；SSH 先以 `git clone --branch <branch> --single-branch` 建立临时 checkout，再将该 checkout 作为 `--repository` source。两种方式均将所选 transport 传给 `--github-transport`；临时 checkout 在安装完成或失败后删除。连接、branch 验证或安装失败即报告原错误并停止；不得自动切换 transport，也不得索要、输出或保存凭据。

完成后确认 `.agents/skills`、`.claude/skills`、所选 agent 的 command 目录和 `skills-lock.json`，重新加载所用 agent，并从 Skill catalog 或原生 command catalog 读取目标入口。
