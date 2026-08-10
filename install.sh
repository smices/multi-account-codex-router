#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
HOME_LAUNCHER="$HOME/codex.sh"
PROJECT_LAUNCHER="$PROJECT_DIR/codex.sh"

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

if [[ ! -f "$PROJECT_LAUNCHER" || ! -f "$PROJECT_DIR/_codex.py" ]]; then
  die "Run this script from a complete multi-account-codex-router checkout."
fi

if ! command -v python3 >/dev/null 2>&1; then
  die "python3 is required to create .venv."
fi

if ! python3 -c 'import tomllib' >/dev/null 2>&1; then
  die "Python 3.11+ is required: the standard-library tomllib module is unavailable."
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  python3 -m venv "$VENV_DIR"
fi

# Apply before changing the user launcher so a failed preset leaves it intact.
"$VENV_DIR/bin/python" "$PROJECT_DIR/_codex.py" config apply

if [[ -e "$HOME_LAUNCHER" || -L "$HOME_LAUNCHER" ]]; then
  if [[ -L "$HOME_LAUNCHER" && "$(readlink "$HOME_LAUNCHER")" == "$PROJECT_LAUNCHER" ]]; then
    :
  else
    BACKUP_PATH="$HOME_LAUNCHER.pre-router-backup.$(date +%Y%m%d%H%M%S)"
    mv "$HOME_LAUNCHER" "$BACKUP_PATH"
    printf 'Existing launcher backed up to: %s\n' "$BACKUP_PATH"
  fi
fi

if [[ ! -L "$HOME_LAUNCHER" ]]; then
  ln -s "$PROJECT_LAUNCHER" "$HOME_LAUNCHER"
fi

printf 'Installed launcher: %s -> %s\n' "$HOME_LAUNCHER" "$PROJECT_LAUNCHER"
printf 'Python environment: %s\n' "$VENV_DIR"
printf 'Applied the portable Sol/Luna preset to the router shared configuration.\n'
printf 'Authentication and session files were not modified.\n'
printf 'Next: ~/codex.sh login list\n'
