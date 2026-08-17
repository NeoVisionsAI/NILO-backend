#!/usr/bin/env bash
#
# Genera un certificado autofirmado para HTTPS en desarrollo (LAN/tablet).
#
# Incluye SAN para localhost, la IP del servidor y un hostname opcional.
# Los navegadores/tablets mostrarán aviso hasta que confíes en el certificado
# (o instales la CA con mkcert; ver abajo).
#
# Uso:
#   ./scripts/generate-dev-certs.sh
#   NILO_DEV_HOST=192.168.1.43 NILO_DEV_DNS=k8-master.local ./scripts/generate-dev-certs.sh
#   CERT_DIR=./certs ./scripts/generate-dev-certs.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CERT_DIR="${CERT_DIR:-$ROOT_DIR/certs}"
DEV_HOST="${NILO_DEV_HOST:-192.168.1.43}"
DEV_DNS="${NILO_DEV_DNS:-}"
DAYS="${CERT_DAYS:-825}"

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: falta '$1'" >&2
    exit 1
  }
}

require_command openssl

mkdir -p "$CERT_DIR"

san_entries=("DNS:localhost" "IP:127.0.0.1" "IP:${DEV_HOST}")
if [[ -n "$DEV_DNS" ]]; then
  san_entries+=("DNS:${DEV_DNS}")
fi

san_line=$(IFS=,; echo "${san_entries[*]}")

openssl_cnf="$(mktemp)"
trap 'rm -f "$openssl_cnf"' EXIT

cat >"$openssl_cnf" <<EOF
[req]
default_bits = 4096
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req

[dn]
CN = NILO Dev (${DEV_HOST})

[v3_req]
subjectAltName = ${san_line}
EOF

openssl req -x509 -nodes -newkey rsa:4096 -days "$DAYS" \
  -keyout "$CERT_DIR/key.pem" \
  -out "$CERT_DIR/cert.pem" \
  -config "$openssl_cnf" -extensions v3_req

chmod 600 "$CERT_DIR/key.pem"
chmod 644 "$CERT_DIR/cert.pem"

echo "Certificados generados en ${CERT_DIR}/"
echo "  cert.pem  (público)"
echo "  key.pem   (privado; no compartir)"
echo "SAN: ${san_line}"
echo
echo "API HTTPS (tras ./deploy.sh): https://${DEV_HOST}:8443/api/v1"
echo
echo "Confiar en el certificado:"
echo "  - PC: abrir https://${DEV_HOST}:8443/health y aceptar excepción, o"
echo "  - mkcert (recomendado para tablets): https://github.com/FiloSottile/mkcert"
echo "    mkcert -install && mkcert localhost 127.0.0.1 ${DEV_HOST} ${DEV_DNS}"
echo "    cp \$(mkcert -CAROOT)/rootCA.pem  # instalar rootCA en la tablet"
