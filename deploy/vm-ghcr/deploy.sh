#!/usr/bin/env bash
#
# VM sin código fuente: pull GHCR + contenedor API (Mongo/MinIO en otro host).
#
#   ./deploy.sh                  # pull + up -d (manual)
#   sudo ./deploy.sh --install-systemd   # arranque automático al boot (+ pull)
#   sudo ./deploy.sh --uninstall-systemd
#
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRED="${CREDENTIALS_FILE:-$DIR/credentials.env}"
UNIT_NAME="nilo-api-vm.service"
UNIT_DEST="/etc/systemd/system/${UNIT_NAME}"
export NILO_API_IMAGE="${NILO_API_IMAGE:-ghcr.io/neovisionsai/nilo-backend:latest}"

require_compose() {
  if ! docker compose version >/dev/null 2>&1; then
    echo "Se necesita 'docker compose'." >&2
    exit 1
  fi
}

require_credentials() {
  if [[ ! -f "$CRED" ]]; then
    echo "Falta $CRED — cp credentials.env.example credentials.env" >&2
    exit 1
  fi
}

compose() {
  docker compose --env-file "$CRED" "$@"
}

cmd_deploy() {
  require_compose
  require_credentials
  cd "$DIR"
  echo "==> Pull ${NILO_API_IMAGE}"
  compose pull api
  echo "==> Up (detached)"
  compose up -d
  echo "==> Listo. Health: curl -s http://127.0.0.1:8001/health"
}

# systemd mantiene compose en primer plano (Restart=always si cae).
cmd_foreground() {
  require_compose
  require_credentials
  cd "$DIR"
  echo "==> Pull ${NILO_API_IMAGE}"
  compose pull api || true
  exec docker compose --env-file "$CRED" up --remove-orphans
}

resolve_docker_compose() {
  if docker compose version >/dev/null 2>&1; then
    echo "docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
  else
    echo "No hay docker compose." >&2
    exit 1
  fi
}

cmd_install_systemd() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Ejecuta: sudo $0 --install-systemd" >&2
    exit 1
  fi
  require_credentials
  local service_user="${SUDO_USER:-root}"
  if [[ "$service_user" == "root" ]]; then
    service_user="${NILO_SERVICE_USER:-root}"
  fi
  if ! groups "$service_user" 2>/dev/null | grep -q '\bdocker\b'; then
    echo "AVISO: $service_user no está en el grupo docker." >&2
  fi
  chmod +x "$DIR/deploy.sh"
  local dc
  dc="$(resolve_docker_compose)"
  local tmp
  tmp="$(mktemp)"
  sed \
    -e "s|@INSTALL_DIR@|${DIR}|g" \
    -e "s|@SERVICE_USER@|${service_user}|g" \
    -e "s|@DOCKER_COMPOSE@|${dc}|g" \
    "$DIR/nilo-api-vm.service" >"$tmp"
  install -m 0644 "$tmp" "$UNIT_DEST"
  rm -f "$tmp"
  systemctl daemon-reload
  systemctl enable "$UNIT_NAME"
  systemctl restart "$UNIT_NAME" || systemctl start "$UNIT_NAME"
  echo "Instalado: $UNIT_NAME (usuario $service_user)"
  echo "  systemctl status $UNIT_NAME"
  echo "  journalctl -u $UNIT_NAME -f"
}

cmd_uninstall_systemd() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Ejecuta: sudo $0 --uninstall-systemd" >&2
    exit 1
  fi
  systemctl stop "$UNIT_NAME" 2>/dev/null || true
  systemctl disable "$UNIT_NAME" 2>/dev/null || true
  rm -f "$UNIT_DEST"
  systemctl daemon-reload
  echo "Desinstalado: $UNIT_NAME"
}

case "${1:-}" in
  --foreground)
    cmd_foreground
    ;;
  --install-systemd)
    cmd_install_systemd
    ;;
  --uninstall-systemd)
    cmd_uninstall_systemd
    ;;
  -h|--help)
    sed -n '2,8p' "$0" | sed 's/^# \?//'
    ;;
  ""|deploy|up)
    cmd_deploy
    ;;
  *)
    echo "Opción desconocida: $1" >&2
    exit 1
    ;;
esac
