#!/usr/bin/env bash
#
# Despliega NILO backend con un solo comando.
#
# MongoDB, MinIO y la API corren en Docker. No hace falta instalar Mongo en el
# host: el contenedor mongo se crea al arrancar y la API provisiona el usuario
# de aplicación (nilo) al iniciar (MONGODB_PROVISION=true).
#
# Uso:
#   ./deploy.sh                  # levantar todo
#   ./deploy.sh --install-docker # instalar Docker (Debian/Ubuntu) y levantar
#   ./deploy.sh --down           # parar y quitar contenedores
#   ./deploy.sh --down -v        # además borrar volúmenes (reset Mongo/MinIO)
#   ./deploy.sh --logs           # seguir logs de la API
#   ./deploy.sh --status         # estado de contenedores
#   ./deploy.sh --fix-docker-config  # quitar credsStore/credHelpers rotos
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CREDENTIALS_FILE="${CREDENTIALS_FILE:-$ROOT_DIR/credentials.env}"
CREDENTIALS_EXAMPLE="$ROOT_DIR/credentials.env.example"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"

API_HOST_PORT="${API_HOST_PORT:-8001}"
MONGO_HOST_PORT="${MONGO_HOST_PORT:-27018}"
MINIO_API_PORT="${MINIO_API_PORT:-9002}"
MINIO_CONSOLE_PORT="${MINIO_CONSOLE_PORT:-9003}"
HEALTH_URL="http://localhost:${API_HOST_PORT}/health"
HEALTH_RETRIES="${HEALTH_RETRIES:-90}"
HEALTH_SLEEP="${HEALTH_SLEEP:-2}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}==>${NC} $*"; }
warn()  { echo -e "${YELLOW}!!>${NC} $*" >&2; }
error() { echo -e "${RED}ERR>${NC} $*" >&2; }

usage() {
  sed -n '2,16p' "$0" | sed 's/^# \?//'
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    error "Falta el comando '$1'."
    return 1
  fi
}

docker_compose() {
  # shellcheck disable=SC2086
  docker compose --env-file "$CREDENTIALS_FILE" -f "$COMPOSE_FILE" "$@"
}

# Linux hosts copied from Docker Desktop often ship credsStore/credHelpers that
# break public image pulls with GPG errors. Use an isolated empty config unless
# the user opts out (NILO_KEEP_DOCKER_CONFIG=1).
use_clean_docker_config() {
  if [[ "${NILO_KEEP_DOCKER_CONFIG:-0}" == "1" ]]; then
    return 0
  fi
  local nocreds="${TMPDIR:-/tmp}/docker-nilo-nocreds"
  mkdir -p "$nocreds"
  printf '%s\n' '{}' >"$nocreds/config.json"
  export DOCKER_CONFIG="$nocreds"
}

docker_config_is_broken() {
  local cfg="$1"
  [[ -f "$cfg" ]] || return 1
  grep -qE '"credsStore"|"credHelpers"' "$cfg" 2>/dev/null
}

setup_docker_config() {
  local user_config="${HOME}/.docker/config.json"
  if docker_config_is_broken "$user_config"; then
    use_clean_docker_config
    warn "Docker config con credsStore/credHelpers detectado en ${user_config}."
    warn "Usando DOCKER_CONFIG=${DOCKER_CONFIG} (imágenes públicas, sin login)."
    warn "Arreglo permanente: ./deploy.sh --fix-docker-config"
    return 0
  fi
  # Sin config rota, igualmente evita helpers si DOCKER_CONFIG no está fijado.
  if [[ -z "${DOCKER_CONFIG:-}" ]]; then
    use_clean_docker_config
  fi
}

fix_docker_config_permanent() {
  local cfg="${HOME}/.docker/config.json"
  if [[ ! -f "$cfg" ]]; then
    info "No existe ${cfg}; nada que arreglar."
    return 0
  fi
  if ! docker_config_is_broken "$cfg"; then
    info "Config OK (sin credsStore/credHelpers)."
    return 0
  fi
  require_command python3
  local backup="${cfg}.bak.$(date +%Y%m%d%H%M%S)"
  cp "$cfg" "$backup"
  python3 - "$cfg" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    cfg = json.load(f)
cfg.pop("credsStore", None)
cfg.pop("credHelpers", None)
with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
PY
  info "Eliminados credsStore/credHelpers de ${cfg}"
  info "Backup: ${backup}"
  info "Vuelve a ejecutar: ./deploy.sh"
}

compose_up_with_retry() {
  local log
  log="$(mktemp)"
  if docker_compose up --build -d >"$log" 2>&1; then
    cat "$log"
    rm -f "$log"
    return 0
  fi
  cat "$log" >&2
  if grep -qiE 'gpg|credentials|credsStore|credHelpers|error getting credentials' "$log"; then
    warn "Fallo por credential helpers de Docker; reintentando con config limpia..."
    use_clean_docker_config
    rm -f "$log"
    docker_compose up --build -d
    return $?
  fi
  rm -f "$log"
  return 1
}

install_docker_debian() {
  if command -v docker >/dev/null 2>&1; then
    info "Docker ya está instalado: $(docker --version)"
    return 0
  fi

  if [[ "$(id -u)" -ne 0 ]]; then
    error "Para instalar Docker ejecuta: sudo ./deploy.sh --install-docker"
    exit 1
  fi

  info "Instalando Docker y Docker Compose plugin (Debian/Ubuntu)..."
  apt-get update -qq
  apt-get install -y docker.io docker-compose-plugin curl
  systemctl enable --now docker
  info "Docker instalado: $(docker --version)"
}

ensure_docker() {
  require_command docker || {
    error "Docker no está instalado. Ejecuta: ./deploy.sh --install-docker (con sudo)"
    exit 1
  }
  docker info >/dev/null 2>&1 || {
    error "Docker no responde. ¿Está el daemon activo? Prueba: sudo systemctl start docker"
    error "Si acabas de instalar Docker, puede que necesites cerrar sesión y volver a entrar (grupo docker)."
    exit 1
  }
  docker compose version >/dev/null 2>&1 || {
    error "Falta 'docker compose'. Instala el plugin: apt install docker-compose-plugin"
    exit 1
  }
}

ensure_credentials() {
  if [[ ! -f "$CREDENTIALS_FILE" ]]; then
    if [[ ! -f "$CREDENTIALS_EXAMPLE" ]]; then
      error "No existe $CREDENTIALS_FILE ni $CREDENTIALS_EXAMPLE"
      exit 1
    fi
    cp "$CREDENTIALS_EXAMPLE" "$CREDENTIALS_FILE"
    info "Creado $CREDENTIALS_FILE desde el ejemplo (valores de desarrollo)."
    warn "En producción, edita las claves y contraseñas antes de desplegar."
  fi

  # Comprueba variables mínimas.
  local required=(
    MONGODB_ADMIN_PASSWORD
    MONGODB_APP_PASSWORD
    MINIO_KMS_KEY
    JWT_SECRET_KEY
    ENCRYPTION_MASTER_KEY
    ROOT_EMAIL
    ROOT_PASSWORD
  )
  local missing=0
  for var in "${required[@]}"; do
    if ! grep -qE "^${var}=" "$CREDENTIALS_FILE"; then
      error "Falta ${var}= en $CREDENTIALS_FILE"
      missing=1
    fi
  done
  if [[ "$missing" -ne 0 ]]; then
    exit 1
  fi
}

read_credential() {
  local key="$1"
  grep -E "^${key}=" "$CREDENTIALS_FILE" | head -n1 | cut -d= -f2- | tr -d '\r'
}

check_ports() {
  local port="$1"
  local label="$2"
  if command -v ss >/dev/null 2>&1; then
    if ss -tln | grep -q ":${port} "; then
      warn "Puerto ${port} (${label}) ya está en uso. Si no es NILO, puede fallar el arranque."
    fi
  fi
}

wait_for_health() {
  require_command curl
  info "Esperando API en ${HEALTH_URL} (máx. $((HEALTH_RETRIES * HEALTH_SLEEP))s)..."
  local i
  for ((i = 1; i <= HEALTH_RETRIES; i++)); do
    if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
      info "API lista."
      return 0
    fi
    sleep "$HEALTH_SLEEP"
  done
  error "La API no respondió a tiempo. Revisa logs: ./deploy.sh --logs"
  docker_compose ps
  return 1
}

print_summary() {
  local admin_pass app_pass root_email root_pass clinician_email clinician_pass

  admin_pass="$(read_credential MONGODB_ADMIN_PASSWORD)"
  app_pass="$(read_credential MONGODB_APP_PASSWORD)"
  root_email="$(read_credential ROOT_EMAIL)"
  root_pass="$(read_credential ROOT_PASSWORD)"
  clinician_email="$(read_credential SEED_CLINICIAN_EMAIL || true)"
  clinician_pass="$(read_credential SEED_CLINICIAN_PASSWORD || true)"

  echo
  info "NILO desplegado correctamente."
  echo
  echo "  API:            http://localhost:${API_HOST_PORT}"
  echo "  Swagger:        http://localhost:${API_HOST_PORT}/docs"
  echo "  Health:         ${HEALTH_URL}"
  echo
  echo "  Mongo (Compass): mongodb://admin:${admin_pass}@localhost:${MONGO_HOST_PORT}/?authSource=admin"
  echo "  BD aplicación:   nilo  (usuario app: nilo / ${app_pass})"
  echo
  echo "  MinIO S3:       http://localhost:${MINIO_API_PORT}"
  echo "  MinIO consola:  http://localhost:${MINIO_CONSOLE_PORT}"
  echo
  echo "  Login root:     ${root_email} / ${root_pass}"
  if [[ -n "${clinician_email:-}" ]]; then
    echo "  Login clínico:  ${clinician_email} / ${clinician_pass}"
  fi
  echo
  echo "  Probar login:"
  echo "    curl -X POST http://localhost:${API_HOST_PORT}/api/v1/auth/login \\"
  echo "      -H 'Content-Type: application/x-www-form-urlencoded' \\"
  echo "      -d 'username=${root_email}&password=${root_pass}'"
  echo
  warn "Mongo y MinIO corren en Docker; el usuario 'nilo' se crea/actualiza solo al arrancar la API."
  warn "Si cambias MONGODB_ADMIN_PASSWORD tras el primer despliegue, resetea volúmenes: ./deploy.sh --down -v"
}

cmd_deploy() {
  cd "$ROOT_DIR"
  setup_docker_config
  ensure_docker
  ensure_credentials

  check_ports "$API_HOST_PORT" "API"
  check_ports "$MONGO_HOST_PORT" "MongoDB"
  check_ports "$MINIO_API_PORT" "MinIO"
  check_ports "$MINIO_CONSOLE_PORT" "MinIO consola"

  info "Construyendo y levantando servicios (mongo, minio, api)..."
  compose_up_with_retry

  wait_for_health
  print_summary
}

cmd_down() {
  cd "$ROOT_DIR"
  setup_docker_config
  ensure_docker
  ensure_credentials
  if [[ "${1:-}" == "-v" ]]; then
    info "Parando servicios y eliminando volúmenes (datos Mongo/MinIO)..."
    docker_compose down -v
  else
    info "Parando servicios..."
    docker_compose down
  fi
}

cmd_logs() {
  cd "$ROOT_DIR"
  setup_docker_config
  ensure_docker
  ensure_credentials
  docker_compose logs -f "${@:-api}"
}

cmd_status() {
  cd "$ROOT_DIR"
  setup_docker_config
  ensure_docker
  ensure_credentials
  docker_compose ps
}

main() {
  case "${1:-}" in
    -h|--help|help)
      usage
      ;;
    --install-docker)
      install_docker_debian
      shift || true
      cmd_deploy
      ;;
    --down)
      cmd_down "${2:-}"
      ;;
    --logs)
      shift || true
      cmd_logs "$@"
      ;;
    --status)
      cmd_status
      ;;
    --fix-docker-config)
      fix_docker_config_permanent
      ;;
    "")
      cmd_deploy
      ;;
    *)
      error "Opción desconocida: $1"
      usage
      exit 1
      ;;
  esac
}

main "$@"
