#!/usr/bin/env bash
# Install the xmodel-review workflow into the global Archon workflow dir so `xreview.sh`
# can run it from any repo (project-scope discovery would otherwise require a local copy).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.archon/workflows"
mkdir -p "$DEST"
cp "$HERE/xmodel-review.yaml" "$DEST/xmodel-review.yaml"
echo "installed xmodel-review.yaml -> $DEST/xmodel-review.yaml"
