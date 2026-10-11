# Restricted FINOVA demo deployment

Nothing in this directory publishes the app. These are templates for a dedicated
Ubuntu Linux host with Python 3.10+, systemd, nginx and Certbot 2.3+. Keep `server.py` bound to
`127.0.0.1:8000`; only nginx may accept public traffic. Python explicitly cautions
against using [`http.server` in production](https://docs.python.org/3/library/http.server.html).
This setup supports a restricted demo with fictional data. A production service
still needs an appropriate application server and a reviewed account/data model.

The path is: browser -> authenticated HTTPS nginx -> private loopback FINOVA ->
optional HTTPS AI service. Do not use a tunnel, router port forward, container
port publication, or cloud ingress that sends public traffic directly to 8000.

## Prepare the account and release

Run these commands on the Linux server, from a reviewed source checkout.
The account has no login shell, home directory or administrative privileges.
The application cannot modify its root-owned code or data. Deploy only tracked
source; `git archive` excludes your local `.env` and the `.git` directory.

```sh
sudo apt-get update
sudo apt-get install python3 nginx apache2-utils ufw certbot
sudo useradd --system --user-group --no-create-home --shell /usr/sbin/nologin finova
sudo install -d -o root -g root -m 0755 /opt/finova
git archive HEAD | sudo tar -x -C /opt/finova --no-same-owner
sudo chown -R root:root /opt/finova
sudo chmod -R go-w /opt/finova
sudo install -d -o root -g www-data -m 0750 /etc/finova
sudo install -d -o root -g root -m 0755 /var/lib/acme
sudo install -o root -g root -m 0600 deploy/finova.env.example /etc/finova/finova.env
```

Commit/review these safeguards locally before archiving; `git archive HEAD` only
includes committed changes. Do not put populated secrets in the checkout.

Generate the proxy token without displaying it or including it in command
history. This creates a root-only environment value and matching root-only nginx
include. The token authenticates nginx to FINOVA; it is separate from the AI key.

```sh
sudo python3 - <<'PY'
from pathlib import Path
import secrets
import os
os.umask(0o077)
token = secrets.token_urlsafe(32)
env = Path('/etc/finova/finova.env')
env.write_text(env.read_text().replace('REPLACE_WITH_SERVER_GENERATED_TOKEN', token))
Path('/etc/finova/proxy-secret.conf').write_text(
    'proxy_set_header X-Finova-Proxy-Token "' + token + '";\n')
PY
sudoedit /etc/finova/finova.env
```

Set `FINOVA_PUBLIC_ORIGIN` to your HTTPS origin (no path). Add the AI key here
only if needed. The service uses its managed environment and ignores the
checkout's `.env` in proxy mode. systemd reads the root-only environment file
before dropping privileges; the `finova` user does not need file access.

Create a different Basic Auth username and a strong password for each operator.
`htpasswd` prompts for the password; do not pass it on the command line. Use `-c`
only for the first account. Revoke accounts by removing their htpasswd entries.
Sessions expire after one idle hour, are capped at 32, and are bound to the
authenticated username. Restarting FINOVA deletes every in-memory upload.

```sh
sudo htpasswd -cB /etc/finova/finova.htpasswd operator1
sudo chown root:www-data /etc/finova/finova.htpasswd
sudo chmod 0640 /etc/finova/finova.htpasswd
```

Basic Auth uses the browser's sign-in dialog. No passwords, proxy tokens, or AI
keys belong in `static/app.js` or `static/wrapped.js`. The public POST marker
`X-Finova-Request: 1` is a CSRF check, not an authentication secret. nginx
overwrites identity/proxy headers and removes the browser's Authorization
header before forwarding requests. Every route, including health, dashboard,
upload, reset, AI chat, connection test, and cover generation, requires sign-in.

## Firewall and HTTPS

Before enabling UFW, preserve your actual SSH management route. Substitute your
administrator CIDR and SSH port; keep a working console/SSH session open. Check
existing rules for broad allowances and remove any allowance for TCP 8000.
Apply the same policy to the cloud firewall/security group, including IPv6:
80/443 for nginx, management SSH only from your administrator network, no 8000.

```sh
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from YOUR_ADMIN_CIDR to any port YOUR_SSH_PORT proto tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 8000/tcp
sudo ufw enable
sudo ufw status numbered
```

Point your hostname's DNS at the server. Obtain a real certificate *before*
loading the HTTPS template. On a new dedicated host, stop nginx briefly and
use ACME standalone verification on port 80:

```sh
sudo systemctl stop nginx
sudo certbot certonly --standalone -d YOUR_HOSTNAME
```

Replace every `finova.example.com` in `deploy/nginx.conf` and
`deploy/finova-proxy.conf` with the same hostname used in `FINOVA_PUBLIC_ORIGIN`.
The templates assume HTTPS on port 443. Review other nginx virtual hosts so no
other site, alias, or static root can serve `/opt/finova` or `/etc/finova`.

```sh
sudo install -o root -g root -m 0644 deploy/finova-proxy.conf /etc/nginx/snippets/finova-proxy.conf
sudo install -o root -g root -m 0644 deploy/nginx.conf /etc/nginx/sites-available/finova
sudo ln -s /etc/nginx/sites-available/finova /etc/nginx/sites-enabled/finova
sudo install -o root -g root -m 0644 deploy/finova.service /etc/systemd/system/finova.service
sudo systemd-analyze verify /etc/systemd/system/finova.service
sudo systemctl daemon-reload
sudo systemctl enable --now finova
sudo nginx -t
sudo systemctl enable --now nginx
sudo install -o root -g root -m 0755 deploy/finova-renewal-hook.sh /etc/letsencrypt/renewal-hooks/deploy/finova-nginx
sudo certbot reconfigure --cert-name YOUR_HOSTNAME --webroot --webroot-path /var/lib/acme
sudo certbot renew --dry-run --run-deploy-hooks
```

The ACME challenge path on port 80 serves only `/var/lib/acme`; other HTTP paths
redirect to HTTPS. Keep automatic certificate renewal enabled; the deploy hook
reloads nginx after renewal so it picks up the new certificate. HSTS is enabled
for the FINOVA hostname. nginx applies connection/request limits and tighter
limits to AI endpoints; its request body limits match the backend.

## Verify before allowing users

From a separate machine, confirm 8000 cannot be reached over either IPv4 or
IPv6. On the server, `sudo ss -ltnp` must show FINOVA only at `127.0.0.1:8000`.
Inspect `sudo systemctl status finova` and `sudo systemd-analyze security finova`.

```sh
# Must redirect to your HTTPS origin.
curl -I http://YOUR_HOSTNAME/
# Must return 401 without credentials, for pages and EVERY sensitive API.
curl -i https://YOUR_HOSTNAME/api/dashboard
curl -i -X POST https://YOUR_HOSTNAME/api/cover
# Prompts for the password; must return 200 without disclosing secrets.
curl --user operator1 https://YOUR_HOSTNAME/api/health
# Backend access bypassing nginx must return 403, even from the server itself.
curl -i http://127.0.0.1:8000/api/dashboard
```

Use two operator accounts and separate browser profiles: upload a fictional CSV
in one, and confirm the other retains its own data. Verify that normal uploads
and local Q&A work; uploads over 12 MiB, malformed/multiple file parts, oversized
JSON, foreign Origins, and POSTs without `X-Finova-Request` fail. The importer
also caps decompressed ZIP bytes, ZIP entries, sheets, rows, columns, and cells,
and rejects XML entities. Files stay in memory; nginx may temporarily buffer
requests in its private temporary directory. Do not configure a public upload
directory. Rotate/restrict nginx logs and keep request bodies out of logs.

## Secrets and publication

Before pushing, run `python3 tools/check_secrets.py` to inspect all reachable local
Git history, the index, and non-ignored working files without printing secret values.
`.gitignore` excludes local environment files, populated deployment env files,
private key files, and htpasswd files. Placeholder-only examples are safe to
track. The browser calls FINOVA; only Python adds the AI Authorization header.

The audit found a credential-shaped value in `.env.example` in the initial
commit `8df8a1e` (blob `22394be54552`). The scanner deliberately fails while
that value remains in reachable Git history. Treat it as exposed and revoke or
rotate it with the provider before publication; this audit does not verify
whether the credential is active. It has not been printed or copied into the
current source. Repository owners must coordinate any history cleanup.

If a key ever appeared in a public commit, revoke/rotate it first. Removing it
from the latest commit does not remove it from history. Coordinate any history
cleanup with repository owners; do not publish the exposed key again.

These files have to be applied and checked on the actual host. Passing local
tests does not verify its firewall, certificate, service account, or cloud rules.
Reference: [nginx Basic Auth](https://nginx.org/en/docs/http/ngx_http_auth_basic_module.html),
[proxy headers](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_set_header),
and [request limits](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html).
