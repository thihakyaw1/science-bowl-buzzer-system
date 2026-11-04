#!/usr/bin/env bash
set -euo pipefail
cd /home/venicesciencebowl/science-bowl-buzzers
test -x .venv/bin/python
test -f data/one_channel.db
test -d /sys/class/net/eth0
command -v nmcli >/dev/null
sudo -v

# Require stopping the foreground server before taking over its GPIO/port.
if ! systemctl is-active --quiet science-bowl.service && ss -ltn 'sport = :8080' | grep -q ':8080'; then
    echo 'Stop the existing scoring server with Ctrl+C, then run this setup again.'
    exit 1
fi

if nmcli -g connection.id connection show science-bowl-direct >/dev/null 2>&1; then
    echo 'Existing science-bowl-direct profile: verifying its address.'
    test "$(nmcli -g ipv4.addresses connection show science-bowl-direct)" = '192.168.77.2/24'
else
    sudo nmcli connection add type ethernet ifname eth0 con-name science-bowl-direct \
        ipv4.method manual ipv4.addresses 192.168.77.2/24 ipv4.never-default yes \
        ipv6.method disabled connection.autoconnect yes connection.autoconnect-priority 100
fi
sudo nmcli connection up science-bowl-direct

if test -f /etc/systemd/system/science-bowl.service; then
    sudo cp -p /etc/systemd/system/science-bowl.service "/etc/systemd/system/science-bowl.service.backup-$(date +%Y%m%d%H%M%S)"
fi
sudo tee /etc/systemd/system/science-bowl.service >/dev/null <<'UNIT'
[Unit]
Description=Science Bowl Buzzer Logger
After=local-fs.target

[Service]
Type=simple
User=venicesciencebowl
WorkingDirectory=/home/venicesciencebowl/science-bowl-buzzers
ExecStart=/home/venicesciencebowl/science-bowl-buzzers/.venv/bin/python run_app.py --host 0.0.0.0 --port 8080 --db data/one_channel.db --mcp23017 --mcp-address 0x27 --reset-gpio 18 --reset-pulse-ms 1000
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=3
KillSignal=SIGINT
TimeoutStopSec=15

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable science-bowl.service
sudo systemctl restart science-bowl.service
sleep 2
systemctl status science-bowl.service --no-pager
curl --max-time 5 --fail http://127.0.0.1:8080/api/state
printf '\nPi ready at http://192.168.77.2:8080/\n'
