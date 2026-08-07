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

## 常用命令

```bash
~/codex.sh login list
~/codex.sh login add
~/codex.sh login retry 2
~/codex.sh login rename 2 quota-account-b
~/codex.sh login sync-shared
~/codex.sh status
~/codex.sh --account 2
~/codex.sh resume <SESSION_ID>
```

不指定 `--account` 时，路由器在可用账号间轮换。`resume` 会尝试定位 session 原本所在的账号。

`status` 会显示账号邮箱、套餐和实时额度窗口；查询期间会显示单行加载状态。无法读取额度通常表示认证失效，使用提示的 `login retry <id>` 重新登录即可。

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
~/codex.sh login set-default 3
codex
```

该命令会让默认 `~/.codex` 使用账号 3 的认证和 session，并接入共享配置。旧的默认认证文件会备份为 `auth.json.default-backup*`。

路由器自身仍按照轮换规则工作；若要固定路由器使用某个账号，请使用 `~/codex.sh --account 3`。

## 卸载

```bash
rm ~/codex.sh
```

卸载只移除启动链接。`.venv`、`~/.codex` 和 `~/.codex-router` 不会被删除。
