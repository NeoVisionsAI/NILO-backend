#!/usr/bin/env bash
#
# Tras commit+push en GitHub, actualiza la VM sin copiar ficheros a mano.
#
#   ./update.sh scripts   # baja deploy/vm-ghcr desde main (bootstrap)
#   ./update.sh image     # docker pull + reinicia API (deploy.sh)
#   ./update.sh           # scripts + imagen (recomendado tras push grande)
#   ./update.sh --help
#
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  sed -n '2,9p' "$0" | sed 's/^# \?//'
}

run_scripts() {
  if [[ ! -x "$DIR/bootstrap.sh" ]]; then
    echo "Falta bootstrap.sh; recupera con:" >&2
    echo "  curl -fsSL https://raw.githubusercontent.com/NeoVisionsAI/NILO-backend/main/deploy/vm-ghcr/bootstrap.sh -o bootstrap.sh" >&2
    echo "  chmod +x bootstrap.sh && ./bootstrap.sh" >&2
    exit 1
  fi
  exec "$DIR/bootstrap.sh"
}

run_image() {
  if [[ ! -x "$DIR/deploy.sh" ]]; then
    echo "Falta deploy.sh; ejecuta primero: ./update.sh scripts" >&2
    exit 1
  fi
  exec "$DIR/deploy.sh"
}

case "${1:-all}" in
  scripts|bootstrap|pull-scripts)
    run_scripts
    ;;
  image|app|pull-image|deploy)
    run_image
    ;;
  all|both)
    "$DIR/bootstrap.sh"
    exec "$DIR/deploy.sh"
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
