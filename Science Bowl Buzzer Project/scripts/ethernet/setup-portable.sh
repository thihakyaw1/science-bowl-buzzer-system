#!/usr/bin/env bash
set -euo pipefail
# Run on the Pi. eth0 must connect directly to ONE laptop, not a router/switch.
test "$(nmcli -g ipv4.addresses connection show science-bowl-direct)" = '192.168.77.2/24'
sudo apt-get update
sudo apt-get install -y dnsmasq-base
sudo install -d /etc/science-bowl
sudo tee /etc/science-bowl/dnsmasq.conf >/dev/null <<'CONFIG'
port=0
interface=eth0
bind-dynamic
dhcp-range=192.168.77.20,192.168.77.100,255.255.255.0,12h
dhcp-option=option:router
dhcp-option=option:dns-server
dhcp-authoritative
CONFIG
sudo tee /etc/systemd/system/science-bowl-dhcp.service >/dev/null <<'UNIT'
[Unit]
Description=Science Bowl direct Ethernet laptop address
After=NetworkManager.service
[Service]
ExecStart=/usr/sbin/dnsmasq --keep-in-foreground --conf-file=/etc/science-bowl/dnsmasq.conf
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
UNIT
sudo /usr/sbin/dnsmasq --test --conf-file=/etc/science-bowl/dnsmasq.conf
sudo systemctl daemon-reload
sudo systemctl enable --now science-bowl-dhcp.service
echo 'Direct Ethernet ready. Use automatic IPv4/DHCP on other laptops.'
echo 'Open http://192.168.77.2:8080/ after plugging into the Pi.'
