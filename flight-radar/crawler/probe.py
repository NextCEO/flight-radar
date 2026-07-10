# -*- coding: utf-8 -*-
"""
Flight Radar 진단 프로브 v3 — 광고 노이즈 제거 + 진짜 가격 API만 포착.
검색 버튼 클릭 후, 모든 JSON 응답을 검사하되:
  - 광고/배너/트래킹 도메인(veta, gfp, banner, ad 등)은 완전 제외
  - 가격 후보 숫자가 여러 개(3+) 있고, 항공/공항 코드가 함께 있는 응답만 '진짜'로 판정
전체 90초 안에 끝난다.
"""
import re
from datetime import date, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"; RAW.mkdir(exist_ok=True)

dep = date(2026,10,15); ret = dep + timedelta(days=7)
url = f"https://flight.naver.com/flights/international/ICN-FCO-{dep:%Y%m%d}/FCO-ICN-{ret:%Y%m%d}?adult=1&fareType=Y"
print("PROBE URL:", url)

# 광고/트래킹/배너 — 완전 제외할 도메인·경로
BLOCK = re.compile(r"(veta|/gfp/|banner|/ad[s/_]|doubleclick|analytics|log|track|pixel|beacon|wcslog|nlog)", re.I)
FARE_RE = re.compile(r'(?<!\d)(\d{6,7})(?!\d)')
CODE_RE = re.compile(r'\b(FCO|ICN|MXP|VCE)\b')          # 공항 코드
AIRLINE_RE = re.compile(r'\b([A-Z]{2}\d{2,4})\b')       # 항공편명 (KE123 등)

records = []; real_hits = []

with sync_playwright() as p:
    br = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled","--lang=ko-KR"])
    ctx = br.new_context(locale="ko-KR", timezone_id="Asia/Seoul", viewport={"width":1440,"height":900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    page = ctx.new_page()

    def on_resp(r):
        u = r.url
        if BLOCK.search(u): return                       # 광고/트래킹 제외
        try:
            ct = r.headers.get("content-type","")
            if "json" not in ct: return
            body = r.text()
        except Exception:
            return
        records.append((r.status, u.split("?")[0][:120]))
        fares = sorted(set(int(x) for x in FARE_RE.findall(body) if 300000 < int(x) < 6000000))
        codes = set(CODE_RE.findall(body))
        airlines = set(AIRLINE_RE.findall(body))
        # 진짜 가격 API 판정: 가격 후보 3개 이상 + (공항코드 또는 항공편명 존재)
        if len(fares) >= 3 and (codes or airlines):
            real_hits.append((u, fares[:10], sorted(codes), sorted(airlines)[:5], len(body)))
            if len(real_hits) <= 3:
                safe = re.sub(r'[^a-zA-Z0-9]', '_', u.split("naver.com")[-1])[:50]
                (RAW/f"real_{safe}.json").write_text(body[:1_500_000], encoding="utf-8")

    page.on("response", on_resp)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000); print("[goto] ok")
    except Exception as e:
        print(f"[goto] EXCEPTION {type(e).__name__}")

    clicked=False
    for sel in ["button:has-text('검색')", "a:has-text('검색')"]:
        try:
            el=page.query_selector(sel)
            if el: el.click(timeout=3000); clicked=True; print(f"[click] 검색 클릭 ({sel})"); break
        except Exception: continue
    if not clicked: print("[click] 버튼 못찾음 — 자동대기")

    for i in range(20):
        page.wait_for_timeout(2000)
        if real_hits: print(f"[wait] {(i+1)*2}초 만에 진짜 가격 API 포착"); break

    print(f"\n[net] 광고 제외 후 JSON 응답 {len(records)}건")
    print(f"[net] 진짜 가격 API 판정 {len(real_hits)}건")
    for u, fares, codes, airlines, ln in real_hits[:6]:
        print(f"   ★ {u.split('?')[0]}")
        print(f"     전체주소: {u[:200]}")
        print(f"     가격: {fares}")
        print(f"     공항코드: {codes}  항공편: {airlines}  (len={ln})")
    if not real_hits:
        print("[net] 진짜 API 못찾음 — JSON 응답 주소 전체:")
        seen=set()
        for s,u in records:
            if u in seen: continue
            seen.add(u); print(f"   - {s}  {u}")

    try:
        page.screenshot(path=str(RAW/"probe_screenshot.png")); print("[save] screenshot")
    except Exception: pass
    br.close()
print("\nPROBE DONE")
