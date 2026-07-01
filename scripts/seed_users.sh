#!/usr/bin/env bash
#
# Seed one user of each type (root, clinician, patient) through the NILO API.
#
# - The ROOT user is auto-created on API startup from ROOT_EMAIL/ROOT_PASSWORD.
# - This script logs in as root and creates a CLINICIAN, then logs in as that
#   clinician and creates a PATIENT (exercising the real permission rules).
#
# Credentials (emails + passwords) are read from an env file. By default it
# reads credentials.env.example; override with ENV_FILE=... The API base URL
# can be overridden with API_URL (default http://localhost:8000/api/v1).
#
# Usage:
#   ./scripts/seed_users.sh
#   ENV_FILE=credentials.env API_URL=http://localhost:8000/api/v1 ./scripts/seed_users.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

ENV_FILE="${ENV_FILE:-$ROOT_DIR/credentials.env.example}"
API_URL="${API_URL:-http://localhost:8000/api/v1}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: env file not found: $ENV_FILE" >&2
  exit 1
fi

command -v curl >/dev/null 2>&1 || { echo "ERROR: 'curl' is required" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: 'python3' is required" >&2; exit 1; }

# Read a KEY=VALUE from the env file (last occurrence wins).
get_env() {
  local key="$1" default="${2:-}"
  local val
  val="$(grep -E "^${key}=" "$ENV_FILE" | tail -n1 | cut -d= -f2- || true)"
  if [[ -z "$val" ]]; then echo "$default"; else echo "$val"; fi
}

ROOT_EMAIL="$(get_env ROOT_EMAIL root@nilo.local)"
ROOT_PASSWORD="$(get_env ROOT_PASSWORD changeme)"
CLIN_EMAIL="$(get_env SEED_CLINICIAN_EMAIL clinician@nilo.local)"
CLIN_PASSWORD="$(get_env SEED_CLINICIAN_PASSWORD changeme)"
PAT_EMAIL="$(get_env SEED_PATIENT_EMAIL patient@nilo.local)"
PAT_PASSWORD="$(get_env SEED_PATIENT_PASSWORD changeme)"

echo "==> API:      $API_URL"
echo "==> Env file: $ENV_FILE"

# Extract a JSON field from stdin without needing jq.
json_get() { python3 -c "import sys,json;
try:
    d=json.load(sys.stdin)
except Exception:
    print(''); sys.exit(0)
print(d.get('$1','') if isinstance(d,dict) else '')"; }

login() {
  # $1=email $2=password -> prints access token (empty on failure)
  curl -sS -X POST "$API_URL/auth/login" \
    --data-urlencode "username=$1" \
    --data-urlencode "password=$2" | json_get access_token
}

create_user() {
  # $1=bearer token  $2=json body  $3=label
  local code body
  body="$(curl -sS -o /tmp/nilo_seed_resp.json -w '%{http_code}' \
    -X POST "$API_URL/users" \
    -H "Authorization: Bearer $1" \
    -H "Content-Type: application/json" \
    --data "$2")"
  code="$body"
  if [[ "$code" == "201" ]]; then
    echo "    created $3 (201)"
  elif [[ "$code" == "409" ]]; then
    echo "    $3 already exists (409), skipping"
  else
    echo "ERROR creating $3 (HTTP $code):" >&2
    cat /tmp/nilo_seed_resp.json >&2; echo >&2
    exit 1
  fi
}

echo "==> Logging in as root ($ROOT_EMAIL)"
ROOT_TOKEN="$(login "$ROOT_EMAIL" "$ROOT_PASSWORD")"
if [[ -z "$ROOT_TOKEN" ]]; then
  echo "ERROR: root login failed. Is the API running and root bootstrapped?" >&2
  exit 1
fi
echo "    root OK"

echo "==> Creating CLINICIAN ($CLIN_EMAIL) as root"
CLIN_BODY=$(cat <<JSON
{
  "name": "Clara",
  "lastname": "Clinician",
  "type_user": "clinician",
  "email": "$CLIN_EMAIL",
  "password": "$CLIN_PASSWORD",
  "phone": "+34600000001",
  "country": "ES",
  "address": "Av. Salud 1",
  "zip": "28001",
  "clinician_profile": {
    "type_clinician": "doctor",
    "institution": "Hospital NILO",
    "location": "Madrid",
    "phone_work": "+34910000000"
  }
}
JSON
)
create_user "$ROOT_TOKEN" "$CLIN_BODY" "clinician"

echo "==> Logging in as clinician ($CLIN_EMAIL)"
CLIN_TOKEN="$(login "$CLIN_EMAIL" "$CLIN_PASSWORD")"
if [[ -z "$CLIN_TOKEN" ]]; then
  echo "ERROR: clinician login failed." >&2
  exit 1
fi
echo "    clinician OK"

echo "==> Creating PATIENT ($PAT_EMAIL) as clinician"
PAT_BODY=$(cat <<JSON
{
  "name": "Pablo",
  "lastname": "Patient",
  "type_user": "patient",
  "email": "$PAT_EMAIL",
  "password": "$PAT_PASSWORD",
  "phone": "+34600000002",
  "country": "ES",
  "address": "Calle Recuperacion 5",
  "zip": "28002",
  "patient_profile": {
    "type_patient": "adult",
    "relative_address": "Calle Familiar 123",
    "relative_contact": "+34600999999"
  }
}
JSON
)
create_user "$CLIN_TOKEN" "$PAT_BODY" "patient"

echo
echo "Done. Seeded users:"
echo "  root      -> $ROOT_EMAIL"
echo "  clinician -> $CLIN_EMAIL"
echo "  patient   -> $PAT_EMAIL (registered by the clinician)"
