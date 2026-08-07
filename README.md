# Multi-Account Codex Router

在一台机器上管理多个 Codex / ChatGPT 登录账号，同时把 skills、agents、plugins、规则和个人配置统一为一份共享配置。

认证、session 和额度仍各自隔离，因此可以在账号额度不足时切换到另一个账号，而不会出现不同账号拥有不同能力配置的问题。

## 安装

```bash
git clone https://github.com/smices/multi-account-codex-router.git
cd multi-account-codex-router
./install.sh
```

安装器会：

- 创建仓库内的 `.venv` Python 环境。
- 将 `~/codex.sh` 链接到仓库中的启动脚本。
- 如果 `~/codex.sh` 已存在且不是本仓库的链接，先备份为 `~/codex.sh.pre-router-backup.<timestamp>`。

安装器不会读取、迁移、删除或覆盖 `~/.codex` 与 `~/.codex-router`。已有账号和配置会原样保留。

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
- `AGENTS.md`、`SOUL.md` 与其他人格或能力配置
- `config.toml` 与相关本地设置

以下内容保持在各自账号目录中，绝不共享：

- `auth.json` 登录凭据
- `sessions` 会话记录
- ChatGPT 套餐、模型权限、工作区权限和额度

同步时遇到同名的本地配置会先创建 `.shared-backup*`，不会静默覆盖。

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
