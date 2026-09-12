"""수동 보정값 로더.

역 좌표는 OSM 릴레이션 노드(`data/raw/osm_rail.json`)에서 바로 나오므로 지오코딩 단계가 없다.
이 파일은 **자동 수집이 틀렸을 때 손으로 덮어쓰는 경로**만 제공한다.
"""
from __future__ import annotations
import csv

from .config import MANUAL

COORD_OVERRIDE = MANUAL / "station_coords_override.csv"


def load_coord_override() -> dict[str, tuple[float, float]]:
    """{역명: (lat, lon)}. 자동 수집 결과를 항상 이긴다."""
    if not COORD_OVERRIDE.exists():
        return {}
    with COORD_OVERRIDE.open(encoding="utf-8", newline="") as fp:
        return {r["station_name"]: (float(r["lat"]), float(r["lon"]))
                for r in csv.DictReader(fp) if r.get("lat")}
