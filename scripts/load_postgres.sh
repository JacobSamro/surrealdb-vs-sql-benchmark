#!/usr/bin/env bash
# Load + index Postgres, timed.
set -e
PGX(){ docker exec -e PGPASSWORD=bench pgbench psql -U postgres -d bench -qtA -v ON_ERROR_STOP=1 -c "$1"; }
timeit(){ local l="$1"; shift; local s=$(date +%s.%N); "$@" >/dev/null 2>&1; local e=$(date +%s.%N); printf "%-28s %8.2f s\n" "$l" "$(echo "$e-$s"|bc)"; }
PGX "CREATE TABLE IF NOT EXISTS events(id bigint PRIMARY KEY, user_id int, status smallint, amount numeric(10,2), created_at bigint, payload text);"
PGX "DROP INDEX IF EXISTS idx_events_user; TRUNCATE events;"
timeit "PG bulk load (COPY)" PGX "\copy events FROM '/data/data10m.csv' WITH (FORMAT csv)"
timeit "PG build 2nd index"  PGX "CREATE INDEX idx_events_user ON events(user_id);"
echo "rows: $(PGX 'SELECT count(*) FROM events;')  size: $(PGX "SELECT pg_size_pretty(pg_total_relation_size('events'));")"
