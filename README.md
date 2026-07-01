# SurrealDB vs MySQL vs PostgreSQL on a tiny box

I wanted a clean 100M-row head-to-head between SurrealDB, MySQL, and Postgres on small
hardware (1 CPU core, 2 GB RAM each). I did not get one. What I got instead turned out to be
more useful: two databases that handle the box fine, and one that falls over well before it
gets interesting.

So this repo is half benchmark, half incident report.

## The short version

Postgres and MySQL loaded and served 10M rows on 2 GB without complaining. SurrealDB couldn't
reliably load even 1 million rows on the same box. Its write path stalls, the client times out,
and then the whole server wedges: CPU drops to zero and every query after that hangs, including
a plain `SELECT count()`. The only way out is a restart. I hit this five or six times before I
accepted it wasn't my client code. When I did get a few hundred thousand rows in, point lookups
came back around 35-65 ms each, versus 0.2 ms on the other two.

If you just want the recommendation: on hardware this small, use Postgres.

## Update: I doubled the box to 2 CPU / 4 GB

The 2 GB verdict was "SurrealDB falls over." So I reran everything with two cores and 4 GB to
see how much of that was just starvation. Turns out most of it was. Full numbers in
[RESULTS-2cpu-4gb.md](RESULTS-2cpu-4gb.md); here's the short of it.

The write wedge is gone. With a second core, SurrealDB loaded all 10M rows without a single
stall, where at 2 GB it hung before 1M every time. Compaction gets its own CPU now instead of
fighting the writer. It's still slow, about 15k rows/s against Postgres's ~425k, but it
finishes.

Then it walked straight into a new wall: **building the `user_id` index on 10M rows got
OOM-killed**, even with 4 GB. So you can load the data and you can't index it, which for a real
workload is nearly the same problem one step later.

| 10M rows | PostgreSQL | MySQL | SurrealDB |
|---|---|---|---|
| Load | 22.2 s | 50.6 s | 668.7 s (no wedge) |
| Build index | 6.7 s | 17.8 s | OOM-killed |
| PK lookup | 0.18 ms | 0.20 ms | 33 ms |
| Secondary lookup | 0.28 ms | 0.34 ms | 5,190 ms (no index) |
| Full-scan agg | 761 ms | 1,883 ms | 20,600 ms |
| On disk | 1034 MB | 593 MB | 986 MB |

Two corrections to my earlier writeup, in fairness to SurrealDB:

- Its RocksDB cache scales with the cgroup. At 2 GB it self-limited to a 16 MB block cache; at
  4 GB it took 1 GB. That's why point lookups improved from ~48-65 ms to 33 ms. Still ~170x
  behind the SQL pair, because 1 GB doesn't hold much of a 10M-row table, but the tiny cache
  at 2 GB was self-inflicted, not something I set.
- The storage bloat I complained about was an artifact. At 573k uncompacted rows it looked like
  ~540 B/row. At a real 10M it compacts to ~99 B/row, right next to Postgres. I was wrong there.

Bottom line moved from "it breaks" to "it works, in a different weight class." Loads finish,
reads are correct, the wedge is gone. You still pay 30x on load and 170x on point reads, and
you can't build a secondary index on 10M inside 4 GB. Postgres stayed the boring, fast default.

Everything below is the original 2 GB / 1 CPU run.

## Setup

- Host: a remote Docker engine (16 vCPU / 32 GB), with each database boxed into its own limits.
- Per-database cap: `--cpus=1 --memory=2g --memory-swap=2g`.
- Images: `postgres:17`, `mysql:8.4`, `surrealdb/surrealdb:latest`.
- Tuning, roughly what you'd set on a real 2 GB box:
  - Postgres: `shared_buffers=512MB`, `effective_cache_size=1536MB`, `maintenance_work_mem=256MB`, `work_mem=32MB`
  - MySQL: `innodb-buffer-pool-size=1200M`, `innodb-redo-log-capacity=512M`
  - SurrealDB: RocksDB defaults. Worth noting: it capped itself at about 150 MB total and a
    16 MB block cache, and never touched the 2 GB it had. More on that below.

## The data

10M synthetic rows, one CSV, loaded into all three in the same order so nobody gets an unfair
deal:

```
id (bigint PK) | user_id (int) | status | amount (decimal) | created_at (epoch) | payload (varchar)
```

`user_id` spreads across ~1M distinct values, so a secondary lookup returns a handful of rows
and a range scan returns a few thousand. Nothing exotic.

## How I ran it

1. Generate one CSV on the host (`scripts/generate_data.sh`).
2. Load it with each engine's own bulk path: Postgres `COPY`, MySQL `LOAD DATA INFILE`, and for
   SurrealDB, batched `INSERT` over the HTTP `/sql` endpoint, because it has no `COPY` equivalent.
3. Build the `user_id` index as a separate, timed step.
4. Hammer all three with the same read workload from one Python client, using the same random
   key sequence for each (`scripts/bench_read.py`).

Reads were measured at ~500k rows, since that's the most SurrealDB would hold. Postgres and
MySQL were reloaded to 500k for that part so the read comparison is fair on row count. The load
numbers below are at the full 10M.

## Load results (10M rows)

| Engine | Load | + index | Rate | On disk |
|---|---|---|---|---|
| PostgreSQL 17 | 23.5 s | +12.5 s | ~425k rows/s | 1034 MB (108 B/row) |
| MySQL 8.4 | 59.9 s | +26.9 s | ~167k rows/s | 603 MB (63 B/row) |
| SurrealDB | never finished | index build hung (300 s timeout) | ~6-15k rows/s until it hangs | 297 MB for 0.57M rows (~540 B/row) |

SurrealDB was fine up to roughly 250-500k rows, moving at about 15k rows/s. Then one write
batch would stall forever. After that, nothing responded until I restarted the container. Even
building the `user_id` index on 570k rows hung the same way, on its own, right after a clean
restart with nothing else running.

## Read latency (~500k rows)

| Operation | PostgreSQL | MySQL | SurrealDB |
|---|---|---|---|
| PK lookup | 0.17 ms · 5900 qps | 0.22 ms · 4500 qps | ~35-65 ms · 15-20 qps |
| Secondary lookup | 0.17 ms | 0.24 ms | no index possible; full scan hung |
| Range agg (5k span) | 4.3 ms | 9.8 ms | timed out |
| Full-scan agg | 79 ms | 103 ms | timed out |
| Single-row insert | 0.57 ms · 1770/s | 1.85 ms · 540/s | skipped (would wedge it) |

My first instinct was that the 35 ms was HTTP overhead: I was opening a fresh TCP connection
per query, which is unfair since Postgres and MySQL run over a persistent binary protocol. So I
retested SurrealDB with a kept-alive connection. It was still 65 ms average, 182 ms at p95. The
overhead wasn't the network. The reads were genuinely hitting disk, because that 16 MB block
cache wasn't holding much of a 570k-row table.

## What I actually learned

The wedging is the real story. On a single core with fsync on every commit, RocksDB's
flush/compaction seems to stall writes long enough that the client gives up, and the abandoned
transaction keeps holding the single writer lock. The server never takes it back on its own. I
tried smaller batches, longer timeouts, idempotent inserts so retries were safe, and the
official `surreal import` with a 921 MB file. Same wall every time, just at slightly different
row counts.

A few smaller things fell out of it:

- SurrealDB left ~1.8 GB of RAM on the table while its reads went to disk. That looks like a
  tuning default nobody expected you to keep, but out of the box, this is what you get.
- It wrote about 540 bytes per row against Postgres's 108 and MySQL's 63. Some of that is the
  uncompacted LSM tree, some is storing field names on every record because it's schemaless.
- MySQL's clustered primary key made its point lookups the most consistent of the three, though
  it was the slowest to load and the weakest on the aggregate query.
- Postgres was the least dramatic option, which is the highest compliment a database can get.

## Being fair to SurrealDB

I don't want this to read as a hit piece. I drove it through the HTTP endpoint; its WebSocket
RPC might behave better. I left RocksDB at defaults, and it clearly wants hand-tuning. It's a
young project moving fast, and I tested `latest`. And this was a deliberately cruel box. On a
machine with real RAM and cores, the multi-model, graph, and live-query features it's actually
built for might be worth the trade. The narrow claim here is just: it is not ready for
100M-on-2GB, and I have the restart count to prove it.

## Reproduce it

```bash
# point DOCKER_HOST at a machine with a few spare cores and GB, then:
./scripts/generate_data.sh 10000000
./scripts/setup_databases.sh
./scripts/load_postgres.sh
./scripts/load_mysql.sh
python scripts/loader.py /data/data10m.csv   # SurrealDB — expect it to hang past ~0.5M on 2GB
python scripts/bench_read.py
```

Raw tool output is in [RESULTS.md](RESULTS.md).

Run in July 2026. This is one constrained run, not a certified TPC result. Treat the numbers as
orders of magnitude and behavior, not gospel.
