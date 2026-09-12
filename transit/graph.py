"""정규화 피드 → 라우팅 그래프.

노드
  STOP(stop_id)        정류장/역 (대합실·지상)
  RIDE(route_id, seq)  그 노선의 그 순번 차량에 타고 있는 상태

RIDE 노드를 (노선, 역)이 아니라 **(노선, 순번)**으로 잡는 게 핵심이다.
2호선 본선처럼 같은 역이 한 노선에 두 번 나오거나 지선이 있어도 경로가 꼬이지 않는다.

환승은 별도 엣지가 아니라 STOP→RIDE 승차 비용(대기 + 페널티)에 흡수된다.
덕분에 한 정류장에 노선이 N개 있어도 엣지가 N²이 아니라 2N개다.
"""
from __future__ import annotations
from array import array
from collections import defaultdict
from dataclasses import dataclass

from .config import (BOARD_PENALTY_SEC, DWELL_SEC, ROUTE_STOPS_CSV, ROUTES_CSV,
                     STOPS_CSV, TRANSFERS_CSV)
from .geo import SpatialGrid
from .model import Route, RouteStop, Stop, Transfer, read_csv


@dataclass
class Graph:
    stops: list[Stop]
    stop_index: dict[str, int]          # stop_id → 노드 번호 (0 .. n_stops-1)
    n_nodes: int
    # CSR (정방향)
    head: array
    to: array
    cost: array
    # CSR (역방향) — 목적지에서 거꾸로 한 번에 푸는 데 쓴다
    rhead: array
    rto: array
    rcost: array
    grid: SpatialGrid

    @property
    def n_stops(self) -> int:
        return len(self.stops)


def _csr(n_nodes: int, edges: list[tuple[int, int, int]]):
    counts = [0] * (n_nodes + 1)
    for u, _, _ in edges:
        counts[u + 1] += 1
    for i in range(1, n_nodes + 1):
        counts[i] += counts[i - 1]
    head = array("i", counts)
    to = array("i", bytes(4 * len(edges)))
    cost = array("i", bytes(4 * len(edges)))
    cursor = list(counts[:-1])
    for u, v, w in edges:
        p = cursor[u]
        to[p] = v
        cost[p] = w
        cursor[u] = p + 1
    return head, to, cost


def load_graph() -> Graph:
    stops = read_csv(STOPS_CSV, Stop)
    routes = {r.route_id: r for r in read_csv(ROUTES_CSV, Route)}
    route_stops = read_csv(ROUTE_STOPS_CSV, RouteStop)
    transfers = read_csv(TRANSFERS_CSV, Transfer)

    stop_index = {s.stop_id: i for i, s in enumerate(stops)}
    n = len(stops)

    by_route: dict[str, list[RouteStop]] = defaultdict(list)
    for rs in route_stops:
        by_route[rs.route_id].append(rs)

    edges: list[tuple[int, int, int]] = []
    ride_base: dict[str, int] = {}

    for rid, seq_rows in by_route.items():
        seq_rows.sort(key=lambda x: x.seq)
        route = routes[rid]
        base = n
        ride_base[rid] = base
        n += len(seq_rows)

        board = route.headway_sec // 2 + BOARD_PENALTY_SEC
        for i, rs in enumerate(seq_rows):
            ride = base + i
            sidx = stop_index[rs.stop_id]
            # transfer_sec = 역 중심 → 이 노선 승강장 도보.
            # 승차·하차 양쪽에 붙으므로 A→B 환승 비용이 p(A)+p(B)로 떨어진다.
            edges.append((sidx, ride, board + rs.transfer_sec))   # 대기 + 페널티 + 승강장 진입
            edges.append((ride, sidx, rs.transfer_sec))           # 하차 + 승강장 이탈
            if i > 0:
                # 주행시간 + 정차시간 (원본에 정차시간이 빠져 있다)
                edges.append((ride - 1, ride, rs.run_time_sec + DWELL_SEC))
        if route.is_loop and len(seq_rows) > 2:
            edges.append((base + len(seq_rows) - 1, base, route.loop_close_sec + DWELL_SEC))

    for t in transfers:
        edges.append((stop_index[t.from_stop_id], stop_index[t.to_stop_id], t.walk_sec))

    head, to, cost = _csr(n, edges)
    rhead, rto, rcost = _csr(n, [(v, u, w) for u, v, w in edges])
    grid = SpatialGrid([(s.stop_id, s.lat, s.lon) for s in stops])
    return Graph(stops, stop_index, n, head, to, cost, rhead, rto, rcost, grid)
