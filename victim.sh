#!/bin/bash

if [ "$#" -eq 0 ]; then
    echo "Usage: ./victim.sh <domain1> [domain2] ..."
    exit 1
fi

timestamp() {
    date +"{%H:%M:%S:%3N}"
}

echo "$(timestamp) Simulating victim's device"
echo "$(timestamp) Target domains: $@"
echo ""

while true; do
    for domain in "$@"; do
        echo "$(timestamp) [ACCESSING] $domain"
        dig @127.0.0.1 "$domain" +short > /dev/null 2>&1
        sleep 3
    done
done