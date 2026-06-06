#!/usr/bin/env bash

atomic_write_json() (
  set -euo pipefail

  if [ "$#" -ne 1 ]; then
    echo "usage: atomic_write_json <target_path>" >&2
    exit 2
  fi

  local target_path="$1"
  local target_dir tmp
  target_dir="$(dirname "$target_path")"
  tmp="${target_path}.tmp.$$.${RANDOM}"

  cleanup() {
    rm -f "$tmp"
  }
  trap cleanup EXIT

  [ -d "$target_dir" ] || {
    echo "atomic_write_json: missing target directory: $target_dir" >&2
    exit 1
  }

  if ! ( set -C; : > "$tmp" ) 2>/dev/null; then
    echo "atomic_write_json: could not create tmp file: $tmp" >&2
    exit 1
  fi

  chmod 600 "$tmp" || exit 1
  cat > "$tmp" || exit 1
  jq -e . "$tmp" >/dev/null || exit 1
  mv -f "$tmp" "$target_path" || exit 1
  trap - EXIT
)
