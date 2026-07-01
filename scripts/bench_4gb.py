import time, random, statistics, json, urllib.request, base64
import psycopg2, mysql.connector

N=10_000_000
PK=3000; SEC=2000; RNG=200; AGG=3; INS=2000
random.seed(42)
pk=[random.randint(1,N) for _ in range(PK)]
sec=[random.randint(0,999999) for _ in range(SEC)]
rng=[random.randint(0,9_900_000) for _ in range(RNG)]

def pct(x,p): x=sorted(x); return x[min(int(len(x)*p/100),len(x)-1)]*1000
def rep(n,l): print(f"  {n:<28} k={len(l):<5} avg={statistics.mean(l)*1000:8.3f}ms  p50={pct(l,50):8.3f}ms  p95={pct(l,95):8.3f}ms  qps={len(l)/sum(l):8.1f}")

def sql_engine(label, connect, insert_sql):
    print(f"\n=== {label} (10M, indexed) ===")
    c=connect(); cur=c.cursor(); cur.execute("SELECT 1"); cur.fetchall()
    l=[]
    for k in pk: t=time.perf_counter(); cur.execute("SELECT * FROM events WHERE id=%s",(k,)); cur.fetchall(); l.append(time.perf_counter()-t)
    rep("PK lookup",l)
    l=[]
    for k in sec: t=time.perf_counter(); cur.execute("SELECT * FROM events WHERE user_id=%s",(k,)); cur.fetchall(); l.append(time.perf_counter()-t)
    rep("secondary lookup",l)
    l=[]
    for k in rng: t=time.perf_counter(); cur.execute("SELECT status,count(*),sum(amount) FROM events WHERE user_id>=%s AND user_id<%s GROUP BY status",(k,k+5000)); cur.fetchall(); l.append(time.perf_counter()-t)
    rep("range agg (5k span)",l)
    l=[]
    for _ in range(AGG): t=time.perf_counter(); cur.execute("SELECT count(*),avg(amount) FROM events"); cur.fetchall(); l.append(time.perf_counter()-t)
    rep("full-scan agg",l)
    l=[]
    for i in range(INS): t=time.perf_counter(); cur.execute(insert_sql,(N+1+i,i%1000000,i%5,9.99,1600000000,f"ins{i}")); l.append(time.perf_counter()-t)
    rep("single-row insert",l)
    c.close()

def pgc():
    c=psycopg2.connect(host="pgbench",user="postgres",password="bench",dbname="bench"); c.autocommit=True; return c
def myc():
    return mysql.connector.connect(host="mybench",user="root",password="bench",database="bench",autocommit=True)

try: sql_engine("PostgreSQL", pgc, "INSERT INTO events VALUES(%s,%s,%s,%s,%s,%s)")
except Exception as e: print("PG ERROR",repr(e)[:150])
try: sql_engine("MySQL", myc, "INSERT INTO events VALUES(%s,%s,%s,%s,%s,%s)")
except Exception as e: print("MySQL ERROR",repr(e)[:150])

AUTH="Basic "+base64.b64encode(b"root:bench").decode()
def sdb(q,tmo=120):
    r=urllib.request.Request("http://sdbbench:8000/sql",data=q.encode(),
        headers={"Accept":"application/json","surreal-ns":"test","surreal-db":"test","Authorization":AUTH,"Content-Type":"text/plain"})
    return json.loads(urllib.request.urlopen(r,timeout=tmo).read())
def run_sdb():
    print("\n=== SurrealDB (10M, NO secondary index — build OOM-killed at 4GB) ===")
    l=[]
    for k in pk: t=time.perf_counter(); sdb(f"SELECT * FROM events:{k}"); l.append(time.perf_counter()-t)
    rep("PK lookup (record id)",l)
    l=[]
    for k in sec[:30]:   # unindexed full scan over 10M — few iters
        try: t=time.perf_counter(); sdb(f"SELECT * FROM events WHERE user_id={k}",tmo=120); l.append(time.perf_counter()-t)
        except Exception as e: print("  secondary lookup FAILED:",type(e).__name__); break
    if l: rep("secondary lookup (NO idx, full scan)",l)
    l=[]
    for _ in range(AGG):
        try: t=time.perf_counter(); sdb("SELECT count() AS c, math::mean(amount) AS a FROM events GROUP ALL",tmo=180); l.append(time.perf_counter()-t)
        except Exception as e: print("  full-scan agg FAILED:",type(e).__name__); break
    if l: rep("full-scan agg",l)

run_sdb()
