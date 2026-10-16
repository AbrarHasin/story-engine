#!/usr/bin/env bash
# Start the local Story Engine stack in Docker: postgres, redis, backend (:8080),
# frontend (:5173) and Langfuse (:3000, localhost only). Builds images, runs
# migrations (backend start), waits for /health and Langfuse.
# backend/.env doubles as the compose env file: Langfuse's first boot creates
# its project keys and login from LANGFUSE_* values there.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f backend/.env ]]; then
  echo "backend/.env is missing (copy backend/.env.example and fill it in)" >&2
  exit 1
fi

docker compose --env-file backend/.env up -d --build

echo -n "waiting for backend /health "
for _ in $(seq 1 90); do
  if curl -fsS --max-time 3 http://localhost:8080/health >/dev/null 2>&1; then
    echo " ok"
    curl -sS --max-time 3 http://localhost:8080/health; echo
    break
  fi
  echo -n "."; sleep 2
done
curl -fsS --max-time 3 http://localhost:8080/health >/dev/null || {
  echo; echo "backend did not become healthy; logs:" >&2
  docker compose logs --tail 50 backend >&2
  exit 1
}

echo -n "waiting for frontend "
for _ in $(seq 1 60); do
  if curl -fsS --max-time 3 -o /dev/null http://localhost:5173/; then echo " ok"; break; fi
  echo -n "."; sleep 2
done
curl -fsS --max-time 3 -o /dev/null http://localhost:5173/ || {
  echo; docker compose logs --tail 50 frontend >&2; exit 1
}

echo -n "waiting for langfuse "
for _ in $(seq 1 90); do
  if curl -fs --max-time 3 -o /dev/null http://localhost:3000/api/public/health; then echo " ok"; break; fi
  echo -n "."; sleep 2
done
curl -fsS --max-time 3 -o /dev/null http://localhost:3000/api/public/health || {
  echo; echo "langfuse did not come up (the app still works, without traces); logs:" >&2
  docker compose logs --tail 30 langfuse >&2
}

echo "Frontend: http://localhost:5173   Backend: http://localhost:8080   Docs: http://localhost:8080/docs"
echo "Langfuse: http://localhost:3000 (login: LANGFUSE_INIT_USER_EMAIL / _PASSWORD in backend/.env)"
