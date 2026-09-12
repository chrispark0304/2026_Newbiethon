"""좌표 유틸. 외부 의존성 없음."""
from __future__ import annotations
import math
from collections import defaultdict
from typing import Iterable, Sequence

from .config import WALK_DETOUR_FACTOR, WALK_SPEED_MPS

EARTH_R = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def walk_sec(distance_m: float) -> int:
    """직선거리(m) → 도보 소요시간(초). 우회계수를 곱해 실제 보행거리로 보정."""
    return int(round(distance_m * WALK_DETOUR_FACTOR / WALK_SPEED_MPS))


class SpatialGrid:
    """반경 질의용 경위도 격자 인덱스.

    정류장이 5만 개까지 늘어나도(버스 포함) 브루트포스 O(N^2) 없이 환승 엣지를 만들기 위한 것.
    KD-tree를 쓰지 않는 이유는 의존성 없이 충분히 빠르기 때문.
    """

    def __init__(self, points: Sequence[tuple[str, float, float]], cell_m: float = 500.0):
        self.cell_m = cell_m
        self.deg_lat = cell_m / 111_320.0
        self.points = list(points)
        self._cells: dict[tuple[int, int], list[int]] = defaultdict(list)
        for i, (_, lat, lon) in enumerate(self.points):
            self._cells[self._key(lat, lon)].append(i)

    def _deg_lon(self, lat: float) -> float:
        return self.cell_m / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))

    def _key(self, lat: float, lon: float) -> tuple[int, int]:
        return (int(lat / self.deg_lat), int(lon / self._deg_lon(lat)))

    def within(self, lat: float, lon: float, radius_m: float) -> Iterable[tuple[str, float]]:
        """반경 내 (stop_id, 거리m)를 yield."""
        span = int(radius_m / self.cell_m) + 1
        r, c = self._key(lat, lon)
        seen: set[int] = set()
        for dr in range(-span, span + 1):
            for dc in range(-span, span + 1):
                for i in self._cells.get((r + dr, c + dc), ()):
                    if i in seen:
                        continue
                    seen.add(i)
                    sid, plat, plon = self.points[i]
                    d = haversine_m(lat, lon, plat, plon)
                    if d <= radius_m:
                        yield sid, d
