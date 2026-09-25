#!/usr/bin/env bash
#
# Copia de seguridad nocturna:
#   - MongoDB (base nilo completa: sesiones, vitales, metadatos de vídeo, etc.)
#   - MinIO: objetos del día UTC excepto categoría video (audio, landmarks, pain…)
#
# Uso:
#   ./scripts/backup-nightly.sh
#   ./scripts/backup-nightly.sh --date 2026-09-25
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CREDENTIALS_FILE="${CREDENTIALS_FILE:-$ROOT_DIR/credentials.env}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.yml}"
BACKUP_DATE="$(date -u +%Y-%m-%d)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)
      BACKUP_DATE="$2"
      shift 2
      ;;
    -h|--help)
      sed -n '2,12p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *)
      echo "Opción desconocida: $1" >&2
      exit 1
      ;;
  esac
done

# shellcheck disable=SC1090
source "$CREDENTIALS_FILE" 2>/dev/null || true

BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
TARGET="$BACKUP_DIR/$BACKUP_DATE"
MONGO_OUT="$TARGET/mongo"

mkdir -p "$MONGO_OUT"

compose() {
  docker compose --env-file "$CREDENTIALS_FILE" -f "$COMPOSE_FILE" "$@"
}

admin_user="${MONGODB_ADMIN_USER:-admin}"
admin_pass="${MONGODB_ADMIN_PASSWORD:-upaelo}"
db_name="${MONGODB_DB:-nilo}"

echo "==> Backup MongoDB -> $MONGO_OUT"
compose exec -T mongo mongodump \
  --username="$admin_user" \
  --password="$admin_pass" \
  --authenticationDatabase=admin \
  --db="$db_name" \
  --out="/tmp/nilo-mongo-dump" >/dev/null

compose cp "mongo:/tmp/nilo-mongo-dump/${db_name}" "$MONGO_OUT"
compose exec -T mongo rm -rf /tmp/nilo-mongo-dump >/dev/null || true

echo "==> Backup MinIO (sin video, día UTC $BACKUP_DATE)"
if compose ps --status running -q api >/dev/null 2>&1; then
  compose exec -T api python scripts/backup_minio_nonvideo.py \
    --date "$BACKUP_DATE" \
    --dest "/app/backups/$BACKUP_DATE/minio"
else
  (cd "$ROOT_DIR" && BACKUP_DIR="$BACKUP_DIR" python3 scripts/backup_minio_nonvideo.py --date "$BACKUP_DATE")
fi

echo "==> Purga backups > ${RETENTION_DAYS} días en $BACKUP_DIR"
find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +"$RETENTION_DAYS" -exec rm -rf {} + 2>/dev/null || true

echo "==> Backup completado: $TARGET"
