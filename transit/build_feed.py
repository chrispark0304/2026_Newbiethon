"""피드 빌드: 원본 → data/feed/*.csv

새 교통수단을 추가하려면 FEEDS에 Feed 구현체를 하나 넣으면 된다.
그래프·라우터 코드는 손대지 않는다.
"""
from __future__ import annotations

from .config import (MAX_TRANSFER_WALK_M, ROUTE_STOPS_CSV, ROUTES_CSV,
                     STOPS_CSV, TRANSFERS_CSV)
from .geo import SpatialGrid, walk_sec
from .model import FeedTables, Route, RouteStop, Stop, Transfer, write_csv


def build_feeds() -> tuple[FeedTables, dict]:
    from .feeds.measured import segment_times
    from .feeds.rail import RailFeed
    from .feeds.transfer_times import expected_lines, hub_penalties
    from .overrides import load_coord_override

    merged = FeedTables([], [], [])

    # --- 광역전철 (수도권 전 노선) ---
    # 토폴로지는 OSM, 구간 소요시간은 서울교통공사 실측 우선 + 없으면 회귀 추정.
    feed = RailFeed(measured=segment_times(), coord_override=load_coord_override(),
                    hub_penalty=hub_penalties(), expected_lines=expected_lines())
    merged.extend(feed.load())

    # --- 버스 (미구현) ---
    # from .feeds.bus import BusFeed
    # merged.extend(BusFeed().load())

    return merged, feed.stats


def build_transfers(stops: list[Stop], radius_m: float = MAX_TRANSFER_WALK_M) -> list[Transfer]:
    """반경 내 정류장 쌍을 전부 도보 환승으로 잇는다.

    지하철끼리든, 지하철↔버스든, 버스끼리든 구분하지 않는다.
    버스 피드를 추가하면 통합 환승망이 자동으로 생긴다.
    """
    grid = SpatialGrid([(s.stop_id, s.lat, s.lon) for s in stops])
    out: list[Transfer] = []
    for s in stops:
        for other_id, dist in grid.within(s.lat, s.lon, radius_m):
            if other_id != s.stop_id:
                out.append(Transfer(s.stop_id, other_id, walk_sec(dist)))
    return out


def build() -> None:
    tables, stats = build_feeds()
    transfers = build_transfers(tables.stops)

    n_stops = write_csv(STOPS_CSV, tables.stops, Stop)
    n_routes = write_csv(ROUTES_CSV, tables.routes, Route)
    n_rs = write_csv(ROUTE_STOPS_CSV, tables.route_stops, RouteStop)
    n_tr = write_csv(TRANSFERS_CSV, transfers, Transfer)

    print(f"  stops       {n_stops:>7,}")
    print(f"  routes      {n_routes:>7,}")
    print(f"  route_stops {n_rs:>7,}")
    print(f"  transfers   {n_tr:>7,}  (반경 {MAX_TRANSFER_WALK_M}m)")

    measured, estimated = stats["measured"], stats["estimated"]
    total = measured + estimated
    if total:
        print(f"  구간 소요시간: 실측 {measured:,} / 추정 {estimated:,} "
              f"(실측 비율 {measured / total:.0%})")
    print(f"  환승 통로 실측 적용: {stats['hub_hit']:,}개 (역·노선)")
    ins = [k.split(":", 1)[1] for k in stats if k.startswith("insert:")]
    if ins:
        print(f"  OSM 누락역 보강: {len(ins)}건 — {', '.join(sorted(ins))}")
    alias = [k.split(":", 1)[1] for k in stats if k.startswith("alias:")]
    if alias:
        print(f"  같은 역의 다른 이름으로 판단해 건너뜀: {', '.join(sorted(alias))}")
    prunes = sum(v for k, v in stats.items() if k.startswith("pruned:"))
    repairs = sum(v for k, v in stats.items() if k.startswith("repaired:"))
    print(f"  OSM 정리: 가짜 엣지 {prunes}종 탐지, 누락역 {repairs}건 복구")
