# 三人数学建模团队 Git / GitHub 协作教程

适用仓库：[mathematical-modeling-nju-2026/mathematical-modeling](https://github.com/mathematical-modeling-nju-2026/mathematical-modeling)

这份教程面向 Git 初学者，包含 Windows、Linux 配置，以及上传 PDF、图片、代码的完整流程。

**说明：编写时未能读取仓库页面，所以没有确认仓库是否公开、默认分支名和现有文件夹。下文以主分支 `main` 为例；如果实际叫 `master` 或其他名字，就替换命令中的 `main`。`docs/`、`figs/` 都是建议目录，不代表仓库已经有这些目录。**

## 先理解这几个词

| 名称 | 在你们项目中的意思 |
|---|---|
| Git | 安装在电脑上的版本管理工具，记录文件的修改历史 |
| GitHub | 存放团队远程仓库的网站 |
| 本地仓库 | 你电脑里的 `mathematical-modeling` 文件夹及其 Git 记录 |
| 远程仓库 | GitHub 上大家共同使用的仓库 |
| commit（提交） | 把选中的修改记成一个本地版本，附带说明 |
| branch（分支） | 一条工作线；可以先在自己的分支修改，再合并进主分支 |
| main | 本教程假定的主分支名，用来放团队已确认的成果 |
| origin | 克隆后 Git 给远程仓库起的默认简称 |
| Pull Request（PR） | GitHub 上请求把一个分支的修改合并到另一个分支 |

**保存文件不等于 commit；commit 不等于 push；push 到个人分支不等于合并进 main。**

你们采用的主流程：从最新 main 创建任务分支，在分支上修改并提交，推送到 GitHub，发 PR，由同学检查后合并。

## 1. 环境配置(if you can not do it by yourself, reach out to AI)

### 1.1 安装 Git

**Windows：**从 [Git 官方 Windows 安装页](https://git-scm.com/install/windows) 安装。安装后打开 **Git Bash**。下文 Windows 命令都在 Git Bash 执行，避免混用 CMD、PowerShell 的路径语法。

**Ubuntu / Debian：**在终端执行：

```bash
sudo apt update
sudo apt install git openssh-client
```

其他 Linux 发行版用对应的软件包管理器。

**两种系统都检查：**

```bash
git --version
```

显示 `git version ...` 即说明可以找到 Git。

### 1.2 设置提交姓名和邮箱

可以在任意目录执行。每台电脑的当前系统用户通常配置一次：

```bash
git config --global user.name "你的名字"
git config --global user.email "你的GitHub邮箱"
```

把引号内文字替换成自己的信息。姓名是提交记录显示的作者名，不要求与 GitHub 用户名相同。邮箱建议使用 GitHub 账号已验证的邮箱；也可以复制 GitHub 邮箱设置中提供的 noreply 邮箱。

```bash
git config --global --get user.name
git config --global --get user.email
```

这两项是在说明“提交的作者是谁”，**不是登录 GitHub，也不会获得仓库写入权限**。

### 1.4 配置 SSH：让 GitHub 识别这台电脑

本教程统一使用 SSH。你们每个人、每台电脑分别配置自己的密钥。

先查看是否已有默认公钥：

```bash
ls ~/.ssh/id_ed25519.pub
```

如果存在，而且是你自己的 GitHub 密钥，可以复用，跳到“添加公钥”。如果没有该文件，再生成：

```bash
ssh-keygen -t ed25519 -C "你的GitHub邮箱"
```

提示保存位置时，首次配置可按回车使用默认位置。提示 `Overwrite` 时不要覆盖已有密钥；先确认原密钥的用途。随后可设置密钥口令，输入时终端不显示字符是正常的。[GitHub 官方密钥生成说明](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent)

生成后有两个文件：

| 文件 | 用途 |
|---|---|
| `~/.ssh/id_ed25519` | 私钥，留在自己的电脑，不上传、不发给同学 |
| `~/.ssh/id_ed25519.pub` | 公钥，添加到自己的 GitHub 账号 |

**添加公钥：**

```bash
cat ~/.ssh/id_ed25519.pub
```

复制输出的完整一行。在 GitHub 个人头像菜单中进入 **Settings → SSH and GPG keys → New SSH key**：Title 填设备名，例如 `my-linux-laptop`；Key type 选择 **Authentication Key**；Key 粘贴公钥并保存。这里是个人账号设置，不是仓库设置。[GitHub 官方添加公钥说明](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account)

**测试连接：**

```bash
ssh -T git@github.com
```

首次连接若询问是否信任主机，对照 [GitHub 官方 SSH 指纹](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints) 核对后输入 `yes`。成功提示大致如下：

```text
Hi USERNAME! You've successfully authenticated, but GitHub does not provide shell access.
```

这代表身份认证成功，后半句不是错误。检查 `USERNAME` 是否为你自己的账号。命令中的 `git@github.com` 固定这样写，**不要把 `git` 改为你的用户名**。身份认证成功后，仍需有目标仓库的权限。[GitHub 官方连接测试说明](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/testing-your-ssh-connection)

如果设置了口令，希望在当前 Git Bash / Linux 终端会话中缓存它，可执行：

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

重新打开终端后可能需要重新加载。Windows 按本教程使用 Git Bash 自带的 SSH，避免混用不同 SSH 客户端和 agent。

## 2. 如何下载、更新团队仓库

### 2.1 首次：clone 下载

先选一个存放项目的父目录。以下任选与你的系统相符的一组。

**Linux 示例：**

```bash
mkdir -p ~/projects
cd ~/projects
```

**Windows Git Bash 示例（假设有 D 盘）：**

```bash
mkdir -p /d/projects
cd /d/projects
```

`mkdir -p` 创建文件夹，`cd` 进入文件夹。Windows Git Bash 的 `/d/projects` 对应 Windows 的 `D:\projects`；没有 D 盘可用 `~/projects`。

在这个父目录中执行：

```bash
git clone git@github.com:mathematical-modeling-nju-2026/mathematical-modeling.git
cd mathematical-modeling
```

Git 会创建项目文件夹、下载仓库及历史、配置名为 origin 的远程地址，并检出默认分支。**无需再执行 `git init`，也无需重复添加 origin。**

检查：

```bash
git status
git branch --show-current
git remote -v
```

| 命令 | 你要看什么 |
|---|---|
| `git status` | 当前分支、是否有未提交的变更 |
| `git branch --show-current` | 当前分支名；正常首次克隆后通常是默认分支 |
| `git remote -v` | origin 是否指向你们团队仓库 |

也可以看 GitHub 仓库文件列表上方的分支选择器。后面例子假设主分支是 `main`。

**不要用 Download ZIP 代替 clone 来开始持续协作。** ZIP 是文件快照，没有可直接用于后续 pull / push 的 Git 仓库记录。

### 2.2 之后：进入已有目录，更新 main

例如 Linux：

```bash
cd ~/projects/mathematical-modeling
```

Windows Git Bash：

```bash
cd /d/projects/mathematical-modeling
```

后续 Git 命令都在这个仓库目录执行。每次准备开始一个新任务：

```bash
git status
git switch main
git pull --ff-only origin main
```

**前提：先处理好 `git status` 显示的未提交变更，再切换分支。**有变更时看下一小节，不要直接把整段当作无条件脚本运行。

`git pull` 会下载远程更新并整合进当前分支；这里先切回 main，才能更新本地 main。`--ff-only` 要求能直接沿远程历史向前更新；如果本地与远程各有不同的新提交，则停止，让你先处理分歧。[Git 官方 pull 文档](https://git-scm.com/docs/git-pull)

提示 `Already up to date.` 表示本次更新没有更多内容。队友只把文件推到自己的分支、尚未合并 PR 时，你更新 main 看不到那些文件是正常的。

### 2.3 已经改了文件，才想起来要更新

**情况 A：改动已经可以保存成一个版本。**

在当前任务分支先 `git add`、`git commit` 保存。若你误在 main 上开始修改，还没有提交，可以先创建任务分支，未提交的修改会跟过去：

```bash
git switch -c zhang/data-notes
```

然后提交到这个任务分支。`zhang/data-notes` 是示例分支名，用你自己的名字和任务替换。

**情况 B：改动还没做完，暂时不想提交。**

先留在当前分支，暂存这份未完成工作：

```bash
git stash push -u -m "更新前暂存未完成工作"
```

`-u` 会一起暂存尚未跟踪的新文件；被 `.gitignore` 忽略的文件不包含在内。记住当前分支名，随后切到 main 更新，再切回原任务分支恢复：

```bash
git switch main
git pull --ff-only origin main
git switch zhang/data-notes
git stash pop
```

把最后的分支名替换为刚才暂存所在的分支；如果原本就在 main，就无需切到示例分支。这只更新了本地 main，没有自动把更新合入任务分支。任务分支需要最新 main 时，按第 4 节操作。`stash pop` 也可能冲突，冲突时先处理再继续。

## 3. 如何上传自己的 PDF、图片等

下面完整演示：张同学上传一篇参考论文和一张结果图片。

### 3.1 从最新 main 创建本次任务分支(we can use three branches, more branches may not be necessary)

确认工作区干净后：

```bash
git switch main
git pull --ff-only origin main
git switch -c zhang/add-paper
```

`git switch -c` 是“新建并切换”。分支名可写成 `li/data-cleaning`、`wang/model-code` 等。**每个新任务新建一个分支；同一个任务下次继续时，用 `git switch 分支名`，不带 `-c`。**

分支不是磁盘上的另一个文件夹。切换分支时，Git 会让同一个项目文件夹显示对应分支的内容。

### 3.2 把文件放入项目目录

如需新建目录：

```bash
mkdir -p docs figs
```

用文件管理器把 PDF、图片复制到对应位置，例如：

| 仓库内路径 | 内容 |
|---|---|
| `docs/reference-paper.pdf` | 参考论文 |
| `figs/result.png` | 结果图片 |

**必须复制到本地仓库内部。**只放在“下载”文件夹里，Git 不会自动看到。

支持中文文件名；路径有空格时用英文双引号包住。团队可约定统一命名，避免跨系统使用 Windows 不允许的文件名字符，以及仅大小写不同的文件名。

### 3.3 查看变更，选择本次要提交的内容

```bash
git status
git add "docs/reference-paper.pdf" "figs/result.png"
git status
```

第一次 status 用来检查 Git 发现了什么。`git add` 把指定文件的当前内容放入“暂存区”，也就是这次提交的待选清单。第二次 status 应显示这些文件位于 `Changes to be committed`。

也可以一次选择当前目录及子目录的全部变更：

```bash
git add .
```

但先检查 `git status`，确认其中没有不该上传的东西。`git add .` 在仓库根目录执行时，通常会暂存整个仓库的新增、修改、删除；在子目录执行时范围只覆盖该目录及其子目录。

**add 后又改了文件，需要再次 add，后改的内容才会包含在下一次提交中。**

### 3.4 在本地生成提交

```bash
git commit -m "添加参考论文和结果图片"
```

`-m` 后面是提交说明，写清做了什么。此时 Git 在本地记录了一个版本，GitHub 上还没有收到它。

代码、Markdown 等文本文件，可用 `git diff` 查看未暂存的文本变化，或用 `git diff --staged` 查看已暂存的变化；PDF、图片需要打开文件本身检查。

### 3.5 推送到 GitHub 的任务分支

本地这个分支第一次推送：

```bash
git push -u origin zhang/add-paper
```

这会把分支推送到团队仓库，并建立本地分支与远程分支的跟踪关系。同一任务分支之后继续修改：

```bash
git add "docs/reference-paper.pdf"
git commit -m "补充参考论文"
git push
```

第一次推送成功后，在 GitHub 的分支选择器中选择 `zhang/add-paper` 就能看到文件。**默认显示 main 时暂时看不到，是因为还没合并。**

### 3.6 在 GitHub 发起 PR，合并到 main

1. 打开团队仓库，点击出现的 **Compare & pull request**；没有这个提示时，进入 **Pull requests → New pull request**。
2. 确认 **base = main**，**compare = zhang/add-paper**。意思是把任务分支合入主分支。
3. 填标题和说明，例如“添加参考论文和结果图片”，说明文件用途。
4. 创建 PR，请另一位同学查看文件是否正确、是否覆盖了别人的成果。
5. 有合并权限的人，在检查和仓库规则通过后点击可用的合并按钮并确认。

PR 创建后，在同一个分支继续 commit 和 push，新提交会自动出现在这个尚未合并的 PR 中，不用每改一次就新开 PR。[GitHub 官方 PR 说明](https://docs.github.com/en/pull-requests/how-tos/create-pull-requests/creating-a-pull-request)

### 3.7 合并后，每个人更新本地 main

工作区干净时：

```bash
git switch main
git pull --ff-only origin main
```

之后的新任务从更新后的 main 创建新分支，不要接着用已经完成并合并的旧任务分支。旧分支暂时留着也没有关系。

### 3.8 修改、删除、重命名文件也是相同流程

Git 能记录这些操作，不仅能新增文件。

| 操作 | 本地怎么做 | 如何暂存 |
|---|---|---|
| 修改 PDF 或图片 | 在原路径保存新内容 | `git add "文件路径"` |
| 删除文件 | 在文件管理器删除 | 在仓库根目录执行 `git add -A` |
| 重命名文件 | 在文件管理器重命名 | 在仓库根目录执行 `git add -A` |

`git add -A` 会暂存整个仓库的新增、修改、删除，之后检查 status，再 commit、push、PR。推送分支上的删除操作只有合并到 main 后，才会进入主分支。

## 4. 三人协作：更新任务分支与处理冲突

### 4.1 正在做任务时，队友已经往 main 合并了新内容

先在你的任务分支提交好自己的改动、确认工作区干净，再执行：

```bash
git fetch origin
git merge --no-edit origin/main
```

`fetch` 获取远程的新记录，不直接修改当前工作文件；`origin/main` 是刚获取的远程 main 的本地记录。`merge` 把它整合进当前任务分支。

没有冲突时继续工作或 `git push` 即可。有冲突时，Git 会暂停合并；按下一节处理。[Git 官方 merge 文档](https://git-scm.com/docs/git-merge)

### 4.2 冲突是什么

你和同学在两个分支中改了同一文件的相互冲突部分，Git 无法自动决定保留哪份内容。例如你把报告标题改成 A，同学把同一处改成 B。

**文本文件冲突：**

1. `git status` 查看冲突文件。
2. 打开文件，查找 `<<<<<<<`、`=======`、`>>>>>>>` 标记。
3. 与同学确认最终内容，编辑成完整正确的版本，并删除这些标记。
4. 保存后执行：

```bash
git add "冲突文件路径"
git commit -m "合并主分支并解决冲突"
git push
```

**PDF、图片、Word 冲突：**

这些文件通常不能像代码一样自动按行合并。先在仓库外备份你手上的版本，与同学确认要保留哪份或由谁生成最终版；把最终文件放回冲突路径，然后 `git add`、`git commit`、`git push`。

如果决定暂时不做这次合并，在合并尚未完成时执行：

```bash
git merge --abort
```

本节假定是在工作区干净时开始 merge，这样更容易回到合并前状态。不要用强制 push 解决冲突。

## 5. 补充：两种更简单的上传方式

### 5.1 GitHub 网页直接上传

偶尔上传少量资料时，可以不安装 Git：

1. 登录自己的账号，进入团队仓库。
2. 在分支选择器中，从 main 创建一个任务分支，例如 `li/upload-notes`。
3. 在该分支进入目标文件夹，点击 **Add file → Upload files**。
4. 拖入文件，写提交说明，提交到这个任务分支。
5. 按第 3.6 节发 PR，合并进 main。

网页上传会在 GitHub 上直接产生提交，你电脑上的文件夹不会自动更新；仍需 pull。网页入口和可选项以实际权限、仓库规则为准。[GitHub 官方上传说明](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)

### 5.2 直接推送 main：仅在团队明确采用且仓库允许时使用

这是另一种流程，和前面的“任务分支 + PR”二选一，不要混着当成同一次操作。

工作区干净，且开始修改之前：

```bash
git switch main
git pull --ff-only origin main
```

复制或修改文件后：

```bash
git status
git add "docs/reference-paper.pdf"
git commit -m "添加参考论文"
git push origin main
```

若你修改期间同学先推送了 main，你的 push 可能被拒绝。自己的修改已经 commit、工作区干净时，可获取并合并：

```bash
git fetch origin
git merge --no-edit origin/main
```

有冲突则先按第 4 节处理；合并完成后：

```bash
git push origin main
```

若报错是分支保护、必须走 PR，就按仓库规则从现有提交创建任务分支，推送并发 PR，不要尝试绕过规则。

## 6. 文件约定与注意事项

### 6.1 可采用的目录分工

尊重仓库已有结构；下面只是没有约定时的一套示例。

| 路径 | 内容 |
|---|---|
| `README.md` | 项目介绍、分工、运行说明 |
| `docs/` | 参考论文、笔记、说明文档 |
| `figs/` | 报告用图、实验结果图 |
| `src/` | 程序代码 |
| `data/` | 适合放入 Git 的小型数据文件 |
| `report/` | LaTeX、Markdown 等报告源文件 |

Git 不记录空目录；目录里有被跟踪的文件后才会随提交出现。

### 6.2 文件大小限制

GitHub 网页上传单文件不能超过 **25 MiB**；普通 Git 推送会阻止大于 **100 MiB** 的文件。更大文件需要 Git LFS 等方案。频繁修改的大 PDF、图片也会增大仓库历史。[GitHub 官方大文件说明](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)

普通小 PDF、PNG 可以直接提交。大型数据集、模型权重、压缩包可放团队约定的外部存储，在 README 记录下载方式。需要 Git LFS 时，三个人应一起约定并配置。

如果超大文件已经 commit，单纯再做一次“删除文件”的提交通常不能解决推送被拒的问题，因为早先提交中仍有它；应根据文件在哪些未推送提交中出现来处理，别反复 push。

### 6.3 用 .gitignore 排除不需要协作的文件

如果团队做 Python / LaTeX，可以在仓库根目录的 `.gitignore` 中按需补充以下内容；已有文件时先合并规则，不要覆盖：

```gitignore
# Python 缓存与本地虚拟环境
__pycache__/
*.pyc
.venv/
venv/

# 本地环境变量
.env

# 常见 LaTeX 编译中间文件
*.aux
*.log
*.out
*.toc
*.synctex.gz

# 操作系统生成文件
.DS_Store
Thumbs.db
```

`.gitignore` 本身也需要提交，才能共享规则。不要忽略全部 `*.pdf` 或 `*.png`，否则会挡住你们要上传的资料。规则对已经被 Git 跟踪的文件不会自动取消跟踪。

### 6.4 三个人先约定五件事

1. 每人每项任务使用独立分支，开始前更新 main。
2. 一次 commit 尽量围绕一件事，写清提交说明。
3. PDF、Word、图片指定当前编辑者，避免同时修改同一个文件。
4. 报告能保存 LaTeX / Markdown 源文件时一起保存，便于比较和协作。
5. PR 合并前由另一人看一遍；push 完确认分支，PR 合并后再通知同学 pull main。

## 7. 常见报错速查

| 提示 / 现象 | 常见原因 | 先做什么 |
|---|---|---|
| `git: command not found` | Git 未安装或终端找不到 | 检查安装，重新打开终端 |
| `not a git repository` | 没进入 clone 得到的仓库目录，或用了 ZIP | 用 `pwd` 看位置，再进入正确目录 |
| `Permission denied (publickey)` | SSH 密钥没被正确识别 | 执行 `ssh -T git@github.com`，核对公钥和账号 |
| `Repository not found` | 地址错或账号无访问权限 | 核对地址、邀请、当前认证账号，不能单凭报错断定仓库不存在 |
| `Author identity unknown` | 未配置提交姓名 / 邮箱 | 配置 `user.name`、`user.email` |
| `nothing to commit, working tree clean` | 没有可提交的变更 | 检查文件是否放对目录、是否已保存；不代表远程一定同步 |
| `no upstream branch` | 新分支尚未设置跟踪关系 | 用 `git push -u origin 你的分支名` |
| `non-fast-forward` / `fetch first` | 远程目标分支有本地尚未包含的提交 | 获取并合并对应远程分支，处理冲突后再推送；不要直接强推 |
| `Not possible to fast-forward` | `--ff-only` 发现历史分歧 | 检查当前分支及本地提交，按对应协作流程 merge，不要删除自己的工作 |
| `Your local changes ... would be overwritten` | 切换 / 更新会影响未提交修改 | 先 commit 或 stash |
| 新文件没出现在 status 中 | 可能在仓库外或被忽略 | 核对位置；用 `git check-ignore -v "文件路径"` 查看忽略规则 |
| push 成功但 main 没文件 | 可能只推送了任务分支 | 在 GitHub 切到该分支，检查 PR 是否合并 |

仓库未找到的原因也可参照 [GitHub 克隆错误排查](https://docs.github.com/en/repositories/creating-and-managing-repositories/troubleshooting-cloning-errors)。

## 8. 日常操作速查卡

### 首次使用这台电脑

安装 Git → 配置姓名邮箱 → 配置 SSH → 接受仓库权限邀请 → 选定项目父目录，执行：

```bash
git clone git@github.com:mathematical-modeling-nju-2026/mathematical-modeling.git
cd mathematical-modeling
```

### 每次新任务

在本地仓库目录中，确认没有未处理修改后：

```bash
git status
git switch main
git pull --ff-only origin main
git switch -c zhang/new-task
```

把分支名替换成自己的名字和本次任务名。复制或修改文件后：

```bash
git status
git add "本次要上传的文件路径"
git commit -m "说明这次做了什么"
git push -u origin zhang/new-task
```

随后：GitHub 发 PR → 同学检查并合并 → 本地切回 main 并 pull。

### 同一个尚未完成的任务继续修改

先确认没有其他分支遗留的未提交改动，再切回该任务分支：

```bash
git switch zhang/new-task
```

修改并保存文件后：

```bash
git status
git add "本次修改的文件路径"
git commit -m "说明本次补充内容"
git push
```

### 不小心 add 了一个不想提交的文件

```bash
git restore --staged "文件路径"
```

这里只撤销该文件的暂存选择，不删除工作文件。不要漏掉 `--staged`：普通 `git restore 文件路径` 的作用不同，会覆盖工作区中该文件的未暂存修改。

### 随时检查状态

```bash
git status
git branch --show-current
git log --oneline -5
```

它们分别回答：哪些文件变了、我在哪个分支、最近提交了什么。
