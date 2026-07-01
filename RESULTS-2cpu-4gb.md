# Raw results — rerun at 2 CPU / 4 GB

Same rig as the 2 GB run, each container capped at `--cpus=2 --memory=4g`.
Tuning bumped for the bigger box: Postgres `shared_buffers=1GB effective_cache_size=3GB
maintenance_work_mem=512MB work_mem=64MB`; MySQL `innodb-buffer-pool-size=2560M`.
SurrealDB left at RocksDB defaults (which now auto-scale — see bottom).

## Bulk load, 10M rows

```
PG load (COPY 10M)                22.17 s
PG build 2nd index                 6.66 s
rows=10000000 size=1034 MB

MySQL load (LOAD DATA 10M)        50.55 s
MySQL build 2nd index             17.76 s
rows=10000000 size_mb=593
```

SurrealDB, chunked HTTP batched INSERT (batch=1000) — completed this time, no wedge:

```
  loaded   250,000     16.1s     15506 rows/s
  loaded 1,000,000     66.2s     15104 rows/s
  loaded 3,000,000    201.0s     14922 rows/s
  loaded 6,000,000    ...        ~14900 rows/s
  loaded 10,000,000   668.7s     14955 rows/s
SDB bulk load: 668.7s  (10,000,000 rows, 14955 rows/s)
```

SurrealDB secondary index build on 10M rows — OOM-killed:

```
docker inspect: OOMKilled=true Status=exited Exit=137
log: A transaction was dropped without being committed or cancelled
log: Failed to send index building result to the consumer
```

## Read latency, 10M rows

```
=== PostgreSQL (10M, indexed) ===
  PK lookup            k=3000  avg=  0.179ms  p50=  0.169ms  p95=  0.247ms  qps=5574.7
  secondary lookup     k=2000  avg=  0.279ms  p50=  0.237ms  p95=  0.485ms  qps=3586.4
  range agg (5k span)  k=200   avg= 11.461ms  p50=  0.228ms  p95= 93.775ms  qps=  87.3
  full-scan agg        k=3     avg=760.995ms  p50=766.780ms  p95=787.124ms  qps=   1.3
  single-row insert    k=2000  avg=  0.489ms  p50=  0.478ms  p95=  0.577ms  qps=2044.8

=== MySQL (10M, indexed) ===
  PK lookup            k=3000  avg=  0.204ms  p50=  0.192ms  p95=  0.267ms  qps=4899.5
  secondary lookup     k=2000  avg=  0.344ms  p50=  0.303ms  p95=  0.545ms  qps=2908.6
  range agg (5k span)  k=200   avg= 22.748ms  p50=  0.251ms  p95=224.453ms  qps=  44.0
  full-scan agg        k=3     avg=1883.107ms p50=1884.208ms p95=1917.595ms qps=   0.5
  single-row insert    k=2000  avg=  1.708ms  p50=  1.601ms  p95=  2.203ms  qps= 585.4

=== SurrealDB (10M, NO secondary index — build OOM-killed at 4GB) ===
  PK lookup (record id)             k=3000  avg=   33.117ms  p50=  32.679ms  p95=  37.501ms  qps=30.2
  secondary lookup (NO idx, scan)   k=30    avg= 5190.521ms  p50=5175.128ms  p95=5498.205ms  qps= 0.2
  full-scan agg                     k=3     avg=20612.446ms  p50=20939.282ms p95=21141.443ms qps= 0.0
```

## On-disk size, 10M rows

```
PostgreSQL: 1034 MB  (108 B/row)
MySQL:       593 MB  (59 B/row)
SurrealDB:   986 MB  (99 B/row)   <- compacts fine at real scale; the ~540 B/row seen at
                                     573k in the 2 GB run was an uncompacted small-dataset artifact
```

## Idle memory (per 4 GB container)

```
pgbench  mem=1.365GiB / 4GiB
mybench  mem=1.610GiB / 4GiB
sdbbench mem=2.049GiB / 4GiB
```

## SurrealDB RocksDB config — now auto-scaled with the cgroup

```
2 GB box:  total memory limit ~150 MB,  block cache 16 MB
4 GB box:  total memory limit ~1.28 GB, block cache 1 GB
```
The cache is cgroup-aware. Give it more RAM and it uses more, which is why PK lookups dropped
from ~48-65 ms (2 GB) to ~33 ms (4 GB).
