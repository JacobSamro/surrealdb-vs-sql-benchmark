import time, json, urllib.request, urllib.error, base64
AUTH="Basic "+base64.b64encode(b"root:bench").decode()
def call(q, ns=True, tmo=120):
    h={"Accept":"application/json","Authorization":AUTH,"Content-Type":"text/plain"}
    if ns: h["surreal-ns"]="test"; h["surreal-db"]="test"
    req=urllib.request.Request("http://sdbbench:8000/sql",data=q.encode(),headers=h)
    t=time.perf_counter()
    try:
        r=json.loads(urllib.request.urlopen(req,timeout=tmo).read()); dt=time.perf_counter()-t
        return dt, r
    except urllib.error.HTTPError as e:
        dt=time.perf_counter()-t
        return dt, {"HTTP_ERROR": e.code, "body": e.read().decode()[:300]}

print("bootstrap:", round(call("DEFINE NAMESPACE IF NOT EXISTS test; USE NS test; DEFINE DATABASE IF NOT EXISTS test;", ns=False)[0],3))
t,r=call("SELECT 1;"); print("SELECT 1:", round(t*1000,1),"ms ->", str(r)[:150])
def ins(n, start):
    rows=",".join(f"{{id:{start+i},user_id:{i},status:0,amount:1.5,created_at:1,payload:'x'}}" for i in range(n))
    t,r=call("INSERT INTO events ["+rows+"];")
    ok = isinstance(r,list) and r and r[0].get("status")=="OK"
    print(f"INSERT {n:>5} rows: {t:7.3f}s  ok={ok}"+("" if ok else f"  -> {str(r)[:250]}"))
for n,s in [(5,1),(100,100),(1000,1000),(1000,5000),(1000,10000)]:
    ins(n,s)
