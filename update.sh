#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "Run update from a Git checkout."
[[ -z "$(git -C "$PROJECT_DIR" status --porcelain --untracked-files=all)" ]] || die "Working tree has changes; preserve or commit them before updating."
[[ "$(git -C "$PROJECT_DIR" symbolic-ref -q --short HEAD || true)" ]] || die "Cannot update from a detached HEAD."
git -C "$PROJECT_DIR" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' >/dev/null 2>&1 || die "Current branch has no upstream configured."

git -C "$PROJECT_DIR" pull --ff-only || die "Update failed; no merge or reset was performed."
bash "$PROJECT_DIR/install.sh" --force || die "Updated installer failed."
bash "$PROJECT_DIR/codex.sh" config status || die "Updated config status check failed."
printf 'Updated to %s.\n' "$(git -C "$PROJECT_DIR" rev-parse --short HEAD)"
