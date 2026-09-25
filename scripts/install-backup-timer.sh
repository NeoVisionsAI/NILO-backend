#!/usr/bin/env bash
#
# Habilita copias de seguridad nocturnas (systemd timer).
#   sudo ./scripts/install-backup-timer.sh
#   sudo ./scripts/install-backup-timer.sh --uninstall
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
SERVICE_SRC="$ROOT_DIR/deploy/systemd/nilo-backup.service"
TIMER_SRC="$ROOT_DIR/deploy/systemd/nilo-backup.timer"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Ejecuta con sudo" >&2
  exit 1
fi

if [[ "${1:-}" == "--uninstall" ]]; then
  systemctl stop nilo-backup.timer 2>/dev/null || true
  systemctl disable nilo-backup.timer 2>/dev/null || true
  rm -f /etc/systemd/system/nilo-backup.service /etc/systemd/system/nilo-backup.timer
  systemctl daemon-reload
  echo "Timer de backup desinstalado."
  exit 0
fi

mkdir -p "$BACKUP_DIR"
chmod +x "$ROOT_DIR/scripts/backup-nightly.sh" "$ROOT_DIR/scripts/backup_minio_nonvideo.py"

tmp_svc="$(mktemp)"
sed \
  -e "s|@INSTALL_DIR@|${ROOT_DIR}|g" \
  -e "s|@BACKUP_DIR@|${BACKUP_DIR}|g" \
  "$SERVICE_SRC" >"$tmp_svc"
install -m 0644 "$tmp_svc" /etc/systemd/system/nilo-backup.service
rm -f "$tmp_svc"

install -m 0644 "$TIMER_SRC" /etc/systemd/system/nilo-backup.timer
systemctl daemon-reload
systemctl enable --now nilo-backup.timer
systemctl list-timers nilo-backup.timer --no-pager
echo "Backups programados (~03:15 UTC). Manual: sudo $ROOT_DIR/scripts/backup-nightly.sh"
