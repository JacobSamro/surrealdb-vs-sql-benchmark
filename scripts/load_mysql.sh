#!/usr/bin/env bash
# Load + index MySQL, timed.
set -e
MYX(){ docker exec mybench mysql -uroot -pbench --local-infile=1 -N -B bench -e "$1" 2>/dev/null; }
timeit(){ local l="$1"; shift; local s=$(date +%s.%N); "$@" >/dev/null 2>&1; local e=$(date +%s.%N); printf "%-28s %8.2f s\n" "$l" "$(echo "$e-$s"|bc)"; }
for i in $(seq 1 30); do MYX "SELECT 1" >/dev/null 2>&1 && break; sleep 2; done
MYX "DROP TABLE IF EXISTS events; CREATE TABLE events(id BIGINT PRIMARY KEY, user_id INT, status TINYINT, amount DECIMAL(10,2), created_at BIGINT, payload VARCHAR(64)) ENGINE=InnoDB;"
timeit "MySQL bulk load (LOAD DATA)" MYX "LOAD DATA INFILE '/data/data10m.csv' INTO TABLE events FIELDS TERMINATED BY ',' LINES TERMINATED BY '\n';"
timeit "MySQL build 2nd index"       MYX "CREATE INDEX idx_events_user ON events(user_id);"
echo "rows: $(MYX 'SELECT count(*) FROM events')"
MYX "SELECT ROUND((data_length+index_length)/1024/1024) AS mb FROM information_schema.tables WHERE table_schema='bench' AND table_name='events';"
