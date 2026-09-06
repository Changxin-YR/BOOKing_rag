# 中文长篇小说工作流（Codex）

一个面向 Codex 的可恢复中文长篇小说创作工作流。它把创作拆成设定、规划、写作、审稿、记忆和归档几个阶段：Codex 负责创作与语义审稿，Python 标准库脚本负责确定性校验，不需要额外 API、第三方 Python 依赖或后台服务。

## 快速部署

### 方式一：npm 一键获取（推荐）

在 PowerShell、Terminal 或 Bash 中运行：

```bash
npx degit Changxin-YR/BOOKing_rag codex-novel-workflow
cd codex-novel-workflow
```

`degit` 是通过 npm 临时下载的命令行工具，不会把依赖写入项目。下载后直接用 Codex 打开 `codex-novel-workflow` 文件夹即可。

### 方式二：Git 克隆

```bash
git clone https://github.com/Changxin-YR/BOOKing_rag.git
cd BOOKing_rag
```

### 方式三：GitHub 网页下载

打开本仓库，点击 **Code → Download ZIP**，解压后用 Codex 打开解压目录。

## 在 Codex 中启用

1. 用 Codex 打开包含本 README 和 `AGENTS.md` 的仓库根目录。
2. 对 Codex 发送：

   ```text
   读取 AGENTS.md，运行自检，执行初始化流程。沿用我的既定要求，缺失内容先给方案，不擅自锁定。先通过开篇试写校准文风，再开始正式连载。
   ```

3. 书籍方案确认后，发送：

   ```text
   按项目工作流写下一章，质量优先，完成精修、审稿和归档。
   ```

`AGENTS.md` 是 Codex 的工作流入口。它要求会话开始时读取规则文件，并先运行 `status` 与 `verify`；不要跳过阶段或直接修改归档状态文件。

## 本地自检

需要 Python 3.10 或更高版本。Windows 如果 `python` 不可用，可将命令中的 `python` 替换为 `py -3`。

```bash
python -X utf8 tools/novel.py status
python -X utf8 tools/novel.py verify
python -m unittest discover -s tests -v
```

## 标准创作流程

```text
初始化 → start → brief/context/preflight → 起草与精修 → memory → prepare-review → 四角度审稿 → check → accept
```

常用命令：

```bash
python -X utf8 tools/novel.py bootstrap --evidence approvals/initial.md
python -X utf8 tools/novel.py start 1
python -X utf8 tools/novel.py context 1
python -X utf8 tools/novel.py preflight 1
python -X utf8 tools/novel.py prepare-review 1
python -X utf8 tools/novel.py check 1
python -X utf8 tools/novel.py accept 1
python -X utf8 tools/novel.py doctor
python -X utf8 tools/novel.py recover
```

`bootstrap` 前必须填写 `01_CANON/book.json`、`01_CANON/canon.json` 和 `07_MEMORY/initial.json`，并在 `approvals/initial.md` 保存真实的用户确认。`accept` 只会归档通过完整校验的章节。

## 目录说明

| 路径 | 用途 |
| --- | --- |
| `00_RULES/` | 创作宪法、工作流、文风、质量门禁和审稿校准 |
| `01_CANON/` | 世界观、术语和开书基线 |
| `02_CHARACTERS/` | 人物档案与声线校准 |
| `03_PLOT/` - `05_VOLUMES/` | 主线、暗线、时间规则和卷纲 |
| `06_CHAPTERS/` | 已归档章节、章节记忆和审稿材料 |
| `07_MEMORY/` | 恢复协议、进度锚点和可重建检索索引 |
| `prompts/` | 初始化、写章、恢复、变更和终审提示词 |
| `templates/` | 章纲、记忆、参考和审稿模板 |
| `tools/novel.py` | Python 标准库工作流 CLI |
| `tests/` | 工作流确定性校验 |

## 设计边界

- 脚本能验证文件、哈希、引用、时间线和归档链，不能代替文学判断。
- 重要章节仍建议作者完整阅读，必要时另请人工审稿。
- `07_MEMORY/search.sqlite` 是可删除重建的检索副本，不是事实源。
- 当前仓库提供空白小说项目骨架，不预设题材、人物或终局。

## 版本与许可

当前工作流版本：**v1.1**。项目使用 Python 标准库；仓库未附加额外第三方运行时依赖。
