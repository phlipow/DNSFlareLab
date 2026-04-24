#!/bin/bash

if [ "$EUID" -ne 0 ]; then
  echo "This script must be run as root. Please use sudo." >&2
  exit 1
fi

if [ "$1" == "--cleanup" ]; then
    echo "Starting cleanup of the lab..."

    echo "Deactivating current virtual environment..."
    deactivate 2>/dev/null || true

    echo "Removing iptables rule for port 0..."
    iptables -D OUTPUT -p tcp --dport 0 -j REJECT --reject-with tcp-reset 2>/dev/null || true

    echo "Restoring /etc/resolv.conf and restarting the network..."
    rm -f /etc/resolv.conf
    systemctl restart NetworkManager

    echo "Removing Chromium PoC's user dir"
    rm -rf /tmp/chromium-DNSFlare

    echo "Deactivating virtual environment..."
    deactivate 2>/dev/null || true

    echo "Cleanup completed."
    exit 0
fi

echo "Setting up the lab environment for the Chromium DNS Rebinding PoC..."

if [ "$1" == "--install" ]; then

    echo "Installing Chromium v133 (vulnerable version)"
    wget -q --show-progress "https://storage.googleapis.com/chromium-browser-snapshots/Linux_x64/1402768/chrome-linux.zip" -O /tmp/chrome-linux-v133.zip
    mkdir -p ./chrome_v133
    unzip -q /tmp/chrome-linux-v133.zip -d ./chrome_v133
    rm -f /tmp/chrome-linux-v133.zip
    echo "Chromium v133 installed in ./chrome_v133"

    python3 -m venv .venv
    ./.venv/bin/python -m pip install -q dnslib flask
fi

echo "Setting up iptables to block outgoing TCP connections to port 0"
iptables -C OUTPUT -p tcp --dport 0 -j REJECT --reject-with tcp-reset 2>/dev/null || iptables -A OUTPUT -p tcp --dport 0 -j REJECT --reject-with tcp-reset

echo "Setting up local DNS resolver to point to 127.0.0.1"
rm -f /etc/resolv.conf
echo "nameserver 127.0.0.1" > /etc/resolv.conf

echo "Activating the virtual enviroment"
source .venv/bin/activate

echo "Lab environment setup complete!"
echo "Next steps:"
echo "1. Terminal 1: sudo ./.venv/bin/python MyPoC.py [-h for help]"
echo "2. Terminal 2: sudo ./.venv/bin/python DNSFowarder.py"
echo "3. Terminal 3: ./chrome_v133/chrome-linux/chrome --user-data-dir=/tmp/chromium-DNSFlare --test-type --disable-background-timer-throttling --ignore-certificate-errors --no-sandbox --disable-gpu --explicitly-allowed-ports=0 --disable-features=dns-over-https --disable-host-cache"
echo "4 - In Chromium, navigate to 127.0.0.1 and observe the attack in action."
echo "5. Terminal 4: ./victim.sh <domain1> [domain2] ... to simulate the victim's device"
echo "To clean up the lab environment, run: sudo ./setup.sh --cleanup"