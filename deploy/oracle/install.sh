#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
test -s deploy/oracle/.env.production
test -s deploy/oracle/.env
sudo systemctl enable --now docker
sudo ufw allow 443/tcp
sudo ufw allow 8000/tcp
sudo docker compose --env-file deploy/oracle/.env -f deploy/oracle/compose.yaml up -d --build
curl --retry 15 --retry-delay 3 --retry-all-errors --fail http://127.0.0.1:8100/health/ready
