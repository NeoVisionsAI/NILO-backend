#!/usr/bin/env bash
# Descarga solo los ficheros de despliegue (sin clonar el repo ni bajar app/).
#
#   mkdir -p ~/nilo-api && cd ~/nilo-api
#   curl -fsSL https://raw.githubusercontent.com/NeoVisionsAI/NILO-backend/main/deploy/vm-ghcr/bootstrap.sh | bash
#
# Actualizar scripts en la misma carpeta (no borra credentials.env):
#   ./bootstrap.sh
#
# Actualizar imagen API tras push de codigo:
#   ./deploy.sh
set -euo pipefail

REPO="${NILO_BOOTSTRAP_REPO:-NeoVisionsAI/NILO-backend}"
BRANCH="${NILO_BOOTSTRAP_BRANCH:-main}"
BASE="https://raw.githubusercontent.com/${REPO}/${BRANCH}/deploy/vm-ghcr"
DIR="${NILO_DEPLOY_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]:-.}")" 2>/dev/null && pwd || echo "$PWD")}"

if [[ ! -f "$DIR/bootstrap.sh" && -z "${BASH_SOURCE:-}" ]]; then
  DIR="$PWD"
fi

# bootstrap.sh al final, como .new + bash -n, para no romper el script en ejecucion
FILES=(
  compose.yaml
  deploy.sh
  configure.sh
  run.sh
  credentials.env.example
  nilo-api-vm.service
  README.md
)

curl_fetch() {
  local url="$1" out="$2"
  if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN}" "$url" -o "$out"
  else
    curl -fsSL "$url" -o "$out"
  fi
}

mkdir -p "$DIR"
cd "$DIR"
echo "==> Descargando deploy/vm-ghcr desde ${REPO}@${BRANCH} -> $DIR"

missing=0
for f in "${FILES[@]}"; do
  if ! curl_fetch "${BASE}/${f}" "$f"; then
    echo "AVISO: no se pudo descargar $f (404 en GitHub?)" >&2
    missing=$((missing + 1))
  fi
done

bootstrap_new="bootstrap.sh.new"
if curl_fetch "${BASE}/bootstrap.sh" "$bootstrap_new"; then
  if bash -n "$bootstrap_new"; then
    chmod +x "$bootstrap_new"
    mv "$bootstrap_new" bootstrap.sh
  else
    echo "AVISO: bootstrap descargado invalido; se conserva el local." >&2
    rm -f "$bootstrap_new"
  fi
else
  echo "AVISO: no se pudo actualizar bootstrap.sh" >&2
  missing=$((missing + 1))
fi

chmod +x deploy.sh run.sh bootstrap.sh 2>/dev/null || true
[[ -f configure.sh ]] && chmod +x configure.sh

if [[ ! -f credentials.env ]]; then
  cp credentials.env.example credentials.env
  echo "==> Creado credentials.env - editalo antes de ./deploy.sh"
else
  echo "==> credentials.env ya existe (no sobrescrito)"
fi

if [[ "$missing" -gt 0 ]]; then
  echo "==> Completado con avisos. Faltan ficheros en ${REPO}@${BRANCH} - haz push a main o copia por scp." >&2
  exit 1
fi

echo "==> Listo. Siguiente: ./configure.sh, docker login ghcr.io si hace falta, ./deploy.sh"
