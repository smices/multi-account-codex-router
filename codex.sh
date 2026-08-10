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

Usage
  codex.sh [global options] <command> [args...]

Global options
  -a <id>            强制指定本次运行账号（绕过默认/轮换）
  -q                 只输出 Codex 结果，不显示路由提示
  -v, --verbose      输出路由诊断信息
  -h, --help         显示帮助

Account management
  account list                 查看账号列表
  account add                  添加新的 Codex 账号（使用 codex login --device-auth）
  account rename <id> <name>   为账号设置本地识别名称
  account sync-shared          同步并修正所有账号的共享配置
  account default <id>         设置直接运行 codex 时默认账号
  account retry <id>           重新登录指定账号

Configuration
  config apply                 应用可移植 Sol/Luna preset 并同步共享配置
  config status                只读检查 Sol/Luna preset 与共享链接

Session & routing
  resume <SESSION_ID>          恢复 Codex session
  status                       显示账号状态与实时额度
  -a <id> <codex args...>     强制指定账号运行任意 codex 命令

Examples
  codex.sh account add                 添加新账号
  codex.sh account list                查看账号列表
  codex.sh account retry 2             重新登录账号 2
  codex.sh account rename 2 alias      修改账号 2 的名称
  codex.sh account sync-shared         同步共享配置
  codex.sh account default 3           将账号 3 设为默认
  codex.sh config apply                应用 Sol/Luna preset
  codex.sh config status               检查 Sol/Luna preset
  codex.sh status                      查看账号状态
  codex.sh resume <SESSION_ID>         按会话恢复
  codex.sh -a 2 resume <SESSION_ID>    强制用账号 2 恢复会话
  codex.sh -a 2 status                强制用账号 2 查看状态

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
QUIET=0
VERBOSE=0
INDEX=0
ACCOUNT_WAS_FORCED=0

while (( INDEX < ${#ARGS[@]} )); do
  ARG="${ARGS[INDEX]}"

  case "$ARG" in
    -h|--help)
      show_help
      exit 0
      ;;
    -a)
      if (( INDEX + 1 >= ${#ARGS[@]} )); then
        die 2 "-a 缺少账号 ID"
      fi
      ACCOUNT_ID="${ARGS[INDEX + 1]}"
      if [[ ! "$ACCOUNT_ID" =~ ^[1-9][0-9]*$ ]]; then
        die 2 "-a 需要正整数账号 ID"
      fi
      ACCOUNT_WAS_FORCED=1
      INDEX=$((INDEX + 2))
      continue
      ;;
    -q)
      QUIET=1
      INDEX=$((INDEX + 1))
      continue
      ;;
    --verbose|-v)
      VERBOSE=1
      INDEX=$((INDEX + 1))
      continue
      ;;
    --)
      INDEX=$((INDEX + 1))
      while (( INDEX < ${#ARGS[@]} )); do
        CODEX_ARGS+=("${ARGS[INDEX]}")
        INDEX=$((INDEX + 1))
      done
      break
      ;;
    *)
      CODEX_ARGS+=("$ARG")
      INDEX=$((INDEX + 1))
      ;;
  esac

done

if (( ${#CODEX_ARGS[@]} > 0 )) && [[ "${CODEX_ARGS[0]}" == "help" ]]; then
  die 2 "已移除 help 子命令，请改用 -h/--help"
fi

if (( ${#CODEX_ARGS[@]} > 1 )) && [[ "${CODEX_ARGS[0]}" == "account" ]]; then
  case "${CODEX_ARGS[1]}" in
    default)
      CODEX_ARGS=(login set-default "${CODEX_ARGS[@]:2}")
      ;;
    list|add|rename|sync-shared|retry)
      CODEX_ARGS=(login "${CODEX_ARGS[@]:1}")
      ;;
    *)
      die 2 "未知 account 子命令: ${CODEX_ARGS[1]}"
      ;;
  esac
elif (( ${#CODEX_ARGS[@]} == 1 )) && [[ "${CODEX_ARGS[0]}" == "account" ]]; then
  show_help
  exit 0
elif (( ${#CODEX_ARGS[@]} > 0 )) && [[ "${CODEX_ARGS[0]}" == "login" ]]; then
  die 2 "已移除 login 子命令，请改用 account 代替"
fi

if (( ${#CODEX_ARGS[@]} > 0 )) && [[ "${CODEX_ARGS[0]}" == "config" ]]; then
  if (( ${#CODEX_ARGS[@]} != 2 )) || [[ "${CODEX_ARGS[1]}" != "apply" && "${CODEX_ARGS[1]}" != "status" ]]; then
    die 2 "config 仅支持 apply 或 status"
  fi
  if [[ -n "$ACCOUNT_ID" ]]; then
    die 2 "-a 不能与管理命令一起使用"
  fi
  if [[ ! -x "$ROUTER_PYTHON" || ! -f "$ROUTER_SCRIPT" ]]; then
    die 1 "路由器未安装或脚本不可读"
  fi
  exec "$ROUTER_PYTHON" "$ROUTER_SCRIPT" "${CODEX_ARGS[@]}"
fi

if [[ ! -x "$ROUTER_PYTHON" ]]; then
  die 1 "未找到虚拟环境 Python: $ROUTER_PYTHON，请在仓库目录运行 ./install.sh"
fi

if [[ ! -f "$ROUTER_SCRIPT" || ! -r "$ROUTER_SCRIPT" ]]; then
  die 1 "未找到可读取的路由脚本 $ROUTER_SCRIPT"
fi

# Management commands are handled by the Python router.
if (( ${#CODEX_ARGS[@]} > 0 )) && [[ "${CODEX_ARGS[0]}" == "status" || "${CODEX_ARGS[0]}" == "login" ]]; then
  if [[ -n "$ACCOUNT_ID" ]]; then
    die 2 "-a 不能与管理命令一起使用"
  fi
  if [[ "${CODEX_ARGS[0]}" == "status" ]]; then
    run_status
    exit $?
  fi
  exec "$ROUTER_PYTHON" "$ROUTER_SCRIPT" "${CODEX_ARGS[@]}"
fi

# -a is router-only and must not be forwarded to the Codex CLI.
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
SELECTED_ID="unknown"
if [[ "$(basename "$SELECTED_CODEX_HOME")" =~ account-([0-9]+)$ ]]; then
  SELECTED_ID="${BASH_REMATCH[1]}"
fi

ROUTE_MODE="rotate"
if (( ACCOUNT_WAS_FORCED == 1 )); then
  ROUTE_MODE="forced"
elif [[ "${CODEX_ARGS[0]}" == "resume" && -n "${CODEX_ARGS[1]:-}" ]]; then
  ROUTE_MODE="resume"
else
  DEFAULT_AUTH="$HOME/.codex/auth.json"
  if [[ -L "$DEFAULT_AUTH" && -f "$DEFAULT_AUTH" ]]; then
    DEFAULT_ACCOUNT_HOME=$(dirname "$(realpath "$DEFAULT_AUTH")")
    if [[ "$DEFAULT_ACCOUNT_HOME" == "$SELECTED_CODEX_HOME" ]]; then
      ROUTE_MODE="default"
    fi
  fi
fi

DEFAULT_AUTH="$HOME/.codex/auth.json"
if (( QUIET == 0 )); then
  case "$ROUTE_MODE" in
    forced)
      printf '🚀 Using account %s (forced):\n   %s\n' "$SELECTED_ID" "$SELECTED_CODEX_HOME"
      ;;
    default)
      printf '🚀 Using default account %s:\n   %s\n' "$SELECTED_ID" "$SELECTED_CODEX_HOME"
      ;;
    resume)
      printf '🚀 Using account for session %s:\n   %s\n' "${CODEX_ARGS[1]}" "$SELECTED_CODEX_HOME"
      ;;
    *)
      printf '🚀 Using account (round-robin): %s:\n   %s\n' "$SELECTED_ID" "$SELECTED_CODEX_HOME"
      ;;
  esac
fi

if (( VERBOSE == 1 )); then
  printf '🔎 route_mode=%s account_id=%s\n' "$ROUTE_MODE" "$SELECTED_ID" >&2
fi

exec codex "${CODEX_ARGS[@]}"
