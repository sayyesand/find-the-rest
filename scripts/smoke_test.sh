#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${1:-http://127.0.0.1:8000}"
KEY="${FIND_THE_REST_API_KEY:-}"
echo "Health:"
curl -fsS "$BASE_URL/health"; echo
echo "Analyze auth check:"
if [[ -n "$KEY" ]]; then
  curl -fsS -H "X-FindTheRest-Key: $KEY" -H 'Content-Type: application/json' -d '{"url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ","scope":"web"}' "$BASE_URL/v1/analyze" | head -c 800; echo
else
  echo "Set FIND_THE_REST_API_KEY to test protected endpoint."
fi
