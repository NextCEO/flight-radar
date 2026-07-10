# -*- coding: utf-8 -*-
"""
Flight Radar 진단 프로브 v2 — 검색 버튼 클릭 + 전체 네트워크 기록.
페이지를 열고, '검색' 버튼을 눌러 실제 가격 조회를 발동시킨 뒤,
네이버가 호출하는 모든 XHR/fetch 응답 주소를 기록한다.
가격 데이터가 실제로 어느 API로 오는지 포착하는 것이 목적.
전체 90초 안에 끝난다.
"""
import json, re, time
from datetime import date, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"; RAW.mkdir(exist_ok=True)

dep = date(2026,10,15); ret = dep + timedelta(days=7)
url = f"https://flight.naver.com/flights/international/ICN-FCO-{dep:%Y%m%d}/FCO-ICN-{ret:%Y%m%d}?adult=1&fareType=Y"
print("PROBE URL:", url)

# 가격 후보를 담고 있을 법한 응답만 걸러서 저장
INTEREST = re.compile(r"(fare|flight|airline|price|international|graphql|api)", re.I)
records = []          # (status, url) 전체
payload_hits = []     # 가격 숫자가 들어있던 응답

FARE_RE = re.compile(r'(?<!\d)(\d{6,7})(?!\d)')  # 6~7자리 숫자 = 항공권가 후보

with sync_playwright() as p:
    br = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled","--lang=ko-KR"])
    ctx = br.new_context(locale="ko-KR", timezone_id="Asia/Seoul", viewport={"width":1440,"height":900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    page = ctx.new_page()

    def on_resp(r):
        u = r.url
        if not INTEREST.search(u): return
        records.append((r.status, u[:150]))
        # JSON 응답이면 가격 숫자가 있는지 확인
        try:
            ct = r.headers.get("content-type","")
            if "json" in ct:
                body = r.text()
                fares = [int(x) for x in FARE_RE.findall(body) if 300000 < int(x) < 6000000]
                if fares:
                    payload_hits.append((u[:150], sorted(set(fares))[:8], len(body)))
                    # 원본도 저장 (최대 3개)
                    if len(payload_hits) <= 3:
                        safe = re.sub(r'[^a-zA-Z0-9]', '_', u.split("naver.com")[-1])[:60]
                        (RAW/f"resp_{safe}.json").write_text(body[:1_500_000], encoding="utf-8")
        except Exception:
            pass

    page.on("response", on_resp)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        print(f"[goto] status ok")
    except Exception as e:
        print(f"[goto] EXCEPTION {type(e).__name__}")

    # 검색 버튼 클릭 시도 (여러 셀렉터 후보)
    clicked = False
    for sel in ["button:has-text('검색')", "a:has-text('검색')", "[class*='search'] button", "button[class*='search']"]:
        try:
            el = page.query_selector(sel)
            if el:
                el.click(timeout=3000); clicked = True
                print(f"[click] '검색' 버튼 클릭 성공  (selector: {sel})")
                break
        except Exception:
            continue
    if not clicked:
        print("[click] 검색 버튼 못 찾음 — 자동 로딩 대기로 진행")

    # 결과가 뜰 때까지 최대 40초 관찰 (가격 응답이 잡히면 조기 종료)
    for i in range(20):
        page.wait_for_timeout(2000)
        if payload_hits:
            print(f"[wait] {(i+1)*2}초 만에 가격 응답 포착")
            break

    print(f"\n[net] 관심 응답 총 {len(records)}건")
    print(f"[net] 가격 숫자 포함 응답 {len(payload_hits)}건")
    for u, fares, ln in payload_hits[:6]:
        print(f"   ★ {u}")
        print(f"     → 가격후보: {fares}  (len={ln})")
    # 가격 응답이 없으면, 어떤 주소들을 불렀는지라도 보여줌
    if not payload_hits:
        print("[net] (가격 응답 없음) 호출된 주소 상위:")
        seen=set()
        for s,u in records:
            base = u.split("?")[0]
            if base in seen: continue
            seen.add(base); print(f"   - {s}  {base}")
            if len(seen)>=15: break

    try:
        page.screenshot(path=str(RAW/"probe_screenshot.png"), full_page=False)
        print("[save] probe_screenshot.png")
    except Exception as e:
        print("[save] screenshot fail:", e)

    br.close()
print("\nPROBE DONE")
