#!/usr/bin/env bash
# ============================================================
# Record a demo GIF showing the Ceramic auth flow.
#
# Prerequisites:
#   brew install vhs       (https://github.com/charmbracelet/vhs)
#
# Usage:
#   ./scripts/record-demo.sh
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
  echo ""
  echo "Alternatively, you can use any terminal recorder and save output to docs/demo.gif"
  exit 1
fi

# Create the VHS tape file
cat > "$ROOT_DIR/docs/demo.tape" << 'EOF'
# Ceramic Demo — ceramic login → tool call
Output docs/demo.gif
Set FontSize 14
Set Width 800
Set Height 500
Set Theme "Catppuccin Mocha"
Set Padding 20
Set TypingSpeed 40ms

Type "# Secure your FastMCP server with Ceramic"
Enter
Sleep 1s

Type "pip install ceramic-fwk"
Enter
Sleep 2s

Type ""
Enter

Type "# One import change — that's it"
Enter
Sleep 500ms

Type 'cat server.py | head -5'
Enter
Sleep 1.5s

Type ""
Enter

Type "# Authenticate with your identity provider"
Enter
Sleep 500ms

Type "ceramic login"
Enter
Sleep 3s

Type ""
Enter

Type "# Check who you are"
Enter
Sleep 500ms

Type "ceramic whoami"
Enter
Sleep 2s

Type ""
Enter

Type "# Run the server — fully authenticated"
Enter
Sleep 500ms

Type "ceramic run"
Enter
Sleep 2s

Type ""
Enter
Sleep 1s

Type "# ✓ Every tool call is now authenticated, authorized, and traced"
Enter
Sleep 3s
EOF

echo "Recording demo GIF..."
cd "$ROOT_DIR"
vhs docs/demo.tape

echo ""
echo "Done! GIF saved to docs/demo.gif"
echo "You can also manually record using any terminal recorder."
