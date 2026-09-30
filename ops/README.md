# Fianna Fit ops runbook

How to build a Fianna Fit server from scratch and deploy to it. Each step says where it happens: the OCI console, your machine, or the VM.

There are two targets, and both are set up with the same `provision.sh` and `deploy.sh`:

- **Production:** an Oracle Cloud (OCI) Always Free ARM64 VM.
- **Local test VM:** a Multipass VM on your machine running the same Ubuntu release. Use it to test changes to `ops/` before they touch production, and to reproduce infrastructure problems. If a problem also happens locally, it's in our setup; if it doesn't, look at OCI.

Design decisions behind this setup are in Linear (project "Fianna Fit", issues DAI-6 and DAI-7). In short: the cloud resources are created by hand in the OCI console, the server config lives in this folder, and `provision.sh` applies it. There's no Terraform and no Docker, and nothing gets hand-edited on the VM.

## Files

| File | Purpose |
| --- | --- |
| `README.md` | This runbook |
| `provision.sh` | Server setup that is safe to re-run. You run it on the VM over SSH |
| `deploy.sh` | You run it locally to ship the latest `main` to a named target (`local`, `prod`) and check its health |
| `targets.env.example` | Template for `targets.env` (gitignored), which maps target names to SSH addresses |
| `fiannafit.service` | systemd unit that runs uvicorn on `127.0.0.1:8000` as the `fiannafit` user |

## Server facts

These aren't secret (DNS publishes the production IP anyway), but they are specific to this host. Keep them here, not in code.

| | Production (OCI) | Local test VM |
| --- | --- | --- |
| Region / AD that worked | *(TODO)* | n/a |
| Name | `fiannafit` | `fiannafit-local` |
| Shape | `VM.Standard.A1.Flex` (ARM64), 1 OCPU / 6 GB | Multipass, x86_64, 1 CPU / 6 GB / 20 GB disk |
| Ubuntu release | *(TODO: exact image name)* | same release as production |
| IP | *(TODO)* | changes on rebuild, see `multipass list` |
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
3. Name: `fiannafit-vcn`. Leave the default CIDRs.
4. Create it. The wizard makes a public subnet, a private subnet, an internet gateway, a NAT gateway and route tables.

The default security list on the public subnet allows inbound SSH (22) from anywhere, plus some ICMP. That's all this step needs. Opening 80/443 is DAI-7's job.

### B3. Create the VM

1. **Compute → Instances → Create instance**.
2. **Name:** `fiannafit`.
3. **Image:** Change image → **Ubuntu** → the latest **Canonical Ubuntu** LTS build (the full image, not "Minimal"). Once you pick the Ampere shape below, make sure the image variant is `aarch64`.
4. **Shape:** Change shape → **Ampere** → `VM.Standard.A1.Flex`, **1 OCPU, 6 GB memory**. Look for the "Always Free-eligible" label. The free allowance is 4 OCPU / 24 GB in total, so this leaves headroom.
5. **Networking:** select `fiannafit-vcn` and its **public** subnet, and make sure **Assign a public IPv4 address** is on.
6. **SSH keys:** "Upload public key files" (or paste) and use `~/.ssh/id_ed25519.pub` from A1. Don't let OCI generate a key pair.
7. **Boot volume:** leave the default size. It's within the 200 GB Always Free block-storage allowance.
8. Create it.

**"Out of host capacity"?** Go back and try a different availability domain (Placement section), or retry later. Record the one that worked in *Server facts*.

When the instance shows **Running**, copy its **Public IP address** into *Server facts*. It stays the same across reboots and stop/start, and is only released if you terminate the instance.

### B4. First SSH login (your machine)

```sh
ssh ubuntu@<public-ip>
```

Accept the host key fingerprint on first connect. If this works, the network and key are set up correctly.

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
- **Firewall:** OCI's Ubuntu images ship with restrictive iptables rules, and the Multipass image doesn't. OCI also filters traffic with the security list before it reaches the VM. This matters from DAI-7 onwards.
- **No public IP or DNS:** so Caddy can't get a Let's Encrypt certificate locally (DAI-7).

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

Copy the `ops/` folder from your checkout to the VM, then run `provision.sh` there as root:

```sh
scp -r ops ubuntu@<vm-ip>:fiannafit-ops
ssh ubuntu@<vm-ip> sudo ./fiannafit-ops/provision.sh
```

This runs your local version of `ops/`, including uncommitted changes, so you can try changes on the local VM before merging. The app code is always cloned from `main` on GitHub.

The script:
1. checks the secrets file
2. applies system updates and installs `git` and `curl`
3. creates the `fiannafit` user
4. installs uv
5. clones the repo to `/opt/fiannafit`, or pulls if it's already there
6. runs `uv sync`
7. installs and enables the systemd service

Every step checks the current state first, so re-running it is safe. That's also how config changes are applied: edit `ops/`, then run D2 again.

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

`deploy.sh` doesn't copy `ops/` to the VM. If you've changed `fiannafit.service` or `provision.sh`, run D2 again first.

### D4. Verify

On the VM:

```sh
curl -i http://127.0.0.1:8000/healthz     # expect 200 and {"status":"ok"}
sudo reboot                                # then SSH back in and repeat the curl
```

If something's wrong, `systemctl status fiannafit` and `journalctl -u fiannafit -n 50` show the service state and the app's logs.
