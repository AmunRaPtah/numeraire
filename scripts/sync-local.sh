#!/bin/bash
# Refreshes the local numeraire warehouse from the OneDrive state.tgz that
# numeraire-harvest.yml (GitHub Actions) rebuilds weekly. Extract-only — never
# rebuilds locally, so this is safe to run on the VPS without OOM risk.
set -euo pipefail
cd /root/projects/numeraire

TMP="data.new.$$"
rclone copyto onedrive:numeraire-state/state.tgz "state.tgz.$$" --onedrive-chunk-size 100M
mkdir -p "$TMP"
tar -xzf "state.tgz.$$" -C "$TMP"
rm -f "state.tgz.$$"

rm -rf data.old
[ -d data ] && mv data data.old
mv "$TMP" data
rm -rf data.old

echo "[numeraire-sync] $(date -u +%FT%TZ) refreshed from OneDrive, warehouse: $(du -sh data/warehouse.duckdb 2>/dev/null | cut -f1)"
