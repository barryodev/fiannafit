# Fianna Fit ops runbook

How to build a Fianna Fit server from scratch and deploy to it. Each step says where it happens: the OCI console, your machine, or the VM.

There are two targets, and both are set up with the same `provision.sh` and `deploy.sh`:

- **Production:** an Oracle Cloud (OCI) Always Free ARM64 VM.
- **Local test VM:** a Multipass VM on your machine running the same Ubuntu release. Use it to test changes to `ops/` before they touch production, and to reproduce infrastructure problems. If a problem also happens locally, it's in our setup; if it doesn't, look at OCI.

Design decisions behind this setup are in Linear (project "Fianna Fit", issues DAI-6, DAI-7 and DAI-10). In short: the cloud resources are created by hand in the OCI console, the server config lives in this folder, and two scripts apply it: `host/provision-host.sh` for what every app on the VM shares, then `provision.sh` for Fianna Fit itself. There's no Terraform and no Docker, and nothing gets hand-edited on the VM.

## Files

| File | Purpose |
| --- | --- |
| `README.md` | This runbook |
| `host/provision-host.sh` | Host setup shared by every app on the VM (updates, Caddy, firewall, SSH, unattended upgrades). Safe to re-run; run it on the VM before `provision.sh` |
| `host/Caddyfile` | The host's main Caddyfile. It only imports one site file per app from `/etc/caddy/sites/` |
| `host/sshd-hardening.conf` | SSH settings: key-only login, no passwords, no root login |
| `host/20auto-upgrades` | Turns on daily unattended security upgrades |
| `provision.sh` | App setup that is safe to re-run. You run it on the VM over SSH |
| `fiannafit.caddy` | Fianna Fit's Caddy site: HTTPS for `fiannafit.barryodev.io`, proxied to the app |
| `deploy.sh` | You run it locally to ship the latest `main` to a named target (`local`, `prod`) and check its health |
| `local-phone-test.sh` | You run it locally to serve the app over HTTPS on your home network (self-signed cert, kept outside the repo), to try it on a phone |
| `targets.env.example` | Template for `targets.env` (gitignored), which maps target names to SSH addresses |
| `fiannafit.service` | systemd unit that runs uvicorn on `127.0.0.1:8000` as the `fiannafit` user |

## Server facts

These aren't secret, but they are specific to this host. Keep them here, not in code. IP addresses live only in the gitignored `ops/targets.env`.

| | Production (OCI) | Local test VM |
| --- | --- | --- |
| Region / AD that worked | `eu-paris-1` / AD-1 | n/a |
| Name | `barryodev-1` | `fiannafit-local` |
| Shape | `VM.Standard.A1.Flex` (ARM64), 1 OCPU / 6 GB | Multipass, x86_64, 1 CPU / 6 GB / 20 GB disk |
| Ubuntu release | `Canonical-Ubuntu-26.04-aarch64-2026.08.17-0` | same release as production (26.04) |
| IP | `PROD` in `ops/targets.env`, or the instance details page in the OCI console | `LOCAL` in `ops/targets.env`; changes on rebuild, see `multipass list` |
| SSH user | `ubuntu` | `ubuntu` |

---

## A. Before you start (your machine, once)

### A1. SSH key

Both VMs let you log in with your SSH key only. If you don't have one:

```sh
ssh-keygen -t ed25519 -C "barryodev@gmail.com"
```

Accept the default path (`~/.ssh/id_ed25519`) and set a passphrase. The public half, `~/.ssh/id_ed25519.pub`, is what you give to OCI and Multipass. The private half never leaves your machine.

---

## B. Production VM (OCI console)

### B1. Check the account type

Always Free resources are available on both account types, but they behave differently:

- **Free Tier only:** Oracle can reclaim Always Free compute that sits idle (roughly <20% CPU, network and memory over 7 days). A Hello World app will look idle. A1 capacity is also harder to get.
- **Pay-As-You-Go (PAYG):** The same Always Free allowances still cost nothing, idle instances aren't reclaimed, and A1 capacity is easier to get. This is the setup the project plan assumes, and why DAI-7 adds a Budget alert.

To check: **Billing & Cost Management → Upgrade and Manage Payment**. On a brand-new account, this page says "Your account provisioning is in progress" until Oracle finishes setting the account up. Wait for the "account is fully provisioned" email before you continue. If you want to upgrade, do it now, before creating the VM. The upgrade can take a while to complete.

### B2. Create the network

1. Make sure the region selector (top right) shows your **home region**. Always Free compute can only be created there.
2. **Networking → Virtual cloud networks → Actions → Start VCN Wizard → "Create VCN with Internet Connectivity"**.
3. Name: `barryodev-vcn`. Leave the default CIDRs.
4. Create it. The wizard makes a public subnet, a private subnet, an internet gateway, a NAT gateway and route tables.

The default security list on the public subnet allows inbound SSH (22) from anywhere, plus some ICMP. That's all this step needs. B5 opens 80 and 443.

### B3. Create the VM

1. **Compute → Instances → Create instance**.
2. **Name:** `barryodev-1`.
3. **Shape** (pick this before the image): Change shape → **Ampere** → `VM.Standard.A1.Flex`, **1 OCPU, 6 GB memory**. Look for the "Always Free-eligible" label. The free allowance is 4 OCPU / 24 GB in total, so this leaves headroom.
4. **Image:** Change image → **Ubuntu** → **Canonical Ubuntu 26.04** (the full image, not "Minimal"; same release as the local VM). The full image has no separate "aarch64" entry, and its build dropdown only shows a date. To check it's the ARM build, expand it and click **View compatible shapes**: it should list only A1 shapes.
5. **Security:** leave **Shielded instance** off. It guards against boot-level malware, isn't needed here, and once on, only the instance name can be changed.
6. **Networking:** select `barryodev-vcn` and its **public** subnet, and make sure **Assign a public IPv4 address** is on.
7. **SSH keys:** "Upload public key files" (or paste) and use `~/.ssh/id_ed25519.pub` from A1. Don't let OCI generate a key pair.
8. **Boot volume:** leave the default size. It's within the 200 GB Always Free block-storage allowance.
9. Leave everything else at its default (Oracle Cloud Agent plugins, live migration, metadata service v2). **Compute Instance Run Command** is worth keeping on: it lets you run commands from the console if SSH ever locks you out.
10. Create it. The instance details page then shows the full image name (e.g. `Canonical-Ubuntu-26.04-aarch64-...`); record it in *Server facts*.

**"Out of host capacity"?** Go back and try a different availability domain (Placement section), or retry later. Record the one that worked in *Server facts*.

When the instance shows **Running**, copy its **Public IP address** into *Server facts*. It stays the same across reboots and stop/start, and is only released if you terminate the instance.

### B4. First SSH login (your machine)

```sh
ssh ubuntu@<public-ip>
```

Accept the host key fingerprint on first connect. If this works, the network and key are set up correctly.

### B5. Open ports 80 and 443

Caddy needs both: 443 for HTTPS, and 80 for the `http://` → `https://` redirect and for Let's Encrypt to check that the domain is yours.

1. **Networking → Virtual cloud networks → `barryodev-vcn` → Security** tab → **Default Security List for barryodev-vcn**.
2. **Security rules → Add Ingress Rules**. Add two rules, both with source CIDR `0.0.0.0/0` and IP protocol TCP: destination port `80`, and destination port `443`.
3. Check the list now allows inbound TCP on 22, 80 and 443 only (plus the default ICMP rules). Nothing else, and in particular not 8000.

This is OCI's firewall, in front of the VM. The VM has its own iptables rules too, which `host/provision-host.sh` opens in D2. Both have to allow a port for traffic to get through.

### B6. DNS record (name.com)

At name.com, open **barryodev.io → Manage DNS records** and add:

| Type | Host | Answer | TTL |
| --- | --- | --- | --- |
| `A` | `fiannafit` | the VM's public IP | `300` |

The short TTL means a mistake is fixed within 5 minutes. Check it from your machine (it can take a few minutes to appear):

```sh
dig +short fiannafit.barryodev.io      # expect the VM's public IP
```

Do this before D2, so Caddy can get the certificate as soon as it's set up. If DNS isn't ready yet, Caddy keeps retrying on its own, more slowly each time. Running D2 again, or `sudo systemctl reload caddy` on the VM, makes it try again straight away.

### B7. Budget alert

The account is Pay-As-You-Go, so an accidental paid resource would be billed. A Budget emails you before that gets far. It's an alert, not a spending cap.

1. **Billing & Cost Management → Budgets → Create Budget**.
2. **Name:** `monthly-spend`. **Target:** the root compartment (the whole tenancy). **Schedule:** monthly. **Amount:** `5` (in the account's currency).
3. Add two alert rules, both emailing you: one on **actual** spend and one on **forecast** spend, each at 100% of the budget. Everything in this runbook is Always Free, so either one firing means something unexpected is being billed.
4. Create it, then open **Budget Alert Rules** and check that both rules are there and the email addresses are spelled right. Budget emails need no confirmation, so nothing arrives at this point, and there's no way to send a test alert. Spent and Forecast show N/A at first: the forecast needs a few days of usage data before it appears.

The email address is set only here in the console, never in the repo.

---

## C. Local test VM (your machine)

### C1. Install Multipass (once)

```sh
sudo snap install multipass
```

[Multipass](https://canonical.com/multipass) is Canonical's tool for running Ubuntu VMs. It boots the official Ubuntu cloud images and sets them up with cloud-init, the same first-boot mechanism OCI uses. That's how both VMs end up with an `ubuntu` user that has your SSH key.

### C2. Create the VM

Use the same Ubuntu release as production (the `26.04` below is an example):

```sh
multipass launch 26.04 --name fiannafit-local --cpus 1 --memory 6G --disk 20G \
  --cloud-init - <<EOF
ssh_authorized_keys:
  - $(cat ~/.ssh/id_ed25519.pub)
EOF
```

The key is read from your machine when you run the command, so nothing host-specific is committed. `multipass find` lists the available releases.

### C3. First SSH login

```sh
multipass list                      # shows fiannafit-local's IPv4 address
ssh ubuntu@<local-vm-ip>
```

Log in over SSH, not with `multipass shell`, because `deploy.sh` will use SSH exactly as it does for production.

### Rebuilding from scratch

```sh
multipass delete --purge fiannafit-local
```

Then repeat C2. Rebuilding is the quickest way to check that the runbook and `provision.sh` still work on a fresh machine.

The new VM often gets the same IP but always has a new host key, so the next `ssh` fails with "REMOTE HOST IDENTIFICATION HAS CHANGED". That's expected here. Clear the old entry, then connect again and accept the new fingerprint:

```sh
ssh-keygen -R <local-vm-ip>
```

### How the local VM differs from production

Keep these in mind before blaming our setup or OCI for a problem:

- **CPU architecture:** local is x86_64 and production is ARM64. It rarely matters here, because uv installs the right Python build and wheels for each platform.
- **Firewall:** OCI's Ubuntu images ship with restrictive iptables rules (all inbound traffic rejected except SSH), and the Multipass image has none. OCI also filters traffic with the security list (B5) before it reaches the VM. `host/provision-host.sh` adds the same 80/443 rules on both. On the local VM, installing `iptables-persistent` also removes `ufw`, which was installed but off.
- **No public IP or DNS:** so Caddy can't get a Let's Encrypt certificate locally. Caddy still tries, and logs certificate errors for `fiannafit.barryodev.io` (`journalctl -u caddy`). That's expected and harmless: the local VM only checks that the Caddy config is valid and that Caddy runs and redirects, and the certificate is tested on production.

---

## D. Set up and deploy (either VM)

### D1. Create the secrets file (VM, once, by hand)

The app's secrets live in `/etc/fiannafit/env`: one `NAME=value` per line, loaded by systemd. The file is never committed. `provision.sh` refuses to run until it exists, and never creates or changes it.

SSH to the VM and run:

```sh
sudo install -d -m 0755 /etc/fiannafit
sudo install -m 0600 -o root -g root /dev/null /etc/fiannafit/env
echo "SESSION_SECRET_KEY=$(openssl rand -hex 32)" | sudo tee /etc/fiannafit/env >/dev/null
```

The first two lines create the folder and an empty file that only root can read. The third generates a random key and writes it to the file without printing it. The app doesn't use the key until Phase 1, but setting it now means this step is done once.

Each VM gets its own key. Never copy production's key to the local VM.

### D2. Provision (your machine → VM)

**Before the first run on a VM, and whenever `host/sshd-hardening.conf` changes:** open a separate SSH session to the VM and leave it open until the end of this step. The host script changes SSH settings. Existing sessions stay open when SSH reloads, so if a mistake ever stopped new logins, that session is how you fix it. (On OCI, the console's **Run Command** is the fallback after that.)

Copy the `ops/` folder from your checkout to the VM, then run the two scripts there as root, host first:

```sh
ssh ubuntu@<vm-ip> rm -rf fiannafit-ops
scp -r ops ubuntu@<vm-ip>:fiannafit-ops
ssh ubuntu@<vm-ip> sudo ./fiannafit-ops/host/provision-host.sh
ssh ubuntu@<vm-ip> sudo ./fiannafit-ops/provision.sh
```

Then check that a **new** SSH login still works (`ssh ubuntu@<vm-ip> true`) before closing the session you kept open.

The first line removes any copy left over from a previous run. Without it, `scp -r` would put the new copy *inside* the old one (`fiannafit-ops/ops/`, the same way `cp -r` does) and the old `provision.sh` would run.

This runs your local version of `ops/`, including uncommitted changes, so you can try changes on the local VM before merging. The app code is always cloned from `main` on GitHub.

`host/provision-host.sh` sets up what every app on the VM shares:
1. adds Caddy's official apt repository
2. applies system updates and installs Caddy, `iptables-persistent` and `unattended-upgrades`
3. opens ports 80 and 443 in iptables and saves the rules so they survive a reboot
4. installs the SSH hardening, checks it with `sshd -t` before reloading SSH, then checks the settings SSH actually uses
5. turns on unattended security upgrades
6. installs the main Caddyfile, after `caddy validate` accepts it, and reloads Caddy

`provision.sh` sets up Fianna Fit:
1. checks the secrets file, and that the host script has run
2. installs `git` and `curl`
3. creates the `fiannafit` user
4. installs uv
5. clones the repo to `/opt/fiannafit`, or pulls if it's already there
6. runs `uv sync`
7. installs and enables the systemd service
8. installs `fiannafit.caddy` into `/etc/caddy/sites/`, after `caddy validate` accepts it, and reloads Caddy

Neither script touches the other's files. A future app adds its own site file next to `fiannafit.caddy`, on its own localhost port.

Every step checks the current state first, so re-running is safe. That's also how config changes are applied: edit `ops/`, then run D2 again. SSH and Caddy are only reloaded when their files have changed, and a config that fails its check is never put live.

`provision.sh` enables the service but doesn't start it. D3 (`deploy.sh`) starts it. Until `deploy.sh` exists, start it by hand on the VM with `sudo systemctl restart fiannafit`.

### D3. Deploy (your machine)

`deploy.sh` always deploys `main` from GitHub, to either VM. There's no option to deploy another branch, so a change has to be merged and pushed before it can be deployed.

**Once:** create your targets file. It's gitignored, because the addresses are host-specific:

```sh
cp ops/targets.env.example ops/targets.env    # then fill in the IPs
```

**Each deploy:** name the target. There's no default, so you always type where you're deploying to:

```sh
ops/deploy.sh local
ops/deploy.sh prod
```

Over SSH, the script:
1. pulls `main` in `/opt/fiannafit` and prints the commit it's now at
2. runs `uv sync --frozen --no-dev`
3. restarts the service
4. polls `http://127.0.0.1:8000/healthz` on the VM for up to 10 seconds

If the check never gets a 200, the script prints the last 30 lines of the app's logs and exits non-zero.

`deploy.sh` doesn't copy `ops/` to the VM. If you've changed anything in `ops/` other than `deploy.sh`, run D2 again first.

### D4. Verify

On the VM:

```sh
curl -i http://127.0.0.1:8000/healthz     # expect 200 and {"status":"ok"}
sudo reboot                                # then SSH back in and repeat the curl
```

If something's wrong, `systemctl status fiannafit` and `journalctl -u fiannafit -n 50` show the service state and the app's logs.

**Production only, from your machine** (needs B5, B6 and D2):

```sh
curl -I http://fiannafit.barryodev.io                 # expect 308, Location: https://...
curl -i https://fiannafit.barryodev.io/healthz        # expect 200, no certificate error
curl -m 5 http://<public-ip>:8000/healthz             # expect a timeout or refusal, never a 200
ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password ubuntu@<public-ip>
                                                      # expect "Permission denied (publickey)"
```

Then open `https://fiannafit.barryodev.io` in a browser and check the padlock. After a `sudo reboot`, all of these should still pass with nothing started by hand.

If HTTPS doesn't work, `journalctl -u caddy -n 50` on the VM shows why. The usual causes are DNS not pointing at the VM yet (B6), or port 80 or 443 blocked in the security list (B5) or iptables (`sudo iptables -L INPUT -n --line-numbers`). If the first attempt fails, Caddy retries against Let's Encrypt's staging server, so a broken setup doesn't use up Let's Encrypt's rate limits while you fix it.

**Local VM:** the certificate can't work there (see *How the local VM differs from production*), but you can check that Caddy is running and redirects:

```sh
curl -I -H 'Host: fiannafit.barryodev.io' http://<local-vm-ip>/   # expect 308 to https://
```
