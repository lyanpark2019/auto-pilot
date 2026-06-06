---
name: sha-deploy-init
description: Generate SHA-based ci.yml deploy workflow for current project
argument-hint: "[python-pm2 | nextjs-pm2 | nextjs-artifact | static-rsync]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - AskUserQuestion
---

# SHA Deploy Init

Generate a SHA-based CI/CD workflow for the current project.

## Steps

1. **Detect project type** (or use argument if provided):
   - `requirements.txt` + `ecosystem.config.*` → `python-pm2`
   - `package.json` + `next.config.*` → `nextjs-pm2` or `nextjs-artifact`
   - Static HTML / `site/public/` → `static-rsync`

2. **Read the matching template** from `${CLAUDE_PLUGIN_ROOT}/deploy/templates/<type>.yml`

3. **Gather project info**:
   - `gh secret list` → available secrets
   - `ecosystem.config.*` → PM2 app name
   - `git remote get-url origin` → org/repo
   - `.github/workflows/` → existing files to replace
   - Ask: single branch (main) or multi-branch (main + development)?

4. **Replace all placeholders**:

   | Placeholder | Value | Templates |
   |---|---|---|
   | `__PROJECT_NAME__` | repo name (concurrency group) | all |
   | `__APP_DIR_NAME__` | deploy directory on EC2 | all |
   | `__PM2_APP_NAME__` | PM2 process name | PM2 templates |
   | `__ENV_NAME__` | deploy target name (e.g. "sportic-dev") | python-pm2 |
   | `__ENV_LABEL__` | audit trail label (prod/dev) | python-pm2 |
   | `__SOURCE_DIR__` | local build output path | static-rsync |
   | `__QUALITY_STEPS__` | lint/build/test steps | static-rsync |
   | `__SHARED_ENV__` | env vars for quality gates + build | nextjs-artifact |
   | `__BUILD_ENV__` | `env:` block with NEXT_PUBLIC_* build secrets | nextjs-pm2 |
   | `__ENV_SECRETS__` | see below | git-based templates |
   | `__ENV_FILE__` | see below | all PM2 templates |

5. **Generate `__ENV_SECRETS__`** from `gh secret list`:
   - Add each secret as `SECRET_NAME: ${{ secrets.SECRET_NAME }}` to `env:` block
   - Add each secret name to `envs:` parameter (comma-separated)
   - Skip EC2/SSH secrets (already in `with:` block)

6. **Generate `__ENV_FILE__`** block:
   ```bash
   cat > .env <<ENVEOF
   SECRET1=${SECRET1}
   SECRET2=${SECRET2}
   ENVEOF
   sed -i 's/^[[:space:]]*//' .env
   ```
   The `sed` command is required to strip YAML indentation from heredoc content.

7. **Write** to `.github/workflows/ci.yml`. Ask to delete old `deploy-*.yml` files.

8. **Validate**: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`

9. **Ask** to commit and push.

## Rules

- Never use `${{ }}` inside `run:` script blocks
- Always use `envs:` parameter for appleboy/ssh-action
- Always include GH_TOKEN cleanup trap for git-based deploys
- Always include audit trail
- Always include git hint suppression (`git config --global`)
- Git URL format: `https://x-access-token:${GH_TOKEN}@github.com/${REPO_PATH}.git`
