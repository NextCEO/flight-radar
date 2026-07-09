# Flight Radar — ICN ⇄ Italia (2026.10–11)

서울↔로마·밀라노·베네치아 왕복(체류 7·10·14일) 최저가를 매일 새벽 자동 수집하고,
캘린더 히트맵에서 한눈에 비교 → 판매처별 가격 · 프로모션 적용가 · 예매 딥링크까지 연결하는 개인용 툴.

## 구조

```
flight-radar/
├── index.html              캘린더 UI (정적, 단일 파일)
├── crawler/crawl.py        Playwright 크롤러 (네이버항공 내부 API 응답 가로채기)
├── data/fares.json         수집 결과 (현재는 샘플 데이터 — sample:true)
├── data/promotions.json    프로모션 수동 관리 DB
└── raw/                    응답 원본 (커밋 안 됨, Actions 아티팩트로만)

.github/workflows/flight-radar.yml   매일 04:00 KST 크롤링 → fares.json 커밋
```

## 설치 (Blake-workspace 기준)

1. 저장소 루트에 `flight-radar/` 폴더 전체 업로드
   (github.com → Add file → Upload files → 폴더째 드래그)
2. `flight-radar.yml`을 `.github/workflows/` 안에 생성
   (웹 업로드가 워크플로우 파일을 거부하면: Add file → Create new file →
   경로에 `.github/workflows/flight-radar.yml` 입력 후 내용 붙여넣기)
3. Actions 탭 → **Flight Radar** → **Run workflow** 로 첫 수집 실행

## 화면 보기 (둘 중 하나)

- **GitHub Pages**: Settings → Pages → Deploy from branch → main / root.
  주소는 `https://<계정>.github.io/Blake-workspace/flight-radar/`
  ⚠️ 저장소가 private이면 Pages는 GitHub Pro 필요.
- **로컬에서 열기**: `index.html`과 `data/` 폴더를 함께 내려받아 브라우저로 열기.
  `file://`로 열면 자동 로드가 막히므로, 하단 **"데이터 파일 직접 불러오기"** 버튼으로
  `fares.json` → `promotions.json` 순서로 선택하면 됨.

## 프로모션 관리

`data/promotions.json`의 `items`에 직접 추가. 판매처명에 `match` 문자열이 포함되면
캘린더 상세 패널에서 할인 적용가가 자동 계산됨.

```json
{
  "id": "고유id",
  "match": ["트립닷컴"],          ← 판매처명 매칭 키워드
  "label": "○○카드 7% 즉시할인",
  "type": "percent",              ← percent | fixed
  "value": 7,
  "maxDiscount": 70000,           ← percent일 때 상한 (선택)
  "minSpend": 1000000,            ← fixed일 때 최소 결제액 (선택)
  "until": "2026-08-31",          ← 만료일 지나면 자동 미적용
  "loginRequired": true           ← 상세 패널에 [로그인] 태그 표시
}
```

## 첫 실행 후 해야 할 일 (중요)

v1 파서는 스키마를 모르는 상태에서 fare/agent 계열 키를 휴리스틱으로 긁는다.
첫 실행이 끝나면:

1. Actions 실행 로그에서 성공/실패 건수 확인
2. 실행 페이지 하단 **raw-responses 아티팩트** 다운로드
3. 그 JSON을 Claude에게 주면 → 실제 스키마 기준으로 파서를 정밀화한 v2 제공

수집이 0건이면 워크플로우가 실패로 표시되도록 해뒀으니, 그때도 로그+아티팩트를 공유해주면 됨.

## 운영 파라미터

| 항목 | 기본값 | 의미 |
|---|---|---|
| ROTATE | 1 | 하루에 목적지 1곳씩 순환 (3일 주기로 전체 갱신, 1회 ~93검색 ≈ 25분) |
| DEP_STEP | 2 | 출발일 이틀 간격 수집 |
| STAYS | 7,10,14 | 체류일수 샘플 (7–14일 범위 대표값) |

전체를 매일 다 돌리려면 Run workflow에서 rotate=0 (1회 ~279검색, 70분+, 비권장).

## 유의

개인용 저빈도 수집이지만 네이버항공 약관상 회색지대임. 요청 간 3–6초 지연을 유지하고,
수집 주기·범위를 무리하게 늘리지 말 것. 로그인 크롤링(계정 자동화)은 하지 않는다 —
로그인 전용 할인은 promotions.json에 수동 반영하는 방식.
