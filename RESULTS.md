# Raw results

Captured from the actual run. Each database limited to `--cpus=1 --memory=2g`.

## Bulk load, 10M rows

```
PG bulk load (COPY 10M)         23.49 s
PG build 2nd index              12.45 s
rows: 10000000  size: 1034 MB

MySQL bulk load (LOAD DATA)     59.90 s
MySQL build 2nd index           26.89 s
rows: 10000000  size: 603 MB
```

SurrealDB, chunked HTTP batched INSERT (batch=1000):

```
  loaded   250,000     16.3s     15305 rows/s
  loaded   500,000     33.6s     14860 rows/s
    [retry 0 TimeoutError]
    [retry 1 TimeoutError]      <- server wedged; count() also times out; CPU 0%
```

One-shot `surreal import` of the 921 MB SurrealQL file:

```
ERROR surrealdb_server::cli::import: Surreal import failed, import might only be partially
completed or have failed entirely.
HTTP error: error sending request for url (http://localhost:8000/import)   (dropped at 49s)
```

Index build on ~570k rows, in isolation, right after a clean restart:

```
count after restart: [{'count': 573000}]
index build FAILED/wedged: TimeoutError 300.1 s
```

## Read latency, ~500k rows

```
=== PostgreSQL (500k, indexed) ===
  PK lookup             n=3000  avg=  0.169ms  p50=  0.159ms  p95=  0.226ms  qps= 5914.2
  secondary lookup      n=2000  avg=  0.171ms  p50=  0.159ms  p95=  0.257ms  qps= 5848.2
  range agg (5k span)   n=200   avg=  4.261ms  p50=  4.141ms  p95=  5.801ms  qps=  234.7
  full-scan agg         n=3     avg= 78.595ms  p50= 98.127ms  p95= 99.675ms  qps=   12.7
  single-row insert     n=2000  avg=  0.566ms  p50=  0.522ms  p95=  0.805ms  qps= 1767.6

=== MySQL (500k, indexed) ===
  PK lookup             n=3000  avg=  0.220ms  p50=  0.207ms  p95=  0.299ms  qps= 4535.6
  secondary lookup      n=2000  avg=  0.238ms  p50=  0.227ms  p95=  0.329ms  qps= 4209.8
  range agg (5k span)   n=200   avg=  9.822ms  p50=  9.676ms  p95= 12.050ms  qps=  101.8
  full-scan agg         n=3     avg=103.155ms  p50=101.719ms  p95=109.019ms  qps=    9.7
  single-row insert     n=2000  avg=  1.851ms  p50=  1.688ms  p95=  2.508ms  qps=  540.1

=== SurrealDB (~573k, NO secondary index — build wedged) ===
  PK lookup (record id) n=3000  avg= 48.333ms  p50= 36.411ms  p95=109.955ms  qps=   20.7
  secondary lookup      -> TimeoutError (unindexed full scan wedged the server)
```

SurrealDB PK lookup, persistent connection (ruling out per-request TCP overhead):

```
SurrealDB PK lookup (PERSISTENT conn): avg=65.168ms p50=35.175ms p95=182.268ms qps=15.3
```

## On-disk size

```
SurrealDB (~573k rows): 297 MB   (~540 B/row)
PostgreSQL (10M rows):  1034 MB  (108 B/row)
MySQL (10M rows):       603 MB   (63 B/row)
```

## Idle memory (per 2 GB container)

```
pgbench  mem=316.8MiB / 2GiB
mybench  mem=1.576GiB / 2GiB     <- InnoDB using its buffer pool
sdbbench mem=239.1MiB / 2GiB     <- RocksDB self-limited, most of the 2 GB unused
```

## SurrealDB RocksDB config, from its own startup log

```
Memory manager: total memory limit: 150994944        (~150 MB)
Memory manager: block cache size:   16777216B        (16 MB)
Memory manager: write buffer size:  67108864B        (64 MB)
Sync mode: every transaction commit
```
