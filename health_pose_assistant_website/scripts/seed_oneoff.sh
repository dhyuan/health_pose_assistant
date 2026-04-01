#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<EOF
Usage: $(basename "$0") --type {admin|stats|all} [options]

Options:
  --type         Which seed to run: admin, stats, or all
  --email        Admin email (required for admin)
  --password     Admin password (required for admin)
  --days         Days for stats seed (default: 30)
  --force        Skip confirmation prompt
  --help         Show this help

Examples:
  # seed admin user
  ./scripts/seed_oneoff.sh --type admin --email admin@example.com --password secret

  # seed stats for 30 days
  ./scripts/seed_oneoff.sh --type stats --days 30

EOF
}

TYPE=""
EMAIL=""
PASSWORD=""
DAYS=30
FORCE=false

if [ "$#" -eq 0 ]; then usage; exit 1; fi

while [ $# -gt 0 ]; do
  case "$1" in
    --help|-h)
      usage; exit 0;;
    --type)
      TYPE="$2"; shift 2;;
    --email)
      EMAIL="$2"; shift 2;;
    --password)
      PASSWORD="$2"; shift 2;;
    --days)
      DAYS="$2"; shift 2;;
    --force)
      FORCE=true; shift 1;;
    *)
      echo "Unknown option: $1"; usage; exit 1;;
  esac
done

if [ -z "$TYPE" ]; then echo "--type is required"; usage; exit 1; fi

# pick compose command
DC_CMD=""
if command -v docker-compose >/dev/null 2>&1; then
  DC_CMD="docker-compose"
elif command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  DC_CMD="docker compose"
else
  echo "docker-compose or 'docker compose' not found in PATH"; exit 1
fi

echo "This will run seed(s) inside a short-lived backend container using: $DC_CMD"
if [ "$FORCE" != "true" ]; then
  read -r -p "Proceed? [y/N] " ans
  case "$ans" in
    [Yy]*) ;;
    *) echo "Aborted"; exit 1;;
  esac
fi

echo "Waiting for Postgres to be ready..."
TRIES=0
MAX_TRIES=60
until (
  if [ "$DC_CMD" = "docker-compose" ]; then
    docker-compose exec db pg_isready -q >/dev/null 2>&1
  else
    docker compose exec db pg_isready -q >/dev/null 2>&1
  fi
); do
  TRIES=$((TRIES+1))
  if [ $TRIES -ge $MAX_TRIES ]; then
    echo "Postgres did not become ready in time"; exit 2
  fi
  printf "."
  sleep 1
done
echo "\nPostgres ready."

run_in_container() {
  # args: full command after python entrypoint
  if [ "$DC_CMD" = "docker-compose" ]; then
    docker-compose run --rm --entrypoint python -v "${REPO_ROOT}:/work" -w /work backend "$@"
  else
    docker compose run --rm --entrypoint python -v "${REPO_ROOT}:/work" -w /work backend "$@"
  fi
}

if [ "$TYPE" = "admin" ] || [ "$TYPE" = "all" ]; then
  if [ -z "$EMAIL" ] || [ -z "$PASSWORD" ]; then
    echo "--email and --password are required for admin seed"; exit 1
  fi
  echo "Seeding admin: $EMAIL"
  run_in_container /work/scripts/seed_admin.py --email "$EMAIL" --password "$PASSWORD"
fi

if [ "$TYPE" = "stats" ] || [ "$TYPE" = "all" ]; then
  echo "Seeding stats for $DAYS days"
  run_in_container /work/scripts/seed_stats.py --days "$DAYS"
fi

echo "Seeding finished."
