#!/usr/bin/env bash
# Deploy CapyMedi len VPS (ADR-0015). Thay cho scripts/deploy_gcp.ps1.
#
# Dong goi DUNG commit HEAD (khong lay thay doi chua commit), chi cac file can
# de build (~200 MB thay vi ca repo), day len VPS, build + khoi dong lai bang
# Docker Compose, roi smoke test qua HTTPS.
#
# Cach dung (Git Bash, tu root repo):
#   ./scripts/deploy_vps.sh
# Bien moi truong tuy chon:
#   VPS_HOST (mac dinh ubuntu@185.176.252.232), VPS_KEY (mac dinh ~/.ssh/capymedi_vps)
#
# Ha tang lan dau (Docker, ufw, /opt/capymedi/.env, nap du lieu): docs/DEPLOY.md.
set -euo pipefail

VPS_HOST="${VPS_HOST:-ubuntu@185.176.252.232}"
VPS_KEY="${VPS_KEY:-$HOME/.ssh/capymedi_vps}"
SSH=(ssh -o BatchMode=yes -i "$VPS_KEY" "$VPS_HOST")
SCP=(scp -o BatchMode=yes -i "$VPS_KEY")

cd "$(git rev-parse --show-toplevel)"
SHA="$(git rev-parse --short HEAD)"

# Chi nhung gi Dockerfile backend + frontend can (xem Dockerfile COPY, .dockerignore).
PATHS=(
  backend migrations alembic.ini requirements.txt Dockerfile docker-entrypoint.sh .dockerignore
  scripts/safe_migrate.py scripts/create_admin.py
  frontend deploy/vps
  "data pharmacy/v2/final_canonical/manifest.json"
  "data pharmacy/v2/final_canonical/drug_product.jsonl"
  "data pharmacy/v2/final_canonical/drug_id_map.jsonl"
  "data pharmacy/v2/final_canonical/drug_product_ingredient.jsonl"
  "data pharmacy/v2/final_canonical/drug_knowledge.jsonl"
  "data pharmacy/v2/final_canonical/rag/v2_chunks.jsonl"
  "data pharmacy/v2/final_canonical/rag/v2_embedding_index.jsonl"
)

if ! git diff --quiet HEAD -- "${PATHS[@]}"; then
  echo "CANH BAO: co thay doi chua commit trong cac file deploy - script chi deploy commit $SHA." >&2
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ARCHIVE="$TMP/capymedi-$SHA.tar.gz"
echo "==> Dong goi commit $SHA"
git archive --format=tar.gz -o "$ARCHIVE" HEAD -- "${PATHS[@]}"
ls -lh "$ARCHIVE" | awk '{print "    " $5}'

echo "==> Upload"
"${SCP[@]}" "$ARCHIVE" "$VPS_HOST:/opt/capymedi/releases/"

echo "==> Build + khoi dong tren VPS"
"${SSH[@]}" "SHA=$SHA bash -s" <<'REMOTE'
set -euo pipefail
cd /opt/capymedi/releases
rm -rf "$SHA" && mkdir "$SHA"
tar -xzf "capymedi-$SHA.tar.gz" -C "$SHA" && rm "capymedi-$SHA.tar.gz"
ln -sfn "/opt/capymedi/releases/$SHA" /opt/capymedi/current
cd /opt/capymedi/current/deploy/vps
docker compose --env-file /opt/capymedi/.env up -d --build --remove-orphans
# Giu 3 ban gan nhat de quay lai nhanh khi can.
ls -1dt /opt/capymedi/releases/*/ | tail -n +4 | xargs -r rm -rf
docker image prune -f >/dev/null
REMOTE

DOMAIN="$("${SSH[@]}" "grep -E '^DOMAIN=' /opt/capymedi/.env | cut -d= -f2-" | tr -d '\r')"
echo "==> Smoke test https://$DOMAIN (backend can ~1 phut de warmup)"
for i in $(seq 1 30); do
  if curl -fsS --max-time 10 "https://$DOMAIN/health" >/dev/null 2>&1; then
    curl -fsS --max-time 20 -o /dev/null "https://$DOMAIN/login" && echo "    OK: https://$DOMAIN"
    exit 0
  fi
  sleep 10
done
echo "LOI: backend chua len sau 5 phut. Xem log: ssh ... 'cd /opt/capymedi/current/deploy/vps && docker compose logs --tail 80 backend'" >&2
exit 1
