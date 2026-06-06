---
name: sha-deploy-standard
description: Use when setting up CI/CD pipelines, creating GitHub Actions workflows, configuring deployment automation, adding SHA-based deploys, or applying deploy standards to projects. Triggers on phrases like "SHA deploy", "ci.yml", "deploy workflow", "GitHub Actions deploy", "rollback", "deploy standard".
---

# SHA Deploy Standard

Apply the SHA-based deploy standard to any project. This standard enables targeted deploys and instant rollbacks via commit SHA.

## Core Principles

1. **Single ci.yml** per project — no separate deploy-dev.yml files
2. **SHA targeting** — `workflow_dispatch` with `target_sha` input for specific commit deploys
3. **Branch routing** — quality gates shared, deploy jobs branch-conditional
4. **Secrets safety** — use `envs:` parameter in appleboy/ssh-action, never inline `${{ }}` in scripts
5. **Auto .env** — generate `.env` on server from GitHub secrets during deploy
6. **Audit trail** — `.deploy/last_good_commit` + `.deploy/deploy.log` on every deploy
7. **GH_TOKEN cleanup** — `trap cleanup_remote EXIT` to remove token from git remote

## Workflow Structure

Every ci.yml follows this pattern:

```yaml
name: CI

on:
  push:
    branches: [main]          # add development if needed
  pull_request:
    branches: [main]          # add development if needed
  workflow_dispatch:
    inputs:
      target_sha:
        description: "Deploy commit SHA (leave empty for branch HEAD)"
        required: false
        default: ""

concurrency:
  group: <project-name>-${{ github.ref }}
  cancel-in-progress: true

env:
  DEPLOY_SHA: ${{ github.event.inputs.target_sha || github.sha }}
```

## Deploy Types

Templates live at `${CLAUDE_PLUGIN_ROOT}/deploy/templates/` (use `/auto-pilot:sha-deploy-init` to apply one):

| Template | Type | Build | Branch | Use For |
|----------|------|-------|--------|---------|
| `deploy/templates/python-pm2.yml` | git + PM2 | server | single | Python apps |
| `deploy/templates/nextjs-pm2.yml` | git + PM2 | server | single | Next.js (build on EC2) |
| `deploy/templates/nextjs-artifact.yml` | artifact + PM2 | CI | multi | Next.js (CI build + SCP) |
| `deploy/templates/static-rsync.yml` | rsync | N/A | single | Static sites, SSG |

All templates include: SHA targeting, concurrency, DEPLOY_SHA env, audit trail.
Git-based templates include: GH_TOKEN cleanup trap, git hint suppression.
PM2 templates include: restart-or-start pattern with `pm2 save`.

## Security Rules

1. **Never use `${{ }}` in `run:` blocks** — use shell variables instead
2. **Pass secrets via `envs:` parameter** in appleboy/ssh-action
3. **GH_TOKEN cleanup trap** — always remove token from git remote on exit
4. **No inline secrets in SSH commands** — pass via env vars

```yaml
# CORRECT: envs parameter
- uses: appleboy/ssh-action@v1.1.0
  env:
    GH_TOKEN: ${{ secrets.GH_TOKEN }}
    TARGET_SHA: ${{ env.DEPLOY_SHA }}
  with:
    envs: GH_TOKEN,TARGET_SHA
    script: |
      echo "$TARGET_SHA"    # shell var, safe

# WRONG: inline expression in script
    script: |
      echo "${{ env.DEPLOY_SHA }}"   # injection risk
```

## Git Operations Pattern

```bash
# Suppress git hints
git config --global init.defaultBranch main
git config --global advice.detachedHead false

# Clone or fetch
if [ -d "$APP_DIR/.git" ]; then
  cd "$APP_DIR"
  git remote set-url origin "$REPO_URL"
  git fetch origin main
else
  git clone --branch main --single-branch "$REPO_URL" "$APP_DIR"
  cd "$APP_DIR"
fi

git checkout -B main origin/main
git checkout "$TARGET_SHA"
```

## GH_TOKEN Cleanup Trap

```bash
REPO_URL="https://x-access-token:${GH_TOKEN}@github.com/${REPO_PATH}.git"
CLEAN_REPO_URL="https://github.com/${REPO_PATH}.git"

cleanup_remote() {
  if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" remote set-url origin "$CLEAN_REPO_URL" || true
  fi
}
trap 'cleanup_remote' EXIT
```

## Auto .env Generation

```bash
# Write .env from CI secrets (passed via envs:)
cat > .env <<ENVEOF
KEY1=${KEY1}
KEY2=${KEY2}
ENVEOF
```

For heredoc inside YAML (indentation issue):
```bash
cat > .env <<ENVEOF
KEY1=${KEY1}
KEY2=${KEY2}
ENVEOF
sed -i 's/^[[:space:]]*//' .env
```

## Audit Trail

```bash
DEPLOY_DIR="$APP_DIR/.deploy"
mkdir -p "$DEPLOY_DIR"
echo "$TARGET_SHA" > "$DEPLOY_DIR/last_good_commit"
echo "$(date -u +%Y-%m-%dT%H:%M:%S%z) | ci | ${TARGET_SHA:0:7} | prod | main | SUCCESS" >> "$DEPLOY_DIR/deploy.log"
```

## PM2 Management

```bash
PM2_APP="app-name"
if pm2 describe "$PM2_APP" >/dev/null 2>&1; then
  pm2 restart "$PM2_APP" --update-env
else
  pm2 start ecosystem.config.js
fi
pm2 save
```

## Multi-Branch Routing

For projects with separate prod/dev deployments:

```yaml
jobs:
  quality:
    # Shared quality gates (lint, test, type-check)
    # Runs on all branches and PRs

  deploy-prod:
    needs: quality
    if: github.ref == 'refs/heads/main' && github.event_name != 'pull_request'
    # Production deploy

  deploy-dev:
    needs: quality
    if: github.ref == 'refs/heads/development' && github.event_name != 'pull_request'
    # Dev deploy
```

## SHA Rollback

To rollback to a specific commit:
1. Go to GitHub Actions → CI workflow
2. Click "Run workflow"
3. Enter the target SHA in `target_sha` field
4. The deploy will checkout and deploy that exact commit

## Checklist

When applying SHA standard to a project:
- [ ] Check `gh secret list` for available secrets
- [ ] Determine deploy type (git/artifact/rsync)
- [ ] Determine branch strategy (single/multi)
- [ ] Create ci.yml with SHA standard
- [ ] Delete old deploy-*.yml files
- [ ] Verify YAML syntax
- [ ] Commit, push, verify CI run
- [ ] Check deploy logs for errors
