#!/bin/sh
set -eu

mkdir -p /var/log/access-broker /run/sshd
timestamp=$(date -u '+%Y-%m-%dT%H:%M:%S+00:00')
printf '%s INFO nutricio-api service healthy\n%s ERROR nutricio-api timeout connecting to database\n' \
  "$timestamp" "$timestamp" > /var/log/access-broker/nutricio-api.log
printf '%s INFO vpn connection established\n%s WARN vpn retrying handshake\n' \
  "$timestamp" "$timestamp" > /var/log/access-broker/vpn.log
chmod 755 /var/log/access-broker
chmod 644 /var/log/access-broker/*.log
exec /usr/sbin/sshd -D -e
