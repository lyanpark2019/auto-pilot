#!/usr/bin/env bash
# PreToolUse(Write|Edit|MultiEdit): block secret-bearing file edits.
set -euo pipefail
input="$(cat)"
file="$(jq -r '.tool_input.file_path // .tool_input.path // empty' <<< "$input")"

block() { echo "BLOCKED: $1" >&2; exit 2; }

base="$(basename "$file")"
case "$base" in
  .env|.env.local|.env.production|.env.staging|.env.development)
    block ".env editing forbidden (secrets). Use .env.example for templates." ;;
  .envrc|.netrc|credentials|credentials.json|service-account*.json|*.pem|*.key|id_rsa|id_ed25519|id_ecdsa)
    block "secret-bearing file ($base) edit forbidden" ;;
esac

# Path-based
case "$file" in
  */.ssh/*|*/.aws/credentials|*/.aws/config|*/.gnupg/*|*/.docker/config.json|*/.kube/config)
    block "credential path ($file) edit forbidden" ;;
esac

exit 0
