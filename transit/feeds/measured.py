"""서울교통공사 실측 구간 소요시간 테이블.

원본: 서울교통공사 역간거리 및 소요시간 (서울 열린데이터광장 OA-12034)
      https://data.seoul.go.kr/dataList/OA-12034/F/1/datasetView.do

이 데이터는 **노선 토폴로지로 쓰기엔 범위가 너무 좁다**(자사 운영 구간만).
그래서 토폴로지는 OSM에서 가져오고(rail.py), 이 파일은 **구간 소요시간 조회표**로만 쓴다.
실측이 있는 구간은 실측을, 없는 구간은 회귀식을 쓴다.

원본의 함정
-----------
1. 지선이 구분자 없이 본선 뒤에 이어붙어 있다.
   그대로 인접 쌍을 만들면 '시청—용답' 같은 없는 구간이 생긴다 → BRANCHES로 교정.
2. '소요시간'은 30초 단위로 떨어지는 **순수 주행시간**이라 정차시간이 빠져 있다.
   정차시간은 graph.py의 DWELL_SEC이 따로 더한다.
3. 역명이 OSM과 다른 경우가 있다(당고개→불암산 개명 등) → ALIAS로 맞춘다.
"""
from __future__ import annotations
import csv
import io

from ..config import RAW
from ..textio import read_text

SOURCE = RAW / "seoul_metro_segments.csv"

#: 원본 역명 → OSM 표기. 개명·표기 흔들림 보정.
ALIAS = {
    "신내역": "신내",
    "당고개": "불암산",     # 2024년 개명
}

#: 지선 첫 역이 실제로 갈라져 나오는 본선 역.
#: 원본이 지선을 본선 뒤에 그냥 붙여 놔서 이 교정이 없으면 없는 구간이 생긴다.
BRANCH_JUNCTION = {
    ("2", "용답"): "성수",
    ("2", "도림천"): "신도림",
    ("5", "둔촌동"): "강동",
}


def _clean(name: str) -> str:
    name = (name or "").strip()
    return ALIAS.get(name, name)


def _parse_sec(raw: str) -> int:
    raw = (raw or "").strip()
    if not raw or raw in {"0", "-", "00:00"}:
        return 0
    mm, ss = raw.split(":")
    return int(mm) * 60 + int(ss)


def segment_times() -> dict[frozenset, int]:
    """{frozenset({역A, 역B}): 주행시간 초}"""
    rows = list(csv.DictReader(io.StringIO(read_text(SOURCE))))
    out: dict[frozenset, int] = {}

    by_line: dict[str, list[dict]] = {}
    for r in rows:
        by_line.setdefault(r["호선"].strip(), []).append(r)

    for line, line_rows in by_line.items():
        prev = None
        for r in line_rows:
            name = _clean(r["역명"])
            sec = _parse_sec(r["소요시간"])
            junction = BRANCH_JUNCTION.get((line, name))
            if junction:
                prev = _clean(junction)      # 지선 시작: 본선 분기역에서 이어 붙인다
            if prev and sec > 0 and prev != name:
                out.setdefault(frozenset((prev, name)), sec)
            prev = name
    return out
