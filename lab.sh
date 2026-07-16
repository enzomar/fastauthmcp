#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════════════
# FastAuthMCP Authentication Compatibility Lab
# ═══════════════════════════════════════════════════════════════════════════════
#
# Usage:
#   ./lab.sh              Run all scenarios (mock only, no Docker needed)
#   ./lab.sh --docker     Start Docker services + run all scenarios
#   ./lab.sh list         List available scenarios
#   ./lab.sh clean        Stop Docker services and cleanup
#
# ═══════════════════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAB_DIR="$SCRIPT_DIR/fastauthmcp/lab"

MODE="${1:-run}"

case "$MODE" in
  --docker)
    echo "→ Starting Docker services..."
    docker compose -f "$LAB_DIR/docker-compose.yml" up -d

    echo "→ Waiting for services to be healthy..."
    for i in $(seq 1 60); do
      if curl -s -o /dev/null --max-time 1 http://localhost:8080/health/ready 2>/dev/null; then
        echo "  ✓ Keycloak ready"
        break
      fi
      printf "."
      sleep 2
    done
    echo ""

    echo "→ Running lab..."
    python -m fastauthmcp.lab run

    echo ""
    echo "→ Stopping Docker services..."
    docker compose -f "$LAB_DIR/docker-compose.yml" down
    ;;

  run)
    python -m fastauthmcp.lab run
    ;;

  list)
    python -m fastauthmcp.lab list
    ;;

  clean)
    echo "→ Stopping Docker services..."
    docker compose -f "$LAB_DIR/docker-compose.yml" down -v 2>/dev/null || true
    rm -rf reports/
    echo "  ✓ Cleaned"
    ;;

  *)
    echo "Usage: ./lab.sh [run|--docker|list|clean]"
    exit 1
    ;;
esac
