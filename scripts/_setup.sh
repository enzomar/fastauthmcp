#!/usr/bin/env bash
# Shared setup logic for Ceramic demo scripts.
# Sources the virtualenv and installs the package.
# After sourcing this, CWD is examples/zitadel/.
#
# Usage (from another script):
#   source "$(dirname "$0")/_setup.sh"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv-demo"
EXAMPLE_DIR="$PROJECT_ROOT/examples/zitadel"

echo "=== Ceramic Dev Demo ==="
echo "Project root: $PROJECT_ROOT"
echo "Virtualenv:   $VENV_DIR"
echo ""

# Create or reuse virtualenv
if [ ! -d "$VENV_DIR" ]; then
  echo "→ Creating virtualenv at $VENV_DIR..."
  python3 -m venv "$VENV_DIR"
else
  echo "→ Reusing existing virtualenv at $VENV_DIR"
fi

# Activate
source "$VENV_DIR/bin/activate"

# Install ceramic-fwk in editable mode with dev deps
echo "→ Installing ceramic-fwk (editable + dev dependencies)..."
pip install -e "$PROJECT_ROOT[dev]" --quiet

echo "→ Installed: $(pip show ceramic-fwk 2>/dev/null | grep Version || echo 'ceramic-fwk (editable)')"
echo ""

# Change to example directory so ceramic.yaml is picked up
cd "$EXAMPLE_DIR"
