"""피드 인터페이스.

새 교통수단을 붙이려면 이 클래스를 상속해 load()만 구현하면 된다.
build_feed.py가 등록된 피드를 순회하며 테이블을 합친다.
"""
from __future__ import annotations
from abc import ABC, abstractmethod

from ..model import FeedTables


class Feed(ABC):
    #: stop_id / route_id 앞에 붙는 네임스페이스. 피드 간 ID 충돌을 막는다.
    mode: str = ""

    @abstractmethod
    def load(self) -> FeedTables:
        """원본 데이터를 읽어 정규화 테이블로 변환한다."""

    def stop_id(self, key: str) -> str:
        return f"{self.mode.upper()[:3]}:{key}"

    def route_id(self, key: str) -> str:
        return f"{self.mode.upper()[:3]}:{key}"


def reverse_route(route: "Route", stops: list["RouteStop"]) -> tuple["Route", list["RouteStop"]]:
    """단방향 정차순서를 역방향 노선으로 뒤집는다.

    원본 데이터가 한쪽 방향만 주는 경우(지하철 역간거리 데이터)에 쓴다.
    버스처럼 상·하행이 이미 별도 노선으로 들어오는 피드는 호출할 필요가 없다.
    """
    from ..model import Route, RouteStop

    rid = f"{route.route_id}:R"
    rev = Route(
        route_id=rid,
        route_name=f"{route.route_name} (역방향)",
        mode=route.mode,
        headway_sec=route.headway_sec,
        is_loop=route.is_loop,
        loop_close_sec=route.loop_close_sec,
    )
    ordered = sorted(stops, key=lambda s: s.seq)
    # 원본에서 seq i의 run_time_sec은 (i-1 → i) 비용이다.
    # 뒤집으면 (i → i-1)이 되므로 한 칸 밀려 붙는다.
    out: list[RouteStop] = []
    n = len(ordered)
    for j, src in enumerate(reversed(ordered)):
        # 역방향 (j-1 → j) 구간은 원본 (n-1-j → n-j) 구간과 같다.
        # 원본에서 그 비용은 ordered[n-j].run_time_sec에 저장돼 있다.
        run = 0 if j == 0 else ordered[n - j].run_time_sec
        out.append(RouteStop(route_id=rid, seq=j, stop_id=src.stop_id,
                             run_time_sec=run, transfer_sec=src.transfer_sec))
    return rev, out
