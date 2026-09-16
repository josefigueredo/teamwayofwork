#!/usr/bin/env bash
# Generic local-board sync entrypoint. Configuration is read from <board-dir>/sync/.env.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOARD_DIR="${1:-board}"
shift || true
ENV_FILE="${BOARD_DIR}/sync/.env"

load_dotenv() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  set -a
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      local key="${BASH_REMATCH[1]}"
      local value="${BASH_REMATCH[2]}"
      if [[ "$value" =~ ^\"(.*)\"$ ]]; then value="${BASH_REMATCH[1]}"; fi
      if [[ "$value" =~ ^\'(.*)\'$ ]]; then value="${BASH_REMATCH[1]}"; fi
      export "$key=$value"
    fi
  done < "$file"
  set +a
}

load_dotenv "$ENV_FILE"
if [[ -n "${SSL_CERT_FILE:-}" && "${SSL_CERT_FILE}" == ~* ]]; then
  export SSL_CERT_FILE="${SSL_CERT_FILE/#\~/$HOME}"
fi
exec python3 "${SCRIPT_DIR}/sync_board.py" --board-dir "$BOARD_DIR" "$@"
