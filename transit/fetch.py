"""원본 데이터 다운로드.

원본을 저장소에 커밋해 두므로 평소엔 실행할 필요가 없다.
데이터가 갱신됐을 때만 돌린다.
"""
from __future__ import annotations
import urllib.parse
import urllib.request

from .config import RAW
from .textio import to_utf8

SEOUL_DOWNLOAD = "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false"

#: 서울 열린데이터광장 파일 다운로드 파라미터.
#: seq 값은 데이터셋 페이지(datasetView.do)의 downloadFile('N') 에서 확인한다.
SOURCES = {
    "seoul_metro_segments.csv": {
        "infId": "OA-12034", "infSeq": "1", "seq": "9", "seqNo": "",
        "_desc": "서울교통공사 역간거리 및 소요시간",
        "_page": "https://data.seoul.go.kr/dataList/OA-12034/F/1/datasetView.do",
    },
    "seoul_metro_transfers.csv": {
        "infId": "OA-13290", "infSeq": "1", "seq": "8", "seqNo": "",
        "_desc": "서울교통공사 환승역거리 소요시간",
        "_page": "https://data.seoul.go.kr/dataList/OA-13290/F/1/datasetView.do",
    },
}


def fetch(name: str) -> None:
    spec = dict(SOURCES[name])
    page = spec.pop("_page")
    desc = spec.pop("_desc")
    body = urllib.parse.urlencode(spec).encode()
    req = urllib.request.Request(
        SEOUL_DOWNLOAD, data=body,
        headers={"User-Agent": "Mozilla/5.0", "Referer": page},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        blob = resp.read()
    # 원본은 CP949로 내려온다. 저장소에는 UTF-8로 통일해 둔다.
    # (편집기에서 열어도 안 깨지고, 누가 무심코 저장해도 빌드가 안 부서진다)
    text = to_utf8(blob)
    (RAW / name).write_text(text, encoding="utf-8")
    print(f"  {desc}: {len(blob):,} bytes → data/raw/{name} (CP949 → UTF-8)")


# --- OSM 노선 토폴로지 -------------------------------------------------------
# 수도권 전철 전 노선의 역 순서를 OSM route 릴레이션에서 가져온다.
# 서울교통공사 데이터(OA-12034)는 1~8호선 중 **자사 운영 구간만** 담고 있어
# 1호선 서울역 이남(코레일 경부·경인선), 9호선, 신분당선, 경의중앙선 등이 통째로 빠진다.
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OSM_RAIL_JSON = "osm_rail.json"

#: 수도권 (south, west, north, east)
RAIL_BBOX = (37.20, 126.55, 37.90, 127.40)

OVERPASS_QUERY = """
[out:json][timeout:300];
(
  relation["type"="route"]["route"="subway"]({s},{w},{n},{e});
  relation["type"="route"]["route"="light_rail"]({s},{w},{n},{e});
  relation["type"="route"]["route"="train"]({s},{w},{n},{e});
)->.r;
.r out body;
node(r.r);
out body;
"""


def fetch_osm_rail(bbox=RAIL_BBOX) -> None:
    s, w, n, e = bbox
    query = OVERPASS_QUERY.format(s=s, w=w, n=n, e=e)
    req = urllib.request.Request(
        OVERPASS_URL, data=urllib.parse.urlencode({"data": query}).encode(),
        headers={"User-Agent": "gachisaljip-transit/0.1"},
    )
    with urllib.request.urlopen(req, timeout=400) as resp:
        blob = resp.read()
    (RAW / OSM_RAIL_JSON).write_bytes(blob)
    print(f"  OSM 철도 노선 릴레이션: {len(blob):,} bytes → data/raw/{OSM_RAIL_JSON}")


def fetch_all() -> None:
    for name in SOURCES:
        fetch(name)
    fetch_osm_rail()
