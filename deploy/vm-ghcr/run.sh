#!/usr/bin/env bash
# Alias de deploy.sh (compatibilidad).
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/deploy.sh" "$@"
