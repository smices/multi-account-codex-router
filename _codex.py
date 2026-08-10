#!/usr/bin/env python3

import json
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import fcntl


ROOT = Path.home() / ".codex-router"
CONFIG = ROOT / "config.json"
LOCK = ROOT / "config.lock"
SHARED_HOME = ROOT / "shared"
PRESET_DIR = Path(__file__).resolve().parent / "presets" / "sol-luna"
PRESET_MARKER_START = "<!-- codex-router:sol-luna:start -->"
PRESET_MARKER_END = "<!-- codex-router:sol-luna:end -->"
TOML_MARKER = "# codex-router:sol-luna managed"
PRESET_CONFIG_KEYS = (
    "model",
    "model_reasoning_effort",
    "agents.default_subagent_model",
    "agents.default_subagent_reasoning_effort",
    "agents.luna-worker.description",
    "agents.luna-worker.config_file",
)


class RouterError(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code

DEFAULT_SHARED_PATHS = (
    "AGENTS.md",
    ".personality_migration",
    "ambient-suggestions",
    "agents",
    "browser",
    "chrome-native-hosts-v2.json",
    "CODEX_CAPABILITY_PROFILE.md",
    "computer-use",
    "config.toml",
    "models_cache.json",
    "plugins",
    "realtime-voice-continuity.json",
    "rules",
    "SOUL.md",
    "skills",
    "sub.AGENTS.md",
    "vendor_imports",
    "visualizations",
)
SHARED_ITEMS = tuple(DEFAULT_SHARED_PATHS)


def validate_shared_item(item):
    path = Path(item)
    if not item or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RouterError(
            "CODEX_ROUTER_SHARED_PATHS 只能包含相对于 CODEX_HOME 的安全路径"
        )
    return item


def shared_items():
    raw = os.getenv("CODEX_ROUTER_SHARED_PATHS")
    if not raw:
        return SHARED_ITEMS
    items = []
    for item in raw.split(","):
        parsed = item.strip()
        if parsed:
            parsed = validate_shared_item(parsed)
        if parsed and parsed not in items:
            items.append(parsed)
    return tuple(items) if items else SHARED_ITEMS


def shared_disabled():
    return os.getenv("CODEX_ROUTER_DISABLE_SHARED", "").lower() in {"1", "true", "yes", "on"}


def ensure_root():
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)


@contextmanager
def config_lock():
    ensure_root()
    fd = os.open(LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "r+") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        yield


def default_config():
    return {"accounts": [], "last_used": 0, "sessions": {}}


def validate_config(cfg):
    if not isinstance(cfg, dict):
        raise RouterError(f"配置格式错误: {CONFIG}")

    accounts = cfg.get("accounts")
    if not isinstance(accounts, list):
        raise RouterError(f"配置中的 accounts 必须是列表: {CONFIG}")

    seen_ids = set()
    normalized = []
    for account in accounts:
        if not isinstance(account, dict):
            raise RouterError(f"配置中存在无效账号记录: {CONFIG}")
        account_id = account.get("id")
        home = account.get("home")
        if not isinstance(account_id, int) or account_id < 1 or account_id in seen_ids:
            raise RouterError(f"配置中存在无效或重复的账号 ID: {CONFIG}")
        if not isinstance(home, str) or not home:
            raise RouterError(f"账号 {account_id} 缺少有效目录: {CONFIG}")
        if Path(home) != account_home(account_id):
            raise RouterError(f"账号 {account_id} 的目录不受路由器管理: {CONFIG}")
        seen_ids.add(account_id)
        normalized.append({
            "id": account_id,
            "name": str(account.get("name") or f"account-{account_id}"),
            "home": home,
        })

    last_used = cfg.get("last_used", 0)
    if not isinstance(last_used, int) or last_used < 0:
        last_used = 0
    raw_sessions = cfg.get("sessions", {})
    sessions = {}
    if isinstance(raw_sessions, dict):
        for session_id, account_id in raw_sessions.items():
            if (
                isinstance(session_id, str)
                and re.fullmatch(r"[0-9A-Fa-f-]{8,}", session_id)
                and isinstance(account_id, int)
                and account_id >= 1
            ):
                sessions[session_id] = account_id
    return {"accounts": normalized, "last_used": last_used, "sessions": sessions}


def load_config():
    ensure_root()
    if not CONFIG.exists():
        return default_config()
    try:
        return validate_config(json.loads(CONFIG.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise RouterError(f"无法读取配置 {CONFIG}: {exc}") from exc


def save_config(cfg):
    ensure_root()
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=ROOT,
            prefix="config.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_name = temp_file.name
            json.dump(cfg, temp_file, ensure_ascii=False, indent=2)
            temp_file.write("\n")
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, CONFIG)
    except OSError as exc:
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        raise RouterError(f"无法保存配置 {CONFIG}: {exc}") from exc


def account_home(account_id):
    return ROOT / f"account-{account_id}"


def ensure_shared_home():
    if shared_disabled():
        return
    SHARED_HOME.mkdir(mode=0o700, parents=True, exist_ok=True)


def _shared_item_backup_path(path):
    base = f"{path.name}.shared-backup"
    candidate = path.with_name(base)
    if not candidate.exists():
        return candidate
    index = 1
    while True:
        next_candidate = path.with_name(f"{base}-{index}")
        if not next_candidate.exists():
            return next_candidate
        index += 1


def _safe_replace_with_symlink(account_item: Path, shared_item: Path):
    if account_item.is_symlink():
        if os.path.realpath(account_item) == os.path.realpath(shared_item):
            return
        account_item.unlink()
    elif account_item.exists():
        backup = _shared_item_backup_path(account_item)
        print(
            f"⚠️ 共享配置冲突，已备份: {account_item} -> {backup}",
            file=sys.stderr,
        )
        account_item.replace(backup)

    account_item.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(str(shared_item), str(account_item))


def sync_shared_for_account(account_home):
    if shared_disabled():
        return
    ensure_shared_home()

    account_home = Path(account_home)
    if not account_home.is_dir():
        raise RouterError(f"账号目录不存在: {account_home}")

    for item in shared_items():
        account_item = account_home / item
        shared_item = SHARED_HOME / item

        if shared_item.exists():
            _safe_replace_with_symlink(account_item, shared_item)
            continue

        if account_item.is_symlink():
            account_item.unlink()
            continue
        if not account_item.exists():
            continue

        shared_item.parent.mkdir(parents=True, exist_ok=True)
        account_item.replace(shared_item)
        _safe_replace_with_symlink(account_item, shared_item)


def seed_shared_from_accounts(accounts):
    if shared_disabled():
        return
    ensure_shared_home()
    if not accounts:
        return

    for account in accounts:
        account_home = Path(account["home"])
        if not account_home.is_dir():
            continue
        for item in shared_items():
            shared_item = SHARED_HOME / item
            if shared_item.exists():
                continue
            account_item = account_home / item
            if account_item.is_symlink() or not account_item.exists():
                continue
            shared_item.parent.mkdir(parents=True, exist_ok=True)
            account_item.replace(shared_item)


def require_codex():
    if shutil.which("codex") is None:
        raise RouterError("未找到 codex CLI 可执行命令")


def run_login(home):
    require_codex()
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    return subprocess.run(
        ["codex", "login", "--device-auth"], env=env, check=False
    ).returncode


def print_accounts(cfg):
    print("\nCodex Accounts\n================")
    if not cfg["accounts"]:
        print("(none)")
        return
    default_id = default_account_id(cfg)
    for account in cfg["accounts"]:
        home = Path(account["home"])
        status = "ok" if home.is_dir() else "missing"
        if account["id"] == default_id:
            status += "; default"
        print(f'{account["id"]}: {account["name"]} [{status}]')
        print(f"    {home}")
        print(f"    relogin: ~/codex.sh login retry {account['id']}")


def login_first():
    bootstrap_login = False
    with config_lock():
        cfg = load_config()
        if cfg["accounts"]:
            print("已有账号:")
            print_accounts(cfg)
            return 0

        source = Path.home() / ".codex"
        if not source.exists():
            bootstrap_login = True
        elif not source.is_dir():
            raise RouterError(f"默认 Codex 目录异常: {source} 不是目录")

        if bootstrap_login:
            pass
        else:
            target = account_home(1)
            if target.exists() and not target.is_dir():
                raise RouterError(f"账号目录异常: {target} 不是目录")
            if target.exists() and any(target.iterdir()):
                raise RouterError(
                    f"account-1 目录已存在且不为空: {target}，请先清理或迁移后再初始化"
                )
            target.mkdir(mode=0o700, parents=True, exist_ok=True)
            print("复制当前 Codex 登录状态...")
            for item in source.iterdir():
                destination = target / item.name
                if item.is_dir():
                    shutil.copytree(item, destination, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, destination)
            sync_shared_for_account(target)

            cfg["accounts"].append({
                "id": 1, "name": "current", "home": str(target)
            })
            save_config(cfg)
    if bootstrap_login:
        print("未发现 ~/.codex，将创建 account-1 并开始设备登录...")
        return login_add()
    login_set_default(1)
    print("✅ account-1 created")
    return 0


def next_account_id(cfg):
    used_ids = {account["id"] for account in cfg["accounts"]}
    account_id = 1
    while account_id in used_ids or account_home(account_id).exists():
        account_id += 1
    return account_id


def login_add():
    with config_lock():
        cfg = load_config()
        first_account = not cfg["accounts"]
        account_id = next_account_id(cfg)
        home = account_home(account_id)
        home.mkdir(mode=0o700, parents=True, exist_ok=False)

    print(f"Add account {account_id}\n\nStarting:\n\ncodex login --device-auth\n")
    result = run_login(home)
    if result != 0:
        print(f"❌ login failed\nDirectory removed:\n{home}", file=sys.stderr)
        shutil.rmtree(home, ignore_errors=True)
        return result

    with config_lock():
        cfg = load_config()
        seed_shared_from_accounts(cfg["accounts"])
        sync_shared_for_account(home)
        if any(account["id"] == account_id for account in cfg["accounts"]):
            raise RouterError(f"账号 ID {account_id} 已存在，未重复写入配置")
        cfg["accounts"].append({
            "id": account_id,
            "name": f"account-{account_id}",
            "home": str(home),
        })
        save_config(cfg)
    if first_account:
        login_set_default(account_id)
        print("✅ 首个账号已设为默认 codex 账号")
    print("✅ account added")
    return 0


def login_retry(account_id):
    with config_lock():
        cfg = load_config()
        account = next(
            (item for item in cfg["accounts"] if item["id"] == account_id), None
        )
    if account is None:
        raise RouterError(f"账号不存在: {account_id}", 2)
    home = Path(account["home"])
    if not home.is_dir():
        raise RouterError(f"账号目录不存在: {home}")
    sync_shared_for_account(home)
    result = run_login(home)
    if result != 0:
        return result

    with config_lock():
        cfg = load_config()
        account = next(
            (item for item in cfg["accounts"] if item["id"] == account_id), None
        )
        if account is None:
            raise RouterError(f"账号不存在: {account_id}", 2)
        sync_shared_for_account(Path(account["home"]))
    print("✅ 登录成功，已同步共享配置")
    return 0


def login_rename(account_id, name):
    name = name.strip()
    if not name or len(name) > 80 or "\n" in name or "\r" in name:
        raise RouterError("账号名称需为 1-80 个非换行字符", 2)

    with config_lock():
        cfg = load_config()
        account = next(
            (item for item in cfg["accounts"] if item["id"] == account_id), None
        )
        if account is None:
            raise RouterError(f"账号不存在: {account_id}", 2)
        account["name"] = name
        save_config(cfg)
    print(f"✅ account-{account_id} 已命名为: {name}")
    return 0


def default_codex_home():
    return Path.home() / ".codex"


def default_account_id(cfg):
    default_auth = default_codex_home() / "auth.json"
    if not default_auth.is_symlink():
        return None
    default_target = os.path.realpath(default_auth)
    for account in cfg["accounts"]:
        if default_target == os.path.realpath(Path(account["home"]) / "auth.json"):
            return account["id"]
    return None


def default_backup_path(path):
    base = f"{path.name}.default-backup"
    candidate = path.with_name(base)
    if not candidate.exists():
        return candidate
    index = 1
    while True:
        candidate = path.with_name(f"{base}-{index}")
        if not candidate.exists():
            return candidate
        index += 1


def replace_default_with_symlink(path, target):
    if path.is_symlink():
        if os.path.realpath(path) == os.path.realpath(target):
            return
        path.unlink()
    elif path.exists():
        backup = default_backup_path(path)
        path.replace(backup)
        print(f"⚠️ 原默认状态已备份: {path} -> {backup}", file=sys.stderr)
    os.symlink(str(target), str(path))


def login_set_default(account_id):
    with config_lock():
        cfg = load_config()
        account = next(
            (item for item in cfg["accounts"] if item["id"] == account_id), None
        )
        if account is None:
            raise RouterError(f"账号不存在: {account_id}", 2)
        account_home_path = Path(account["home"])
        auth_file = account_home_path / "auth.json"
        if not auth_file.is_file():
            raise RouterError(
                f"账号 {account_id} 没有有效的本地认证文件，请先重新登录", 2
            )

        default_home = default_codex_home()
        default_home.mkdir(mode=0o700, parents=True, exist_ok=True)
        sync_shared_for_account(default_home)
        replace_default_with_symlink(default_home / "auth.json", auth_file)
        replace_default_with_symlink(
            default_home / "sessions", account_home_path / "sessions"
        )
    print(f"✅ 默认 codex 账号已切换为 {account_id}: {account['name']}")
    return 0


def sync_shared():
    with config_lock():
        cfg = load_config()
        accounts = usable_accounts(cfg)
        if not accounts:
            raise RouterError("没有可用账号")

        for account in accounts:
            sync_shared_for_account(Path(account["home"]))
    print("✅ shared config synced")
    return 0


def _preset_text(name):
    try:
        return (PRESET_DIR / name).read_text(encoding="utf-8")
    except OSError as exc:
        raise RouterError(f"无法读取内置 Sol/Luna preset: {exc}") from exc


def _preset_config_values():
    try:
        parsed = tomllib.loads(_preset_text("config.toml"))
    except tomllib.TOMLDecodeError as exc:
        raise RouterError(f"内置 Sol/Luna config.toml 无效: {exc}") from exc
    values = {}
    for dotted_key in PRESET_CONFIG_KEYS:
        current = parsed
        for component in dotted_key.split("."):
            if not isinstance(current, dict) or component not in current:
                raise RouterError(f"内置 Sol/Luna config.toml 缺少 {dotted_key}")
            current = current[component]
        if not isinstance(current, str):
            raise RouterError(f"内置 Sol/Luna config.toml 的 {dotted_key} 必须为字符串")
        values[dotted_key] = current
    return values


def _dotted_value(parsed, dotted_key):
    current = parsed
    for component in dotted_key.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(component)
    return current


def _backup_existing(path, backup_root):
    if not path.exists():
        return None
    relative = path.relative_to(ROOT)
    destination = backup_root / relative
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    shutil.copy2(path, destination)
    return destination


def _atomic_write(path, content, mode):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as temp_file:
            temp_name = temp_file.name
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)
    except OSError as exc:
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        raise RouterError(f"无法写入 {path}: {exc}") from exc


def _toml_section(line):
    match = re.match(r"^\s*\[([^\]]+)\]\s*(?:#.*)?$", line)
    return match.group(1).strip() if match else None


def _toml_key(line):
    match = re.match(r"^\s*([A-Za-z0-9_.-]+)\s*=", line)
    return match.group(1) if match else None


def _strip_preset_toml(content):
    """Remove managed keys and lift legacy agents-table extras to root dots."""
    output = []
    legacy_extras = []
    section = None
    drop_managed_root_spacing = False
    legacy_prefix = None
    for line in content.splitlines(keepends=True):
        if line.strip() == TOML_MARKER:
            continue
        header = _toml_section(line)
        if header is not None:
            section = header
            drop_managed_root_spacing = False
            legacy_prefix = header if header in {"agents", "agents.luna-worker"} else None
            if legacy_prefix is None:
                output.append(line)
            continue
        key = _toml_key(line)
        if drop_managed_root_spacing and section is None and not line.strip():
            continue
        managed = (
            (section is None and key in PRESET_CONFIG_KEYS)
            or (section == "agents" and key in {
                "default_subagent_model", "default_subagent_reasoning_effort"
            })
            or (section == "agents.luna-worker" and key in {
                "description", "config_file"
            })
        )
        if section is None and managed:
            drop_managed_root_spacing = True
        if managed:
            continue
        drop_managed_root_spacing = False
        if legacy_prefix:
            if key:
                line = re.sub(
                    r"^(\s*)[A-Za-z0-9_.-]+(\s*=)",
                    rf"\1{legacy_prefix}.{key}\2",
                    line,
                    count=1,
                )
            legacy_extras.append(line)
        else:
            output.append(line)
    while legacy_extras and not legacy_extras[0].strip():
        legacy_extras.pop(0)
    while legacy_extras and not legacy_extras[-1].strip():
        legacy_extras.pop()
    return output, legacy_extras


def merge_sol_luna_config(content):
    """Preserve unrelated TOML text while owning only the preset's exact keys."""
    lines, legacy_extras = _strip_preset_toml(content)
    values = _preset_config_values()
    root_additions = [f"{TOML_MARKER}\n"]
    root_additions.extend(
        f"{key} = {json.dumps(values[key], ensure_ascii=False)}\n"
        for key in PRESET_CONFIG_KEYS
    )
    root_additions.append("\n")
    if legacy_extras:
        root_additions.extend(legacy_extras)
        if root_additions[-1].strip():
            root_additions.append("\n")
    first_table = next(
        (index for index, line in enumerate(lines) if _toml_section(line) is not None),
        len(lines),
    )
    lines = lines[:first_table] + root_additions + lines[first_table:]
    merged = "".join(lines)
    if not merged.endswith("\n"):
        merged += "\n"
    try:
        parsed = tomllib.loads(merged)
    except tomllib.TOMLDecodeError as exc:
        raise RouterError(f"合并后的 config.toml 无效: {exc}") from exc
    if any(_dotted_value(parsed, key) != value for key, value in values.items()):
        raise RouterError("Sol/Luna preset 配置验证失败")
    return merged


def upsert_preset_agents(content):
    managed = _preset_text("AGENTS.managed.md").rstrip() + "\n"
    pattern = re.compile(
        rf"{re.escape(PRESET_MARKER_START)}.*?{re.escape(PRESET_MARKER_END)}\s*",
        re.DOTALL,
    )
    retained = pattern.sub("", content).rstrip()
    return (retained + ("\n\n" if retained else "") + managed)


def _preset_backup_root():
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    return ROOT / "backups" / f"sol-luna-preset-{stamp}"


def apply_sol_luna_preset():
    """Install shared managed files and synchronize every usable account."""
    with config_lock():
        ensure_shared_home()
        config_path = SHARED_HOME / "config.toml"
        agents_path = SHARED_HOME / "AGENTS.md"
        worker_path = SHARED_HOME / "agents" / "luna-worker.toml"
        desired = {
            config_path: merge_sol_luna_config(
                config_path.read_text(encoding="utf-8") if config_path.exists() else ""
            ),
            agents_path: upsert_preset_agents(
                agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
            ),
            worker_path: _preset_text("agents/luna-worker.toml"),
        }
        changed = [(path, text) for path, text in desired.items()
                   if not path.exists() or path.read_text(encoding="utf-8") != text]
        backup_root = _preset_backup_root() if any(path.exists() for path, _ in changed) else None
        for path, text in changed:
            if backup_root and path.exists():
                backup = _backup_existing(path, backup_root)
                print(f"已备份: {path.relative_to(ROOT)} -> {backup.relative_to(ROOT)}")
            mode = 0o600 if path == config_path else 0o644
            _atomic_write(path, text, mode)
        if config_path.stat().st_mode & 0o077:
            os.chmod(config_path, 0o600)
        cfg = load_config()
        for account in usable_accounts(cfg):
            sync_shared_for_account(Path(account["home"]))
    print("✅ Sol/Luna preset 已应用并同步共享配置")
    return 0


def sol_luna_preset_status():
    """Read-only verification for the portable preset and usable-account links."""
    problems = []
    config_path = SHARED_HOME / "config.toml"
    agents_path = SHARED_HOME / "AGENTS.md"
    worker_path = SHARED_HOME / "agents" / "luna-worker.toml"
    try:
        merged = merge_sol_luna_config(config_path.read_text(encoding="utf-8"))
        if config_path.read_text(encoding="utf-8") != merged:
            problems.append("shared/config.toml 已漂移")
    except (OSError, RouterError) as exc:
        problems.append(f"shared/config.toml 缺失或无效: {exc}")
    try:
        if agents_path.read_text(encoding="utf-8") != upsert_preset_agents(agents_path.read_text(encoding="utf-8")):
            problems.append("shared/AGENTS.md 已漂移")
    except OSError:
        problems.append("shared/AGENTS.md 缺失")
    try:
        if worker_path.read_text(encoding="utf-8") != _preset_text("agents/luna-worker.toml"):
            problems.append("shared/agents/luna-worker.toml 已漂移")
    except OSError:
        problems.append("shared/agents/luna-worker.toml 缺失")
    if CONFIG.exists():
        try:
            cfg = validate_config(json.loads(CONFIG.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, RouterError) as exc:
            problems.append(f"router config 缺失或无效: {exc}")
            cfg = default_config()
    else:
        cfg = default_config()
    for account in usable_accounts(cfg):
        for item in ("config.toml", "AGENTS.md", "agents"):
            account_item = Path(account["home"]) / item
            shared_item = SHARED_HOME / item
            if not account_item.is_symlink() or os.path.realpath(account_item) != os.path.realpath(shared_item):
                problems.append(f"account-{account['id']}/{item} 未同步")
    if problems:
        for problem in problems:
            print(f"❌ {problem}", file=sys.stderr)
        return 1
    print("✅ Sol/Luna preset 状态一致")
    return 0


def list_accounts():
    with config_lock():
        print_accounts(load_config())
    return 0


def app_server_request(home):
    requests = (
        {"method": "initialize", "id": 1, "params": {
            "clientInfo": {"name": "codex-router", "version": "1.0"}
        }},
        {"method": "initialized", "params": {}},
        {"method": "account/read", "id": 2, "params": {"refreshToken": False}},
        {"method": "account/rateLimits/read", "id": 3, "params": {}},
    )
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    try:
        process = subprocess.Popen(
            ["codex", "app-server"],
            stdin=subprocess.PIPE,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            bufsize=1,
        )
    except OSError:
        return None, "无法启动额度服务"

    responses = {}
    try:
        for request in requests:
            process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()

        deadline = time.monotonic() + 20
        while {2, 3} - responses.keys():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None, "读取超时"
            ready, _, _ = select.select([process.stdout], [], [], remaining)
            if not ready:
                return None, "读取超时"
            line = process.stdout.readline()
            if not line:
                return None, "无法读取，请重新登录"
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            message_id = message.get("id")
            if message_id in {2, 3}:
                responses[message_id] = message
    finally:
        if process.stdin:
            process.stdin.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()

    if "error" in responses[2] or "error" in responses[3]:
        return None, "无法读取，请重新登录"
    return {
        "account": responses[2].get("result", {}).get("account"),
        "limits": responses[3].get("result", {}),
    }, None


def format_reset_time(timestamp):
    if not isinstance(timestamp, (int, float)):
        return "重置时间未知"
    return datetime.fromtimestamp(timestamp).astimezone().strftime("%m-%d %H:%M")


def format_limit(bucket):
    primary = bucket.get("primary") if isinstance(bucket, dict) else None
    if not isinstance(primary, dict) or not isinstance(primary.get("usedPercent"), (int, float)):
        return None
    name = bucket.get("limitName") or bucket.get("limitId") or "Codex"
    remaining = max(0, 100 - primary["usedPercent"])
    duration = primary.get("windowDurationMins")
    window = f"{duration} 分钟窗口" if isinstance(duration, int) else "额度窗口"
    return f"{name}: 剩余 {remaining:g}%（{window}，{format_reset_time(primary.get('resetsAt'))} 重置）"


def account_status(account):
    home = Path(account["home"])
    if not home.is_dir():
        return account["id"], None, "账号目录不存在"
    return account["id"], *app_server_request(home)


def status_accounts():
    require_codex()
    with config_lock():
        accounts = usable_accounts(load_config())
    if not accounts:
        raise RouterError("没有可用账号")

    results = {}
    with ThreadPoolExecutor(max_workers=min(4, len(accounts))) as executor:
        futures = [executor.submit(account_status, account) for account in accounts]
        for future in futures:
            account_id, details, error = future.result()
            results[account_id] = (details, error)

    print("\nCodex Account Status\n====================")
    for account in accounts:
        details, error = results[account["id"]]
        print(f'{account["id"]}: {account["name"]}')
        if error:
            print(f"    额度: {error}")
            print(f"    处理: ~/codex.sh login retry {account['id']}")
            continue

        account_info = details.get("account") or {}
        email = account_info.get("email") or "未知"
        plan = account_info.get("planType") or "未知"
        print(f"    账号: {email} ({plan})")
        limits = details.get("limits", {})
        buckets = limits.get("rateLimitsByLimitId")
        if not isinstance(buckets, dict) or not buckets:
            fallback = limits.get("rateLimits")
            buckets = {"codex": fallback} if isinstance(fallback, dict) else {}
        rendered = [format_limit(bucket) for bucket in buckets.values()]
        rendered = [line for line in rendered if line]
        if rendered:
            for line in rendered:
                print(f"    额度: {line}")
        else:
            print("    额度: 服务端未提供")
    return 0


def usable_accounts(cfg):
    return [account for account in cfg["accounts"] if Path(account["home"]).is_dir()]


def session_id_from_args(args):
    if len(args) < 2 or args[0] != "resume" or args[1].startswith("-"):
        return None
    session_id = args[1]
    if not re.fullmatch(r"[0-9A-Fa-f-]{8,}", session_id):
        return None
    return session_id


def account_for_session(cfg, accounts, session_id):
    remembered_id = cfg["sessions"].get(session_id)
    if remembered_id is not None:
        remembered = next(
            (account for account in accounts if account["id"] == remembered_id), None
        )
        if remembered is not None and Path(remembered["home"]).is_dir():
            return remembered
        cfg["sessions"].pop(session_id, None)

    for account in accounts:
        sessions = Path(account["home"]) / "sessions"
        try:
            found = sessions.is_dir() and next(
                sessions.rglob(f"*{session_id}*.jsonl"), None
            )
        except OSError:
            found = None
        if found:
            cfg["sessions"][session_id] = account["id"]
            return account
    return None


def choose(args):
    with config_lock():
        cfg = load_config()
        accounts = usable_accounts(cfg)
        if not accounts:
            raise RouterError("没有目录有效的可用账号")
        seed_shared_from_accounts(cfg["accounts"])

        if "--account" in args:
            index = args.index("--account")
            if index + 1 >= len(args):
                raise RouterError("--account 缺少账号 ID", 2)
            account_id = parse_positive_int(args[index + 1], "账号 ID")
            account = next(
                (item for item in accounts if item["id"] == account_id), None
            )
            if account is None:
                raise RouterError(f"账号不存在或目录无效: {account_id}", 2)
            sync_shared_for_account(Path(account["home"]))
            print(account["home"])
            return 0

        session_id = session_id_from_args(args)
        if session_id:
            account = account_for_session(cfg, accounts, session_id)
            if account is not None:
                save_config(cfg)
                sync_shared_for_account(Path(account["home"]))
                print(account["home"])
                return 0

        default_account_id_value = default_account_id(cfg)
        if default_account_id_value is not None:
            account = next(
                (item for item in accounts if item["id"] == default_account_id_value),
                None,
            )
            if account is not None:
                sync_shared_for_account(Path(account["home"]))
                save_config(cfg)
                print(account["home"])
                return 0

        position = cfg["last_used"]
        account = accounts[position % len(accounts)]
        sync_shared_for_account(Path(account["home"]))
        cfg["last_used"] = position + 1
        save_config(cfg)
        print(account["home"])
        return 0


def parse_positive_int(value, label):
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RouterError(f"{label} 必须是正整数", 2) from exc
    if parsed < 1:
        raise RouterError(f"{label} 必须是正整数", 2)
    return parsed


def main(args):
    if args == ["config", "apply"]:
        return apply_sol_luna_preset()
    if args == ["config", "status"]:
        return sol_luna_preset_status()
    if args == ["login"]:
        return login_first()
    if args == ["login", "add"]:
        return login_add()
    if args == ["login", "list"]:
        return list_accounts()
    if args == ["status"]:
        return status_accounts()
    if args == ["login", "sync-shared"]:
        return sync_shared()
    if len(args) == 3 and args[:2] == ["login", "set-default"]:
        return login_set_default(parse_positive_int(args[2], "账号 ID"))
    if len(args) >= 4 and args[:2] == ["login", "rename"]:
        return login_rename(parse_positive_int(args[2], "账号 ID"), " ".join(args[3:]))
    if len(args) == 3 and args[:2] == ["login", "retry"]:
        return login_retry(parse_positive_int(args[2], "账号 ID"))
    if args and args[0] == "choose":
        return choose(args[1:])
    raise RouterError("未知命令或参数不完整", 2)


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except RouterError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        raise SystemExit(exc.code)
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        raise SystemExit(130)
