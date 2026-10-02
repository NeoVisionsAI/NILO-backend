#!/usr/bin/env bash
# Alias: tras cada push en GitHub, ejecuta esto en la VM.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/update.sh" "$@"
