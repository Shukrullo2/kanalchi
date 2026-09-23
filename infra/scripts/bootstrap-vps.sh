#!/bin/sh
# One-time bootstrap for a fresh Ubuntu 24.04 droplet (run as root):
#   docker + compose plugin, a swap file (the stack is sized for 8 GB and peaks close to it),
#   log rotation for containers, unattended security updates, and a firewall that only
#   admits SSH, HTTP and HTTPS.
set -eu

apt-get update
apt-get install -y ca-certificates curl git ufw unattended-upgrades fail2ban
curl -fsSL https://get.docker.com | sh

# Container logs: compose.yml caps the app services, this caps everything else.
mkdir -p /etc/docker
if [ ! -f /etc/docker/daemon.json ]; then
  cat > /etc/docker/daemon.json <<'JSON'
{ "log-driver": "json-file", "log-opts": { "max-size": "20m", "max-file": "5" } }
JSON
  systemctl restart docker
fi

# 4 GB swap: Postgres, three workers, MinIO and Next.js together sit near the 8 GB line.
if [ ! -f /swapfile ]; then
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo "/swapfile none swap sw 0 0" >> /etc/fstab
  sysctl -w vm.swappiness=10
  echo "vm.swappiness=10" > /etc/sysctl.d/99-kanalchi.conf
fi

dpkg-reconfigure -f noninteractive unattended-upgrades
systemctl enable --now fail2ban

ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

mkdir -p /opt/kanalchi
cat <<'TXT'

bootstrap: done. Next:
  git clone <repo> /opt/kanalchi && cd /opt/kanalchi
  cp infra/.env.example infra/.env   # fill it in; `make gen-keys` prints APP_MASTER_KEY / SESSION_SECRET
  make deploy
See README.md → "Production" for DNS, Telegram and first-login steps.
TXT
