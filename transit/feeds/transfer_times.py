"""환승역 통로 도보시간 (실측).

원본: 서울교통공사_환승역거리 소요시간 정보 (서울 열린데이터광장 OA-13290)
      https://data.seoul.go.kr/dataList/OA-13290/F/1/datasetView.do
      (환승거리 / 보행속도 1.2m/s 기준)

왜 필요한가
-----------
역 이름으로 정류장을 합치면 같은 역의 노선 간 환승이 **공짜**가 된다.
하지만 종로3가 1↔5호선은 312m(4분 20초), 신도림 1↔2호선은 그 1/4다.
전부 같은 페널티로 묶으면 환승이 많은 경로가 실제보다 훨씬 빨라 보인다.

허브 모형
---------
원본은 **노선 쌍** 단위 값이지만(1호선↔5호선), 그래프는 역 단위 노드를 쓴다.
그래서 각 노선이 "역 중심에서 얼마나 떨어져 있는가" p(노선)로 분해한다.

    환승시간(A, B) ≈ p(A) + p(B)

2개 노선 역은 p = T/2로 정확히 떨어지고, 3개 이상은 최소제곱으로 맞춘다.
p는 승차/하차 비용에 각각 붙으므로 A→B 환승은 자동으로 p(A) + p(B)가 된다.
지상에서 처음 탈 때도 p(A)를 내는데, 깊은 승강장일수록 오래 걸리는 게 맞으므로 의도된 동작이다.
"""
from __future__ import annotations
import collections
import csv
import io

from ..config import RAW
from ..textio import read_text

SOURCE = RAW / "seoul_metro_transfers.csv"

#: 원본 '호선'/'환승노선' 표기 → rail.py의 노선명
#: '호선' 컬럼은 맨숫자('1'), '환승노선' 컬럼은 'N호선' 표기라 둘 다 받는다.
LINE_ALIAS = {
    **{str(i): f"{i}호선" for i in range(1, 10)},
    **{f"{i}호선": f"{i}호선" for i in range(1, 10)},
    #: '국철'·'경원선'은 역마다 가리키는 노선이 다르다 → AMBIGUOUS_BY_STATION에서 해석.
    "공항철도": "공항철도", "경의중앙선": "경의중앙선", "경의·중앙선": "경의중앙선",
    "수인분당선": "수인분당선", "수인·분당선": "수인분당선", "분당선": "수인분당선",
    "신분당선": "신분당선", "경춘선": "경춘선", "서해선": "서해선",
    "우이신설선": "우이신설선", "인천1호선": "인천1호선", "인천2호선": "인천2호선",
    "김포골드라인": "김포골드라인", "의정부경전철": "의정부경전철", "신림선": "신림선",
    "용인경전철": "용인에버라인", "경강선": "경강선",
}

#: 역마다 다른 것을 가리키는 옛 표기. {(역명, 원본표기): 노선명}
AMBIGUOUS_BY_STATION = {
    ("수서", "국철"): "수인분당선",     # 수서는 3호선↔수인분당선 환승
    ("석계", "경원선"): "1호선",        # 석계는 1호선↔6호선 환승
}

#: 최소제곱 반복 횟수. 역당 노선이 많아야 5개라 금방 수렴한다.
FIT_ITERS = 60


def _parse_sec(raw: str) -> int:
    raw = (raw or "").strip()
    if not raw:
        return 0
    if ":" in raw:
        mm, ss = raw.split(":")[:2]
        return int(mm) * 60 + int(ss)
    return int(float(raw))


def expected_lines() -> dict[str, set[str]]:
    """{역명: {노선, ...}} — 실측 환승 데이터가 말하는 역별 노선 구성.

    OSM 릴레이션이 역을 빠뜨렸는지 교차검증하는 데 쓴다.
    """
    out: dict[str, set[str]] = collections.defaultdict(set)
    for (station, a, b) in pair_times():
        out[station].update((a, b))
    return dict(out)


def pair_times() -> dict[tuple[str, str, str], int]:
    """{(역명, 노선A, 노선B): 초}. 노선 쌍은 정렬해 한 방향만 담는다."""
    out: dict[tuple[str, str, str], int] = {}
    if not SOURCE.exists():
        return out
    for r in csv.DictReader(io.StringIO(read_text(SOURCE))):
        station = (r.get("환승역명") or "").strip()
        raw_a = (r.get("호선") or "").strip()
        raw_b = (r.get("환승노선") or "").strip()
        a = AMBIGUOUS_BY_STATION.get((station, raw_a)) or LINE_ALIAS.get(raw_a)
        b = AMBIGUOUS_BY_STATION.get((station, raw_b)) or LINE_ALIAS.get(raw_b)
        sec = _parse_sec(r.get("환승소요시간", ""))
        if not (station and a and b and sec) or a == b:
            continue
        key = (station, *sorted((a, b)))
        out[key] = max(out.get(key, 0), sec)
    return out


def hub_penalties() -> dict[tuple[str, str], int]:
    """{(역명, 노선): 초} — 역 중심에서 그 노선 승강장까지의 편도 시간.

    p(A) + p(B) ≈ 실측 환승시간(A, B) 이 되도록 최소제곱으로 분해한다.
    """
    pairs = pair_times()
    by_station: dict[str, list[tuple[str, str, int]]] = collections.defaultdict(list)
    for (station, a, b), sec in pairs.items():
        by_station[station].append((a, b, sec))

    out: dict[tuple[str, str], int] = {}
    for station, rows in by_station.items():
        lines = sorted({x for a, b, _ in rows for x in (a, b)})
        # 초기값: 자기가 낀 환승시간 평균의 절반
        p = {ln: sum(s for a, b, s in rows if ln in (a, b))
                 / max(1, sum(1 for a, b, _ in rows if ln in (a, b))) / 2
             for ln in lines}
        # 좌표하강: p_i ← mean_j(T_ij - p_j)
        for _ in range(FIT_ITERS):
            for ln in lines:
                vals = [sec - p[b if a == ln else a] for a, b, sec in rows if ln in (a, b)]
                if vals:
                    p[ln] = max(0.0, sum(vals) / len(vals))
        for ln in lines:
            out[(station, ln)] = int(round(p[ln]))
    return out
