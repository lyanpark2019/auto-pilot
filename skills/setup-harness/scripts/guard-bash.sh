#!/usr/bin/env bash
# PreToolUse(Bash): block destructive commands + hook-bypass attempts.
# Exit code 2 + stderr is fed back to Claude as actionable feedback.
set -euo pipefail
input="$(cat)"
cmd="$(jq -r '.tool_input.command // empty' <<< "$input")"

block() { echo "BLOCKED: $1" >&2; exit 2; }

# 1. Destructive filesystem
echo "$cmd" | grep -qE 'rm -rf +(/|~|\$HOME|/\*)' && block "rm -rf on root/home/glob — too broad"

# 2. Hook bypass
echo "$cmd" | grep -qE 'git commit[^|]*--no-verify' && block "git commit --no-verify forbidden — fix the linter error"
echo "$cmd" | grep -qE -- '--dangerously-skip-permissions' && block "--dangerously-skip-permissions disables safety hooks"
echo "$cmd" | grep -qE 'git +-c +commit\.gpgsign=false' && block "do not bypass gpg signing"

# 3. Destructive git
echo "$cmd" | grep -qE 'git +(branch +-D|reset +--hard|clean +-fd?)' && block "destructive git — run manually with user confirmation"

# 4. Force-push to protected branches
echo "$cmd" | grep -qE 'git +push.*--force.*origin +(main|master|production|prod|release)' && block "force-push to protected branch"
echo "$cmd" | grep -qE 'git +push.*-f .*origin +(main|master|production|prod|release)' && block "force-push to protected branch"

# 5. Pipe network content to shell
echo "$cmd" | grep -qE '(curl|wget)[^|]*\| *(bash|sh|zsh|fish)' && block "piping network content to shell — verify and run manually"

# 6. git add -A / .
echo "$cmd" | grep -qE 'git +add +(-A|\.|\-\-all|:/)([^a-zA-Z0-9]|$)' && block "git add -A/. forbidden — use explicit filenames to avoid committing secrets"

# 7. sudo escalation in agent context
echo "$cmd" | grep -qE '^sudo |^doas |^pkexec ' && block "sudo/doas/pkexec forbidden in agent context"

# 8. eval / source from untrusted location
echo "$cmd" | grep -qE 'eval +"\$\(curl|eval +"\$\(wget' && block "eval-from-network forbidden"

# 9. SSH key write
echo "$cmd" | grep -qE '> +~/\.ssh/|> +\$HOME/\.ssh/' && block "writing to ~/.ssh/ forbidden"

exit 0
