#!/usr/bin/env bash
set -euo pipefail

# Ceramic Web UI Demo
# Starts the Chat UI + MCP server and opens the browser automatically.
#
# Usage:
#   ./scripts/demo-web.sh

source "$(dirname "$0")/_setup.sh"

exec python demo.py
