# 정규화 피드 규격 (GTFS-lite)

모든 교통수단은 아래 4개 CSV로 정규화된다. **버스를 추가할 때 그래프·라우터 코드는 건드리지 않는다.**
`transit/feeds/` 아래에 새 Feed 구현체를 하나 추가해 같은 테이블을 뱉게 하면 끝이다.

시각표(timetable)를 쓰지 않고 **배차간격 기반(frequency-based)** 으로 모델링한다.
출퇴근 시간대 평균 통근시간을 비교하는 것이 목적이라 첫차/막차·정시성은 의도적으로 무시한다.

## stops.csv — 정류장/역 (물리적 위치)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `stop_id` | str | 전역 고유. `SUB:종로3가`, `BUS:23456` 처럼 **mode prefix 필수** |
| `stop_name` | str | 표시용 이름 |
| `lat`, `lon` | float | WGS84 |
| `mode` | str | `subway` \| `bus` |

> 지하철은 **역 이름 단위로 통합**한다. 종로3가(1·3·5호선)는 stop 1개다.
> 노선 간 환승 비용은 승차 페널티로 처리한다(아래 참조).
>
> **`stops.csv`에는 호선 컬럼이 없다.** 한 역에 여러 노선이 서기 때문에 역 테이블에 넣으면
> 정규화가 깨진다. 호선은 `routes.csv` ↔ `route_stops.csv` ↔ `stops.csv` 조인으로 얻는다
> (`CommuteRouter.lines_at(역명)` 헬퍼 제공).

## routes.csv — 노선

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `route_id` | str | `SUB:2`, `SUB:2-성수지선`, `BUS:100100118` |
| `route_name` | str | 표시용 |
| `mode` | str | `subway` \| `bus` |
| `headway_sec` | int | 출근시간대 배차간격(초). 평균 대기 = `headway_sec / 2` |
| `is_loop` | 0/1 | 1이면 마지막 순번에서 첫 순번으로 연결(2호선 본선, 6호선 응암순환) |

## route_stops.csv — 노선별 정차 순서

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `route_id` | str | |
| `seq` | int | 0부터. **같은 역이 두 번 나와도 된다**(순환선) |
| `stop_id` | str | |
| `run_time_sec` | int | **직전 순번에서 이 순번까지** 걸리는 시간. `seq=0`은 0 |
| `transfer_sec` | int | 역 중심 ↔ 이 노선 승강장 편도 도보시간. 승차·하차에 각각 붙는다 |

### 같은 역 안에서의 환승

지하철은 역 이름 단위로 stop을 합치므로, 같은 역의 노선 간 환승에는 `transfers.csv` 행이 생기지 않는다.
대신 `transfer_sec`이 그 역할을 한다.

    A→B 환승 비용 = transfer_sec(A) + 대기(headway/2) + BOARD_PENALTY_SEC + transfer_sec(B)

`transfer_sec`은 노선 쌍 실측값(종로3가 1↔5호선 = 4분 20초)을
`p(A) + p(B) ≈ 실측(A,B)` 이 되도록 최소제곱으로 분해해 얻는다 (`feeds/transfer_times.py`).
그래서 종로3가·고속터미널처럼 통로가 긴 역은 자동으로 비싸지고, 신도림처럼 짧은 역은 싸진다.

## transfers.csv — 서로 다른 역 사이의 도보 환승 (빌드 시 자동 생성)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `from_stop_id`, `to_stop_id` | str | 양방향 각각 1행 |
| `walk_sec` | int | 직선거리 × 우회계수 ÷ 도보속도 |

`build` 단계에서 반경 내 정류장 쌍을 전부 찾아 생성한다.
**이름이 다른 역 사이만** 담긴다(용산↔신용산, 총신대입구↔이수 등). 같은 이름 역은 위를 참조.
지하철역 ↔ 버스정류장 연결도 **이 파일이 자동으로 만들어 준다.** 버스 피드를 추가하면 별도 작업 없이 통합 환승망이 된다.

---

## 그래프 변환 (graph.py)

```
노드
  STOP(stop_id)        정류장 대합실/지상
  RIDE(route_id, seq)  "그 노선의 그 순번 차량에 타고 있는 상태"

엣지
  RIDE(r,i) → RIDE(r,i+1)   run_time_sec          (이동)
  STOP(s)   → RIDE(r,i)     headway/2 + 페널티 + transfer_sec  (대기+승강장 진입)
  RIDE(r,i) → STOP(s)       transfer_sec                       (하차+승강장 이탈)
  STOP(a)   → STOP(b)       walk_sec               (도보 환승)
```

`RIDE` 노드를 `(노선, 역)`이 아니라 `(노선, 순번)`으로 잡는 이유:
2호선 본선처럼 **한 노선에 같은 역이 두 번 등장**하거나 지선이 있어도 경로가 꼬이지 않는다.

환승 비용은 별도 엣지가 아니라 **`STOP → RIDE` 승차 비용에 흡수**된다.
이 덕분에 한 정류장에 노선이 N개 있어도 엣지가 N²이 아니라 2N개로 끝난다.
