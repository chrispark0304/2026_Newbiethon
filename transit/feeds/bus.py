"""서울 시내버스 피드 — **미구현 스텁**

지하철 피드와 동일한 테이블(stops/routes/route_stops)만 내놓으면
graph.py·router.py는 한 줄도 고치지 않아도 된다.
도보 환승 엣지(지하철역 ↔ 버스정류장 포함)는 build_feed.build_transfers()가 자동 생성한다.

구현 순서
---------
1. `fetch.py`의 SOURCES에 아래 원본을 추가한다.
2. load()를 채운다.
3. `build_feed.build_feeds()`의 주석 처리된 두 줄을 푼다.

필요한 원본
-----------
| 채울 컬럼                    | 데이터셋 | 비고 |
|------------------------------|----------|------|
| `route_stops.run_time_sec`   | 서울시 노선별 정류장 구간별 평균 운행시간 (OA-21217) | **시간대별 실측.** 08시대만 쓴다. 월 파일 100MB대라 평일 하루치만 받아 필터 |
| `stops.lat/lon`              | 서울시 버스정류소 위치정보 (OA-15067) | CSV 직접 다운로드 |
| `route_stops.seq`            | 서울시 버스 노선 정보 조회 (OA-1095) | API. 노선별 경유 정류소 순서 |
| `routes.headway_sec`         | 서울시 버스노선 기본정보 (OA-15262) | 배차간격 |

주의사항
--------
* **ARS-ID 5자리 0 패딩**: CSV로 받으면 앞자리 0이 날아간다. `zfill(5)` 필수.
* **상·하행**: 버스 원본은 보통 양방향이 한 노선에 섞여 있다.
  기·종점 기준으로 쪼개 별도 route_id로 내보낼 것 (`BUS:100100118:up` / `:down`).
  지하철처럼 `reverse_route()`를 쓰면 안 된다 — 실제 경유 정류장이 다르다.
* **regex 매칭 금지**: 정류소명이 아니라 정류소ID로 조인할 것. 동명 정류소가 많다.
* **규모**: route-stop 약 20만 개. 현재 CSR 빌더로 감당되지만
  브라우저로 내보낼 거라면 08시대 한 컬럼만 남겨 바이너리로 압축할 것.
* **범위**: 위 데이터는 서울시 시내버스 전용이다.
  경기·인천 버스는 경기데이터드림 / 국토부 TAGO에서 따로 받아야 한다.
"""
from __future__ import annotations

from ..model import FeedTables
from .base import Feed


class BusFeed(Feed):
    mode = "bus"

    def stop_id(self, key: str) -> str:
        return f"BUS:{key}"

    def load(self) -> FeedTables:
        raise NotImplementedError(
            "버스 피드 미구현. transit/feeds/bus.py 상단 주석의 구현 순서를 참고하세요."
        )
