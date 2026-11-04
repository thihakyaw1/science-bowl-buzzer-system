#!/usr/bin/env bash
set -euo pipefail
cd /home/venicesciencebowl/science-bowl-buzzers
test -f "$HOME/science-bowl-update.tar.gz"
test -x .venv/bin/python
sudo -v
stamp=$(date +%Y%m%d-%H%M%S)
backup="$HOME/science-bowl-backup-$stamp.tar.gz"
sudo systemctl stop science-bowl.service
trap 'sudo systemctl start science-bowl.service' EXIT
tar --exclude='./.venv' --exclude='./outputs' -czf "$backup" .
tar -xzf "$HOME/science-bowl-update.tar.gz" -C .
.venv/bin/python -m pip install 'pypdf>=4.0'
.venv/bin/python -m compileall -q science_bowl_buzzer
sudo systemctl start science-bowl.service
sleep 3
curl --fail --max-time 5 http://127.0.0.1:8080/api/state
printf '\nUpdate installed. Backup: %s\n' "$backup"
