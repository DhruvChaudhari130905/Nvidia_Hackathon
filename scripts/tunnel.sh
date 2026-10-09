#!/usr/bin/env bash
# Public https addresses for the local web app (:3000) and API (:8000), so teammates on other computers
# can open a room link. Uses Cloudflare quick tunnels (no account); the addresses change on every run.
# Run `make server` and `make web` first, then this, then restart the two as it prints.
set -euo pipefail

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared isn't installed. On macOS: brew install cloudflared" >&2
  exit 1
fi

logs=$(mktemp -d)
pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null || true; rm -rf "$logs"; }
trap cleanup EXIT INT TERM

start_tunnel() { # port name
  cloudflared tunnel --no-autoupdate --url "http://localhost:$1" >"$logs/$2.log" 2>&1 &
  pids+=($!)
}

wait_for_url() { # name
  for _ in $(seq 1 60); do
    url=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$logs/$1.log" | head -1 || true)
    if [ -n "$url" ]; then echo "$url"; return 0; fi
    sleep 0.5
  done
  echo "Timed out waiting for the $1 tunnel; its log:" >&2
  cat "$logs/$1.log" >&2
  return 1
}

start_tunnel 8000 api
start_tunnel 3000 web
api_url=$(wait_for_url api)
web_url=$(wait_for_url web)

cat <<EOF

  Web app: $web_url
  API:     $api_url

  1. Restart the API (Ctrl+C in its terminal) so invite emails link to the public address:
       WEB_APP_URL=$web_url make server

  2. Restart the web app so browsers call the public API:
       NEXT_PUBLIC_API_URL=$api_url make web

  3. Supabase dashboard > Authentication > URL Configuration > Redirect URLs, add (once):
       https://*.trycloudflare.com/**

  Then open $web_url yourself, sign in, and share room links from there.
  Keep this running; Ctrl+C closes both tunnels.

EOF

wait
