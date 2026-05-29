#!/usr/bin/env bash
# UserPromptSubmit: block pasted live credentials before reaching the model.
# Patterns from Trail of Bits + Lasso Security + AWS/GitHub/Anthropic/OpenAI/Stripe/Slack public formats.
set -euo pipefail
input="$(cat)"
prompt="$(jq -r '.prompt // empty' <<< "$input")"
[ -z "$prompt" ] && exit 0

block() {
  echo "BLOCKED: live credential pattern detected ($1). Rotate immediately. Use env vars or secret manager." >&2
  exit 2
}

# AWS access key
echo "$prompt" | grep -qE 'AKIA[0-9A-Z]{16}' && block "AWS access key"
# AWS secret (40 char base64-ish following an AWS context word)
echo "$prompt" | grep -qE '(aws_secret_access_key|AWS_SECRET).{0,5}[A-Za-z0-9/+=]{40}' && block "AWS secret"
# GitHub PAT (classic + fine-grained)
echo "$prompt" | grep -qE 'gh[pousr]_[A-Za-z0-9]{36,255}' && block "GitHub token"
# Anthropic
echo "$prompt" | grep -qE 'sk-ant-[A-Za-z0-9_-]{40,}' && block "Anthropic API key"
# OpenAI (project + classic)
echo "$prompt" | grep -qE 'sk-(proj-)?[A-Za-z0-9_-]{40,}' && block "OpenAI API key"
# Stripe live
echo "$prompt" | grep -qE '(rk|sk)_live_[A-Za-z0-9]{20,}' && block "Stripe live key"
# Slack
echo "$prompt" | grep -qE 'xox[bpsare]-[A-Za-z0-9-]{10,}' && block "Slack token"
# Google API key
echo "$prompt" | grep -qE 'AIza[0-9A-Za-z_-]{35}' && block "Google API key"
# PEM private key
echo "$prompt" | grep -qE -- '-----BEGIN ([A-Z ]+ )?PRIVATE KEY-----' && block "PEM private key"
# SSH private key inline
echo "$prompt" | grep -qE 'ssh-(rsa|ed25519|ecdsa) [A-Za-z0-9+/=]{100,}' && block "SSH key"
# BIP39 12-24 word mnemonic (rough heuristic: 12+ lowercase words)
echo "$prompt" | grep -qE '^([a-z]{3,8} ){11,23}[a-z]{3,8}$' && block "possible BIP39 mnemonic"

exit 0
