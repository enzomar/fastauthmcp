#!/usr/bin/env bash
# ============================================================
# Record a demo GIF showing the FastAuthMCP auth flow.
#
# Prerequisites:
#   brew install vhs       (https://github.com/charmbracelet/vhs)
#
# Usage:
#   ./scripts/record-demo.sh
#
# This will:
#   1. Set up the recording environment (venv + sample files)
#   2. Record the GIF using VHS
#
# Output:
#   docs/demo.gif
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Check for vhs
if ! command -v vhs &>/dev/null; then
  echo "Error: 'vhs' is required to record the demo GIF."
  echo "Install it with: brew install vhs"
  exit 1
fi

# Set up recording environment
echo "=== Setting up recording environment ==="
"$SCRIPT_DIR/setup-demo-recording.sh"

echo ""
echo "=== Recording demo GIF ==="
cd "$ROOT_DIR"
vhs docs/demo.tape

echo ""
echo "Done! GIF saved to docs/demo.gif"
