#!/usr/bin/env bash
# Build the sandbox image the agent runs code inside.
set -euo pipefail
cd "$(dirname "$0")/.."
docker build -t autoswe-sandbox:latest -f server/Dockerfile.sandbox server
echo "Built autoswe-sandbox:latest"
