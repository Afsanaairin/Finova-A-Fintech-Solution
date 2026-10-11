#!/bin/sh
# Install root-owned in /etc/letsencrypt/renewal-hooks/deploy/finova-nginx.
set -eu
/usr/sbin/nginx -t
/usr/bin/systemctl reload nginx
