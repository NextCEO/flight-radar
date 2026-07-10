# -*- coding: utf-8 -*-
"""
Flight Radar 진단 프로브 — 네이버가 GitHub 해외 IP를 받아주는지 확인.
딱 1개 검색(FCO 왕복 1건)만 열고:
  - 페이지 로딩 성공 여부
  - airline-api 응답을 하나라도 받았는지
  - 스크린샷 + 페이지 HTML 앞부분을 raw/ 에 저장 (차단/캡차 확인용)
전체 60초 안에 무조건 끝난다.
"""
import json, time
from datetime import date, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"; RAW.mkdir(exist_ok=True)

dep = date(2026,10,15); ret = dep + timedelta(days=7)
url = f"https://flight.naver.com/flights/international/ICN-FCO-{dep:%Y%m%d}/FCO-ICN-{ret:%Y%m%d}?adult=1&fareType=Y"
print("PROBE URL:", url)

api_hits = []
with sync_playwright() as p:
    br = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled","--lang=ko-KR"])
    ctx = br.new_context(locale="ko-KR", timezone_id="Asia/Seoul", viewport={"width":1440,"height":900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    page = ctx.new_page()
    def on_resp(r):
        if "airline-api.naver.com" in r.url:
            api_hits.append((r.status, r.url[:120]))
    page.on("response", on_resp)

    t0 = time.time(); status="?"
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        status = resp.status if resp else "no-response"
        print(f"[goto] status={status}  elapsed={time.time()-t0:.1f}s")
    except Exception as e:
        print(f"[goto] EXCEPTION {type(e).__name__}: {e}  elapsed={time.time()-t0:.1f}s")

    # 최대 20초 동안 api 응답을 기다리며 관찰
    for i in range(10):
        page.wait_for_timeout(2000)
        if api_hits: break
    print(f"[api] airline-api 응답 {len(api_hits)}건")
    for s,u in api_hits[:5]: print(f"   - {s}  {u}")

    # 증거 저장
    try:
        page.screenshot(path=str(RAW/"probe_screenshot.png"), full_page=False)
        print("[save] probe_screenshot.png")
    except Exception as e:
        print("[save] screenshot fail:", e)
    try:
        title = page.title(); html = page.content()
        (RAW/"probe_page.html").write_text(html[:200_000], encoding="utf-8")
        print(f"[save] probe_page.html  (title={title!r}, len={len(html)})")
        # 차단 징후 키워드 탐지
        low = html.lower()
        flags = [k for k in ["captcha","보안문자","비정상","접근이 차단","access denied","forbidden","robot","자동화","unusual traffic"] if k in low]
        print("[flags] 차단 의심 키워드:", flags if flags else "없음")
    except Exception as e:
        print("[save] html fail:", e)

    br.close()
print("\nPROBE DONE")
