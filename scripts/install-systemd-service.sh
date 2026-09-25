#!/usr/bin/env bash
#
# Instala un servicio systemd para arrancar NILO al boot y recuperarse de fallos.
#
# Uso (desde la raíz del repo):
#   sudo ./scripts/install-systemd-service.sh              # Docker api-only (VM)
#   sudo ./scripts/install-systemd-service.sh --full     # Docker stack completo
#   sudo ./scripts/install-systemd-service.sh --native   # uvicorn en .venv (sin Docker)
#   sudo ./scripts/install-systemd-service.sh --uninstall
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_NAME="nilo-backend.service"
UNIT_DEST="/etc/systemd/system/${UNIT_NAME}"
MODE="docker-api"
SERVICE_USER="${SUDO_USER:-${USER:-root}}"
API_PORT="${API_PORT:-8001}"
ENABLE_ONLY=0

usage() {
  sed -n '2,12p' "$0" | sed 's/^# \?//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --full) MODE="docker-full"; shift ;;
    --native) MODE="native"; shift ;;
    --user)
      SERVICE_USER="$2"
      shift 2
      ;;
    --enable-only)
      ENABLE_ONLY=1
      shift
      ;;
    --uninstall)
      systemctl stop "$UNIT_NAME" 2>/dev/null || true
      systemctl disable "$UNIT_NAME" 2>/dev/null || true
      rm -f "$UNIT_DEST"
      systemctl daemon-reload
      echo "Desinstalado: $UNIT_NAME"
      exit 0
      ;;
    -h|--help) usage 0 ;;
    *) echo "Opción desconocida: $1" >&2; usage 1 ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Ejecuta con sudo: sudo $0 ..." >&2
  exit 1
fi

if [[ ! -f "$ROOT_DIR/credentials.env" ]]; then
  echo "Falta $ROOT_DIR/credentials.env (cp credentials.env.example credentials.env)" >&2
  exit 1
fi

resolve_docker_compose() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo "docker compose"
    return 0
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
    return 0
  fi
  echo "No se encontró 'docker compose' ni 'docker-compose'." >&2
  exit 1
}

case "$MODE" in
  docker-api)
    COMPOSE_FILE="docker-compose.api-only.yml"
    TEMPLATE="$ROOT_DIR/deploy/systemd/nilo-backend-docker.service"
    if ! groups "$SERVICE_USER" 2>/dev/null | grep -q '\bdocker\b'; then
      echo "AVISO: el usuario $SERVICE_USER no está en el grupo 'docker'."
      echo "  sudo usermod -aG docker $SERVICE_USER && newgrp docker"
    fi
    ;;
  docker-full)
    COMPOSE_FILE="docker-compose.yml"
    TEMPLATE="$ROOT_DIR/deploy/systemd/nilo-backend-docker.service"
    ;;
  native)
    TEMPLATE="$ROOT_DIR/deploy/systemd/nilo-backend-native.service"
    if [[ ! -x "$ROOT_DIR/.venv/bin/uvicorn" ]]; then
      echo "Falta .venv con uvicorn en $ROOT_DIR (.venv/bin/uvicorn)" >&2
      exit 1
    fi
    ;;
esac

DOCKER_COMPOSE=""
if [[ "$MODE" == docker-* ]]; then
  DOCKER_COMPOSE="$(resolve_docker_compose)"
fi

tmp="$(mktemp)"
sed \
  -e "s|@INSTALL_DIR@|${ROOT_DIR}|g" \
  -e "s|@SERVICE_USER@|${SERVICE_USER}|g" \
  -e "s|@COMPOSE_FILE@|${COMPOSE_FILE}|g" \
  -e "s|@DOCKER_COMPOSE@|${DOCKER_COMPOSE}|g" \
  -e "s|@API_PORT@|${API_PORT}|g" \
  "$TEMPLATE" >"$tmp"

install -m 0644 "$tmp" "$UNIT_DEST"
rm -f "$tmp"

systemctl daemon-reload
systemctl enable "$UNIT_NAME"
if [[ "$ENABLE_ONLY" == "1" ]]; then
  echo ""
  echo "Instalado y habilitado al arranque: $UNIT_NAME (modo: $MODE, sin reiniciar stack)"
  echo "  systemctl status $UNIT_NAME"
  echo "  journalctl -u nilo-backend -f"
  exit 0
fi

systemctl restart "$UNIT_NAME" 2>/dev/null || systemctl start "$UNIT_NAME"

echo ""
echo "Instalado y activado: $UNIT_NAME (modo: $MODE)"
echo "  systemctl status $UNIT_NAME"
echo "  journalctl -u $UNIT_NAME -f"
