#!/usr/bin/env bash
# Serve the app on your tailnet, to try it on a phone from anywhere (Wi-Fi or mobile data).
# Run from your machine, with Tailscale on and signed in on both it and the phone:
#
#   ops/remote-phone-test.sh
#
# The app listens on localhost only. `tailscale serve` puts it behind a real HTTPS
# certificate for this machine's *.ts.net name, so the Secure session cookie works
# without warnings. Only devices signed into your tailnet can reach it: this is serve,
# not funnel, so nothing is opened to the internet. Ctrl+C stops both.
#
# One-time setup (see README): HTTPS certificates enabled in the Tailscale admin console,
# and `sudo tailscale set --operator=$USER` so this script can run serve without sudo.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT=8000

die() { echo "ERROR: $*" >&2; exit 1; }

command -v uv >/dev/null || die "uv isn't installed"
command -v tailscale >/dev/null || die "tailscale isn't installed (see README)"
[[ -f $REPO_DIR/.env ]] || die "$REPO_DIR/.env is missing. Copy .env.example and set SESSION_SECRET_KEY (see README)."
tailscale status >/dev/null 2>&1 || die "Tailscale isn't connected. Run: sudo tailscale up"
if ss -ltn "sport = :$PORT" | grep -q LISTEN; then
  die "port $PORT is already in use. Is the app already running in another terminal?"
fi

echo "==> Sharing localhost:$PORT on your tailnet"
tailscale serve --bg "127.0.0.1:$PORT" >/dev/null ||
  die "tailscale serve failed. If it said 'access denied', run once: sudo tailscale set --operator=\$USER"

# Stop sharing however the script ends, so the tailnet address doesn't outlive the app
stop_sharing() {
  echo "==> Stopped sharing on your tailnet"
  tailscale serve --https=443 off >/dev/null 2>&1 || true
}
trap stop_sharing EXIT

URL="$(tailscale serve status | awk '/^https:\/\//{print $1; exit}')"
cat <<EOF
==> On your phone, with Tailscale switched on, open:  $URL
    For a long session away, run stay-awake in another terminal so the machine doesn't sleep.
    Ctrl+C stops the server and the sharing.
EOF

cd "$REPO_DIR"
uv run --env-file .env uvicorn fiannafit.main:app --reload --host 127.0.0.1 --port "$PORT"
