#!/bin/sh
# One-time VPS bootstrap (Ubuntu 24.04): docker, firewall, deploy user layout.
set -eu
apt-get update && apt-get install -y ca-certificates curl git ufw
curl -fsSL https://get.docker.com | sh
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
mkdir -p /opt/kanalchi && echo "clone the repo into /opt/kanalchi, copy infra/.env.example to infra/.env, fill it, then: make deploy"
