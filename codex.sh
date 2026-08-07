#!/usr/bin/env bash

# When sourced, re-run in a child shell so exit/exec and strict-mode options
# cannot terminate or modify the caller's interactive shell.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  bash "${BASH_SOURCE[0]}" "$@"
  return $?
fi

set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
while [[ -h "$SCRIPT_PATH" ]]; do
  SCRIPT_DIR="$(cd -P "$(dirname "$SCRIPT_PATH")" && pwd)"
  LINK_TARGET="$(readlink "$SCRIPT_PATH")"
  if [[ "$LINK_TARGET" == /* ]]; then
    SCRIPT_PATH="$LINK_TARGET"
  else
    SCRIPT_PATH="$SCRIPT_DIR/$LINK_TARGET"
  fi
done
SCRIPT_DIR="$(cd -P "$(dirname "$SCRIPT_PATH")" && pwd)"
ROUTER_PYTHON="${CODEX_ROUTER_PYTHON:-$SCRIPT_DIR/.venv/bin/python}"
ROUTER_SCRIPT="${CODEX_ROUTER_SCRIPT:-$SCRIPT_DIR/_codex.py}"

show_help() {
  cat <<'EOF'

Codex Router

Usage:

  codex.sh login
      初始化当前账号 ~/.codex 到 account-1

  codex.sh login add
      添加新的 Codex 账号
      使用 codex login --device-auth

  codex.sh login list
      查看账号列表

  codex.sh login rename <id> <name>
      为账号设置本地识别名称

  codex.sh login sync-shared
      同步并修正所有账号的共享配置

  codex.sh login set-default <id>
      让直接运行 codex 时使用指定账号

  codex.sh status
      显示每个账号的登录身份、套餐与当前 Codex 额度

  codex.sh login retry <id>
      重新登录指定账号

  codex.sh resume <SESSION_ID>
      恢复 Codex session

  codex.sh --account <id> <command>
      强制指定账号

Examples:

  ~/codex.sh login
  ~/codex.sh login add
  ~/codex.sh login list
  ~/codex.sh login rename 2 quota-account-b
  ~/codex.sh login sync-shared
  ~/codex.sh login set-default 3
  ~/codex.sh status
  ~/codex.sh resume 019fa256-a879-7111-a646-1e9b5df4ed3f
  ~/codex.sh --account 2 resume SESSION_ID
  ~/codex.sh --account=2 resume SESSION_ID

EOF
}

die() {
  local code="$1"
  shift
  printf '❌ %s\n' "$*" >&2
  exit "$code"
}

run_status() {
  local status_file status_pid status_code spinner_index=0 started_at elapsed message
  local -a spinner_frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
  status_file=$(mktemp "${TMPDIR:-/tmp}/codex-router-status.XXXXXX") || die 1 "无法创建状态临时文件"

  "$ROUTER_PYTHON" "$ROUTER_SCRIPT" status >"$status_file" 2>&1 &
  status_pid=$!
  started_at=$SECONDS
  if [[ -t 2 ]]; then
    while kill -0 "$status_pid" 2>/dev/null; do
      elapsed=$((SECONDS - started_at))
      if (( elapsed < 6 )); then
        message="正在读取账号额度..."
      else
        message="仍在等待服务端响应..."
      fi
      printf '\r\033[2K  %s  %s' "${spinner_frames[spinner_index++ % ${#spinner_frames[@]}]}" "$message" >&2
      sleep 0.12
    done
    printf '\r\033[2K' >&2
  else
    printf '正在读取账号额度...\n' >&2
  fi
  if wait "$status_pid"; then
    status_code=0
  else
    status_code=$?
  fi
  cat "$status_file"
  rm -f "$status_file"
  return "$status_code"
}

ARGS=("$@")
CODEX_ARGS=()
ACCOUNT_ID=""
SAW_COMMAND=0
INDEX=0

while (( INDEX < ${#ARGS[@]} )); do
  ARG="${ARGS[INDEX]}"

  if (( SAW_COMMAND == 0 )); then
    case "$ARG" in
      -h|--help|help)
        show_help
        exit 0
        ;;
      --account)
        if (( INDEX + 1 >= ${#ARGS[@]} )); then
          die 2 "--account 缺少账号 ID"
        fi
        ACCOUNT_ID="${ARGS[INDEX + 1]}"
        if [[ ! "$ACCOUNT_ID" =~ ^[1-9][0-9]*$ ]]; then
          die 2 "--account 需要正整数账号 ID"
        fi
        INDEX=$((INDEX + 2))
        continue
        ;;
      --account=*)
        ACCOUNT_ID="${ARG#*=}"
        if [[ ! "$ACCOUNT_ID" =~ ^[1-9][0-9]*$ ]]; then
          die 2 "--account 需要正整数账号 ID"
        fi
        INDEX=$((INDEX + 1))
        continue
        ;;
      *)
        SAW_COMMAND=1
        CODEX_ARGS+=("$ARG")
        ;;
    esac
  else
    CODEX_ARGS+=("$ARG")
  fi

  INDEX=$((INDEX + 1))
done

if [[ ! -x "$ROUTER_PYTHON" ]]; then
  die 1 "未找到虚拟环境 Python: $ROUTER_PYTHON，请在仓库目录运行 ./install.sh"
fi

if [[ ! -f "$ROUTER_SCRIPT" || ! -r "$ROUTER_SCRIPT" ]]; then
  die 1 "未找到可读取的路由脚本 $ROUTER_SCRIPT"
fi

# Management commands are handled by the Python router.
if (( ${#CODEX_ARGS[@]} > 0 )) && [[ "${CODEX_ARGS[0]}" == "login" || "${CODEX_ARGS[0]}" == "status" ]]; then
  if [[ -n "$ACCOUNT_ID" ]]; then
    die 2 "--account 不能与管理命令一起使用"
  fi
  if [[ "${CODEX_ARGS[0]}" == "status" ]]; then
    run_status
    exit $?
  fi
  exec "$ROUTER_PYTHON" "$ROUTER_SCRIPT" "${CODEX_ARGS[@]}"
fi

# --account is router-only and must not be forwarded to the Codex CLI.
CHOOSER_ARGS=()
if [[ -n "$ACCOUNT_ID" ]]; then
  CHOOSER_ARGS+=(--account "$ACCOUNT_ID")
fi
CHOOSER_ARGS+=("${CODEX_ARGS[@]}")

SELECTED_CODEX_HOME=$("$ROUTER_PYTHON" "$ROUTER_SCRIPT" choose "${CHOOSER_ARGS[@]}")
if [[ -z "$SELECTED_CODEX_HOME" ]]; then
  die 1 "没有可用账号"
fi

if ! command -v codex >/dev/null 2>&1; then
  die 1 "未找到 codex CLI 可执行命令"
fi

export CODEX_HOME="$SELECTED_CODEX_HOME"
printf '🚀 Using:\n   %s\n' "$SELECTED_CODEX_HOME"

exec codex "${CODEX_ARGS[@]}"
