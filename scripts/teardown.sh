#!/usr/bin/env bash
docker rm -f pgbench mybench sdbbench pyrun >/dev/null 2>&1 || true
docker volume rm benchdata sdbdata >/dev/null 2>&1 || true
docker network rm benchnet >/dev/null 2>&1 || true
echo "cleaned up"
