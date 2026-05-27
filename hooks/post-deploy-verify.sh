#!/usr/bin/env bash
# auto-pilot post-deploy smoke test trigger.
# Fires after every Bash command. Only does real work if the command looks like a deploy.
# Non-blocking — prints warnings, exits 0.
#
# Fires from /insights friction class: zombie process on port 8000, SSL outages,
# hardcoded 'private' env var escaping to prod.

set -uo pipefail

input=$(cat 2>/dev/null || echo "{}")
cmd=$(echo "$input" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.stderr.write("auto-pilot: WARNING malformed tool_input json — hook skipped\n")
    sys.exit(0)
print(d.get("tool_input", {}).get("command", ""))
')

[[ -z "$cmd" ]] && exit 0

# Only run if command looks like a deploy
is_deploy=0
case "$cmd" in
  *"git push"*|*"vercel deploy"*|*"vercel --prod"*|*"fly deploy"*|*"docker push"*|*"systemctl restart"*|*"pm2 reload"*|*"pm2 restart"*)
    is_deploy=1
    ;;
esac

[[ "$is_deploy" -eq 0 ]] && exit 0

echo "auto-pilot: detected deploy-class command — running post-deploy checks" >&2

# Check 1: zombie process on common ports
for port in 8000 3000 5000 8080; do
  pids=$(lsof -ti tcp:$port 2>/dev/null | tr '\n' ' ')
  count=$(echo "$pids" | wc -w | tr -d ' ')
  if [[ "$count" -gt 1 ]]; then
    echo "auto-pilot: WARNING multiple processes on :$port — possible zombie: $pids" >&2
  fi
done

# Check 2: .env contains literal 'private' / 'test' / 'placeholder' (hardcoded test value leak)
for env_file in .env .env.production .env.prod; do
  if [[ -f "$env_file" ]]; then
    if grep -qE '^[A-Z_]+=.*(private|placeholder|REPLACE_ME|TODO|xxx|test_)' "$env_file" 2>/dev/null; then
      echo "auto-pilot: WARNING $env_file contains placeholder/test-looking values — verify before relying on prod" >&2
    fi
  fi
done

exit 0
