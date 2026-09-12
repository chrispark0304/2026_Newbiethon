"""ODsay 실측과 비교해 파라미터를 보정한다.

무료 쿼터가 하루 30회뿐이라 기본값도 30으로 잡았다.
경로 탐색 자체는 우리 그래프가 하고, ODsay는 **검증에만** 쓴다.

    export ODSAY_API_KEY=...
    python -m transit.calibrate --work 37.4979,127.0276 --homes transit/data/manual/homes.sample.csv

출력의 `제안 BOARD_PENALTY_SEC` 를 config.py에 반영하면 오차가 줄어든다.
환승 통로 도보·대기 시간이 이 파라미터 하나에 몰려 있기 때문이다.
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import statistics
import time
import urllib.parse
import urllib.request

ODSAY_URL = "https://api.odsay.com/v1/api/searchPubTransPathT"


def odsay_minutes(sx, sy, ex, ey, key) -> int | None:
    params = urllib.parse.urlencode(
        {"SX": sx, "SY": sy, "EX": ex, "EY": ey, "apiKey": key, "OPT": 0}
    )
    with urllib.request.urlopen(f"{ODSAY_URL}?{params}", timeout=20) as resp:
        payload = json.load(resp)
    if "error" in payload:
        raise RuntimeError(f"ODsay 오류: {payload['error']}")
    paths = payload.get("result", {}).get("path", [])
    return paths[0]["info"]["totalTime"] if paths else None


def main(argv=None):
    p = argparse.ArgumentParser(description="ODsay 대비 오차 측정")
    p.add_argument("--work", required=True, metavar="LAT,LON")
    p.add_argument("--homes", required=True, metavar="CSV")
    p.add_argument("--limit", type=int, default=30, help="ODsay 호출 상한 (무료 30/일)")
    args = p.parse_args(argv)

    key = os.environ.get("ODSAY_API_KEY")
    if not key:
        raise SystemExit("ODSAY_API_KEY 환경변수를 설정하세요.")

    from .router import CommuteRouter
    r = CommuteRouter()
    wlat, wlon = (float(v) for v in args.work.split(","))
    field = r.times_to(wlat, wlon)

    with open(args.homes, encoding="utf-8", newline="") as fp:
        homes = list(csv.DictReader(fp))[: args.limit]

    diffs = []
    print(f"{'집':<16}{'우리':>6}{'ODsay':>7}{'차이':>7}")
    for h in homes:
        hlat, hlon = float(h["lat"]), float(h["lon"])
        ours = r.commute(hlat, hlon, field, explain=False)
        if not ours.reachable:
            continue
        ref = odsay_minutes(hlon, hlat, wlon, wlat, key)
        time.sleep(0.3)
        if ref is None:
            continue
        d = ours.minutes - ref
        diffs.append(d)
        print(f"{h['name']:<16}{ours.minutes:>6}{ref:>7}{d:>+7}")

    if not diffs:
        print("비교 가능한 표본이 없습니다.")
        return
    bias = statistics.mean(diffs)
    mae = statistics.mean(abs(d) for d in diffs)
    print(f"\n표본 {len(diffs)}건 · 평균편차 {bias:+.1f}분 · 평균절대오차 {mae:.1f}분")

    from .config import BOARD_PENALTY_SEC
    # 편차는 대부분 환승 페널티 과소/과대에서 온다. 표본당 평균 환승 1.5회로 가정해 역산.
    suggest = max(0, int(BOARD_PENALTY_SEC - bias * 60 / 1.5))
    print(f"제안 BOARD_PENALTY_SEC = {suggest}  (현재 {BOARD_PENALTY_SEC})")


if __name__ == "__main__":
    main()
