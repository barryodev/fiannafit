#!/usr/bin/env bash
# Server setup for Fianna Fit. Safe to re-run: every step checks before it
# changes anything. Run on the VM as root, from a copy of the ops/ folder
# (see ops/README.md, step D2):
#
#   sudo ./fiannafit-ops/provision.sh
#
# Config files are installed from this script's own folder, not from the
# repo clone, so local ops/ changes can be tested before they're merged.
set -euo pipefail

APP_USER=fiannafit
APP_HOME=/var/lib/fiannafit     # home dir: uv and its Python live under here
APP_DIR=/opt/fiannafit          # clone of the repo
REPO_URL=https://github.com/barryodev/fiannafit.git
ENV_FILE=/etc/fiannafit/env
UV_VERSION=0.12.20              # keep in step with the uv used for development
UV="$APP_HOME/.local/bin/uv"

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { echo "==> $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }
as_app() { sudo -u "$APP_USER" -H "$@"; }

[[ $EUID -eq 0 ]] || die "run as root: sudo $0"

# --- Secrets: check only, never create or change ---------------------------
log "Checking $ENV_FILE"
if [[ ! -f $ENV_FILE ]]; then
  die "$ENV_FILE is missing. Create it by hand first (ops/README.md, step D1)."
fi
if [[ $(stat -c '%U %a' "$ENV_FILE") != "root 600" ]]; then
  die "$ENV_FILE must be owned by root with mode 600. Fix with:
  sudo chown root:root $ENV_FILE && sudo chmod 600 $ENV_FILE"
fi

# --- System packages --------------------------------------------------------
log "Applying system updates and installing base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -y -q -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold
apt-get install -y -q git curl

# --- App user ---------------------------------------------------------------
if id "$APP_USER" &>/dev/null; then
  log "User $APP_USER exists"
else
  log "Creating system user $APP_USER"
  useradd --system --create-home --home-dir "$APP_HOME" --shell /usr/sbin/nologin "$APP_USER"
fi

# --- uv ---------------------------------------------------------------------
if [[ -x $UV ]] && [[ $(as_app "$UV" --version) == "uv $UV_VERSION"* ]]; then
  log "uv $UV_VERSION already installed"
else
  log "Installing uv $UV_VERSION for $APP_USER"
  as_app env UV_NO_MODIFY_PATH=1 sh -c "curl -LsSf https://astral.sh/uv/$UV_VERSION/install.sh | sh"
fi

# --- Repo -------------------------------------------------------------------
if [[ -d $APP_DIR/.git ]]; then
  log "Updating $APP_DIR"
  as_app git -C "$APP_DIR" pull --ff-only
else
  log "Cloning $REPO_URL to $APP_DIR"
  install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
  as_app git clone "$REPO_URL" "$APP_DIR"
fi

log "Syncing Python environment"
(cd "$APP_DIR" && as_app "$UV" sync --frozen --no-dev)

# --- systemd service --------------------------------------------------------
log "Installing fiannafit.service"
install -m 0644 "$OPS_DIR/fiannafit.service" /etc/systemd/system/fiannafit.service
systemctl daemon-reload
systemctl enable fiannafit

log "Done. Start or restart the app with deploy.sh (or: sudo systemctl restart fiannafit)"
