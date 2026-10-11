# FINOVA — Akamai Cloud & DuckDNS Configuration Guide

**Project:** FINOVA (Finance Innovation) | Hack Midwest 2026  
**Public demo:** https://finova-intelligence.duckdns.org/  
**Cloud provider:** Akamai Connected Cloud (Linode) | **OS:** Debian 12 (Bookworm)  
**Repository:** https://github.com/Afsanaairin/Finova-A-Fintech-Solution  
**Purpose:** Reproduce the setup, understand every connection, troubleshoot it, and deploy future FINOVA versions safely.

> **Please read before updating the live site.** The original server was deployed using an earlier FINOVA version. The uploaded source ZIP now contains **email-code login and a persistent SQLite authentication database**. The older, read-only systemd service will not let that database be created. Follow **Part H** before deploying the updated source. An existing online dashboard is not proof that this newer ZIP is online.
>
> This file is a reconstruction of the workflow performed during the hackathon, plus a **separate, explicitly marked upgrade plan** inferred from the current source. It is not a record that every new-version change has already been executed on the Linode.

## Contents

- [A. What was connected](#a-what-was-connected)
- [B. Accounts, credentials, and SSH](#b-accounts-credentials-and-ssh)
- [C. Linode creation and the cloud firewall](#c-linode-creation-and-the-cloud-firewall)
- [D. Workshop API and Linode CLI](#d-workshop-api-and-linode-cli)
- [E. Debian, Git, source checkout, and application service](#e-debian-git-source-checkout-and-application-service)
- [F. DuckDNS, nginx, HTTPS, and operator access](#f-duckdns-nginx-https-and-operator-access)
- [G. How the existing deployment is arranged](#g-how-the-existing-deployment-is-arranged)
- [H. REQUIRED: upgrade the new email-login version](#h-required-upgrade-the-new-email-login-version)
- [I. Deploy later GitHub updates safely](#i-deploy-later-github-updates-safely)
- [J. Verification and troubleshooting](#j-verification-and-troubleshooting)
- [K. Safety, costs, and team handover](#k-safety-costs-and-team-handover)

## A. What was connected

```text
Windows VS Code (team development)
    -> git push -> GitHub: Afsanaairin/Finova-A-Fintech-Solution (main)
    -> git pull on Linode (/root/finova-source: source checkout)
    -> tested code copied into /opt/finova (running release)

Browser -> finova-intelligence.duckdns.org (DuckDNS A record)
    -> Linode public IP (currently 172.232.18.105)
    -> Akamai Cloud Firewall (80 HTTP, 443 HTTPS, limited SSH 22)
    -> nginx (Let's Encrypt TLS, Basic Auth, request limits, proxy token)
    -> 127.0.0.1:8000 (FINOVA Python service, user finova)
    -> local financial calculations + optional Akamai workshop AI over HTTPS
```

**Two addresses must never be confused:** The *source* IP allowed on port 22 is the administrator's **current public home/hotspot IP** (check `https://api.ipify.org`). The *destination* IP is the **Linode public IPv4** (check `linode-cli linodes list`). DuckDNS must point to the **Linode IP**, not to a laptop.

**Deployment inventory (from the successful setup):**

| Item | Value / role |
| --- | --- |
| Linode label | `debian-us-ord` |
| Region | `us-ord` (Chicago) |
| OS | Debian 12 |
| Public IPv4 at setup | `172.232.18.105` — recheck before reuse |
| DuckDNS | `finova-intelligence.duckdns.org` |
| HTTPS | Let's Encrypt certificate issued October 11, 2026; original expiry January 9, 2027 (renew automatically; verify) |
| Repo checkout | `/root/finova-source` |
| Deployed application | `/opt/finova` |
| Service | `finova.service` running as `finova` |
| Backend listener | `127.0.0.1:8000`, **not public** |
| Proxy configuration | `/etc/nginx/sites-available/finova` and `/etc/nginx/snippets/finova-proxy.conf` |
| Private configuration | `/etc/finova/finova.env`, `/etc/finova/proxy-secret.conf`, `/etc/finova/finova.htpasswd` |

The cloud plan and current promotional credits **must be checked in Akamai billing**. A selected hourly compute price is not proof the server is free. Billing can continue while an instance is powered off.

## B. Accounts, credentials, and SSH

### B1. What each secret does (never mix them up)

| Credential | Used for | Store it where |
| --- | --- | --- |
| Linode **root password** | LISH Console / emergency Linux login | Password manager |
| SSH **private key + passphrase** | Encrypted terminal access from Windows | Private key only on laptop; passphrase in password manager |
| SSH **public key** | Authorizes a computer to log in | Akamai profile and server `authorized_keys` |
| Akamai **Personal Access Token** | `linode-cli` managing cloud resources | CLI credential store; least privilege, short expiry |
| Workshop inference **`hk_...` key** | Optional `hackathon-chat` and `hackathon-image` requests | Server-only environment file; **not** the Linode PAT |
| FINOVA **proxy token** | nginx authenticates to Python backend | `/etc/finova/finova.env` + root-only nginx include |
| FINOVA **Basic Auth password** | Browser access to the protected demo | Hashed in `/etc/finova/finova.htpasswd` |
| Gmail **app password** | New version sends email verification codes | Server-only environment file; **not** Google account password |

Never commit `.env`, passwords, API keys, auth databases, private keys, credentials, or unredacted configuration screenshots.

### B2. Generate the Windows SSH key

Use Windows **PowerShell** locally (`PS C:\Users\...>`), not a Debian shell:

```powershell
New-Item -ItemType Directory -Force "$HOME\.ssh" | Out-Null
ssh-keygen -t ed25519 -C "finova_akamai" -f "$HOME\.ssh\finova_akamai"
Get-Content "$HOME\.ssh\finova_akamai.pub" | Set-Clipboard
```

Paste only the `.pub` contents into **Akamai Cloud Manager -> SSH Keys -> Add SSH Key** and select it during Linode creation. A passphrase encrypts the local **private** key; it is *not* the root password. If unsure whether the passphrase works:

```powershell
ssh-keygen -y -f "$HOME\.ssh\finova_akamai" | Out-Null
$LASTEXITCODE  # 0 means the command succeeded
```

If the Windows agent reports `Error connecting to agent`, open **PowerShell as Administrator** once:

```powershell
Set-Service ssh-agent -StartupType Manual
Start-Service ssh-agent
Get-Service ssh-agent
```

Back in a normal PowerShell session:

```powershell
ssh-add "$HOME\.ssh\finova_akamai"
ssh-add -l
```

Never replace a functioning private key simply because the agent stopped. Do not share a private key with teammates; register separate public keys for authorized people.

### B3. First SSH connection and identity verification

Find the current server IP in Akamai; then from **Windows PowerShell**:

```powershell
ssh -o IdentitiesOnly=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -i "$HOME\.ssh\finova_akamai" root@172.232.18.105
```

On first connect, verify the ED25519 **server host fingerprint** in the Akamai **LISH Console**, logged in with `root` and the root password:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Only type `yes` in PowerShell if the fingerprints match. If the private key is not authorized yet, a successful LISH/root-password login can add **the public key** to `/root/.ssh/authorized_keys`, followed by `chmod 700 /root/.ssh` and `chmod 600 /root/.ssh/authorized_keys`. Test with `PasswordAuthentication=no` before considering removal of password login. Keep LISH available for recovery.

**Terminal check:** `PS C:\...>` means you are on Windows; `root@localhost:~#` means you are on Debian. The earlier `install` error was caused by an SSH disconnect and running Linux commands in PowerShell. `localhost` in the Debian prompt was the Linux hostname, not the public server label.

## C. Linode creation and the cloud firewall

1. In Akamai Cloud Manager, create a Linode with a supported Linux image (**Debian 12** used here), a suitable region (**Chicago** used here), and a compute size matching the expected workload and available credits. A G8 Dedicated plan was selected during setup; verify the actual active plan and ongoing charges before keeping it running.
2. Use **Public Internet**, **Auto-assigned IPv4** (rather than reserving an unnecessary new address), and **Linode Interfaces** where available.
3. Set a strong root password and assign the SSH public key.
4. Create or select a Cloud Firewall, **attach it to the Linode's public interface**, and configure rules below. The firewall must be both attached **and saved**.

| Rule | TCP port | Source | Action |
| --- | --- | --- | --- |
| `allow-ssh` | 22 | Current administrator public IP, e.g. `YOUR_PUBLIC_IP/32` | Accept |
| `allow-http` | 80 | All IPv4 | Accept |
| `allow-https` | 443 | All IPv4 | Accept |
| Default inbound | other | all | **Drop** |
| Default outbound | all | all | **Accept** |

For an IPv6-enabled public interface, explicitly review and secure IPv6 traffic too. Do **not** expose port 8000. Port 80 is used for ACME validation and redirects to HTTPS; port 443 serves the app. Save the overall firewall changes after adding/editing each rule.

**Why SSH originally timed out:** First the new inbound rule was not saved; then it mistakenly used the **Linode IP as the source**; then the rule was set to **Drop** rather than **Accept**. The correct source was the **Windows network's** public IPv4 at the time. Verify:

```powershell
Invoke-RestMethod 'https://api.ipify.org'  # computer's current public IPv4
linode-cli linodes list --format id,label,status,ipv4
Test-NetConnection -ComputerName 172.232.18.105 -Port 22
```

A failed ping alone is not definitive. `TcpTestSucceeded : True` is the important check for port 22. Your home or hotspot IP can change, requiring a firewall source update. If SSH still fails, use LISH and check `systemctl status ssh` and `journalctl -u ssh -n 30 --no-pager` before changing keys.

## D. Workshop API and Linode CLI

These are **different integrations**:

- **Linode CLI** manages infrastructure using an Akamai *personal access token*; it does not provide the AI model.
- **Akamai workshop inference** uses a *team-specific key*, `OPENAI_API_KEY`, with `https://ws.akamai-workshops.com/v1` and the `hackathon-chat`/`hackathon-image` aliases. Never substitute a Linode PAT for the workshop key.

On **Windows PowerShell**, install and configure the CLI:

```powershell
py -m pip install --upgrade linode-cli
linode-cli configure --token
linode-cli profile view --format username
linode-cli regions view us-sea --format id,label,status
```

The setup questions for **default region, plan, and image** are optional if scripts supply those values. During this setup, the profile username was `Rosalyn-DSAI`, which is a CLI identity, not the Linux root login. When selecting permissions, use only the scopes actually needed by your chosen scripts. Avoid unnecessarily broad `Read/Write` privileges and use a short token expiry. Never paste token values into command output or chat.

The Object Storage CLI plugin required the `boto3` package on the Windows environment in this setup:

```powershell
py -m pip install boto3
linode-cli obj --help
```

This verifies the command is available; it does **not** prove Object Storage access or create a bucket. FINOVA itself does not require Object Storage to run.

For the separately cloned **Akamai Hack Midwest workshop agent**, configure its own `.env` with the authorized team key, not in the public FINOVA repository. The successful workshop health check was:

```powershell
python -m agent --once "Say hello in one sentence."
```

That proved the workshop model responded, but did not deploy FINOVA. The workshop's example deployment scripts can provision *other* cloud services; review them before running to avoid new billable resources.

## E. Debian, Git, source checkout, and application service

### E1. First server setup (commands run in Debian)

```bash
apt-get update
apt-get install -y git python3 python3-pip python3-venv nginx apache2-utils certbot
python3 --version
 git --version
```

Debian normally calls Python `python3`, **not** `python`. The app's core needs Python 3.10+ and uses no third-party Python packages. For PDF imports/OCR, install **optional** system tools:

```bash
apt-get install -y poppler-utils tesseract-ocr tesseract-ocr-eng
```

### E2. Download and test the tracked version

```bash
cd /root
git clone https://github.com/Afsanaairin/Finova-A-Fintech-Solution.git finova-source
cd /root/finova-source
git status
git log -1 --oneline
python3 -m unittest discover -s tests -v
```

The originally deployed checkout was commit `89d9c15`; **28 tests passed at that time**. That is historical deployment evidence, not the current upload's test count. The **newer supplied ZIP** passed **95 Python tests** during this documentation audit; browser behavior and server upgrade still require testing on Akamai.

### E3. Install a restricted application user and copy the code

```bash
id finova >/dev/null 2>&1 || useradd --system --user-group --no-create-home --shell /usr/sbin/nologin finova
install -d -o root -g root -m 0755 /opt/finova
git -C /root/finova-source archive HEAD | tar -x -C /opt/finova --no-same-owner
chown -R root:root /opt/finova
chmod -R go-w /opt/finova
install -d -o root -g www-data -m 0750 /etc/finova
install -d -o root -g root -m 0755 /var/lib/acme
install -o root -g root -m 0600 /opt/finova/deploy/finova.env.example /etc/finova/finova.env
```

The service environment is managed **outside Git**. The `finova` account is not a human login and does not get `sudo`. The systemd unit from `deploy/finova.service` runs `/usr/bin/python3 /opt/finova/run.py`, binds the backend to `127.0.0.1:8000`, and uses security restrictions. The live configuration was installed with:

```bash
install -o root -g root -m 0644 /opt/finova/deploy/finova.service /etc/systemd/system/finova.service
systemd-analyze verify /etc/systemd/system/finova.service
systemctl daemon-reload
systemctl enable --now finova
systemctl is-active finova
ss -ltnp | grep ':8000'
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/health
```

In **proxy mode**, a direct unsigned request to port 8000 returns **403**. Do not disable this boundary; nginx forwards the real requests with verified identity and token.

### E4. Private proxy token and browser Basic Auth

Generate the server-only token once; a regeneration requires updating both matching locations and restarting/reloading the affected services. **Never display it in documentation.**

```bash
python3 - <<'PY'
from pathlib import Path
import secrets, os
os.umask(0o077)
env = Path('/etc/finova/finova.env')
marker = 'REPLACE_WITH_SERVER_GENERATED_TOKEN'
content = env.read_text()
if marker in content:
    token = secrets.token_urlsafe(32)
    env.write_text(content.replace(marker, token))
    Path('/etc/finova/proxy-secret.conf').write_text(
        'proxy_set_header X-Finova-Proxy-Token "' + token + '";\n')
    print('Proxy credentials configured.')
else:
    print('Token already configured; no changes made.')
PY
```

Create the first operator password with nginx Basic Auth:

```bash
htpasswd -cB /etc/finova/finova.htpasswd finovaadmin
chown root:www-data /etc/finova/finova.htpasswd
chmod 0640 /etc/finova/finova.htpasswd
```

For a second operator, run `htpasswd -B /etc/finova/finova.htpasswd SECOND_USERNAME` **without `-c`**, which otherwise overwrites the first account. The **updated ZIP adds an additional, separate email-code login** discussed in Part H.

## F. DuckDNS, nginx, HTTPS, and operator access

### F1. Connect DuckDNS to the correct IP

Register `finova-intelligence` at https://www.duckdns.org/. Initially, DuckDNS used the laptop public IP, which was wrong. Change **current ip** to the Linode public IP (`172.232.18.105` at original setup) and click **update ip**. Leave IPv6 blank unless deliberately configured.

Verify in **Windows PowerShell**:

```powershell
Resolve-DnsName finova-intelligence.duckdns.org -Type A
```

This returned `172.232.18.105` during setup. A domain does not run the application; it only directs traffic to Akamai. Do not expose or commit the DuckDNS account token. The subdomain persists when code is updated.

### F2. Obtain trusted HTTPS with Certbot webroot

First allow and **save** inbound TCP 80/443 in the Akamai firewall. On Debian:

```bash
apt-get install -y certbot nginx
mkdir -p /var/lib/acme/.well-known/acme-challenge
```

Before the final HTTPS template, create a temporary nginx HTTP site in `/etc/nginx/sites-available/finova-acme`:

```nginx
server {
    listen 80;
    server_name finova-intelligence.duckdns.org;
    location ^~ /.well-known/acme-challenge/ {
        root /var/lib/acme;
        default_type text/plain;
        try_files $uri =404;
    }
    location / { return 404; }
}
```

Enable/test/start:

```bash
ln -sfn /etc/nginx/sites-available/finova-acme /etc/nginx/sites-enabled/finova-acme
nginx -t
systemctl enable --now nginx
systemctl reload nginx
echo 'finova-acme-ready' > /var/lib/acme/.well-known/acme-challenge/check.txt
```

Confirm from Windows:

```powershell
Invoke-RestMethod 'http://finova-intelligence.duckdns.org/.well-known/acme-challenge/check.txt'
```

It returned `finova-acme-ready`. Then on Debian:

```bash
certbot certonly --webroot -w /var/lib/acme -d finova-intelligence.duckdns.org
```

The certificate was issued October 11, 2026, with an initial expiry **2027-01-09**. Certbot scheduled renewal; actual renewal must still be checked, not assumed. The TLS private key in `/etc/letsencrypt/live/finova-intelligence.duckdns.org/privkey.pem` must never be shared.

### F3. Activate the real nginx application proxy

Configure the host in the private environment (`FINOVA_PUBLIC_ORIGIN=https://finova-intelligence.duckdns.org`) and install the tracked templates:

```bash
install -D -o root -g root -m 0644 /opt/finova/deploy/finova-proxy.conf /etc/nginx/snippets/finova-proxy.conf
install -D -o root -g root -m 0644 /opt/finova/deploy/nginx.conf /etc/nginx/sites-available/finova
sed -i 's|finova.example.com|finova-intelligence.duckdns.org|g' /etc/nginx/sites-available/finova /etc/nginx/snippets/finova-proxy.conf
ln -sfn /etc/nginx/sites-available/finova /etc/nginx/sites-enabled/finova
rm -f /etc/nginx/sites-enabled/finova-acme /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
systemctl restart finova
```

Nginx terminates HTTPS, requires the website password, overwrites identity/proxy headers, injects the secret `X-Finova-Proxy-Token` read from `/etc/finova/proxy-secret.conf`, and proxies to `http://127.0.0.1:8000`. It keeps public port **8000 closed**.

### F4. Renewals and smoke tests

The repository contains a renewal reload hook. If not yet installed:

```bash
install -D -o root -g root -m 0755 /opt/finova/deploy/finova-renewal-hook.sh /etc/letsencrypt/renewal-hooks/deploy/finova-nginx
certbot renew --dry-run
systemctl list-timers | grep -i certbot
```

Do not claim renewal is confirmed without successful testing. The final nginx port-80 config keeps the ACME webroot path accessible while redirecting other HTTP requests to HTTPS.

From Windows:

```powershell
curl.exe -I https://finova-intelligence.duckdns.org/
```

Expected result without the nginx operator password: **HTTP 401** (Basic Auth challenge). A browser that passes nginx authentication can show the FINOVA landing page. The **new ZIP** additionally requires email-code login (Part H). A dashboard screenshot does not prove that every app feature and new login flow works.

## G. Why the two source directories matter

**`/root/finova-source`** is the Git checkout. **`/opt/finova`** is the actual copied code running under systemd. `git pull` alone changes only the first directory. The private `/etc/finova/` files and `/etc/letsencrypt/` certificates are **not** in the repository and must not be overwritten when deploying code.

Important files:

```text
/root/finova-source/                    reviewed Git checkout
/opt/finova/                            deployed application
/etc/finova/finova.env                  protected environment variables
/etc/finova/proxy-secret.conf           matching private nginx header
/etc/finova/finova.htpasswd            operator password hashes
/etc/systemd/system/finova.service      restricted Python service
/etc/nginx/sites-available/finova       website TLS/auth/rate limits
/etc/nginx/snippets/finova-proxy.conf  trusted upstream headers
/var/lib/acme/                           HTTP-01 challenge path
/etc/letsencrypt/live/...               HTTPS certificate and private key
```

## H. REQUIRED: upgrade the new email-login version

> **NOT YET COMPLETED on Akamai.** The updated ZIP includes `auth.py`, a new login page, email code endpoints, and `data/auth.sqlite3`. The original systemd service has `ProtectSystem=strict`; with root-owned `/opt/finova`, the new code cannot create/write its SQLite database. Simply copying the new files and restarting will not make the new login usable.

### H1. Add SMTP settings to the *server-only* environment

On Debian as root, edit `/etc/finova/finova.env` with `nano`. Retain the **already configured** `FINOVA_PROXY_TOKEN` and optional `OPENAI_API_KEY`. Add these settings, entering authorized real values privately on your server:

```dotenv
FINOVA_DEPLOYMENT=proxy
HOST=127.0.0.1
PORT=8000
FINOVA_PUBLIC_ORIGIN=https://finova-intelligence.duckdns.org
PUBLIC_ORIGIN=https://finova-intelligence.duckdns.org
COOKIE_SECURE=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=YOUR_SENDING_EMAIL
SMTP_APP_PASSWORD=YOUR_GOOGLE_APP_PASSWORD
SMTP_FROM=YOUR_SENDING_EMAIL
AUTH_CODE_TTL_SECONDS=300
AUTH_SESSION_TTL_SECONDS=604800
```

Gmail requires a sending account with 2-Step Verification and a valid app password (where available). The app sends the six-digit code through SMTP STARTTLS; no SMTP setup means users cannot finish this new login. **Do not use your Akamai token or SSH passphrase as the Gmail password.** The managed proxy mode ignores the repo `.env` and uses systemd's environment file.

### H2. Give SQLite controlled write access

The current code hardcodes its SQLite file under `/opt/finova/data/auth.sqlite3` and enables WAL mode (which also needs sidecar files). A practical **demo-only** workaround is to allow writing to the `data/` directory while leaving code root-owned:

```bash
chown finova:finova /opt/finova/data
chmod 0700 /opt/finova/data
install -d -o root -g root -m 0755 /etc/systemd/system/finova.service.d
cat > /etc/systemd/system/finova.service.d/10-auth-state.conf <<'EOF'
[Service]
ReadWritePaths=/opt/finova/data
EOF
systemctl daemon-reload
systemctl cat finova
```

`ProtectSystem=strict` still applies outside this path. **Caveat:** granting directory write permissions means the service can rename or remove other files in `data/`, including the fictional workbook. A stronger subsequent code change should make the auth DB path configurable, use `/var/lib/finova/auth.sqlite3` with a systemd `StateDirectory`, and remove this broad write exception. **That code change is not included in this documentation-only update.**

### H3. Deploy, then test the *new* hosted login

Follow Part I to deploy the tested updated source. Restart the service and inspect logs (without printing passwords):

```bash
systemctl restart finova
systemctl is-active finova
journalctl -u finova -n 50 --no-pager
```

End-to-end acceptance checklist: nginx operator password -> email login page -> request code -> receive via SMTP -> verify code -> financial dashboard -> upload synthetic CSV/PDF -> investigate anomaly -> download PDF report -> logout -> confirm session ended. Refresh and verify email login restoration. Test two different email users in separate browser profiles and verify their uploaded financial records are isolated.

If code email requests return 503, investigate `SMTP_*`, SQLite permissions/ownership and logs; do not expose credentials. **Auth users/session hashes persist in SQLite**, but **financial uploads and results remain in memory** and reset when the service restarts.

## I. Safe GitHub-to-Akamai updates (manual deployment)

**GitHub push is not an automatic server deployment.** Finish development and tests on Windows, commit/merge to GitHub `main`, then SSH to Debian. Before touching the live files:

```bash
cd /root/finova-source
git status --short
git pull --ff-only origin main
git log -1 --oneline
python3 -m unittest discover -s tests -v
```

If tests fail, **do not deploy**. Node.js browser smoke tests are optional: `node tests/test_auth_ui.js` and `node tests/test_story_reset.js`. Also review source diffs and secrets before updating.

**Before an update**, stop the service and keep a **root-only backup** (the archive may contain private SQLite authentication state, so never commit or share it):

```bash
install -d -o root -g root -m 0700 /root/finova-backups
systemctl stop finova
STAMP=$(date +%Y%m%d-%H%M%S)
tar -czf "/root/finova-backups/finova-$STAMP.tgz" -C /opt finova
chmod 0600 "/root/finova-backups/finova-$STAMP.tgz"
```

Copy the *reviewed commit* into the deployed folder and re-apply read-only code permissions **plus** the new auth database state permissions:

```bash
git -C /root/finova-source archive HEAD | tar -x -C /opt/finova --no-same-owner
chown -R root:root /opt/finova
chmod -R go-w /opt/finova
chown finova:finova /opt/finova/data
chmod 0700 /opt/finova/data
find /opt/finova/data -maxdepth 1 -type f -name 'auth.sqlite3*' -exec chown finova:finova {} +
systemctl start finova
systemctl is-active finova
journalctl -u finova -n 30 --no-pager
```

**Warning:** `git archive` extraction into an existing folder does not delete files that the new commit removed; review deletions and migrations. The systemd `ReadWritePaths` drop-in must be present for the new login version. If a release fails, stop the service, preserve logs, and restore the prior known-good code and state from a protected backup. The website address and SSL cert normally stay the same after code updates.

## J. Checks and troubleshooting

| Symptom | Explanation / what to check |
| --- | --- |
| `install: ... not recognized` | You're in Windows PowerShell because SSH disconnected. Reconnect before Linux commands. |
| `python: command not found` | Debian provides `python3`. |
| `ssh: Connection timed out` | Use **Linode IP as destination**; verify cloud firewall attached, saved, Accept TCP 22 from current laptop public IP. |
| Fingerprint question | Verify in LISH with `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` before `yes`. |
| `TcpTestSucceeded : False` | Check firewall, network source, and sshd. Ping failure alone is not definitive. |
| Backend `/api/health` direct returns 403 | **Expected**; the nginx proxy token is absent. |
| Public HTTPS returns 401 | **Expected** when nginx operator Basic Auth is not supplied. |
| After operator login app returns 401 | Updated FINOVA email-login cookie is absent/expired; complete email verification. |
| Email send returns 503 | SMTP credential, Gmail restrictions, or SQLite directory permissions; inspect server logs. |
| Public HTTPS returns 502 | Check `systemctl is-active finova`, listener on 127.0.0.1:8000, and `journalctl -u finova`. |
| Certificate warning | Check `nginx -t`, configured domain and Let's Encrypt renewal, don't bypass browser warnings. |
| Git push did not change page | Deploy Git checkout to `/opt/finova`, restart service, hard refresh. |
| PDF extraction unavailable | Verify `pdfinfo`, `pdftotext`, `pdftoppm`, `tesseract`, then restart. |
| Workshop AI 401 | Check **team** `hk_...` key, not Linode Personal Access Token. |

Useful Debian checks:

```bash
systemctl status finova --no-pager
systemctl status nginx --no-pager
ss -ltnp | grep -E ':(80|443|8000)'
nginx -t
journalctl -u finova -n 50 --no-pager
certbot certificates
certbot renew --dry-run
```

## K. Security, costs, and handover

- **Restricted demo only** with fictional data. `http.server` is not a hardened production financial web server. Evaluate further user/data isolation, privacy, secure serving, monitoring, and backups before accepting real business records.
- Never put secrets or runtime auth SQLite in GitHub. `tools/check_secrets.py` requires a Git checkout. The uploaded ZIP has **no `.git` history**, so it cannot prove that a past credential is clean.
- Existing `deploy/README.md` flags a **credential-shaped value** in historical commit `8df8a1e`. If genuine, coordinate with repository owners to **revoke/rotate** the exposed key; cleaning recent source alone does not clean history. Don't display the old key.
- DuckDNS and Let's Encrypt are free services, **not free cloud compute**. Monitor Linode plan pricing, event credits/expiry, uptime, and teardown. Stopping a Linode does not automatically stop its billing.
- Keep protected records of the Linode owner, current source commit, team member SSH public keys, domain account, certificate renewal results, account recovery, and backup/restore plan.
- Do not regenerate matching proxy credentials casually; do not share passwords in screenshots or README examples.

**Companion files:** [README.md](README.md) (business/product), [README_TECHNOLOGY.md](README_TECHNOLOGY.md) (tech and modules), [architecture.txt](architecture.txt) (ASCII diagram), and [deploy/README.md](deploy/README.md) (original Ubuntu-oriented deployment template). This configuration README records the **Debian + DuckDNS + Certbot webroot** path actually used.
