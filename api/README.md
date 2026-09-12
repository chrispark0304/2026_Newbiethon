# 같이살집 API

```bash
pip install -r api/requirements.txt

export KAKAO_REST_API_KEY=...        # 없어도 동작한다 (자체 엔진으로 폴백)
export COMMUTE_PROVIDER=hybrid       # hybrid(기본) | engine | kakao

uvicorn api.main:app --reload --port 8000
```

문서: http://localhost:8000/docs (Swagger, 바로 테스트 가능)

## POST /api/search

첫 화면 "같이 살자" 버튼이 보내는 페이로드 그대로 받는다.

```json
{
  "people": [
    { "name": "재윤", "work": { "lat": 37.4979, "lon": 127.0276 } },
    { "name": "친구", "work": { "lat": 37.5216, "lon": 126.9243 } }
  ],
  "price": { "min": 70, "max": 140 },
  "area":  { "min": 15, "max": 22 },
  "commute_limit_min": 45,
  "top": 20
}
```

| 필드 | 의미 |
|---|---|
| `people[].work` | 직장 좌표(WGS84). 2~4명 |
| `price` | **환산월세** 범위(만원). 아래 "가격을 어떻게 비교하나" 참조 |
| `area` | **총 전용면적** 범위(㎡) |
| `commute_limit_min` | 선택. 주면 초과 매물을 제외 |
| `weights` | 선택. `{"price":1,"area":1,"commute":2}` 기본값 덮어쓰기 |
| `include_legs` | 경로 상세 포함 여부 (기본 true) |
| `max_per_building` | 한 건물 최대 노출 수 (기본 1). 실거래가는 호실별로 여러 건이 잡힌다 |
| `max_per_hood` | 한 동네 최대 노출 수 (기본 0 = 제한 없음) |

### 응답

```json
{
  "stats": { "total": 22, "after_price": 20, "after_area": 20, "after_commute": 18, "returned": 5 },
  "results": [
    {
      "id": "seed-007", "hood": "신림", "desc": "투룸 · 2층 · 넓음",
      "lat": 37.484, "lon": 126.929,
      "rent_total": 80, "rooms": [11, 9], "area_total": 20, "coord_source": "address",
      "nearest_station": { "name": "신림", "lines": ["2호선","신림선"], "walk_min": 1 },
      "commute": [
        { "name": "재윤", "minutes": 22, "boarding_stop": "신림",
          "source": "kakao", "transfers": 1, "fare": 1500, "legs": [] },
        { "name": "친구", "minutes": 21, "boarding_stop": "신림",
          "source": "engine", "transfers": null, "fare": null,
          "legs": [ { "kind": "ride", "detail": "신림선  신림 → 샛강", "minutes": 14 } ] }
      ],
      "commute_worst": 22, "commute_gap": 1,
      "joint_score": 70.8,
      "per_person": [ { "price": 85.7, "area": 100.0, "commute": 70.7, "total": 81.8 } ],
      "assignment": [ { "name": "재윤", "room_sqm": 11, "rent": 44 },
                      { "name": "친구", "room_sqm": 9,  "rent": 36 } ]
    }
  ],
  "hint": null
}
```

- `stats`는 **어느 필터에서 몇 개가 떨어졌는지** 보여 준다. 결과가 0건일 때 `hint`로 무엇을 풀어야 하는지 알려 준다.
- `assignment`는 방 배정 2가지를 모두 계산해 더 나은 쪽을 고른 결과다. 월세는 방 면적 비율로 나눈다.
- `joint_score`는 개인 점수 평균에서 **격차에 벌점**을 뺀 값이다. 한쪽만 아주 만족하는 집이 위로 올라오지 않는다.

### 오류

| 코드 | 상황 |
|---|---|
| 422 | 좌표가 한반도 밖이거나, 직장 반경 900m에 역이 없음 |
| 422 | `price.max < price.min` 등 범위 역전 |

## GET /api/health

```json
{ "ok": true, "stops": 652, "listings": 22 }
```

## 통근시간은 어디서 오나

두 가지 출처를 쓴다. 응답의 `commute[].source`가 어느 쪽인지 알려 준다.

| | 자체 엔진 (`transit/`) | 카카오맵 대중교통 |
|---|---|---|
| 호출 | 0회 | `GET /v2/routing/publictraffic` |
| 속도 | 1,329건 전체 9ms | 건당 네트워크 왕복 |
| 범위 | 수도권 전철만 (버스 없음) | 버스·지하철 전부 |
| 쿼터 | 없음 | **1,000건/일** |

### 왜 전부 카카오로 안 가나

매물 1,329건이 좌표 35개를 공유하므로 검색 1회에 `35 × 2명 = 70콜`이 든다.

```
1,000콜 ÷ 70 = 하루 14회 검색
```

심사 중에 몇 명만 다른 직장으로 돌려보면 말라붙는다.

### hybrid (기본)

```
자체 엔진으로 1,329건 전부 필터·랭킹   →  0콜
   ↓
화면에 나가는 상위 N개만 카카오로 정밀화  →  ~20콜
   ↓
시간이 바뀌었으니 점수·순서 재계산
```

- **보이는 숫자는 전부 실제 값**이고, 버스 경로도 반영된다
- 좌표 반올림(≈11m) 캐시를 디스크에 남기므로 같은 직장으로 재검색하면 0콜
- 쿼터 소진·네트워크 실패·경로 없음이면 **조용히 자체 엔진 값으로 폴백**한다
  (`source: "engine"`으로 표시되므로 프론트에서 구분 가능)
- 일일 예산은 `KAKAO_DAILY_BUDGET`(기본 900)으로 여유를 둔다

### 연결 확인 (쿼터 1~2건만 사용)

```bash
export KAKAO_REST_API_KEY=...
python -m api.check_kakao
```

자체 엔진 값과 나란히 찍어 주므로 오차를 바로 볼 수 있다.

## 구조

```
프론트 ──POST /api/search──► api/main.py
                              ├── transit/  통근시간 엔진 (의존성 없음)
                              ├── api/listings.py  매물 소스
                              └── api/scoring.py   공동 적합도
```

자체 엔진 비용은 **직장 수만큼의 다익스트라뿐**이다(2명이면 2회, 각 0.5ms).
매물이 1,329건이든 2만 건이든 같다. 여기에 hybrid면 상위 N개 정밀화 호출이 붙는다.

## 매물 데이터

`rtms_같이살집_최종_202608.csv` — 국토교통부 실거래가(RTMS) 연립다세대 전월세, 2026년 8월.
**1,408건 → 중복 제거 후 1,329건**, 서울 19개 동네.

| 동네 | 건수 |
|---|---|
| 건대입구 285 · 신림 186 · 역삼 150 · 상도 140 · 노원 111 · 사당 110 · 수유 101 | |
| 합정 74 · 홍대 63 · 성수 60 · 신촌 39 · 왕십리 25 · 안암 23 · 공덕 13 | |
| 회기 7 · 흑석 7 · 길음 6 · 청량리 5 · 신설동 3 | |

### 가격을 어떻게 비교하나

원본에 **전세 510건과 월세 898건이 섞여 있다.** 슬라이더 하나로 비교하려면 공통 척도가 필요해서
`rent_total`에 **환산월세**를 담는다.

```
환산월세 = 월세 + 보증금 × 전월세전환율(연 5.5%) / 12
```

예: 전세 2.7억 → 124만원 / 보증금 2,000 + 월세 56 → 65만원.
전환율은 `api/listings.py`의 `JEONSE_CONVERSION_RATE`에서 조정한다.

**원본 값(`lease_type`·`deposit`·`monthly_rent`)은 그대로 응답에 넣는다.**
화면에는 "전세 2.7억"으로 표시하고, 필터·정렬에만 환산월세를 쓰면 된다.

### 좌표는 지오코딩한 실좌표를 쓴다

CSV의 위도·경도는 **동네 대표점**이라 1,408건이 좌표 35개를 공유한다.
실제 지번주소와 **중앙값 741m, 최대 2.8km** 차이가 나고, 그 탓에
매물 절반의 통근시간이 5분 넘게 틀어진다(평균절대차 6.2분, 최대 32분).

그래서 `시군구 + 번지`를 카카오 로컬 `search/address`로 지오코딩한 좌표를 우선 쓴다.
고유 주소 1,167개가 전부 해석돼 현재 **1,329건 모두 실좌표**다.
응답의 `coord_source`가 `"address"`(지오코딩) / `"hood"`(대표점 폴백) 중 어느 쪽인지 알려 준다.

```bash
export KAKAO_REST_API_KEY=...
python -m api.geocode_listings      # 이미 있는 주소는 건너뛴다
```

결과는 `api/data/address_coords.json`에 커밋돼 있어서 평소엔 실행할 필요가 없다.
주소→좌표 쿼터는 100,000건/일이라 경로 조회와 달리 여유롭다.

### 알고 있어야 할 한계

1. **도보 접근 반경을 1,600m로 넓게 잡았다.** 실좌표로 바꾼 뒤에도 엔진 기본값(900m)에서는
   106건이 unreachable이다 — 연립다세대가 실제로 역에서 먼 경우가 많고, 그런 집은 보통 버스를 탄다.
   자체 엔진에 버스가 없으니 긴 도보가 그 대역이다. 넓게 잡으면 도보시간이 그만큼 더해져
   순위에서 알아서 밀리고, 상위에 올라오면 카카오가 실제 버스 경로로 바로잡는다.
   1,600m에서 unreachable은 8건이고 `stats.unreachable`로 노출된다.
2. **방 개수 정보가 없다.** 전용면적 총합만 있어서 `ROOM_SPLIT`(기본 55:45)로 쪼갠다.
   `rooms`와 `assignment`는 **데이터가 아니라 가정**이다. 실제 방 구성이 아니다.
3. **거래 건 단위다.** 주소·건물·층·면적이 같은 행(69조 148건)은 같은 집의 여러 계약이라
   가장 싼 계약만 남긴다. 층이나 면적이 다르면 별개 호실로 본다.
4. **2026년 8월 한 달치 실거래**다. 지금 나와 있는 매물이 아니라 "이 동네 이 가격대에
   이런 집이 거래됐다"는 기록이다.

### 다른 소스로 갈아끼우기

`api/listings.py`의 `ListingSource` 프로토콜(`all()` 하나)만 구현하면
API·점수 코드는 손대지 않아도 된다. 매물이 수만 건이 되면 `all()` 대신
공간 인덱스 질의를 받도록 인터페이스를 넓힐 것.
