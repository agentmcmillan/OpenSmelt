#!/bin/bash
# Securely provision a new mTLS client certificate
# Usage: ./provision-client.sh <client-name> <common-name> [--deploy <user@host>]
set -e

CERT_DIR="$(dirname "$0")/client-certs"
CA_KEY="${CERT_DIR}/ca.key"
CA_CRT="${CERT_DIR}/ca.crt"

usage() {
    echo "Usage: $0 <client-name> <common-name> [--deploy user@host:path]"
    echo ""
    echo "Examples:"
    echo "  $0 my-laptop 'My Laptop'"
    echo "  $0 dev-server 'Dev Server' --deploy user@192.168.1.100:~/.mcp-certs"
    echo ""
    echo "The script will:"
    echo "  1. Generate a 2048-bit RSA key pair"
    echo "  2. Create a CSR and sign it with the OpenSmelt CA"
    echo "  3. Bundle into a .p12 for easy import"
    echo "  4. Optionally deploy via SCP to a remote host"
    echo "  5. Print connection config for your MCP client"
    exit 1
}

if [ -z "$1" ] || [ -z "$2" ]; then
    usage
fi

NAME="$1"
CN="$2"
DEPLOY_TARGET=""

# Parse optional --deploy flag
shift 2
while [[ $# -gt 0 ]]; do
    case $1 in
        --deploy)
            DEPLOY_TARGET="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

# Ensure CA exists
if [ ! -f "$CA_KEY" ] || [ ! -f "$CA_CRT" ]; then
    echo "ERROR: CA not found. Run generate-certs.sh first."
    exit 1
fi

# Check if cert already exists
if [ -f "${CERT_DIR}/${NAME}.crt" ]; then
    echo "WARNING: Certificate '${NAME}' already exists."
    read -p "Regenerate? This will revoke the old cert. [y/N] " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "Aborted."
        exit 0
    fi
fi

echo "=== Provisioning client certificate: ${NAME} ==="

# Generate key with secure permissions
umask 077
openssl genrsa -out "${CERT_DIR}/${NAME}.key" 2048

# Generate CSR
openssl req -new \
    -key "${CERT_DIR}/${NAME}.key" \
    -out "${CERT_DIR}/${NAME}.csr" \
    -subj "/C=US/O=OpenSmelt/OU=MCP Clients/CN=${CN}"

# Sign with CA (valid 365 days)
openssl x509 -req -days 365 \
    -in "${CERT_DIR}/${NAME}.csr" \
    -CA "$CA_CRT" -CAkey "$CA_KEY" -CAcreateserial \
    -out "${CERT_DIR}/${NAME}.crt" \
    -extfile <(printf "basicConstraints=CA:FALSE\nkeyUsage=digitalSignature\nextendedKeyUsage=clientAuth")

# Create PKCS12 bundle with random password
P12_PASS=$(openssl rand -hex 16)
openssl pkcs12 -export \
    -out "${CERT_DIR}/${NAME}.p12" \
    -inkey "${CERT_DIR}/${NAME}.key" \
    -in "${CERT_DIR}/${NAME}.crt" \
    -certfile "$CA_CRT" \
    -passout "pass:${P12_PASS}"

# Cleanup CSR
rm -f "${CERT_DIR}/${NAME}.csr"

# Verify the cert
echo ""
echo "=== Certificate Details ==="
openssl x509 -in "${CERT_DIR}/${NAME}.crt" -noout -subject -issuer -dates

# Deploy if requested
if [ -n "$DEPLOY_TARGET" ]; then
    echo ""
    echo "=== Deploying to ${DEPLOY_TARGET} ==="
    IFS=':' read -r HOST PATH <<< "$DEPLOY_TARGET"
    REMOTE_PATH="${PATH:-~/.mcp-certs}"

    ssh "$HOST" "mkdir -p ${REMOTE_PATH} && chmod 700 ${REMOTE_PATH}"
    scp "${CERT_DIR}/${NAME}.crt" "${CERT_DIR}/${NAME}.key" "${CA_CRT}" "${HOST}:${REMOTE_PATH}/"
    ssh "$HOST" "chmod 600 ${REMOTE_PATH}/*.key"
    echo "Deployed to ${HOST}:${REMOTE_PATH}"
fi

echo ""
echo "=== Files Created ==="
echo "  ${CERT_DIR}/${NAME}.crt  (certificate)"
echo "  ${CERT_DIR}/${NAME}.key  (private key)"
echo "  ${CERT_DIR}/${NAME}.p12  (PKCS12 bundle)"
echo ""
echo "=== PKCS12 Password (save securely) ==="
echo "  ${P12_PASS}"
echo ""
echo "=== MCP Client Config ==="
echo "Add to your MCP client config:"
echo ""
cat << EOF
{
  "mcpServers": {
    "mcp-gateway": {
      "type": "http",
      "url": "https://YOUR_DOMAIN/gateway/mcp"
    }
  }
}
EOF
echo ""
echo "NOTE: The client must present the .crt/.key or .p12 when connecting via mTLS."
echo "For curl testing:"
echo "  curl --cert ${CERT_DIR}/${NAME}.crt --key ${CERT_DIR}/${NAME}.key https://YOUR_DOMAIN/health"
