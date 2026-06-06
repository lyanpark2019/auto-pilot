#!/usr/bin/env bash
set -euo pipefail

if ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  :
else
  ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi

trim() {
  printf '%s' "$1" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'
}

scalar_value() {
  local v first last
  v="$(trim "$1")"
  v="${v%$'\r'}"
  if [ "${#v}" -ge 2 ]; then
    first="${v:0:1}"
    last="${v: -1}"
    if { [ "$first" = '"' ] && [ "$last" = '"' ]; } || { [ "$first" = "'" ] && [ "$last" = "'" ]; }; then
      v="$(trim "${v:1:${#v}-2}")"
    fi
  fi
  printf '%s' "$v"
}

abs_path() {
  local path dir base
  path="$1"
  dir="$(dirname "$path")"
  base="$(basename "$path")"
  if [ -d "$dir" ]; then
    printf '%s/%s' "$(cd "$dir" && pwd)" "$base"
  else
    printf '%s' "$path"
  fi
}

rel_path() {
  local path
  path="$1"
  case "$path" in
    "$ROOT"/*) printf '%s' "${path#"$ROOT"/}" ;;
    *) printf '%s' "$path" ;;
  esac
}

frontmatter() {
  awk '
    NR == 1 && $0 != "---" { exit 42 }
    NR == 1 { next }
    $0 == "---" { found = 1; exit 0 }
    { print }
    END { if (NR == 0 || found != 1) exit 42 }
  ' "$1"
}

key_value() {
  local key
  key="$1"
  awk -v key="$key" '
    $0 ~ "^[[:space:]]*" key "[[:space:]]*:" {
      sub("^[[:space:]]*" key "[[:space:]]*:[[:space:]]*", "", $0)
      print
      exit
    }
  '
}

fail_file() {
  printf 'FAIL %s: %s\n' "$1" "$2"
  return 1
}

lint_file() {
  local file rel expected fm name description
  file="$(abs_path "$1")"
  rel="$(rel_path "$file")"
  expected="$(basename "$(dirname "$file")")"

  if ! fm="$(frontmatter "$file" 2>/dev/null)"; then
    fail_file "$rel" "missing-frontmatter"
    return 1
  fi

  name="$(scalar_value "$(printf '%s\n' "$fm" | key_value name)")"
  if [ -z "$name" ]; then
    fail_file "$rel" "missing-name"
    return 1
  fi
  if [ "${#name}" -gt 64 ] || ! [[ "$name" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
    fail_file "$rel" "name-invalid"
    return 1
  fi
  if [ "$name" != "$expected" ]; then
    fail_file "$rel" "name-mismatch"
    return 1
  fi

  description="$(scalar_value "$(printf '%s\n' "$fm" | key_value description)")"
  if [ -z "$description" ]; then
    fail_file "$rel" "missing-description"
    return 1
  fi
  if [ "${#description}" -lt 20 ]; then
    fail_file "$rel" "description-too-short"
    return 1
  fi
  if [ "${#description}" -gt 1024 ]; then
    fail_file "$rel" "description-too-long"
    return 1
  fi

  printf 'OK  %s\n' "$rel"
}

FILES=()
if [ "$#" -gt 0 ]; then
  FILES+=("$1")
elif [ -d "$ROOT/skills" ]; then
  while IFS= read -r file; do
    FILES+=("$file")
  done < <(find "$ROOT/skills" -mindepth 2 -maxdepth 2 -type f -name SKILL.md | sort)
fi

if [ "${#FILES[@]}" -eq 0 ]; then
  exit 1
fi

FAILED=0
for file in "${FILES[@]}"; do
  if ! lint_file "$file"; then
    FAILED=1
  fi
done

exit "$FAILED"
