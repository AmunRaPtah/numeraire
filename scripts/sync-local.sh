#!/bin/bash
# Refreshes the local numeraire warehouse from the Google Drive state.tgz that
# numeraire-harvest.yml (GitHub Actions) rebuilds weekly. Extract-only — never
# rebuilds locally, so this is safe to run on the VPS without OOM risk.
set -euo pipefail
cd /root/projects/numeraire

TMP="data.new.$$"
rclone copyto gdrive4:numeraire-state/state.tgz "state.tgz.$$" --drive-chunk-size 64M
mkdir -p "$TMP"
# raw/ lives off-box now (moved to media2:numeraire-data/raw on 2026-08-04 to relieve
# local disk pressure: it was 5.6G and this VPS was down to 11G free). Skip extracting
# it from the tarball entirely and re-symlink it below instead of letting it land back
# on local disk every week.
tar -xzf "state.tgz.$$" -C "$TMP" --exclude='raw' --exclude='raw/*'
rm -f "state.tgz.$$"

rm -rf data.old
[ -d data ] && mv data data.old
mv "$TMP" data
ln -s /media/numeraire-data/raw data/raw
rm -rf data.old

echo "[numeraire-sync] $(date -u +%FT%TZ) refreshed from Google Drive, warehouse: $(du -sh data/warehouse.duckdb 2>/dev/null | cut -f1)"

# Push the refreshed warehouse to the Modal Volume so Hermes's off-box signal
# compute (modal app 'hermes-numeraire') stays in sync. Non-fatal: a Modal
# hiccup must never break the local warehouse refresh above.
MODAL_BIN=/root/projects/pardalos/.venv/bin/modal
if [ -x "$MODAL_BIN" ] && [ -f data/warehouse.duckdb ]; then
  ( set +e
    set -a; . /root/projects/pardalos/.env.local 2>/dev/null; set +a
    "$MODAL_BIN" volume put numeraire-warehouse data/warehouse.duckdb /warehouse.duckdb --force \
      && echo "[numeraire-sync] pushed warehouse to Modal Volume numeraire-warehouse" \
      || echo "[numeraire-sync] WARN: Modal Volume push failed (off-box signals may be stale)"
  ) || true
fi
