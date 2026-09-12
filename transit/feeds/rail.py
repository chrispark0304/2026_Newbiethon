"""수도권 전철 전 노선 피드.

토폴로지(역 순서)는 **OpenStreetMap route 릴레이션**에서, 구간 소요시간은
서울교통공사 실측값에서 가져온다. 실측이 없는 구간만 회귀식으로 채운다.

왜 OSM인가
----------
서울교통공사 데이터(OA-12034)는 **자사 운영 구간만** 담는다.
1호선은 서울역~청량리 10개역이 전부고, 남영·용산·노량진·영등포·구로 이남(코레일 경부·경인선)이
통째로 없다. 9호선·신분당선·경의중앙선·수인분당선·공항철도도 마찬가지다.
서울 서남권(영등포·구로·금천)이 사라지므로 주거지 비교 용도로는 쓸 수 없다.
전국 GTFS(KTDB)는 신청·승인제라 바로 못 쓴다. OSM은 키 없이 즉시 받을 수 있고 커버리지가 완전하다.

OSM 데이터의 함정
-----------------
1. 한 노선에 릴레이션이 수십 개다(1호선 92개). 급행·구간운행·방향별 변형이 전부 별개다.
   → 급행/특급은 이름으로 걸러내고, 나머지는 **정차 순서가 같으면 합치고
     다른 것의 연속 부분수열이면 버린다.**
2. 일부 릴레이션이 중간 역을 빠뜨려 **없는 급행 구간**을 만들어 낸다.
   → 지지 릴레이션 수가 2개 이하면서, 우회로가 직선거리의 1.3배 이내인 엣지를 제거한다
     (그 사이 역을 건너뛴 것이므로). 지지도만 보면 광명셔틀·서동탄지선 같은
     진짜 지선이 같이 날아가므로 기하 조건을 함께 본다.
"""
from __future__ import annotations
import collections
import json
import math
import re

from ..config import RAW
from ..geo import haversine_m
from ..model import FeedTables, Route, RouteStop, Stop
from .base import Feed, reverse_route

SOURCE = RAW / "osm_rail.json"

#: 광역전철로 취급할 노선. OSM `ref` 태그 기준.
#: KTX·무궁화·새마을 등 일반철도를 배제하기 위해 화이트리스트로 간다.
LINE_NAMES = {
    "1": "1호선", "2": "2호선", "3": "3호선", "4": "4호선", "5": "5호선",
    "6": "6호선", "7": "7호선", "8": "8호선", "9": "9호선",
    "경의·중앙": "경의중앙선", "경춘": "경춘선", "수인·분당": "수인분당선",
    "서해": "서해선", "경강": "경강선", "신분당": "신분당선",
    "공항철도": "공항철도", "AREX": "공항철도",
    "인천1": "인천1호선", "I2": "인천2호선",
    "U": "의정부경전철", "W": "우이신설선", "Silim": "신림선",
    "김포 골드라인": "김포골드라인", "용인": "용인에버라인",
    "GTX-A": "GTX-A",
}

#: 이름에 이 단어가 있으면 별도 서비스로 보고 제외한다.
#: 급행을 완행과 같은 배차로 섞으면 통근시간이 크게 과소평가된다.
EXCLUDE_NAME = re.compile(r"급행|특급|직통|KTX|무궁화|새마을|ITX|누리로")

#: 출근시간대 평균 배차간격(초). 노선 단위로 준다(급행 변형을 제외했으므로).
HEADWAY_SEC = {
    "1호선": 240, "2호선": 150, "3호선": 210, "4호선": 210, "5호선": 210,
    "6호선": 240, "7호선": 180, "8호선": 270, "9호선": 240,
    "경의중앙선": 480, "경춘선": 900, "수인분당선": 360, "서해선": 600,
    "경강선": 900, "신분당선": 300, "공항철도": 360,
    "인천1호선": 300, "인천2호선": 300, "우이신설선": 300, "신림선": 300,
    "김포골드라인": 240, "용인에버라인": 300, "GTX-A": 600,
}
DEFAULT_HEADWAY_SEC = 420

#: 회귀식보다 확연히 빠른 노선만 배수로 보정한다. 기본 1.0.
#: 신분당선·공항철도는 회귀식(순항 57km/h)으로도 실제와 잘 맞아 보정하지 않는다.
SPEED_FACTOR = {"GTX-A": 0.45}

#: 실측 271개 구간에 적합한 선형모형: 소요시간(초) = A + B * 거리(m)
#: → 정차·가감속 오버헤드 24초 + 순항속도 57km/h. 잔차 평균절대오차 11초.
#: calibrate.py로 재적합할 수 있다.
FIT_A, FIT_B = 23.9, 0.06324
#: 직선거리 → 선로거리 보정.
TRACK_DETOUR = 1.08

#: 실측 환승 데이터가 "이 역에 이 노선이 선다"고 하는데 OSM에 없을 때 끼워 넣는다.
#: 후보 자체는 실측이 보증하므로 임계값은 "넣을까"가 아니라 "어느 계통에 넣을까"를 가른다.
#: 노선이 크게 굽는 구간(공항철도 홍대입구~마곡나루)에서도 통과하도록 구간 길이에 비례시킨다.
INSERT_MAX_DETOUR_M = 800
INSERT_MAX_DETOUR_RATIO = 0.35
#: 그 노선에 이미 이만큼 가까운 역이 있으면 같은 역의 다른 이름으로 보고 건너뛴다.
#: (4호선 총신대입구 / 7호선 이수처럼 한 복합역을 노선마다 다르게 부르는 경우)
INSERT_MIN_DIST_M = 300
#: 한 번에 하나씩 끼우므로, 연속으로 빠진 역은 여러 번 돌아야 다 들어간다.
#: (공항철도는 공덕~마곡나루 사이에 홍대입구와 디지털미디어시티가 같이 빠져 있다)
INSERT_PASSES = 4

#: 릴레이션 지지도가 이 값 이하인 엣지만 가짜 후보로 본다.
SKIP_EDGE_MAX_SUPPORT = 2
#: 우회로가 직선거리의 이 배수 이내면 "역을 건너뛴 엣지"로 판정한다.
SKIP_EDGE_RATIO = 1.3

_PAREN = re.compile(r"\s*\(.*?\)\s*")


def norm_station(name: str) -> str:
    """'총신대입구(이수)' → '총신대입구'"""
    return _PAREN.sub("", (name or "").strip())


def estimate_run_sec(dist_m: float, line: str) -> int:
    return max(30, int(round((FIT_A + FIT_B * dist_m * TRACK_DETOUR) * SPEED_FACTOR.get(line, 1.0))))


class RailFeed(Feed):
    mode = "subway"

    def __init__(self, measured: dict[frozenset, int] | None = None,
                 coord_override: dict[str, tuple[float, float]] | None = None,
                 hub_penalty: dict[tuple[str, str], int] | None = None,
                 expected_lines: dict[str, set[str]] | None = None):
        self.measured = measured or {}
        self.coord_override = coord_override or {}
        #: {(역명, 노선): 초} 승강장 진입 도보시간. 없으면 0(= 기본 페널티만).
        self.hub_penalty = hub_penalty or {}
        #: {역명: {노선}} 실측 환승 데이터가 말하는 역 구성. OSM 누락 교차검증용.
        self.expected_lines = expected_lines or {}
        self.stats = collections.Counter()

    def stop_id(self, key: str) -> str:
        return f"SUB:{key}"

    # ------------------------------------------------------------ 파싱
    def _load_osm(self):
        payload = json.loads(SOURCE.read_text(encoding="utf-8"))
        nodes = {e["id"]: e for e in payload["elements"] if e["type"] == "node"}
        rels = [e for e in payload["elements"] if e["type"] == "relation"]
        return rels, nodes

    def _sequence(self, rel, nodes) -> list[tuple[str, float, float]]:
        """릴레이션 → [(역명, lat, lon)] 정차 순서."""
        out: list[tuple[str, float, float]] = []
        for m in rel.get("members", ()):
            if m["type"] != "node" or not m["role"].startswith("stop"):
                continue
            node = nodes.get(m["ref"])
            if not node:
                continue
            name = norm_station((node.get("tags") or {}).get("name", ""))
            if not name:
                continue
            if not out or out[-1][0] != name:      # 같은 역 연속 중복 제거
                out.append((name, node["lat"], node["lon"]))
        return out

    def _prune_skip_edges(self, seqs_by_line, coords):
        """중간 역을 빠뜨린 가짜 엣지를 노선별로 찾아낸다."""
        pruned: dict[str, set[frozenset]] = {}
        for line, seqs in seqs_by_line.items():
            support = collections.Counter()
            adj = collections.defaultdict(set)
            for seq in seqs:
                for a, b in zip(seq, seq[1:]):
                    support[frozenset((a, b))] += 1
                    adj[a].add(b)
                    adj[b].add(a)
            bad: dict[frozenset, str] = {}
            for edge, cnt in sorted(support.items(), key=lambda kv: kv[1]):
                if cnt > SKIP_EDGE_MAX_SUPPORT:
                    continue
                a, b = tuple(edge)
                direct = haversine_m(*coords[a], *coords[b])
                vias = [x for x in (adj[a] & adj[b]) if x not in (a, b)]
                if not vias:
                    continue                       # 우회로 없음 → 진짜 지선
                via = min(vias, key=lambda x: haversine_m(*coords[a], *coords[x])
                                              + haversine_m(*coords[x], *coords[b]))
                best = haversine_m(*coords[a], *coords[via]) + haversine_m(*coords[via], *coords[b])
                if best <= direct * SKIP_EDGE_RATIO:
                    bad[edge] = via                # 이 엣지는 via 역을 빠뜨린 것
                    adj[a].discard(b)
                    adj[b].discard(a)
            pruned[line] = bad
            self.stats[f"pruned:{line}"] = len(bad)
        return pruned

    def _insert_missing(self, seqs_by_line, coords) -> None:
        """실측 환승 데이터가 아는데 OSM에 없는 역을 노선에 끼워 넣는다.

        OSM 릴레이션은 역을 통째로 빠뜨리기도 한다(경의중앙선·공항철도의 홍대입구).
        _prune_skip_edges는 다른 릴레이션이 그 역을 알고 있어야 탐지할 수 있어서
        아무도 모르는 누락은 못 잡는다. 그래서 외부 데이터로 교차검증한다.

        끼워 넣을 자리는 **우회 증가량이 가장 작은 구간**으로 정한다.
        """
        by_line: dict[str, set[str]] = collections.defaultdict(set)
        for line, seqs in seqs_by_line.items():
            for seq in seqs:
                by_line[line].update(seq)

        for _ in range(INSERT_PASSES):
            added = 0
            for station, lines in self.expected_lines.items():
                if station not in coords:
                    continue
                for line in lines:
                    if line not in seqs_by_line or station in by_line[line]:
                        continue
                    # 이미 그 노선에 아주 가까운 역이 있으면 같은 역의 다른 이름이다.
                    near = [other for other in by_line[line]
                            if other in coords
                            and haversine_m(*coords[station], *coords[other]) < INSERT_MIN_DIST_M]
                    if near:
                        self.stats[f"alias:{line}:{station}={near[0]}"] = 1
                        continue
                    inserted = False
                    for idx, seq in enumerate(seqs_by_line[line]):
                        best, at, best_span = None, None, 0.0
                        for i, (a, b) in enumerate(zip(seq, seq[1:])):
                            span = haversine_m(*coords[a], *coords[b])
                            detour = (haversine_m(*coords[a], *coords[station])
                                      + haversine_m(*coords[station], *coords[b]) - span)
                            if best is None or detour < best:
                                best, at, best_span = detour, i + 1, span
                        limit = max(INSERT_MAX_DETOUR_M, INSERT_MAX_DETOUR_RATIO * best_span)
                        if best is not None and best <= limit:
                            seqs_by_line[line][idx] = seq[:at] + (station,) + seq[at:]
                            inserted = True
                    if inserted:
                        by_line[line].add(station)
                        added += 1
                        self.stats[f"insert:{line}:{station}"] = 1
            if not added:
                break

    def _repair(self, seq: tuple[str, ...], bad: dict[frozenset, str], line: str) -> tuple[str, ...]:
        """가짜 엣지를 만나면 빠진 역을 끼워 넣어 복구한다.

        릴레이션을 통째로 버리면 그 노선의 일부 구간이 통째로 사라진다
        (경의중앙선 용산~용문이 그렇게 없어졌었다). 복구가 훨씬 안전하다.
        """
        out = [seq[0]]
        for a, b in zip(seq, seq[1:]):
            via = bad.get(frozenset((a, b)))
            if via and via not in (a, b):
                out.append(via)
                self.stats[f"repaired:{line}"] += 1
            out.append(b)
        return tuple(out)

    @staticmethod
    def _dedupe(seqs: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
        """중복·부분수열 제거. 긴 것부터 보며 이미 담긴 노선의 연속 부분이면 버린다."""
        uniq = sorted({s for s in seqs}, key=len, reverse=True)
        kept: list[tuple[str, ...]] = []
        for seq in uniq:
            rev = seq[::-1]
            if any(_contains(k, seq) or _contains(k, rev) for k in kept):
                continue
            kept.append(seq)
        return kept

    # ------------------------------------------------------------ 빌드
    def load(self) -> FeedTables:
        rels, nodes = self._load_osm()

        coords: dict[str, tuple[float, float]] = {}
        seqs_by_line: dict[str, list[tuple[str, ...]]] = collections.defaultdict(list)

        for rel in rels:
            tags = rel.get("tags", {})
            line = LINE_NAMES.get(tags.get("ref", ""))
            if not line or EXCLUDE_NAME.search(tags.get("name", "")):
                continue
            seq = self._sequence(rel, nodes)
            if len(seq) < 2:
                continue
            for name, lat, lon in seq:
                coords.setdefault(name, (lat, lon))
            seqs_by_line[line].append(tuple(n for n, _, _ in seq))

        coords.update(self.coord_override)
        pruned = self._prune_skip_edges(seqs_by_line, coords)
        self._insert_missing(seqs_by_line, coords)

        stops: dict[str, Stop] = {}
        routes: list[Route] = []
        route_stops: list[RouteStop] = []

        for line, seqs in sorted(seqs_by_line.items()):
            bad = pruned[line]
            clean = [self._repair(s, bad, line) for s in seqs]
            for variant, seq in enumerate(self._dedupe(clean)):
                rid = f"SUB:{line}" if variant == 0 else f"SUB:{line}#{variant}"
                is_loop = int(len(seq) > 2 and seq[0] == seq[-1])
                body = seq[:-1] if is_loop else seq

                prev = None
                loop_close = 0
                for i, name in enumerate(body):
                    sid = self.stop_id(name)
                    if sid not in stops:
                        lat, lon = coords[name]
                        stops[sid] = Stop(sid, name, lat, lon, self.mode)
                    run = 0 if prev is None else self._run_sec(prev, name, line, coords)
                    hub = self.hub_penalty.get((name, line), 0)
                    if hub:
                        self.stats["hub_hit"] += 1
                    route_stops.append(RouteStop(rid, i, sid, run, hub))
                    prev = name
                if is_loop:
                    loop_close = self._run_sec(body[-1], body[0], line, coords)
                route = Route(
                    route_id=rid,
                    route_name=line if variant == 0 else f"{line} ({variant + 1}계통)",
                    mode=self.mode,
                    headway_sec=HEADWAY_SEC.get(line, DEFAULT_HEADWAY_SEC),
                    is_loop=is_loop,
                    loop_close_sec=loop_close,
                )
                routes.append(route)
                # _dedupe()가 역방향 릴레이션을 중복으로 지우므로 여기서 다시 만들어 준다.
                # 이게 없으면 노선이 단방향이 되어 A→B와 B→A 통근시간이 달라진다.
                mine = [x for x in route_stops if x.route_id == rid]
                rev_route, rev_stops = reverse_route(route, mine)
                routes.append(rev_route)
                route_stops.extend(rev_stops)

        return FeedTables(list(stops.values()), routes, route_stops)

    def _run_sec(self, a: str, b: str, line: str, coords) -> int:
        hit = self.measured.get(frozenset((a, b)))
        if hit:
            self.stats["measured"] += 1
            return hit
        self.stats["estimated"] += 1
        return estimate_run_sec(haversine_m(*coords[a], *coords[b]), line)


def _contains(haystack: tuple, needle: tuple) -> bool:
    """needle이 haystack의 연속 부분수열인가."""
    n, m = len(haystack), len(needle)
    if m > n:
        return False
    return any(haystack[i:i + m] == needle for i in range(n - m + 1))
