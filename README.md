# Multi-Account Codex Router

在一台机器上管理多个 Codex / ChatGPT 登录账号，同时把 skills、agents、plugins、规则和个人配置统一为一份共享配置。

认证、session 和额度仍各自隔离，因此可以在账号额度不足时切换到另一个账号，而不会出现不同账号拥有不同能力配置的问题。

## 安装

前置条件：Python 3.11 或更高版本（需要标准库 `tomllib`）以及已安装的 Codex CLI。

```bash
git clone https://github.com/smices/multi-account-codex-router.git
cd multi-account-codex-router
./install.sh
```

安装器会：

- 创建仓库内的 `.venv` Python 环境。
- 将 `~/codex.sh` 链接到仓库中的启动脚本。
- 如果 `~/codex.sh` 已存在且不是本仓库的链接，先备份为 `~/codex.sh.pre-router-backup.<timestamp>`。

安装器会自动应用可移植的 Sol/Luna preset 到路由器的共享配置；只管理该 preset 声明的字段，已有的无关配置、认证和 session 会保留。每个被改动的既有共享文件都会在路由器备份目录中保存时间戳副本。

## 首次启用

安装完成后执行：

```bash
~/codex.sh account add
```

全新机器上，路由器会自动创建 `~/.codex-router`、`account-1`、`shared` 与配置文件，然后打开设备登录流程。登录成功后，首个账号会自动成为直接运行 `codex` 时的默认账号。

如果机器上已有 `~/.codex`，该命令会将其迁移到 `account-1`，统一共享配置，并将默认 `codex` 认证链接到该账号。原默认认证和 session 会保留为 `.default-backup*` 备份，而不会被静默删除。

## 常用命令

Global options

| 选项 | 说明 |
| --- | --- |
| `-a <id>` | 强制指定本次运行账号（绕过默认/轮换） |
| `-q` | 只输出 Codex 结果，不显示路由提示 |
| `-v` / `--verbose` | 输出路由诊断信息 |
| `-h` / `--help` | 显示帮助 |

Account management

| 命令 | 说明 |
| --- | --- |
| `codex.sh account list` | 查看账号列表 |
| `codex.sh account add` | 添加账号 |
| `codex.sh account retry 2` | 重新登录账号 2 |
| `codex.sh account default 3` | 设置账号 3 为默认账号 |
| `codex.sh account rename 2 quota-account-b` | 设置账号 2 的本地名称 |
| `codex.sh account sync-shared` | 同步共享配置 |
| `codex.sh config apply` | 应用 Sol/Luna preset，并同步所有可用账号 |
| `codex.sh config status` | 只读检查 preset 文件、受管字段和账号共享链接 |
| `codex.sh -p efficient` | 高效模式：Sol high + Luna high |
| `codex.sh -p quality` | 高质量模式：Sol max + Luna xhigh |
| `codex.sh -p ultra` | Ultra 模式：Sol ultra 自动委派 + Luna xhigh |

Session & routing

| 命令 | 说明 |
| --- | --- |
| `codex.sh status` | 查看账号身份与额度 |
| `codex.sh -a 2 status` | 强制使用账号 2 查看状态 |
| `codex.sh resume <SESSION_ID>` | 恢复会话 |
| `codex.sh -a 2 resume <SESSION_ID>` | 强制用账号 2 恢复会话 |

不指定 `-a` 时，路由器优先使用通过 `account default` 设置的默认账号；若未配置默认账号，则按账号间轮换。`resume` 会尝试定位 session 原本所在的账号。

提示信息会显示本次路由来源，例如：
- `default account`：使用了默认账号
- `forced`：使用 `-a`
- `round-robin`：按轮询回退
- `session`：使用 `resume` 对应的原账号

`status` 会显示账号邮箱、套餐和实时额度窗口；查询期间会显示单行加载状态。无法读取额度通常表示认证失效，使用 `account retry <id>` 重新登录即可。

## 共享配置与隔离边界

以下内容位于 `~/.codex-router/shared`，每个账号通过软链接使用同一份：

- `skills`、`agents`、`plugins`、`rules`
- `AGENTS.md` 与按需读取的 `RTK.md`
- `config.toml` 与相关本地设置

以下内容保持在各自账号目录中，绝不共享：

- `auth.json` 登录凭据
- `sessions` 会话记录
- ChatGPT 套餐、模型权限、工作区权限和额度

同步时遇到同名的本地配置会先创建 `.shared-backup*`，不会静默覆盖。

## 可移植 Sol/Luna preset

新设备只需 clone 仓库并运行 `./install.sh`。安装后 preset 自动生效；也可以随时运行：

```bash
codex.sh config apply
codex.sh config status
```

仓库随附完整的 `AGENTS.md`、`RTK.md`、三个推理 Profile、模型配置和四个 Agent 定义：`luna-worker`、仅在 Luna 不可用时接管实现的 `terra-worker`、只读的 `terra-explorer` 与 `terra-docs`。安装器会检查 Codex CLI、Python 3.11+ 和正确的 RTK Token Killer；Codex 或 RTK 缺失时会提示是否使用各自官方安装器自动安装，默认选择安装。非交互环境必须显式使用 `--force` 才会自动安装缺失组件。

检测到已有共享 preset 或 launcher 时会分别询问是否覆盖，默认回车跳过。需要先备份再强制覆盖时运行：

```bash
./install.sh --force
```

既有 `config.toml` 中非受管的 MCP、插件和其他设置会保留，现有 Skills、plugins 和 rules 目录也不会被清空。

默认受管字段固定为：主模型 `gpt-5.6-sol` / `max`、默认子代理 `gpt-5.6-luna` / `xhigh`、Luna 不可用时的 `gpt-5.6-terra` / `xhigh`，以及四个 canonical Agent 的描述和 TOML 文件。`presets/sol-luna/AGENTS.md` 是完整共享指令的仓库源文件，覆盖按需加载 Skills/MCP/RTK、输出压缩、重试与等待熔断，以及 Sol/Luna/Terra 调度。

模式通过 Codex 原生 Profile 在启动时选择，不改写共享默认配置：

```bash
codex.sh -p efficient  # Sol high + Luna high，常规任务
codex.sh -p quality    # Sol max + Luna xhigh，默认高质量模式
codex.sh -p ultra      # Sol ultra 自动委派，大型可并行任务
```

不传 `-p` 时与 `quality` 相同。Luna 不可用或模型无法使用时，`terra-worker` 按 AGENTS 策略以 Terra xhigh 自动补偿。安全或高风险任务默认使用 `quality`；只有能拆成互不重叠所有权的并行任务才使用 `ultra`。

`config apply` 仅更新这些精确 TOML 字段，并用仓库 preset 同步完整共享 `AGENTS.md`、`RTK.md` 和 Agent TOML；它不会触碰 `auth.json` 或 `sessions`。旧的 `SOUL.md` 和 `sub.AGENTS.md` 会先归档到 `backups/sol-luna-preset-<timestamp>`，再从共享加载链移除。对已有受管文件的备份也写入同一目录。需要回滚时，先运行 `config status` 确认漂移，再从对应备份恢复目标共享文件并运行 `account sync-shared`；恢复后可再次运行 `config apply` 回到受管版本。

## 让直接运行 `codex` 使用某个账号

```bash
~/codex.sh account default 3
codex
```

该命令会让默认 `~/.codex` 使用账号 3 的认证和 session，并接入共享配置。旧的默认认证文件会备份为 `auth.json.default-backup*`。

路由器默认先按 `account default` 决定账号，不满足时才轮换。若要固定本次运行某账号，请使用 `~/codex.sh -a 3`。

## 卸载

```bash
rm ~/codex.sh
```

卸载只移除启动链接。`.venv`、`~/.codex` 和 `~/.codex-router` 不会被删除。
