#!/usr/bin/env bash
# Baja scripts de deploy/vm-ghcr desde GitHub main. No borra credentials.env.
# Uso: cd ~/nilo-api && ./bootstrap.sh
# Codigo API: solo ./deploy.sh (no hace falta bootstrap cada vez).
set -euo pipefail

REPO="${NILO_BOOTSTRAP_REPO:-NeoVisionsAI/NILO-backend}"
BRANCH="${NILO_BOOTSTRAP_BRANCH:-main}"
BASE="https://raw.githubusercontent.com/${REPO}/${BRANCH}/deploy/vm-ghcr"

SCRIPT_PATH="${BASH_SOURCE[0]}"
if [[ -n "$SCRIPT_PATH" && -f "$SCRIPT_PATH" ]]; then
  DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
else
  DIR="${NILO_DEPLOY_DIR:-$PWD}"
fi

FILES="compose.yaml deploy.sh configure.sh update.sh run.sh credentials.env.example nilo-api-vm.service README.md"

curl_fetch() {
  url="$1"
  out="$2"
  if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN}" "$url" -o "$out"
  else
    curl -fsSL "$url" -o "$out"
  fi
}

mkdir -p "$DIR"
cd "$DIR"

echo "==> Descargando deploy/vm-ghcr desde ${REPO}@${BRANCH} hacia ${DIR}"

missing=0
for f in $FILES; do
  if ! curl_fetch "${BASE}/${f}" "$f"; then
    echo "AVISO: fallo al descargar ${f}" >&2
    missing=$((missing + 1))
  fi
done

if curl_fetch "${BASE}/bootstrap.sh" "bootstrap.sh.new"; then
  if bash -n "bootstrap.sh.new"; then
    chmod +x "bootstrap.sh.new"
    mv "bootstrap.sh.new" "bootstrap.sh"
  else
    echo "AVISO: bootstrap remoto invalido; se mantiene el local." >&2
    rm -f "bootstrap.sh.new"
    missing=$((missing + 1))
  fi
else
  echo "AVISO: no se pudo descargar bootstrap.sh" >&2
  missing=$((missing + 1))
fi

chmod +x deploy.sh update.sh run.sh bootstrap.sh 2>/dev/null || true
if [[ -f configure.sh ]]; then
  chmod +x configure.sh
fi

if [[ ! -f credentials.env ]]; then
  cp credentials.env.example credentials.env
  echo "==> Creado credentials.env"
else
  echo "==> credentials.env sin cambios"
fi

if [[ "$missing" -gt 0 ]]; then
  echo "==> Terminado con errores. Revisa que main tenga deploy/vm-ghcr en GitHub." >&2
  exit 1
fi

echo "==> OK. Codigo API: ./deploy.sh   Scripts: ./bootstrap.sh o ./update.sh"
