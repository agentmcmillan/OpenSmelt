#!/bin/bash
# Generate mTLS certificates for OpenSmelt
# Creates a CA. Use provision-client.sh to generate per-device client certs.
set -e

CERT_DIR="$(dirname "$0")/client-certs"
mkdir -p "$CERT_DIR"
cd "$CERT_DIR"

# --- Generate CA (Certificate Authority) ---
if [ ! -f ca.key ]; then
    echo "=== Generating Certificate Authority ==="
    openssl genrsa -out ca.key 4096
    openssl req -new -x509 -days 3650 -key ca.key -out ca.crt \
        -subj "/C=US/O=OpenSmelt/CN=OpenSmelt CA"
    echo "CA created: ca.crt + ca.key"
else
    echo "CA already exists, skipping..."
fi

echo ""
echo "=== Certificate Authority Ready ==="
echo ""
echo "Files in ${CERT_DIR}:"
ls -la ca.crt ca.key 2>/dev/null
echo ""
echo "Next steps:"
echo "  1. Generate client certs:  ./caddy/provision-client.sh my-device 'My Device'"
echo "  2. Distribute .p12 files to devices securely"
echo "  3. Uncomment the mTLS block in caddy/Caddyfile"
