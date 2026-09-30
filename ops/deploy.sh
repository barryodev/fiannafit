#!/usr/bin/env bash
# Ship the latest main to a VM, restart the app and check its health.
# Run from your machine:
#
#   ops/deploy.sh local
#   ops/deploy.sh prod
#
# Target names map to SSH destinations in ops/targets.env (gitignored,
# see ops/targets.env.example). Always deploys main, never another branch.
set -euo pipefail

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGETS_FILE="$OPS_DIR/targets.env"

die() { echo "ERROR: $*" >&2; exit 1; }

[[ $# -eq 1 ]] || die "usage: $0 <target>   (e.g. local, prod)"
[[ -f $TARGETS_FILE ]] || die "$TARGETS_FILE is missing. Copy ops/targets.env.example and fill it in."

# shellcheck source=/dev/null
source "$TARGETS_FILE"
TARGET_VAR="${1^^}"                       # local -> LOCAL
HOST="${!TARGET_VAR:-}"
[[ -n $HOST ]] || die "no target '$1' in $TARGETS_FILE (expected a line like $TARGET_VAR=ubuntu@<ip>)"

echo "==> Deploying main to $1 ($HOST)"

# Everything between the EOFs runs on the VM as root. Paths match provision.sh.
ssh "$HOST" sudo bash -s <<'EOF'
set -euo pipefail
as_app() { sudo -u fiannafit -H "$@"; }
cd /opt/fiannafit

echo "==> Pulling main"
as_app git checkout -q main
as_app git pull -q --ff-only origin main
echo "    now at $(as_app git log -1 --format='%h %s')"

echo "==> Syncing Python environment"
as_app /var/lib/fiannafit/.local/bin/uv sync -q --frozen --no-dev

echo "==> Restarting fiannafit"
systemctl restart fiannafit

echo "==> Health check"
for _ in $(seq 10); do
  # -s without -S: no "connection refused" noise while uvicorn is starting
  if curl -fs http://127.0.0.1:8000/healthz; then
    echo
    echo "==> Deploy OK"
    exit 0
  fi
  sleep 1
done

echo "ERROR: /healthz didn't return 200 within 10 seconds. Recent logs:" >&2
journalctl -u fiannafit -n 30 --no-pager >&2
exit 1
EOF
