#!/usr/bin/env bash
# One-command update for the VPS: back up the database, pull the latest code, rebuild, verify.
#
#   cd /var/www/DIU_Hackathon && bash deploy/deploy.sh
#
# Optional: run a nightly backup with cron (keeps the last 14 dumps):
#   (crontab -l 2>/dev/null; echo "15 3 * * * cd /var/www/DIU_Hackathon && bash deploy/deploy.sh --backup-only") | crontab -
set -euo pipefail

cd "$(dirname "$0")"
DC="docker compose -f docker-compose.prod.yml --env-file .env"
BACKUP_DIR="${BACKUP_DIR:-$HOME/shurokkha-backups}"

[ -f .env ] || { echo "deploy/.env is missing. Copy .env.example to .env and fill it in first." >&2; exit 1; }

backup() {
  mkdir -p "$BACKUP_DIR"
  if $DC ps --status running postgres 2>/dev/null | grep -q postgres; then
    f="$BACKUP_DIR/shurokkha_$(date +%F_%H%M).sql.gz"
    $DC exec -T postgres pg_dump -U shurokkha shurokkha | gzip > "$f"
    echo "Backup written: $f"
    ls -1t "$BACKUP_DIR"/shurokkha_*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm --
  else
    echo "Postgres is not running yet; skipping backup."
  fi
}

backup
[ "${1:-}" = "--backup-only" ] && exit 0

if ! grep -q '^ADMIN_PASSWORD=.\+' .env; then
  echo "Note: ADMIN_PASSWORD is not set in deploy/.env, so the Admin page stays read-only."
fi

echo "Pulling latest code..."
git -C .. pull --ff-only

echo "Rebuilding and restarting..."
$DC up -d --build

echo "Waiting for the API to become healthy..."
domain=$(grep '^DOMAIN=' .env | cut -d= -f2)
for _ in $(seq 1 60); do
  if curl -fsS "https://$domain/health/ready" >/dev/null 2>&1; then
    curl -fsS "https://$domain/health/ready"; echo
    $DC ps
    echo "Deployed: https://$domain"
    exit 0
  fi
  sleep 5
done
echo "The API did not report healthy within 5 minutes. Check: $DC logs --tail=100 api" >&2
exit 1
