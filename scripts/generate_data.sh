#!/usr/bin/env bash
# Generate one canonical CSV into the shared `benchdata` docker volume.
# Usage: ./generate_data.sh <row_count>   (default 10000000)
set -e
N="${1:-10000000}"
docker volume create benchdata >/dev/null
docker network create benchnet >/dev/null 2>&1 || true
echo "Generating $N rows..."
docker run --rm -e N="$N" -v benchdata:/data alpine:latest sh -c '
awk -v n="$N" "BEGIN{
  base=1600000000
  for(i=1;i<=n;i++){
    uid=(i*2654435761)%1000000; if(uid<0)uid=-uid
    status=i%5
    amt=(i%10000)+0.99
    ts=base+(i%30000000)
    printf \"%d,%d,%d,%.2f,%d,u%d_item\n\", i, uid, status, amt, ts, uid
  }
}" > /data/data10m.csv
wc -l < /data/data10m.csv; ls -lh /data/data10m.csv'
