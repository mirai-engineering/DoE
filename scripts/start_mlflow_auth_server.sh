#!/usr/bin/env sh
set -eu

: "${MLFLOW_BACKEND_STORE_URI:?MLFLOW_BACKEND_STORE_URI is required}"
: "${MLFLOW_ARTIFACT_ROOT:?MLFLOW_ARTIFACT_ROOT is required}"
: "${MLFLOW_FLASK_SERVER_SECRET_KEY:?MLFLOW_FLASK_SERVER_SECRET_KEY is required for MLflow basic-auth CSRF protection}"
: "${MLFLOW_AUTH_ADMIN_USERNAME:?MLFLOW_AUTH_ADMIN_USERNAME is required}"
: "${MLFLOW_AUTH_ADMIN_PASSWORD:?MLFLOW_AUTH_ADMIN_PASSWORD is required}"

if [ "${MLFLOW_AUTH_ADMIN_USERNAME}" = "admin" ] && [ "${MLFLOW_AUTH_ADMIN_PASSWORD}" = "password1234" ]; then
  echo "Refusing to start MLflow auth with the documented default admin password." >&2
  exit 1
fi

if [ "${MLFLOW_ALLOWED_HOSTS:-}" = "*" ] || [ -z "${MLFLOW_ALLOWED_HOSTS:-}" ]; then
  echo "Refusing to start MLflow auth proxy with wildcard or empty MLFLOW_ALLOWED_HOSTS." >&2
  exit 1
fi

if [ "${MLFLOW_CORS_ALLOWED_ORIGINS:-}" = "*" ] || [ -z "${MLFLOW_CORS_ALLOWED_ORIGINS:-}" ]; then
  echo "Refusing to start MLflow auth proxy with wildcard or empty MLFLOW_CORS_ALLOWED_ORIGINS." >&2
  exit 1
fi

AUTH_CONFIG_DIR="/tmp/mlflow-auth"
AUTH_CONFIG_PATH="${AUTH_CONFIG_DIR}/basic_auth.ini"
mkdir -p "${AUTH_CONFIG_DIR}"
chmod 700 "${AUTH_CONFIG_DIR}"

AUTH_DATABASE_URI=$(python3 - <<'PY'
import os
value = os.getenv("MLFLOW_AUTH_DATABASE_URI") or os.environ["MLFLOW_BACKEND_STORE_URI"]
# MLflow reads this with configparser interpolation enabled, so literal percent
# characters in URL-encoded database URIs must be escaped.
print(value.replace("%", "%%"))
PY
)

cat > "${AUTH_CONFIG_PATH}" <<EOF
[mlflow]
database_uri = ${AUTH_DATABASE_URI}
default_permission = ${MLFLOW_AUTH_DEFAULT_PERMISSION:-NO_PERMISSIONS}
grant_default_workspace_access = ${MLFLOW_AUTH_GRANT_DEFAULT_WORKSPACE_ACCESS:-false}
admin_username = ${MLFLOW_AUTH_ADMIN_USERNAME}
admin_password = ${MLFLOW_AUTH_ADMIN_PASSWORD}
authorization_function = mlflow.server.auth:authenticate_request_basic_auth
EOF
chmod 600 "${AUTH_CONFIG_PATH}"
export MLFLOW_AUTH_CONFIG_PATH="${AUTH_CONFIG_PATH}"

MLFLOW_INTERNAL_PORT="${MLFLOW_INTERNAL_PORT:-5001}"
export MLFLOW_INTERNAL_URL="http://127.0.0.1:${MLFLOW_INTERNAL_PORT}"

mlflow server \
  --app-name basic-auth \
  --host 127.0.0.1 \
  --port "${MLFLOW_INTERNAL_PORT}" \
  --workers "${MLFLOW_WORKERS:-1}" \
  --allowed-hosts "127.0.0.1,localhost" \
  --cors-allowed-origins "${MLFLOW_CORS_ALLOWED_ORIGINS}" \
  --backend-store-uri "${MLFLOW_BACKEND_STORE_URI}" \
  --artifacts-destination "${MLFLOW_ARTIFACT_ROOT}" \
  --serve-artifacts &
MLFLOW_PID="$!"

cleanup() {
  kill "${MLFLOW_PID}" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# Give the local MLflow server a short startup window so obvious auth/config
# errors fail the container before Railway marks it healthy.
sleep 5
if ! kill -0 "${MLFLOW_PID}" 2>/dev/null; then
  wait "${MLFLOW_PID}"
fi

python3 /app/mlflow_basic_auth_proxy.py &
PROXY_PID="$!"
wait "${PROXY_PID}"
