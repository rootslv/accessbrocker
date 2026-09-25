#!/bin/bash
# Run once before the demo — creates the CA key that will sign
# all temporary SSH certificates.
set -e

mkdir -p ca
if [ -f ca/ca_key ]; then
  echo "CA already exists at ./ca/ca_key — skipping."
else
  ssh-keygen -t ed25519 -f ca/ca_key -N "" -C "access-broker-ca"
  echo "CA created: ca/ca_key (private), ca/ca_key.pub (public)"
fi

echo ""
echo "CA public key (copy it to the test server):"
cat ca/ca_key.pub
