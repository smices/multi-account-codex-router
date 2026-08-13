#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
HOME_LAUNCHER="$HOME/codex.sh"
PROJECT_LAUNCHER="$PROJECT_DIR/codex.sh"
SHARED_HOME="$HOME/.codex-router/shared"
FORCE=0

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: ./install.sh [--force]

  --force  Install missing required tools and overwrite managed files after backup.
EOF
}

case "${1:-}" in
  "") ;;
  --force|-f) FORCE=1 ;;
  --help|-h) usage; exit 0 ;;
  *) usage >&2; die "Unknown option: $1" ;;
esac
if (( $# > 1 )); then
  usage >&2
  die "Only one install option is supported."
fi

confirm_install() {
  local prompt="$1" reply
  if (( FORCE == 1 )); then
    return 0
  fi
  if [[ ! -t 0 ]]; then
    return 1
  fi
  read -r -p "$prompt [Y/n] " reply
  [[ -z "$reply" || "$reply" =~ ^[Yy]([Ee][Ss])?$ ]]
}

confirm_overwrite() {
  local prompt="$1" reply
  if (( FORCE == 1 )); then
    return 0
  fi
  if [[ ! -t 0 ]]; then
    return 1
  fi
  read -r -p "$prompt [y/N] " reply
  [[ "$reply" =~ ^[Yy]([Ee][Ss])?$ ]]
}

require_curl() {
  command -v curl >/dev/null 2>&1 || die "curl is required for automatic installation."
}

ensure_codex() {
  if command -v codex >/dev/null 2>&1; then
    return
  fi
  if ! confirm_install "Codex CLI is missing. Install it with the official OpenAI installer"; then
    die "Codex CLI is required. Install it or rerun ./install.sh --force."
  fi
  require_curl
  curl -fsSL https://chatgpt.com/codex/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  hash -r
  command -v codex >/dev/null 2>&1 || die "Codex CLI installation completed but codex is not on PATH."
}

rtk_is_token_killer() {
  command -v rtk >/dev/null 2>&1 && rtk --version >/dev/null 2>&1 && rtk gain >/dev/null 2>&1
}

ensure_rtk() {
  if rtk_is_token_killer; then
    return
  fi
  if command -v rtk >/dev/null 2>&1; then
    die "An incompatible rtk command is installed. Remove it before installing rtk-ai/rtk."
  fi
  if ! confirm_install "RTK Token Killer is missing. Install it from rtk-ai/rtk"; then
    die "RTK Token Killer is required. Install it or rerun ./install.sh --force."
  fi
  require_curl
  curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  hash -r
  rtk_is_token_killer || die "RTK installation failed verification; expected rtk gain to succeed."
}

for required in \
  "$PROJECT_LAUNCHER" \
  "$PROJECT_DIR/_codex.py" \
  "$PROJECT_DIR/presets/sol-luna/AGENTS.md" \
  "$PROJECT_DIR/presets/sol-luna/RTK.md" \
  "$PROJECT_DIR/presets/sol-luna/config.toml" \
  "$PROJECT_DIR/presets/sol-luna/agents/luna-worker.toml" \
  "$PROJECT_DIR/presets/sol-luna/agents/terra-worker.toml" \
  "$PROJECT_DIR/presets/sol-luna/agents/terra-explorer.toml" \
  "$PROJECT_DIR/presets/sol-luna/agents/terra-docs.toml"; do
  [[ -f "$required" ]] || die "Incomplete checkout; missing repository preset component: ${required#$PROJECT_DIR/}"
done

if ! command -v python3 >/dev/null 2>&1; then
  die "Python 3.11+ is required. Install it before running this installer."
fi
if ! python3 -c 'import tomllib' >/dev/null 2>&1; then
  die "Python 3.11+ is required: the standard-library tomllib module is unavailable."
fi

ensure_codex
ensure_rtk

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  python3 -m venv "$VENV_DIR"
fi

PRESET_EXISTS=0
for target in AGENTS.md RTK.md config.toml \
  agents/luna-worker.toml agents/terra-worker.toml \
  agents/terra-explorer.toml agents/terra-docs.toml; do
  if [[ -e "$SHARED_HOME/$target" || -L "$SHARED_HOME/$target" ]]; then
    PRESET_EXISTS=1
    break
  fi
done

PRESET_APPLIED=0
if (( PRESET_EXISTS == 0 )) || confirm_overwrite \
  "Existing shared Codex preset found. Overwrite managed files"; then
  "$VENV_DIR/bin/python" "$PROJECT_DIR/_codex.py" config apply
  PRESET_APPLIED=1
else
  printf 'Skipped shared preset files. Use ./install.sh --force to overwrite them.\n'
fi

if [[ -e "$HOME_LAUNCHER" || -L "$HOME_LAUNCHER" ]]; then
  if [[ -L "$HOME_LAUNCHER" && "$(readlink "$HOME_LAUNCHER")" == "$PROJECT_LAUNCHER" ]]; then
    :
  elif ! confirm_overwrite "Existing launcher found. Replace it"; then
    printf 'Skipped existing launcher. Use ./install.sh --force to replace it.\n'
  else
    BACKUP_PATH="$HOME_LAUNCHER.pre-router-backup.$(date +%Y%m%d%H%M%S)"
    mv "$HOME_LAUNCHER" "$BACKUP_PATH"
    printf 'Existing launcher backed up to: %s\n' "$BACKUP_PATH"
  fi
fi

if [[ ! -e "$HOME_LAUNCHER" && ! -L "$HOME_LAUNCHER" ]]; then
  ln -s "$PROJECT_LAUNCHER" "$HOME_LAUNCHER"
fi

if [[ -L "$HOME_LAUNCHER" && "$(readlink "$HOME_LAUNCHER")" == "$PROJECT_LAUNCHER" ]]; then
  printf 'Installed launcher: %s -> %s\n' "$HOME_LAUNCHER" "$PROJECT_LAUNCHER"
fi
printf 'Python environment: %s\n' "$VENV_DIR"
if (( PRESET_APPLIED == 1 )); then
  printf 'Applied the portable Codex/Sol/Luna/Terra preset.\n'
fi
printf 'Authentication and session files were not modified.\n'
printf 'Next: ~/codex.sh account list\n'
