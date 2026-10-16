#!/usr/bin/env bash
# Stop the local Story Engine stack.
#   scripts/local-down.sh            stop and remove containers; keep data volumes and images
#   scripts/local-down.sh --destroy  also delete the data volumes (postgres, redis, langfuse)
#                                    and the images this compose file built
set -euo pipefail
cd "$(dirname "$0")/.."

# Include the optional profile so its containers stop too if they were started.
if [[ "${1:-}" == "--destroy" ]]; then
  docker compose --profile langfuse down --volumes --rmi local --remove-orphans
  echo "Destroyed: containers, volumes and locally built images."
elif [[ -z "${1:-}" ]]; then
  docker compose --profile langfuse down --remove-orphans
  echo "Stopped. Data volumes kept; start again with scripts/local-up.sh"
else
  echo "usage: $0 [--destroy]" >&2
  exit 2
fi
