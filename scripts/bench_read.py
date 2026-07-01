import time, random, statistics, json, urllib.request, base64
import psycopg2, mysql.connector

N = 500000
PK_ITERS=3000; SEC_ITERS=2000; RANGE_ITERS=200; AGG_ITERS=3; INS_PG_MY=2000; INS_SDB=100
random.seed(42)
pk_keys  = [random.randint(1, N) for _ in range(PK_ITERS)]
sec_keys = [random.randint(0, 999999) for _ in range(SEC_ITERS)]
rng_keys = [random.randint(0, 995000) for _ in range(RANGE_ITERS)]

def pct(xs,p):
    xs=sorted(xs); return xs[min(int(len(xs)*p/100),len(xs)-1)]*1000
def rep(name,lat):
    print(f"  {name:<26} n={len(lat):<5} avg={statistics.mean(lat)*1000:8.3f}ms  p50={pct(lat,50):8.3f}ms  p95={pct(lat,95):8.3f}ms  qps={len(lat)/sum(lat):8.1f}")

def run_pg():
    print("\n=== PostgreSQL (500k, indexed) ===")
    c=psycopg2.connect(host="pgbench",user="postgres",password="bench",dbname="bench"); c.autocommit=True; cur=c.cursor(); cur.execute("SELECT 1")
    lat=[]
    for k in pk_keys:
        t=time.perf_counter(); cur.execute("SELECT * FROM events WHERE id=%s",(k,)); cur.fetchall(); lat.append(time.perf_counter()-t)
    rep("PK lookup",lat)
    lat=[]
    for k in sec_keys:
        t=time.perf_counter(); cur.execute("SELECT * FROM events WHERE user_id=%s",(k,)); cur.fetchall(); lat.append(time.perf_counter()-t)
    rep("secondary lookup",lat)
    lat=[]
    for k in rng_keys:
        t=time.perf_counter(); cur.execute("SELECT status,count(*),sum(amount) FROM events WHERE user_id>=%s AND user_id<%s GROUP BY status",(k,k+5000)); cur.fetchall(); lat.append(time.perf_counter()-t)
    rep("range agg (5k span)",lat)
    lat=[]
    for _ in range(AGG_ITERS):
        t=time.perf_counter(); cur.execute("SELECT count(*),avg(amount) FROM events"); cur.fetchall(); lat.append(time.perf_counter()-t)
    rep("full-scan agg",lat)
    lat=[]
    for i in range(INS_PG_MY):
        t=time.perf_counter(); cur.execute("INSERT INTO events VALUES(%s,%s,%s,%s,%s,%s)",(N+1+i,i%1000000,i%5,9.99,1600000000,f"ins{i}")); lat.append(time.perf_counter()-t)
    rep("single-row insert",lat)
    c.close()

def run_my():
    print("\n=== MySQL (500k, indexed) ===")
    c=mysql.connector.connect(host="mybench",user="root",password="bench",database="bench",autocommit=True); cur=c.cursor(); cur.execute("SELECT 1"); cur.fetchall()
    lat=[]
    for k in pk_keys:
        t=time.perf_counter(); cur.execute("SELECT * FROM events WHERE id=%s",(k,)); cur.fetchall(); lat.append(time.perf_counter()-t)
    rep("PK lookup",lat)
    lat=[]
    for k in sec_keys:
        t=time.perf_counter(); cur.execute("SELECT * FROM events WHERE user_id=%s",(k,)); cur.fetchall(); lat.append(time.perf_counter()-t)
    rep("secondary lookup",lat)
    lat=[]
    for k in rng_keys:
        t=time.perf_counter(); cur.execute("SELECT status,count(*),sum(amount) FROM events WHERE user_id>=%s AND user_id<%s GROUP BY status",(k,k+5000)); cur.fetchall(); lat.append(time.perf_counter()-t)
    rep("range agg (5k span)",lat)
    lat=[]
    for _ in range(AGG_ITERS):
        t=time.perf_counter(); cur.execute("SELECT count(*),avg(amount) FROM events"); cur.fetchall(); lat.append(time.perf_counter()-t)
    rep("full-scan agg",lat)
    lat=[]
    for i in range(INS_PG_MY):
        t=time.perf_counter(); cur.execute("INSERT INTO events VALUES(%s,%s,%s,%s,%s,%s)",(N+1+i,i%1000000,i%5,9.99,1600000000,f"ins{i}")); lat.append(time.perf_counter()-t)
    rep("single-row insert",lat)
    c.close()

AUTH="Basic "+base64.b64encode(b"root:bench").decode()
def sdb(q,tmo=120):
    r=urllib.request.Request("http://sdbbench:8000/sql",data=q.encode(),
        headers={"Accept":"application/json","surreal-ns":"test","surreal-db":"test","Authorization":AUTH,"Content-Type":"text/plain"})
    return json.loads(urllib.request.urlopen(r,timeout=tmo).read())
def run_sdb():
    print("\n=== SurrealDB (~573k, NO secondary index — build wedged) ===")
    lat=[]
    for k in pk_keys:
        t=time.perf_counter(); sdb(f"SELECT * FROM events:{k}"); lat.append(time.perf_counter()-t)
    rep("PK lookup (record id)",lat)
    lat=[]
    for k in sec_keys[:300]:   # unindexed full scan — fewer iters
        t=time.perf_counter(); sdb(f"SELECT * FROM events WHERE user_id={k}"); lat.append(time.perf_counter()-t)
    rep("secondary lookup (NO idx)",lat)
    lat=[]
    for k in rng_keys[:50]:
        t=time.perf_counter(); sdb(f"SELECT status,count() AS c,math::sum(amount) AS s FROM events WHERE user_id>={k} AND user_id<{k+5000} GROUP BY status"); lat.append(time.perf_counter()-t)
    rep("range agg (5k span)",lat)
    lat=[]
    for _ in range(AGG_ITERS):
        t=time.perf_counter(); sdb("SELECT count() AS c, math::mean(amount) AS a FROM events GROUP ALL"); lat.append(time.perf_counter()-t)
    rep("full-scan agg",lat)
    lat=[]
    for i in range(INS_SDB):
        t=time.perf_counter(); sdb(f"INSERT INTO events {{id:{N+1+i},user_id:{i},status:0,amount:9.99,created_at:1600000000,payload:'ins{i}'}}"); lat.append(time.perf_counter()-t)
    rep("single-row insert",lat)

for fn in (run_pg, run_my, run_sdb):
    try: fn()
    except Exception as e: print("  ERROR:", repr(e)[:200])
