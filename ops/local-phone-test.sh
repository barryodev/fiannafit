#!/usr/bin/env bash
# Serve the app over HTTPS on your home network, to try it on a phone.
# Run from your machine, with the phone on the same Wi-Fi:
#
#   ops/local-phone-test.sh
#
# The session cookie is Secure, so it only works over HTTPS. Rather than
# loosening that in the app, this uses a self-signed certificate, made on the
# first run and kept outside the repo. The phone warns about it once per
# address; tap through ("Advanced" on Android, "Show Details" on iPhone).
#
# It listens on every network interface, so anyone on the same network can
# reach it while it runs. Only use it on a network you trust.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/fiannafit-dev"
KEY="$CERT_DIR/key.pem"
CERT="$CERT_DIR/cert.pem"
PORT=8443

die() { echo "ERROR: $*" >&2; exit 1; }

command -v uv >/dev/null || die "uv isn't installed"
command -v openssl >/dev/null || die "openssl isn't installed"
[[ -f $REPO_DIR/.env ]] || die "$REPO_DIR/.env is missing. Copy .env.example and set SESSION_SECRET_KEY (see README)."

# The first address is the one on the home network (DHCP, so it can change)
IP="$(hostname -I | awk '{print $1}')"
[[ -n $IP ]] || die "couldn't find this machine's network address. Is it connected?"

# Make the certificate if it's missing or expires within a day
if [[ ! -f $KEY || ! -f $CERT ]] || ! openssl x509 -checkend 86400 -noout -in "$CERT" >/dev/null 2>&1; then
  echo "==> Creating a self-signed certificate in $CERT_DIR (valid for a year)"
  mkdir -p "$CERT_DIR"
  openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
    -keyout "$KEY" -out "$CERT" -subj "/CN=fiannafit-dev" \
    -addext "subjectAltName=IP:$IP,IP:127.0.0.1,DNS:localhost,DNS:$(hostname).local" \
    2>/dev/null
  chmod 600 "$KEY"
fi

# A changed address still works: the phone just warns once more for it
if ! openssl x509 -noout -ext subjectAltName -in "$CERT" | grep -qE "IP Address:${IP//./\\.}(,|$)"; then
  echo "==> Note: the certificate was made for a different address than $IP."
  echo "    The phone's warning will mention it; tap through as usual, or delete"
  echo "    $CERT_DIR to make a new certificate."
fi

cat <<EOF
==> On your phone, open:  https://$IP:$PORT
    Cookies belong to the address, so a workout logged at an old address
    won't show at a new one. If the page doesn't load, check the firewall:
    sudo ufw status  (allow with: sudo ufw allow from ${IP%.*}.0/24 to any port $PORT proto tcp)
    Ctrl+C stops the server.
EOF

cd "$REPO_DIR"
exec uv run --env-file .env uvicorn fiannafit.main:app --reload \
  --host 0.0.0.0 --port "$PORT" --ssl-keyfile "$KEY" --ssl-certfile "$CERT"
