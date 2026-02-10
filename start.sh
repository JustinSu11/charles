#!/usr/bin/env bash
# Mac and Linux startup script
set -e

echo ""
echo "=== Charles AI Assistant — Starting ==="

# Start containers
echo "[*] Pulling latest images and starting containers..."
docker compose up -d

# Show status
echo ""
echo "[*] Container status:"
docker compose ps

echo ""
echo "=== Charles is running at http://localhost:3000 ==="
echo "    First visit: create an admin account (first user = admin)."
echo "    Then go to Settings -> Connections to add your API key."
echo "    To stop:  docker compose down"
echo "    Logs:     docker compose logs -f"
echo ""
