#!/usr/bin/env bash
set -euo pipefail
umask 077

MODE="${1:-backup}"
SOURCE_DATABASE_URL="${SOURCE_DATABASE_URL:-}"
TARGET_DATABASE_URL="${TARGET_DATABASE_URL:-}"
BACKUP_FILE="${BACKUP_FILE:-artifacts/mr-ai-stan-postgres.dump}"

if [[ "$MODE" != "backup" && "$MODE" != "migrate" ]]; then
  echo "Usage: $0 backup|migrate" >&2
  exit 2
fi

if [[ -z "$SOURCE_DATABASE_URL" ]]; then
  echo "SOURCE_DATABASE_URL is required. Set it as a protected environment variable." >&2
  exit 2
fi
if [[ "$MODE" == "migrate" && -z "$TARGET_DATABASE_URL" ]]; then
  echo "TARGET_DATABASE_URL is required for migrate mode." >&2
  exit 2
fi

for command in pg_dump pg_restore psql sha256sum; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Required PostgreSQL utility is missing: $command" >&2
    exit 127
  fi
done

PG_DUMP_VERSION="$(pg_dump --version | awk '{print $3}' | cut -d. -f1)"
if [[ ! "$PG_DUMP_VERSION" =~ ^[0-9]+$ ]] || (( PG_DUMP_VERSION < 18 )); then
  echo "PostgreSQL 18 client tools are required for this PostgreSQL 18 source." >&2
  exit 2
fi

mkdir -p "$(dirname "$BACKUP_FILE")"
echo "Creating a compressed PostgreSQL custom-format backup..."
pg_dump \
  --format=custom \
  --no-owner \
  --no-acl \
  --file="$BACKUP_FILE" \
  "$SOURCE_DATABASE_URL"

echo "Validating the backup archive..."
pg_restore --list "$BACKUP_FILE" > "$BACKUP_FILE.toc"
if [[ ! -s "$BACKUP_FILE.toc" ]]; then
  echo "Backup archive validation returned an empty table-of-contents list." >&2
  exit 1
fi
sha256sum "$BACKUP_FILE" > "$BACKUP_FILE.sha256"
echo "PASS: backup created, archive validated, and SHA-256 recorded."

if [[ "$MODE" == "backup" ]]; then
  exit 0
fi

SOURCE_ID="$(psql -X -qAt -v ON_ERROR_STOP=1 "$SOURCE_DATABASE_URL" -c "SELECT current_database() || '|' || COALESCE(inet_server_addr()::text, 'local') || '|' || COALESCE(inet_server_port()::text, '')")"
TARGET_ID="$(psql -X -qAt -v ON_ERROR_STOP=1 "$TARGET_DATABASE_URL" -c "SELECT current_database() || '|' || COALESCE(inet_server_addr()::text, 'local') || '|' || COALESCE(inet_server_port()::text, '')")"
if [[ "$SOURCE_ID" == "$TARGET_ID" || "${SOURCE_DATABASE_URL%%\?*}" == "${TARGET_DATABASE_URL%%\?*}" ]]; then
  echo "Source and target resolve to the same PostgreSQL database; refusing migration." >&2
  exit 2
fi

TARGET_TABLE_COUNT="$(psql -X -qAt -v ON_ERROR_STOP=1 "$TARGET_DATABASE_URL" -c "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")"
if [[ ! "$TARGET_TABLE_COUNT" =~ ^0+$ ]]; then
  echo "Target database is not empty ($TARGET_TABLE_COUNT user tables). No restore was attempted." >&2
  echo "Choose a new empty target database; this script never drops target tables." >&2
  exit 2
fi

echo "Restoring into the empty target database without dropping existing objects..."
pg_restore \
  --dbname="$TARGET_DATABASE_URL" \
  --no-owner \
  --no-acl \
  --exit-on-error \
  "$BACKUP_FILE"

table_counts() {
  local url="$1"
  local table
  local count
  while IFS= read -r table; do
    [[ -z "$table" ]] && continue
    count="$(psql -X -qAt -v ON_ERROR_STOP=1 "$url" -c "SELECT count(*) FROM $table")"
    printf '%s|%s\n' "$table" "$count"
  done < <(
    psql -X -qAt -v ON_ERROR_STOP=1 "$url" -c \
      "SELECT format('%I.%I', schemaname, tablename) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1"
  )
}

table_counts "$SOURCE_DATABASE_URL" > "$BACKUP_FILE.source-counts"
table_counts "$TARGET_DATABASE_URL" > "$BACKUP_FILE.target-counts"
if ! diff -u "$BACKUP_FILE.source-counts" "$BACKUP_FILE.target-counts"; then
  echo "RESTORE FAILED VERIFICATION: source and target table row counts differ." >&2
  exit 1
fi

TABLE_COUNT="$(wc -l < "$BACKUP_FILE.source-counts" | tr -d ' ')"
echo "PASS: migration verified. Source/target row counts match across $TABLE_COUNT tables."
echo "The source database was not modified."
