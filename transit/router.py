"""통근시간 계산기.

핵심 아이디어: **직장에서 역방향 다익스트라를 한 번** 돌리면
모든 정류장 → 직장 소요시간이 한꺼번에 나온다.
집 후보가 50개든 5,000개든 계산량이 똑같다.
"""
from __future__ import annotations
import heapq
from array import array
from dataclasses import dataclass

from .config import MAX_ACCESS_WALK_M, MAX_TRANSFERS
from .geo import walk_sec
from .graph import Graph, load_graph
from .model import Route, RouteStop, read_csv
from .config import ROUTE_STOPS_CSV, ROUTES_CSV

INF = 1 << 30


@dataclass
class Leg:
    kind: str          # walk | ride
    detail: str        # 사람이 읽는 한 줄 설명
    seconds: int
    #: 구조화 필드. 문자열 detail을 파싱하지 않고 바로 쓰라고 둔 것.
    route_name: str = ""      # ride일 때 노선명
    from_stop: str = ""
    to_stop: str = ""


@dataclass
class Commute:
    total_sec: int
    access_stop: str | None
    legs: list[Leg]
    #: 환승 횟수. 탑승 횟수 - 1 (MAX_TRANSFERS 이하가 보장된다).
    transfers: int = 0

    @property
    def minutes(self) -> int:
        return (self.total_sec + 30) // 60

    @property
    def reachable(self) -> bool:
        return self.total_sec < INF


class Field:
    """한 번의 역방향 다익스트라 결과.

    상태가 (노드, 탑승횟수)로 확장돼 있다. 환승 상한이 있으면 "빠르지만 3환승"인 경로를
    버리고 "조금 느리지만 2환승"인 경로를 찾아야 하는데, 노드 하나에 최단시간 하나만
    들고 있으면 그 판단을 할 수 없기 때문이다.

    `field[정류장]`은 탑승횟수와 무관하게 가장 빠른 시간을 돌려준다.
    """

    __slots__ = ("dist", "parent", "k", "n_nodes")

    def __init__(self, dist, parent, k: int, n_nodes: int):
        self.dist, self.parent, self.k, self.n_nodes = dist, parent, k, n_nodes

    def __getitem__(self, node: int) -> int:
        base = node * self.k
        return min(self.dist[base:base + self.k])

    def best_state(self, node: int) -> tuple[int, int]:
        """(최단시간, 그때의 탑승횟수)"""
        base = node * self.k
        best, at = INF, 0
        for b in range(self.k):
            if self.dist[base + b] < best:
                best, at = self.dist[base + b], b
        return best, at


def _dijkstra(n, head, to, cost, sources, n_stops, max_boardings, reverse):
    """(노드, 탑승횟수) 상태 공간 위의 다익스트라.

    승차 엣지를 지날 때만 탑승횟수가 는다. 정방향 그래프에서 승차는 STOP→RIDE이고,
    역방향 그래프에서는 그 엣지가 뒤집혀 RIDE→STOP으로 나타난다.
    """
    k = max_boardings + 1
    dist = array("l", [INF] * (n * k))
    parent = array("l", [-1] * (n * k))
    pq: list[tuple[int, int]] = []
    for node, init in sources:
        idx = node * k                      # 출발 시점은 아직 0회 탑승
        if init < dist[idx]:
            dist[idx] = init
            heapq.heappush(pq, (init, idx))

    while pq:
        d, su = heapq.heappop(pq)
        if d > dist[su]:
            continue
        u, b = divmod(su, k)
        for p in range(head[u], head[u + 1]):
            v = to[p]
            boarding = (u >= n_stops > v) if reverse else (u < n_stops <= v)
            nb = b + 1 if boarding else b
            if nb >= k:
                continue                    # 환승 상한 초과 — 이 경로는 버린다
            sv = v * k + nb
            nd = d + cost[p]
            if nd < dist[sv]:
                dist[sv] = nd
                parent[sv] = su
                heapq.heappush(pq, (nd, sv))
    return Field(dist, parent, k, n)


class CommuteRouter:
    def __init__(self, graph: Graph | None = None):
        self.g = graph or load_graph()
        self._routes = {r.route_id: r for r in read_csv(ROUTES_CSV, Route)}
        self._ride_label: dict[int, tuple[str, str]] = {}
        self._lines_by_stop: dict[str, set[str]] = {}
        self._build_ride_labels()

    def _build_ride_labels(self):
        """RIDE 노드 번호 → (노선명, 정류장명). 경로 설명 출력용."""
        from collections import defaultdict
        rows = read_csv(ROUTE_STOPS_CSV, RouteStop)
        by_route = defaultdict(list)
        for rs in rows:
            by_route[rs.route_id].append(rs)
        node = self.g.n_stops
        names = {s.stop_id: s.stop_name for s in self.g.stops}
        for rid in by_route:
            by_route[rid].sort(key=lambda x: x.seq)
        for rid, seq_rows in by_route.items():
            line = self._routes[rid].route_name.split(" (")[0]
            for i, rs in enumerate(seq_rows):
                self._ride_label[node + i] = (self._routes[rid].route_name, names[rs.stop_id])
                self._lines_by_stop.setdefault(names[rs.stop_id], set()).add(line)
            node += len(seq_rows)

    def lines_at(self, stop_name: str) -> list[str]:
        """그 역에 서는 노선 목록.

        호선은 stops.csv가 아니라 routes ↔ route_stops 조인에 있다.
        한 역에 여러 노선이 서므로 역 테이블에 넣으면 정규화가 깨지기 때문이다.
        """
        return sorted(self._lines_by_stop.get(stop_name, ()))

    # ------------------------------------------------------------- access
    def access(self, lat: float, lon: float, radius_m: float = MAX_ACCESS_WALK_M):
        """좌표 → [(정류장 노드번호, 도보 초)]"""
        out = []
        for stop_id, dist_m in self.g.grid.within(lat, lon, radius_m):
            out.append((self.g.stop_index[stop_id], walk_sec(dist_m)))
        return out

    # ------------------------------------------------------------- core
    def times_to(self, lat: float, lon: float, radius_m: float = MAX_ACCESS_WALK_M):
        """직장 좌표 하나로 **모든 정류장 → 직장** 소요시간을 한 번에 계산한다.

        반환: Field. `field[정류장번호]`로 소요시간을 읽는다.
        집 후보가 몇 개든 이 결과를 재사용한다.
        """
        sources = self.access(lat, lon, radius_m)
        if not sources:
            raise ValueError(f"({lat}, {lon}) 반경 {radius_m}m 안에 정류장이 없습니다.")
        return _dijkstra(self.g.n_nodes, self.g.rhead, self.g.rto, self.g.rcost, sources,
                         self.g.n_stops, MAX_TRANSFERS + 1, reverse=True)

    def commute(self, home_lat: float, home_lon: float, field, explain: bool = True,
                radius_m: float = MAX_ACCESS_WALK_M) -> Commute:
        """times_to() 결과(Field)를 받아 집 후보 하나의 통근시간을 뽑는다."""
        best, best_node, best_walk, best_b = INF, None, 0, 0
        for node, w in self.access(home_lat, home_lon, radius_m):
            t, b = field.best_state(node)
            if t >= INF:
                continue
            if t + w < best:
                best, best_node, best_walk, best_b = t + w, node, w, b
        if best_node is None:
            return Commute(INF, None, [], 0)
        legs = self._explain(best_node, best_b, best_walk, field) if explain else []
        return Commute(best, self.g.stops[best_node].stop_name, legs, max(0, best_b - 1))

    def _explain(self, start_node: int, start_b: int, access_walk: int, field) -> list[Leg]:
        legs = [Leg("walk", f"집 → {self.g.stops[start_node].stop_name}", access_walk,
                    from_stop="집", to_stop=self.g.stops[start_node].stop_name)]
        state, guard = start_node * field.k + start_b, 0
        dist, parent = field.dist, field.parent
        cur_route, cur_from, cur_cost = None, None, 0

        def flush():
            nonlocal cur_route, cur_from, cur_cost
            if cur_route is not None:
                legs.append(Leg("ride", f"{cur_route}  {cur_from} → {last_stop}", cur_cost,
                                route_name=cur_route, from_stop=cur_from, to_stop=last_stop))
                cur_route, cur_from, cur_cost = None, None, 0

        last_stop = ""
        while parent[state] != -1 and guard < 10_000:
            guard += 1
            nxt_state = parent[state]
            node, nxt = state // field.k, nxt_state // field.k
            step = dist[state] - dist[nxt_state]
            if nxt in self._ride_label:                     # 차량에 타고 있는 구간
                route_name, stop_name = self._ride_label[nxt]
                if cur_route != route_name:
                    flush()
                    cur_route = route_name
                    cur_from = self.g.stops[node].stop_name if node < self.g.n_stops else stop_name
                cur_cost += step
                last_stop = stop_name
            elif node in self._ride_label:                  # 하차
                flush()
            elif node < self.g.n_stops and nxt < self.g.n_stops:   # 도보 환승
                flush()
                legs.append(Leg("walk",
                                f"{self.g.stops[node].stop_name} → {self.g.stops[nxt].stop_name}", step,
                                from_stop=self.g.stops[node].stop_name,
                                to_stop=self.g.stops[nxt].stop_name))
            state = nxt_state
        flush()
        return [l for l in legs if l.seconds > 0]
