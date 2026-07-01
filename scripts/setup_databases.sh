#!/usr/bin/env bash
# Launch all three databases, each capped at 1 CPU / 2 GB.
set -e
for c in pgbench mybench sdbbench; do docker rm -f $c >/dev/null 2>&1 || true; done

docker run -d --name pgbench --cpus=1 --memory=2g --memory-swap=2g --network benchnet -v benchdata:/data \
  -e POSTGRES_PASSWORD=bench -e POSTGRES_DB=bench postgres:17 \
  -c shared_buffers=512MB -c effective_cache_size=1536MB -c maintenance_work_mem=256MB \
  -c work_mem=32MB -c max_connections=20 -c max_wal_size=4GB

docker run -d --name mybench --cpus=1 --memory=2g --memory-swap=2g --network benchnet -v benchdata:/data \
  -e MYSQL_ROOT_PASSWORD=bench -e MYSQL_DATABASE=bench mysql:8.4 \
  --innodb-buffer-pool-size=1200M --innodb-redo-log-capacity=512M --local-infile=1 --secure-file-priv=/data

# SurrealDB runs unprivileged, so give it its own writable volume.
docker volume create sdbdata >/dev/null
docker run --rm -v sdbdata:/sdb alpine:latest sh -c 'chmod 777 /sdb'
docker run -d --name sdbbench --cpus=1 --memory=2g --memory-swap=2g --network benchnet \
  -v sdbdata:/sdb -v benchdata:/data:ro \
  surrealdb/surrealdb:latest start --user root --pass bench --bind 0.0.0.0:8000 rocksdb:/sdb/surreal.db

echo "waiting for surreal..."
until docker exec sdbbench /surreal isready --endpoint http://localhost:8000 >/dev/null 2>&1; do sleep 1; done
echo "all up"
