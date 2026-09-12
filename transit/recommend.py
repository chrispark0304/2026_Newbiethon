"""직장 좌표 → 살기 좋은 역 추천.

문제 구조
---------
두 사람이 한 집에 산다면 통근시간은 **서로 상충한다.** A의 직장에 가까워지면
B는 대개 멀어진다. 그래서 "최적 위치"는 하나로 정해지지 않고, 무엇을 중시하느냐에 달린다.

  minimax  더 오래 걸리는 쪽을 줄인다      → 형평성. 기본값
  total    둘의 합을 줄인다                → 총 이동시간 효율
  pareto   어느 쪽도 손해 없이 개선 불가능한 후보만 → 취향을 묻지 않는 정답 집합

알고리즘
--------
    1. 직장 k곳에서 각각 역방향 다익스트라 1회  →  모든 역까지의 통근시간
    2. 제약(통근 한도) 필터
    3. 목적함수로 정렬 / 파레토 프론트 추출
    4. 공간 억제: 이미 뽑은 역과 가까우면 건너뛴다

계산량은 **직장 수에만** 비례한다. 후보 역이 652개든 5만 개(버스 포함)든 같다.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .geo import haversine_m
from .router import INF, CommuteRouter

#: 추천 결과가 인접 역으로 도배되는 걸 막는 기본 반경(m).
#: 강남·역삼·선릉을 따로 보여 줘 봐야 사용자에겐 같은 선택지다.
DEFAULT_SPREAD_M = 1000


@dataclass
class Candidate:
    stop_id: str
    stop_name: str
    lat: float
    lon: float
    lines: list[str]
    #: 직장별 통근시간(분). works 순서와 같다.
    minutes: list[int] = field(default_factory=list)

    @property
    def worst(self) -> int:
        return max(self.minutes)

    @property
    def total(self) -> int:
        return sum(self.minutes)

    @property
    def gap(self) -> int:
        """가장 오래 걸리는 사람과 짧은 사람의 차이. 클수록 불공평하다."""
        return max(self.minutes) - min(self.minutes)


def _dominates(a: Candidate, b: Candidate) -> bool:
    """a가 b를 지배하는가 = 모든 직장에서 같거나 낫고, 하나 이상에서 확실히 낫다."""
    return (all(x <= y for x, y in zip(a.minutes, b.minutes))
            and any(x < y for x, y in zip(a.minutes, b.minutes)))


def pareto_front(cands: list[Candidate]) -> list[Candidate]:
    """지배당하지 않는 후보만 남긴다.

    O(n²)이지만 후보가 수백~수천이라 체감되지 않는다.
    """
    return [c for c in cands if not any(_dominates(o, c) for o in cands if o is not c)]


SORT_KEYS = {
    # 형평성 우선: 더 힘든 쪽을 먼저 줄이고, 동률이면 합, 그다음 격차
    "minimax": lambda c: (c.worst, c.total, c.gap),
    # 총 이동시간 우선
    "total": lambda c: (c.total, c.worst, c.gap),
    # 둘의 통근시간을 최대한 비슷하게
    "fair": lambda c: (c.gap, c.worst, c.total),
}


def recommend(
    works: list[tuple[str, float, float]],
    router: CommuteRouter | None = None,
    *,
    limits: list[int] | None = None,
    objective: str = "minimax",
    pareto_only: bool = False,
    spread_m: float = DEFAULT_SPREAD_M,
    access_walk_min: int = 0,
    top: int = 20,
) -> tuple[list[Candidate], dict]:
    """직장 목록을 받아 추천 역을 돌려준다.

    works           [(이름, lat, lon)]
    limits          직장별 통근 한도(분). None이면 무제한
    objective       SORT_KEYS 참조
    pareto_only     파레토 프론트만 남길지
    spread_m        결과 간 최소 거리(m). 0이면 억제 없음
    access_walk_min 집→역 도보(분). 모든 후보에 일괄 가산된다
    """
    if objective not in SORT_KEYS:
        raise ValueError(f"objective는 {sorted(SORT_KEYS)} 중 하나여야 합니다.")
    r = router or CommuteRouter()

    # ① 직장 수만큼만 다익스트라를 돌린다. 후보 역 개수와 무관.
    fields = [r.times_to(lat, lon)[0] for _, lat, lon in works]

    cands: list[Candidate] = []
    unreachable = 0
    for idx, stop in enumerate(r.g.stops):
        secs = [f[idx] for f in fields]
        if any(s >= INF for s in secs):
            unreachable += 1
            continue
        cands.append(Candidate(
            stop_id=stop.stop_id, stop_name=stop.stop_name,
            lat=stop.lat, lon=stop.lon, lines=r.lines_at(stop.stop_name),
            minutes=[(s + 30) // 60 + access_walk_min for s in secs],
        ))

    stats = {"후보 역": len(cands), "연결 안 됨": unreachable}

    # ② 제약 필터
    if limits:
        before = len(cands)
        cands = [c for c in cands
                 if all(m <= lim for m, lim in zip(c.minutes, limits) if lim)]
        stats["한도 통과"] = len(cands)
        stats["한도 탈락"] = before - len(cands)

    # ③ 파레토 / 정렬
    if pareto_only:
        cands = pareto_front(cands)
        stats["파레토 프론트"] = len(cands)
    cands.sort(key=SORT_KEYS[objective])

    # ④ 공간 억제 — 인접 역 중복 제거
    if spread_m > 0:
        kept: list[Candidate] = []
        for c in cands:
            if all(haversine_m(c.lat, c.lon, k.lat, k.lon) >= spread_m for k in kept):
                kept.append(c)
            if len(kept) >= top:
                break
        cands = kept
        stats["공간 억제 후"] = len(cands)

    return cands[:top], stats
