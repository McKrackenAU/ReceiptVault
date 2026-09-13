#!/usr/bin/env bash
# Make the Postgres role match RECEIPTVAULT_DATABASE_URL in the env file.
set -euo pipefail
ENV_FILE="${ENV_FILE:-/etc/receiptvault/receiptvault.env}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi
# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a
systemctl enable --now postgresql >/dev/null 2>&1 || true
python3 - <<'PY'
import os, subprocess, urllib.parse

raw = os.environ.get("RECEIPTVAULT_DATABASE_URL", "")
url = raw.replace("postgresql+psycopg://", "postgresql://", 1)
parsed = urllib.parse.urlparse(url)
user = urllib.parse.unquote(parsed.username or "receiptvault")
password = urllib.parse.unquote(parsed.password or "")
database = (parsed.path or "/receiptvault").lstrip("/") or "receiptvault"
if not password:
    raise SystemExit("RECEIPTVAULT_DATABASE_URL has no password")

def psql(*args: str) -> None:
    subprocess.run(["runuser", "-u", "postgres", "--", "psql", "-v", "ON_ERROR_STOP=1", *args], check=True)

pw = password.replace("'", "''")
psql("-c", f"DO $$ BEGIN CREATE ROLE {user} LOGIN PASSWORD '{pw}'; EXCEPTION WHEN duplicate_object THEN NULL; END $$;")
psql("-c", f"ALTER ROLE {user} WITH LOGIN PASSWORD '{pw}';")
psql("-c", f"SELECT 1 FROM pg_database WHERE datname = '{database}';")
exists = subprocess.run(
    ["runuser", "-u", "postgres", "--", "psql", "-tAc", f"SELECT 1 FROM pg_database WHERE datname = '{database}'"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
if exists != "1":
    psql("-c", f"CREATE DATABASE {database} OWNER {user};")
psql("-d", database, "-c", f"GRANT ALL ON SCHEMA public TO {user}; ALTER DATABASE {database} OWNER TO {user};")
print(f"database ready for {user} / {database}")
PY
