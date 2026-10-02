#!/usr/bin/env bash
#
# Menú interactivo para crear o editar credentials.env (VM + Mongo/MinIO en el host).
#
#   ./configure.sh
#   CREDENTIALS_FILE=/ruta/credentials.env ./configure.sh
#
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRED="${CREDENTIALS_FILE:-$DIR/credentials.env}"
EXAMPLE="${CRED}.example"
[[ -f "$EXAMPLE" ]] || EXAMPLE="$DIR/credentials.env.example"

# Valores en memoria (se cargan del fichero si existe)
declare -A V=(
  [NILO_INFRA_HOST]=""
  [MINIO_PUBLIC_HOST]=""
  [MONGODB_PORT]="27018"
  [MINIO_API_PORT]="9002"
  [MONGODB_ADMIN_USER]="admin"
  [MONGODB_ADMIN_PASSWORD]=""
  [MONGODB_DB]="nilo"
  [MONGODB_APP_USER]="nilo"
  [MONGODB_APP_PASSWORD]=""
  [MONGODB_PROVISION]="true"
  [MINIO_ACCESS_KEY]=""
  [MINIO_SECRET_KEY]=""
  [JWT_SECRET_KEY]=""
  [ENCRYPTION_MASTER_KEY]=""
  [ROOT_EMAIL]="root@niloai.net"
  [ROOT_PASSWORD]=""
  [SEED_USERS]="false"
  [CORS_ORIGINS]=""
  [NILO_API_IMAGE]="ghcr.io/neovisionsai/nilo-backend:latest"
)

load_credentials() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  local line key val
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -z "$line" || "$line" != *=* ]] && continue
    key="${line%%=*}"
    val="${line#*=}"
    key="${key%"${key##*[![:space:]]}"}"
    if [[ -v "V[$key]" ]]; then
      V["$key"]="$val"
    fi
  done <"$f"
}

prompt() {
  local key="$1" label="$2" default="${3:-}" secret="${4:-0}"
  local current="${V[$key]:-$default}"
  local input
  if [[ "$secret" == "1" ]]; then
    if [[ -n "$current" ]]; then
      read -r -s -p "$label [Enter = mantener actual]: " input
      echo ""
    else
      read -r -s -p "$label: " input
      echo ""
    fi
  else
    if [[ -n "$current" ]]; then
      read -r -p "$label [$current]: " input
    else
      read -r -p "$label: " input
    fi
  fi
  if [[ -n "${input:-}" ]]; then
    V["$key"]="$input"
  elif [[ -n "$current" ]]; then
    V["$key"]="$current"
  elif [[ -n "$default" ]]; then
    V["$key"]="$default"
  fi
}

prompt_yes_no() {
  local key="$1" label="$2" default="${3:-false}"
  local current="${V[$key]:-$default}"
  local hint="s/N"
  [[ "$current" == "true" ]] && hint="S/n"
  local input
  read -r -p "$label ($hint): " input
  input="${input:-}"
  case "${input,,}" in
    s|si|y|yes|true|1) V["$key"]="true" ;;
    n|no|false|0) V["$key"]="false" ;;
    "") V["$key"]="$current" ;;
    *) V["$key"]="$current" ;;
  esac
}

gen_secret_urlsafe() {
  python3 -c "import secrets; print(secrets.token_urlsafe(48))" 2>/dev/null \
    || openssl rand -base64 48 | tr -d '/+=' | head -c 64
}

gen_encryption_key() {
  python3 -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())" 2>/dev/null \
    || openssl rand -base64 32
}

save_credentials() {
  local tmp
  tmp="$(mktemp)"
  cat >"$tmp" <<EOF
# Generado por configure.sh — no versionar.
# $(date -Iseconds 2>/dev/null || date)

# --- Infra (Mongo + MinIO en el host) ---
NILO_INFRA_HOST=${V[NILO_INFRA_HOST]}
MINIO_PUBLIC_HOST=${V[MINIO_PUBLIC_HOST]}
MONGODB_PORT=${V[MONGODB_PORT]}
MINIO_API_PORT=${V[MINIO_API_PORT]}

# --- MongoDB ---
MONGODB_ADMIN_USER=${V[MONGODB_ADMIN_USER]}
MONGODB_ADMIN_PASSWORD=${V[MONGODB_ADMIN_PASSWORD]}
MONGODB_DB=${V[MONGODB_DB]}
MONGODB_APP_USER=${V[MONGODB_APP_USER]}
MONGODB_APP_PASSWORD=${V[MONGODB_APP_PASSWORD]}
MONGODB_PROVISION=${V[MONGODB_PROVISION]}

# --- MinIO ---
MINIO_ACCESS_KEY=${V[MINIO_ACCESS_KEY]}
MINIO_SECRET_KEY=${V[MINIO_SECRET_KEY]}

# --- Seguridad ---
JWT_SECRET_KEY=${V[JWT_SECRET_KEY]}
ENCRYPTION_MASTER_KEY=${V[ENCRYPTION_MASTER_KEY]}

# --- Root API (bootstrap) ---
ROOT_EMAIL=${V[ROOT_EMAIL]}
ROOT_PASSWORD=${V[ROOT_PASSWORD]}
SEED_USERS=${V[SEED_USERS]}

EOF
  if [[ -n "${V[CORS_ORIGINS]}" ]]; then
    echo "CORS_ORIGINS=${V[CORS_ORIGINS]}" >>"$tmp"
  fi
  if [[ -n "${V[NILO_API_IMAGE]}" && "${V[NILO_API_IMAGE]}" != "ghcr.io/neovisionsai/nilo-backend:latest" ]]; then
    echo "NILO_API_IMAGE=${V[NILO_API_IMAGE]}" >>"$tmp"
  fi
  chmod 600 "$tmp"
  mv "$tmp" "$CRED"
  echo "Guardado: $CRED (permisos 600)"
}

mask() {
  local s="$1"
  [[ ${#s} -le 4 ]] && echo "****" && return
  echo "${s:0:2}****${s: -2}"
}

show_summary() {
  echo ""
  echo "=== Resumen (secretos enmascarados) ==="
  echo "  NILO_INFRA_HOST=${V[NILO_INFRA_HOST]}"
  echo "  MINIO_PUBLIC_HOST=${V[MINIO_PUBLIC_HOST]}"
  echo "  MONGODB_PORT=${V[MONGODB_PORT]}  MINIO_API_PORT=${V[MINIO_API_PORT]}"
  echo "  Mongo admin=${V[MONGODB_ADMIN_USER]} / $(mask "${V[MONGODB_ADMIN_PASSWORD]}")"
  echo "  Mongo db=${V[MONGODB_DB]} app=${V[MONGODB_APP_USER]} / $(mask "${V[MONGODB_APP_PASSWORD]}")"
  echo "  MONGODB_PROVISION=${V[MONGODB_PROVISION]}"
  echo "  MinIO key=$(mask "${V[MINIO_ACCESS_KEY]}") secret=$(mask "${V[MINIO_SECRET_KEY]}")"
  echo "  ROOT=${V[ROOT_EMAIL]} / $(mask "${V[ROOT_PASSWORD]}")"
  echo "  SEED_USERS=${V[SEED_USERS]}"
  echo "  Imagen: ${V[NILO_API_IMAGE]}"
  echo ""
}

section_infra() {
  echo ""
  echo "--- Infra: host con Mongo y MinIO ---"
  prompt NILO_INFRA_HOST "IP o hostname del host (visto desde esta VM)"
  if [[ -z "${V[MINIO_PUBLIC_HOST]}" ]]; then
    V[MINIO_PUBLIC_HOST]="${V[NILO_INFRA_HOST]}"
  fi
  prompt MINIO_PUBLIC_HOST "IP/DNS para URLs presignadas MinIO (clientes/nilo-node)"
  prompt MONGODB_PORT "Puerto Mongo en el host" "${V[MONGODB_PORT]}"
  prompt MINIO_API_PORT "Puerto API MinIO en el host" "${V[MINIO_API_PORT]}"
}

section_mongo() {
  echo ""
  echo "--- MongoDB ---"
  prompt MONGODB_ADMIN_USER "Usuario admin Mongo" "${V[MONGODB_ADMIN_USER]}"
  prompt MONGODB_ADMIN_PASSWORD "Contraseña admin Mongo" "" 1
  prompt MONGODB_DB "Nombre de la base de datos" "${V[MONGODB_DB]}"
  prompt MONGODB_APP_USER "Usuario de aplicación" "${V[MONGODB_APP_USER]}"
  prompt MONGODB_APP_PASSWORD "Contraseña usuario aplicación" "" 1
  prompt_yes_no MONGODB_PROVISION "¿Provisionar usuario app al arrancar la API?" "${V[MONGODB_PROVISION]}"
}

section_minio() {
  echo ""
  echo "--- MinIO ---"
  prompt MINIO_ACCESS_KEY "MINIO access key (usuario)" "" 1
  prompt MINIO_SECRET_KEY "MINIO secret key (contraseña)" "" 1
}

section_security() {
  echo ""
  echo "--- Seguridad (JWT y cifrado de datos) ---"
  local gen
  read -r -p "¿Generar JWT_SECRET_KEY aleatorio? (s/N): " gen
  if [[ "${gen,,}" == "s" || "${gen,,}" == "si" ]]; then
    V[JWT_SECRET_KEY]="$(gen_secret_urlsafe)"
    echo "  JWT generado."
  else
    prompt JWT_SECRET_KEY "JWT_SECRET_KEY" "" 1
  fi
  read -r -p "¿Generar ENCRYPTION_MASTER_KEY aleatorio? (s/N): " gen
  if [[ "${gen,,}" == "s" || "${gen,,}" == "si" ]]; then
    V[ENCRYPTION_MASTER_KEY]="$(gen_encryption_key)"
    echo "  ENCRYPTION_MASTER_KEY generado (guárdalo; sin él no hay datos)."
  else
    prompt ENCRYPTION_MASTER_KEY "ENCRYPTION_MASTER_KEY (base64)" "" 1
  fi
}

section_root() {
  echo ""
  echo "--- Usuario root de la API (bootstrap) ---"
  prompt ROOT_EMAIL "Email root" "${V[ROOT_EMAIL]}"
  prompt ROOT_PASSWORD "Contraseña root API" "" 1
  prompt_yes_no SEED_USERS "¿Crear usuarios demo al arrancar?" "${V[SEED_USERS]}"
}

section_advanced() {
  echo ""
  echo "--- Avanzado ---"
  prompt CORS_ORIGINS "CORS_ORIGINS (opcional, separado por comas)"
  prompt NILO_API_IMAGE "Imagen Docker GHCR" "${V[NILO_API_IMAGE]}"
}

wizard_full() {
  echo ""
  echo "=== Asistente completo credentials.env ==="
  section_infra
  section_mongo
  section_minio
  section_security
  section_root
  show_summary
  read -r -p "¿Guardar? (S/n): " ok
  ok="${ok:-S}"
  if [[ "${ok,,}" != "n" && "${ok,,}" != "no" ]]; then
    save_credentials
  fi
}

test_ports() {
  local host="${V[NILO_INFRA_HOST]}"
  if [[ -z "$host" ]]; then
    echo "Configura NILO_INFRA_HOST primero (menú 2)."
    return 1
  fi
  echo "Probando TCP desde esta VM hacia $host ..."
  if command -v nc >/dev/null 2>&1; then
    nc -zv -w 3 "$host" "${V[MONGODB_PORT]}" 2>&1 || true
    nc -zv -w 3 "$host" "${V[MINIO_API_PORT]}" 2>&1 || true
  else
    echo "Instala netcat: sudo apt install -y netcat-openbsd"
  fi
}

test_health() {
  local url="${1:-http://127.0.0.1:8001/health}"
  if ! command -v curl >/dev/null 2>&1; then
    echo "Falta curl."
    return 1
  fi
  echo "GET $url"
  curl -s "$url" | python3 -m json.tool 2>/dev/null || curl -s "$url"
  echo ""
}

run_deploy() {
  if [[ ! -x "$DIR/deploy.sh" ]]; then
    echo "No se encuentra $DIR/deploy.sh"
    return 1
  fi
  CREDENTIALS_FILE="$CRED" "$DIR/deploy.sh"
}

main_menu() {
  while true; do
    echo ""
    echo "========== NILO configure.sh =========="
    echo "  Fichero: $CRED"
    echo "  1) Asistente completo (recomendado 1ª vez)"
    echo "  2) Infra (IP host, puertos, MinIO público)"
    echo "  3) MongoDB"
    echo "  4) MinIO"
    echo "  5) Seguridad (JWT, cifrado)"
    echo "  6) Usuario root API"
    echo "  7) Avanzado (CORS, imagen GHCR)"
    echo "  8) Ver resumen"
    echo "  9) Guardar credentials.env"
    echo " 10) Probar puertos al host (nc)"
    echo " 11) Probar /health (API en :8001)"
    echo " 12) Ejecutar ./deploy.sh"
    echo "  0) Salir"
    echo "========================================"
    local choice
    read -r -p "Opción: " choice
    case "$choice" in
      1) wizard_full ;;
      2) section_infra ;;
      3) section_mongo ;;
      4) section_minio ;;
      5) section_security ;;
      6) section_root ;;
      7) section_advanced ;;
      8) show_summary ;;
      9) save_credentials ;;
      10) test_ports ;;
      11) test_health ;;
      12) run_deploy ;;
      0|q|Q) echo "Chao."; exit 0 ;;
      *) echo "Opción no válida." ;;
    esac
  done
}

if [[ ! -f "$CRED" && -f "$EXAMPLE" ]]; then
  echo "No hay $CRED — se usará $EXAMPLE como referencia de defaults."
fi

load_credentials "$CRED"
if [[ ! -f "$CRED" ]]; then
  load_credentials "$EXAMPLE"
fi

if [[ "${1:-}" == "--wizard" ]]; then
  wizard_full
  exit 0
fi

main_menu
