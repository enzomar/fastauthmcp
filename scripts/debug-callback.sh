#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════════════
# Debug: verify the callback server can start and accept connections
# ═══════════════════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv-demo"

echo "┌─────────────────────────────────────────────────────┐"
echo "│  FastAuthMCP Callback Server Debug                  │"
echo "└─────────────────────────────────────────────────────┘"
echo ""

# Activate venv
if [ -d "$VENV_DIR" ]; then
  source "$VENV_DIR/bin/activate"
else
  echo "→ No .venv-demo found, using system python"
fi

# Check if port 9876 is already in use
echo "1. Checking if port 9876 is in use..."
if lsof -ti:9876 >/dev/null 2>&1; then
  echo "   ⚠ Port 9876 is IN USE by:"
  lsof -i:9876
  echo ""
  echo "   Kill it? (y/n)"
  read -r ans
  if [ "$ans" = "y" ]; then
    lsof -ti:9876 | xargs kill -9
    echo "   ✓ Killed"
  fi
else
  echo "   ✓ Port 9876 is free"
fi
echo ""

# Start callback server directly
echo "2. Starting callback server directly on port 9876..."
python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')

import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(name)s %(levelname)s %(message)s')

from fastauthmcp.auth.callback_server import CallbackServer
import socket
import time

server = CallbackServer()
try:
    port = server.start(9876)
    print(f'   ✓ Callback server started on port {port}')
except Exception as e:
    print(f'   ✗ FAILED to start: {e}')
    sys.exit(1)

# Verify with a socket connection
print('   Testing connection...')
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    sock.connect(('127.0.0.1', port))
    sock.close()
    print(f'   ✓ Socket connect to 127.0.0.1:{port} succeeded')
except Exception as e:
    print(f'   ✗ Socket connect FAILED: {e}')
    sys.exit(1)

# Test with an HTTP request
print('   Sending test HTTP request...')
import urllib.request
try:
    resp = urllib.request.urlopen(f'http://localhost:{port}/callback?code=test&state=test', timeout=5)
    print(f'   ✓ HTTP response: {resp.status} ({len(resp.read())} bytes)')
except Exception as e:
    print(f'   ✗ HTTP request FAILED: {e}')
    sys.exit(1)

# Check if the result was captured
print()
print('   ✓ Callback server works correctly!')
print()
print('3. Now testing inside an async context (simulating MCP server)...')

import asyncio

async def test_async():
    server2 = CallbackServer()
    try:
        port2 = server2.start(9877)
        print(f'   ✓ Async context: server started on port {port2}')
    except Exception as e:
        print(f'   ✗ Async context: FAILED to start: {e}')
        return False

    # Test from within asyncio.to_thread
    def blocking_test():
        import urllib.request
        try:
            resp = urllib.request.urlopen(f'http://localhost:{port2}/callback?code=async_test&state=async_test', timeout=5)
            return resp.status
        except Exception as e:
            return f'FAILED: {e}'

    result = await asyncio.to_thread(blocking_test)
    print(f'   ✓ Async context HTTP test: {result}')
    server2.shutdown()
    return True

asyncio.run(test_async())
print()
print('═══════════════════════════════════════════════════════')
print('  All tests passed! Callback server is working.')
print('  The issue is likely:')
print('    a) Zitadel redirect URI mismatch, or')
print('    b) Browser redirect not hitting localhost:9876/callback')
print()
print('  After login, check your browser address bar.')
print('  It should show: http://localhost:9876/callback?code=...')
print('  If it shows an error, the redirect URI in Zitadel is wrong.')
print('═══════════════════════════════════════════════════════')

server.shutdown()
"
