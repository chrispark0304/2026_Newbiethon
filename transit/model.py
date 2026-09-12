"""정규화 피드의 자료형. 규격 설명은 SCHEMA.md 참조."""
from __future__ import annotations
import csv
from dataclasses import dataclass, fields, asdict
from pathlib import Path
from typing import Iterable, Type, TypeVar


@dataclass(frozen=True)
class Stop:
    stop_id: str
    stop_name: str
    lat: float
    lon: float
    mode: str


@dataclass(frozen=True)
class Route:
    route_id: str
    route_name: str
    mode: str
    headway_sec: int
    is_loop: int = 0
    #: is_loop=1일 때 마지막 순번 → 첫 순번 이동시간(초)
    loop_close_sec: int = 0


@dataclass(frozen=True)
class RouteStop:
    route_id: str
    seq: int
    stop_id: str
    run_time_sec: int
    #: 역 중심 ↔ 이 노선 승강장 편도 도보시간(초). 승차·하차에 각각 붙어
    #: 두 노선 환승이 자동으로 p(A)+p(B)가 된다. feeds/transfer_times.py 참조.
    transfer_sec: int = 0


@dataclass(frozen=True)
class Transfer:
    from_stop_id: str
    to_stop_id: str
    walk_sec: int


@dataclass
class FeedTables:
    """한 교통수단(피드)이 내놓는 결과물."""
    stops: list[Stop]
    routes: list[Route]
    route_stops: list[RouteStop]

    def extend(self, other: "FeedTables") -> None:
        self.stops.extend(other.stops)
        self.routes.extend(other.routes)
        self.route_stops.extend(other.route_stops)


T = TypeVar("T")


def write_csv(path: Path, rows: Iterable, cls: Type) -> int:
    cols = [f.name for f in fields(cls)]
    rows = list(rows)
    with path.open("w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))
    return len(rows)


def read_csv(path: Path, cls: Type[T]) -> list[T]:
    casts = {f.name: f.type for f in fields(cls)}
    out: list[T] = []
    with path.open(encoding="utf-8", newline="") as fp:
        for row in csv.DictReader(fp):
            kw = {}
            for k, v in row.items():
                t = casts.get(k)
                kw[k] = int(v) if t in (int, "int") else float(v) if t in (float, "float") else v
            out.append(cls(**kw))
    return out
