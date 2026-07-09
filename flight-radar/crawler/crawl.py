# -*- coding: utf-8 -*-
"""
Flight Radar crawler v2 — ICN <-> Italy, 왕복 + 오픈조
routes.json의 9개 노선(왕복3+오픈조6)을 하루 ROTATE_GROUP개씩 순환 수집.
네이버항공 내부 API(airline-api.naver.com) 응답 JSON을 가로채 파싱. HTML 미사용.
"""
import json, os, random, re, sys, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT/"data"; RAW_DIR = ROOT/"raw"
DATA_DIR.mkdir(parents=True, exist_ok=True); RAW_DIR.mkdir(parents=True, exist_ok=True)
ROUTES = json.loads((Path(__file__).resolve().parent/"routes.json").read_text(encoding="utf-8"))
ORIGIN = ROUTES["origin"]; ALL_ROUTES = ROUTES["routes"]

DEP_START = date.fromisoformat(os.environ.get("DEP_START","2026-10-01"))
DEP_END   = date.fromisoformat(os.environ.get("DEP_END","2026-11-30"))
STAYS     = [int(s) for s in os.environ.get("STAYS","7,10,14").split(",")]
DEP_STEP  = int(os.environ.get("DEP_STEP","2"))
ROTATE_GROUP = int(os.environ.get("ROTATE_GROUP","3"))
MAX_SEARCHES = int(os.environ.get("MAX_SEARCHES","400"))
KST = timezone(timedelta(hours=9))

FARE_KEY_RE=re.compile(r"fare|price|amount",re.I)
VENDOR_KEY_RE=re.compile(r"agt|agent|partner|seller|vendor",re.I)
NAME_KEY_RE=re.compile(r"name|label|title",re.I)
FARE_MIN,FARE_MAX=350_000,6_000_000
VENDOR_CANON=[("트립닷컴",["trip.com","트립닷컴","trip"]),("인터파크투어",["인터파크","interpark"]),
  ("더현대트래블",["현대트래블","thehyundai","현대드림"]),("마이리얼트립",["마이리얼트립","myrealtrip"]),
  ("여행이지",["여행이지","tourez"]),("네이버항공",["네이버","naver"])]

def canon_vendor(name):
    low=name.lower()
    for c,keys in VENDOR_CANON:
        if any(k.lower() in low for k in keys): return c
    return name
def plausible(v): return isinstance(v,(int,float)) and FARE_MIN<=v<=FARE_MAX

def extract_fares(payload):
    fares=[]; vendor_fares={}
    def scan(node):
        if isinstance(node,dict):
            name=fare=None
            for k,v in node.items():
                if isinstance(v,str) and VENDOR_KEY_RE.search(k) and NAME_KEY_RE.search(k) and 1<len(v)<40: name=v
                if FARE_KEY_RE.search(k):
                    if plausible(v): fare=v if fare is None else min(fare,v)
                    elif isinstance(v,str) and v.replace(",","").isdigit():
                        n=int(v.replace(",",""))
                        if plausible(n): fare=n if fare is None else min(fare,n)
            if fare is not None:
                fares.append(fare)
                if name:
                    c=canon_vendor(name); vendor_fares[c]=min(vendor_fares.get(c,fare),fare)
            for v in node.values(): scan(v)
        elif isinstance(node,list):
            for v in node: scan(v)
    scan(payload)
    if not fares: return None,[]
    vendors=sorted([{"name":n,"fare":int(f)} for n,f in vendor_fares.items()],key=lambda x:x["fare"])[:12]
    return int(min(fares)),vendors

def build_url(route,dep,ret):
    ci,co=route["in"],route["out"]
    if route["type"]=="roundtrip":
        return f"https://flight.naver.com/flights/international/{ORIGIN}-{ci}-{dep:%Y%m%d}/{ci}-{ORIGIN}-{ret:%Y%m%d}?adult=1&fareType=Y"
    return f"https://flight.naver.com/flights/international/{ORIGIN}-{ci}-{dep:%Y%m%d}/{co}-{ORIGIN}-{ret:%Y%m%d}?adult=1&fareType=Y"

def search_once(page,route,dep,ret,dump=None):
    url=build_url(route,dep,ret); captured=[]; last=[time.time()]
    def on_resp(r):
        try:
            if "airline-api.naver.com" not in r.url: return
            captured.append(r.json()); last[0]=time.time()
        except Exception: pass
    page.on("response",on_resp)
    try:
        page.goto(url,wait_until="domcontentloaded",timeout=45_000)
        end=time.time()+35
        while time.time()<end:
            page.wait_for_timeout(1500)
            if captured and time.time()-last[0]>6: break
    finally:
        page.remove_listener("response",on_resp)
    best=(None,[]); best_raw=None
    for b in captured:
        f,vs=extract_fares(b)
        if f is not None and (best[0] is None or f<best[0] or len(vs)>len(best[1])): best=(f,vs); best_raw=b
    if best_raw is not None and dump is not None and not dump.exists():
        dump.write_text(json.dumps(best_raw,ensure_ascii=False)[:2_000_000],encoding="utf-8")
    return best

def todays_routes():
    if ROTATE_GROUP<=0 or ROTATE_GROUP>=len(ALL_ROUTES): return ALL_ROUTES
    groups=[ALL_ROUTES[i:i+ROTATE_GROUP] for i in range(0,len(ALL_ROUTES),ROTATE_GROUP)]
    gi=date.today().toordinal()%len(groups)
    print(f"[rotate] 오늘 그룹 {gi+1}/{len(groups)}: {[r['id'] for r in groups[gi]]}")
    return groups[gi]

def main():
    routes=todays_routes(); deps=[]; d=DEP_START
    while d<=DEP_END: deps.append(d); d+=timedelta(days=DEP_STEP)
    combos=[(rt,dep,dep+timedelta(days=st),st) for rt in routes for dep in deps for st in STAYS][:MAX_SEARCHES]
    print(f"검색 {len(combos)}건 · 노선 {len(routes)} · 출발 {len(deps)}일 · 체류 {STAYS}")
    out_path=DATA_DIR/"fares.json"; existing={}
    if out_path.exists():
        try:
            prev=json.loads(out_path.read_text(encoding="utf-8"))
            if not prev.get("sample"):
                for r in prev.get("results",[]): existing[(r["route"],r["dep"],r["stay"])]=r
        except Exception: pass
    ok=fail=0
    with sync_playwright() as p:
        br=p.chromium.launch(headless=True,args=["--disable-blink-features=AutomationControlled","--lang=ko-KR"])
        ctx=br.new_context(locale="ko-KR",timezone_id="Asia/Seoul",viewport={"width":1440,"height":900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
        page=ctx.new_page()
        for i,(rt,dep,ret,st) in enumerate(combos,1):
            raw=RAW_DIR/f"sample_{rt['id']}.json"
            try: fare,vendors=search_once(page,rt,dep,ret,dump=raw)
            except Exception as e:
                print(f"  [{i}/{len(combos)}] {rt['id']} {dep} +{st}d ERROR {type(e).__name__}"); fare,vendors=None,[]
            if fare is not None:
                ok+=1
                existing[(rt["id"],dep.isoformat(),st)]={"route":rt["id"],"in":rt["in"],"out":rt["out"],
                    "type":rt["type"],"label":rt["label"],"dep":dep.isoformat(),"ret":ret.isoformat(),"stay":st,
                    "minFare":fare,"vendors":vendors,"fetchedAt":datetime.now(KST).isoformat(timespec="minutes")}
                print(f"  [{i}/{len(combos)}] {rt['id']} {dep} +{st}d → {fare:,}원 (판매처 {len(vendors)})")
            else:
                fail+=1; print(f"  [{i}/{len(combos)}] {rt['id']} {dep} +{st}d → 실패")
            time.sleep(random.uniform(3,6))
        br.close()
    out={"generated":datetime.now(KST).isoformat(timespec="minutes"),"origin":ORIGIN,
         "window":{"start":DEP_START.isoformat(),"end":DEP_END.isoformat()},"stays":STAYS,
         "routes":ALL_ROUTES,"results":sorted(existing.values(),key=lambda r:(r["route"],r["dep"],r["stay"]))}
    out_path.write_text(json.dumps(out,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print(f"\n완료: 성공 {ok} / 실패 {fail} → {out_path} ({out_path.stat().st_size:,} bytes)")
    if ok==0 and combos: sys.exit(1)

if __name__=="__main__": main()
