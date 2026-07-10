# -*- coding: utf-8 -*-
"""
Flight Radar 블랙박스 프로브 — 필터 없이 전부 기록.
목적: 네이버가 실제로 부르는 모든 요청을 눈으로 보고 진짜 가격 API를 찾는다.
  1) 검색 버튼 클릭 → URL이 바뀌는지 추적
  2) 모든 요청(request) 주소를 requests_all.txt 에 통째로 저장
  3) 6~7자리 숫자(가격 후보) 3개 이상 담긴 JSON 응답을 candidates.txt 에 기록
  4) 클릭 전/후 스크린샷 2장
전체 100초 안에 끝난다. 아무것도 필터링하지 않는다.
"""
import re, time
from datetime import date, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"; RAW.mkdir(exist_ok=True)

dep = date(2026,10,15); ret = dep + timedelta(days=7)
url = f"https://flight.naver.com/flights/international/ICN-FCO-{dep:%Y%m%d}/FCO-ICN-{ret:%Y%m%d}?adult=1&fareType=Y"
print("PROBE URL:", url)

FARE_RE = re.compile(r'(?<!\d)(\d{6,7})(?!\d)')
all_requests = []      # 모든 요청 주소
json_responses = []    # (url, status, fare_count, sample_fares)
candidates = []        # 가격 후보 3+ 인 응답

with sync_playwright() as p:
    br = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled","--lang=ko-KR"])
    ctx = br.new_context(locale="ko-KR", timezone_id="Asia/Seoul", viewport={"width":1440,"height":900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    page = ctx.new_page()

    def on_request(req):
        all_requests.append(f"{req.method} {req.url}")

    def on_resp(r):
        try:
            ct = r.headers.get("content-type","")
            if "json" not in ct: return
            body = r.text()
        except Exception:
            return
        fares = sorted(set(int(x) for x in FARE_RE.findall(body) if 300000 < int(x) < 6000000))
        json_responses.append((r.url.split("?")[0], r.status, len(fares), fares[:6]))
        if len(fares) >= 3:
            candidates.append((r.url, fares[:12], len(body)))
            idx = len(candidates)
            if idx <= 5:
                safe = re.sub(r'[^a-zA-Z0-9]', '_', r.url.split("//")[-1])[:55]
                (RAW/f"cand{idx}_{safe}.json").write_text(body[:1_500_000], encoding="utf-8")

    page.on("request", on_request)
    page.on("response", on_resp)

    url_before = None
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        url_before = page.url
        print(f"[goto] ok  현재URL: {url_before[:90]}")
    except Exception as e:
        print(f"[goto] EXCEPTION {type(e).__name__}")

    page.wait_for_timeout(2000)
    try:
        page.screenshot(path=str(RAW/"1_before_click.png"))
        print("[save] 1_before_click.png")
    except Exception: pass

    # 검색 버튼 클릭 + 클릭 후 URL/네비게이션 관찰
    clicked=False
    for sel in ["button:has-text('검색')", "a:has-text('검색')", "[role=button]:has-text('검색')"]:
        try:
            el=page.query_selector(sel)
            if el:
                el.click(timeout=3000); clicked=True
                print(f"[click] 검색 클릭 성공 ({sel})")
                break
        except Exception as e:
            continue
    if not clicked: print("[click] 버튼 못찾음")

    # 클릭 후 40초 관찰 (가격 후보 잡히면 조기 종료)
    for i in range(20):
        page.wait_for_timeout(2000)
        if candidates:
            print(f"[wait] {(i+1)*2}초 만에 가격후보 응답 포착")
            break
    url_after = page.url
    print(f"[url] 클릭 후 URL: {url_after[:90]}")
    print(f"[url] URL 변경됨: {url_before != url_after}")

    try:
        page.screenshot(path=str(RAW/"2_after_click.png"))
        print("[save] 2_after_click.png")
    except Exception: pass

    # 전체 요청 목록 저장
    (RAW/"requests_all.txt").write_text("\n".join(all_requests), encoding="utf-8")
    print(f"\n[net] 전체 요청 {len(all_requests)}건 → requests_all.txt 저장")
    print(f"[net] JSON 응답 {len(json_responses)}건")
    print(f"[net] 가격후보(3+) 응답 {len(candidates)}건")
    for u, fares, ln in candidates[:8]:
        print(f"   ★ {u[:160]}")
        print(f"     가격: {fares}  (len={ln})")

    # 가격후보 없으면 JSON 응답이라도 전부 보여줌
    if not candidates:
        print("[net] 가격후보 없음 — JSON 응답 전체 목록:")
        for u,s,fc,fs in json_responses:
            print(f"   - {s} fares={fc} {u[:110]}")
        # naver 도메인 요청 중 특이한 것 상위 20개
        print("\n[net] naver.com 요청 주소 상위(중복제거):")
        seen=set()
        for line in all_requests:
            u=line.split(" ",1)[-1].split("?")[0]
            if "naver.com" not in u or u in seen: continue
            seen.add(u); print(f"   - {u[:120]}")
            if len(seen)>=25: break

    br.close()
print("\nPROBE DONE")
