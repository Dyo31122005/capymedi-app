#!/bin/sh
# Backup DB hang ngay (ADR-0015). Cai bang cron cua user ubuntu tren VPS (gio
# VPS la Europe/Berlin: 21:15 Berlin ~ 03:15 gio Viet Nam, luc it nguoi dung):
#   15 21 * * * /opt/capymedi/current/deploy/vps/backup.sh >> /opt/capymedi/backups/backup.log 2>&1
#
# Ghi ra file tam roi moi doi ten: neu pg_dump chet giua chung thi khong de lai
# 1 file .dump hong mang ten nhu ban that. Giu 14 ban gan nhat.
#
# Khoi phuc: docker compose --env-file /opt/capymedi/.env exec -T db \
#   pg_restore -U vmec -d vmec04 --clean --if-exists < /opt/capymedi/backups/vmec04-YYYY-MM-DD.dump
set -eu
cd /opt/capymedi/current/deploy/vps
out="/opt/capymedi/backups/vmec04-$(date +%F).dump"
docker compose --env-file /opt/capymedi/.env exec -T db pg_dump -U vmec -Fc vmec04 > "$out.tmp"
mv "$out.tmp" "$out"
find /opt/capymedi/backups -name 'vmec04-*.dump' -mtime +14 -delete
echo "$(date -Is) backup ok: $out ($(du -h "$out" | cut -f1))"
