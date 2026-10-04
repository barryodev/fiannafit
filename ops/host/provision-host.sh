#!/usr/bin/env bash
# Host-level setup, shared by every app on the VM: system updates, Caddy and
# its main Caddyfile, the firewall, SSH hardening and unattended upgrades.
# App-specific setup is in ../provision.sh, which needs this to run first.
# Safe to re-run: every step checks before it changes anything. Run on the VM
# as root, from a copy of the ops/ folder (see ops/README.md, step D2):
#
#   sudo ./fiannafit-ops/host/provision-host.sh
#
# This folder holds nothing Fianna Fit specific, so it can move to its own
# host-config repo once a second app arrives.
set -euo pipefail

HOST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CADDY_KEYRING=/usr/share/keyrings/caddy-stable-archive-keyring.gpg
CADDY_LIST=/etc/apt/sources.list.d/caddy-stable.list
SSHD_DROPIN=/etc/ssh/sshd_config.d/01-hardening.conf
OPEN_PORTS=(80 443)             # 22 is already open; Caddy needs 80 and 443

log() { echo "==> $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

# Copy a config file into place. Succeeds only if the file changed, so the
# caller can reload just when needed: `if install_conf src dest; then ...`.
install_conf() {
  cmp -s "$1" "$2" && return 1
  install -m 0644 "$1" "$2"
}

[[ $EUID -eq 0 ]] || die "run as root: sudo $0"

# --- Packages ---------------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive

if [[ ! -f $CADDY_LIST ]]; then
  log "Adding Caddy's apt repository"
  apt-get update -q
  apt-get install -y -q curl gnupg
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
    | gpg --dearmor --yes -o "$CADDY_KEYRING"
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > "$CADDY_LIST"
  chmod o+r "$CADDY_KEYRING" "$CADDY_LIST"
fi

# iptables-persistent asks whether to save the current rules when it's
# installed. Answer yes up front so the install doesn't stop to ask.
debconf-set-selections <<'EOF'
iptables-persistent iptables-persistent/autosave_v4 boolean true
iptables-persistent iptables-persistent/autosave_v6 boolean true
EOF

log "Applying system updates and installing host packages"
apt-get update -q
apt-get upgrade -y -q -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold
apt-get install -y -q caddy iptables iptables-persistent unattended-upgrades

# --- Firewall ---------------------------------------------------------------
# OCI's Ubuntu image ends its INPUT chain with a REJECT, so rules appended
# after it never match. Insert at the top instead, which works with or without
# Oracle's rules (the local VM has none).
fw_changed=false
for port in "${OPEN_PORTS[@]}"; do
  rule=(INPUT -p tcp -m state --state NEW --dport "$port" -j ACCEPT)
  if iptables -C "${rule[@]}" 2>/dev/null; then
    log "iptables: port $port already open"
  else
    log "iptables: opening port $port"
    iptables -I "${rule[@]}"
    fw_changed=true
  fi
done
if $fw_changed; then
  log "Saving iptables rules so they survive a reboot"
  netfilter-persistent save
fi

# --- SSH --------------------------------------------------------------------
if install_conf "$HOST_DIR/sshd-hardening.conf" "$SSHD_DROPIN"; then
  log "Installed SSH hardening, checking it"
  if ! sshd -t; then
    rm -f "$SSHD_DROPIN"
    die "sshd rejected the new config. Removed $SSHD_DROPIN so SSH keeps its old settings."
  fi
  # Existing sessions stay open across a reload. try-: on Ubuntu, sshd may
  # not be running yet (socket activation), and then it reads the new config
  # when it starts.
  systemctl try-reload-or-restart ssh
else
  log "SSH hardening already installed"
fi

# Check the settings sshd actually uses, in case another file overrides ours.
effective=$(sshd -T)
for setting in "pubkeyauthentication yes" "passwordauthentication no" \
               "kbdinteractiveauthentication no" "permitrootlogin no"; do
  grep -qx "$setting" <<<"$effective" \
    || die "sshd isn't using '$setting'. Check the other files in /etc/ssh/sshd_config.d/."
done

# --- Unattended upgrades ----------------------------------------------------
if install_conf "$HOST_DIR/20auto-upgrades" /etc/apt/apt.conf.d/20auto-upgrades; then
  log "Enabled unattended security upgrades"
else
  log "Unattended security upgrades already enabled"
fi

# --- Caddy ------------------------------------------------------------------
install -d -m 0755 /etc/caddy/sites
if ! out=$(caddy validate --adapter caddyfile --config "$HOST_DIR/Caddyfile" 2>&1); then
  echo "$out" >&2
  die "Caddy rejected ops/host/Caddyfile, so it wasn't installed."
fi
if install_conf "$HOST_DIR/Caddyfile" /etc/caddy/Caddyfile; then
  log "Installed the main Caddyfile, reloading Caddy"
  systemctl reload-or-restart caddy
else
  log "Main Caddyfile already installed"
fi
systemctl enable caddy

log "Host done. Next: sudo ./fiannafit-ops/provision.sh"
