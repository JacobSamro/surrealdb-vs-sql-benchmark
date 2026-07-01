import time, json, urllib.request, base64, sys

BATCH = 1000
TMO = 300
AUTH = "Basic " + base64.b64encode(b"root:bench").decode()

def call(q, ns=True):
    last=None
    for attempt in range(8):
        try:
            h={"Accept":"application/json","Authorization":AUTH,"Content-Type":"text/plain"}
            if ns: h["surreal-ns"]="test"; h["surreal-db"]="test"
            req=urllib.request.Request("http://sdbbench:8000/sql",data=q.encode(),headers=h)
            r=json.loads(urllib.request.urlopen(req,timeout=TMO).read())
            for s in r:
                if s.get("status")!="OK": raise RuntimeError(s)
            return r
        except Exception as e:
            last=e; print(f"    [retry {attempt} {type(e).__name__}]",flush=True); time.sleep(3)
    raise last

call("DEFINE NAMESPACE IF NOT EXISTS test; USE NS test; DEFINE DATABASE IF NOT EXISTS test;", ns=False)

t0=time.perf_counter(); buf=[]; done=0
def flush():
    global buf,done
    if not buf: return
    # idempotent: retried batches that already committed become no-ops
    call("INSERT INTO events [" + ",".join(buf) + "] ON DUPLICATE KEY UPDATE id=id;")
    done+=len(buf); buf=[]

CSV = sys.argv[1] if len(sys.argv)>1 else "/data/data10m.csv"
with open(CSV) as f:
    for line in f:
        i,uid,st,amt,ts,pl=line.rstrip("\n").split(",")
        buf.append(f"{{id:{i},user_id:{uid},status:{st},amount:{amt},created_at:{ts},payload:'{pl}'}}")
        if len(buf)==BATCH:
            flush()
            if done%250000==0:
                el=time.perf_counter()-t0
                print(f"  loaded {done:>9,}  {el:7.1f}s  {done/el:8.0f} rows/s",flush=True)
flush()
el=time.perf_counter()-t0
print(f"SDB bulk load: {el:.1f}s  ({done:,} rows, {done/el:.0f} rows/s)",flush=True)
t1=time.perf_counter()
call("DEFINE INDEX idx_user ON events FIELDS user_id;")
print(f"SDB build 2nd index: {time.perf_counter()-t1:.1f}s",flush=True)
print("count:", call("SELECT count() FROM events GROUP ALL;")[0]["result"])
