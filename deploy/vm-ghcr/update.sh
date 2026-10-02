#!/usr/bin/env bash
#
# UN SOLO COMANDO en la VM tras commit+push en GitHub:
#
#   cd ~/nilo-api && ./update.sh
#
# Hace: (1) baja scripts de deploy/vm-ghcr desde main  (2) pull imagen GHCR + reinicia API
#
#   ./update.sh          # todo (lo normal)
#   ./update.sh image    # solo imagen API (mas rapido si solo cambio codigo)
#   ./update.sh scripts  # solo scripts (configure, compose, etc.)
#
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  sed -n '2,13p' "$0" | sed 's/^# \?//'
}

ensure_bootstrap() {
  if [[ -x "$DIR/bootstrap.sh" ]]; then
    return 0
  fi
  echo "==> Descargando bootstrap.sh (primera vez o recuperacion) ..."
  curl -fsSL "https://raw.githubusercontent.com/NeoVisionsAI/NILO-backend/main/deploy/vm-ghcr/bootstrap.sh" \
    -o "$DIR/bootstrap.sh"
  chmod +x "$DIR/bootstrap.sh"
}

run_scripts() {
  ensure_bootstrap
  "$DIR/bootstrap.sh"
}

run_image() {
  if [[ ! -x "$DIR/deploy.sh" ]]; then
    echo "Falta deploy.sh; ejecuta: ./update.sh" >&2
    exit 1
  fi
  CREDENTIALS_FILE="${CREDENTIALS_FILE:-$DIR/credentials.env}" "$DIR/deploy.sh"
}

run_all() {
  echo "=========================================="
  echo " NILO update — scripts + imagen API"
  echo "=========================================="
  echo ""
  echo "==> Paso 1/2: scripts desde GitHub (main) ..."
  if ensure_bootstrap; then
    if ! "$DIR/bootstrap.sh"; then
      echo ""
      echo "AVISO: bootstrap incompleto (¿push a main aun no visible?). Sigo con la imagen." >&2
    fi
  fi
  echo ""
  echo "==> Paso 2/2: imagen GHCR + contenedor API ..."
  run_image
  echo ""
  echo "==> Listo. Health: curl -s http://127.0.0.1:8001/health | python3 -m json.tool"
}

case "${1:-}" in
  ""|all|both|sync|update)
    run_all
    ;;
  scripts|bootstrap|pull-scripts)
    run_scripts
    ;;
  image|app|pull-image|deploy)
    run_image
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "Opcion desconocida: $1" >&2
    usage
    exit 1
    ;;
esac
