#!/usr/bin/env bash
# ============================================================
# Prepare the environment for recording docs/demo.gif with VHS.
#
# This creates a self-contained directory at /tmp/fastauthmcp-recording/
# with a Python venv, sample server, and config file — so the VHS
# recording is deterministic and doesn't depend on network access
# during the actual recording.
#
# Usage:
#   ./scripts/setup-demo-recording.sh
#   vhs docs/demo.tape
# ============================================================
set -euo pipefail

RECORDING_DIR="/tmp/fastauthmcp-recording"
VENV_DIR="$RECORDING_DIR/venv"
PROJECT_DIR="$RECORDING_DIR/project"

echo "Setting up demo recording environment..."

# Clean previous recording env
rm -rf "$RECORDING_DIR"
mkdir -p "$PROJECT_DIR"

# Create venv with Python 3.11+
PYTHON=""
for py in python3.13 python3.12 python3.11 python3; do
  if command -v "$py" &>/dev/null; then
    version=$("$py" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)
    if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
      PYTHON="$py"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  echo "Error: Python 3.11+ is required. Found none."
  exit 1
fi

echo "Using $PYTHON ($($PYTHON --version))"

$PYTHON -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet fastauthmcp

# Create the demo server.py
cat > "$PROJECT_DIR/server.py" << 'PYEOF'
from fastauthmcp import FastMCP, identity, access_token
import httpx

mcp = FastMCP("enterprise-tools", config="fastauthmcp.yaml")

@mcp.tool()
def whoami() -> dict:
    """Show the authenticated user."""
    user = identity()
    return {"email": user.email, "roles": sorted(user.roles)}

@mcp.tool()
def get_orders() -> list:
    """Fetch orders from the enterprise API."""
    token = access_token()
    resp = httpx.get(
        "https://api.internal.com/v1/orders",
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.json()
PYEOF

# Create the demo config
cat > "$PROJECT_DIR/fastauthmcp.yaml" << 'YAMLEOF'
auth:
  provider: oidc
  issuer: https://ceramic-oss-agq8i8.eu1.zitadel.cloud
  client_id: "380842820363183891"
  scopes:
    - openid
    - profile
    - email
  callback_port: 9876
YAMLEOF

echo ""
echo "Recording environment ready at: $RECORDING_DIR"
echo ""
echo "Next steps:"
echo "  1. Run 'fastauthmcp login' manually first (needs browser)"
echo "     cd $PROJECT_DIR && $VENV_DIR/bin/fastauthmcp login"
echo ""
echo "  2. Record the demo:"
echo "     vhs docs/demo.tape"
echo ""
echo "Note: If you're behind a corporate proxy, set:"
echo "  export SSL_CERT_FILE=/tmp/combined-ca.pem"
echo "  (extract with: security find-certificate -a -p /Library/Keychains/System.keychain > /tmp/combined-ca.pem)"
