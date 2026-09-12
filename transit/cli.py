"""명령줄 진입점.

    python -m transit.cli fetch      # 원본 재다운로드 (평소 불필요)
    python -m transit.cli build      # 원본 → data/feed/*.csv
    python -m transit.cli query --work 37.4979,127.0276 --home 37.5571,126.9245
    python -m transit.cli matrix --work 강남:37.4979,127.0276 --work 여의도:37.5216,126.9243 --homes homes.csv
"""
from __future__ import annotations
import argparse
import csv
import sys


def _coord(text: str) -> tuple[float, float]:
    lat, lon = text.split(",")
    return float(lat), float(lon)


def _named_coord(text: str) -> tuple[str, float, float]:
    if ":" in text:
        name, rest = text.split(":", 1)
    else:
        name, rest = text, text
    lat, lon = _coord(rest)
    return name, lat, lon


def cmd_fetch(_args):
    from .fetch import fetch_all
    print("원본 다운로드")
    fetch_all()


def cmd_build(args):
    from .build_feed import build
    print("피드 빌드")
    build()


def cmd_query(args):
    from .router import CommuteRouter
    r = CommuteRouter()
    wlat, wlon = _coord(args.work)
    dist, parent = r.times_to(wlat, wlon)
    hlat, hlon = _coord(args.home)
    c = r.commute(hlat, hlon, dist, parent)
    if not c.reachable:
        print("경로 없음 (반경 내 정류장이 없거나 연결되지 않음)")
        return
    lines = "·".join(r.lines_at(c.access_stop))
    print(f"통근시간 {c.minutes}분  ·  승차역 {c.access_stop} ({lines})")
    for leg in c.legs:
        icon = "🚶" if leg.kind == "walk" else "🚇"
        print(f"  {icon} {leg.detail}  {leg.seconds // 60}분")


def cmd_matrix(args):
    """집 후보 × 직장 통근시간 표. 직장 1곳당 다익스트라 1회만 돈다."""
    from .router import CommuteRouter
    r = CommuteRouter()

    works = [_named_coord(w) for w in args.work]
    with open(args.homes, encoding="utf-8", newline="") as fp:
        homes = [(row["name"], float(row["lat"]), float(row["lon"]))
                 for row in csv.DictReader(fp)]

    # ★ 직장 수만큼만 계산한다. 집 후보 개수와 무관.
    fields = {name: r.times_to(lat, lon)[0] for name, lat, lon in works}

    w = csv.writer(sys.stdout)
    w.writerow(["home"] + [name for name, _, _ in works] + ["max", "sum"])
    for hname, hlat, hlon in homes:
        mins = []
        for name, _, _ in works:
            c = r.commute(hlat, hlon, fields[name])
            mins.append(c.minutes if c.reachable else "")
        nums = [m for m in mins if m != ""]
        w.writerow([hname] + mins + [max(nums) if nums else "", sum(nums) if nums else ""])


def cmd_recommend(args):
    """직장 좌표만 받아 살 만한 역을 찾아낸다."""
    import json
    from .recommend import recommend

    works = [_named_coord(w) for w in args.work]
    limits = args.limit if args.limit else None
    if limits and len(limits) == 1:
        limits = limits * len(works)          # 한도 하나만 주면 전원 공통
    if limits and len(limits) != len(works):
        raise SystemExit(f"--limit은 1개 또는 직장 수({len(works)})만큼 주세요.")

    cands, stats = recommend(
        works, limits=limits, objective=args.objective,
        pareto_only=args.pareto, spread_m=args.spread,
        access_walk_min=args.access_walk, top=args.top,
    )

    if args.json:
        print(json.dumps([{
            "stop_id": c.stop_id, "name": c.stop_name, "lat": c.lat, "lon": c.lon,
            "lines": c.lines, "minutes": c.minutes,
            "worst": c.worst, "total": c.total, "gap": c.gap,
        } for c in cands], ensure_ascii=False, indent=2))
        return

    print("  ".join(f"{k} {v:,}" for k, v in stats.items()))
    if not cands:
        print("조건을 만족하는 역이 없습니다. --limit을 늘려 보세요.")
        return

    names = [n for n, _, _ in works]
    head = "".join(f"{n[:6]:>7}" for n in names)
    print(f"\n{'역':<14}{head}{'최대':>6}{'합':>6}{'격차':>6}  노선")
    print("-" * (22 + 7 * len(names) + 18))
    for c in cands:
        cells = "".join(f"{m:>7}" for m in c.minutes)
        print(f"{c.stop_name:<14}{cells}{c.worst:>6}{c.total:>6}{c.gap:>6}  {'·'.join(c.lines)}")
    print("\n(단위: 분, 역 기준. objective=%s)" % args.objective)


def main(argv=None):
    p = argparse.ArgumentParser(prog="transit", description="대중교통 통근시간 엔진")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("fetch", help="원본 데이터 다운로드")
    sp.set_defaults(func=cmd_fetch)

    sp = sub.add_parser("build", help="원본 → 정규화 피드")
    sp.set_defaults(func=cmd_build)

    sp = sub.add_parser("query", help="집 1곳 → 직장 1곳 통근시간")
    sp.add_argument("--work", required=True, metavar="LAT,LON")
    sp.add_argument("--home", required=True, metavar="LAT,LON")
    sp.set_defaults(func=cmd_query)

    sp = sub.add_parser("matrix", help="집 후보 CSV × 직장 여러 곳 → 통근시간 표")
    sp.add_argument("--work", action="append", required=True, metavar="[이름:]LAT,LON")
    sp.add_argument("--homes", required=True, metavar="CSV", help="name,lat,lon 헤더 필요")
    sp.set_defaults(func=cmd_matrix)

    sp = sub.add_parser("recommend", help="직장 좌표 → 살 만한 역 추천")
    sp.add_argument("--work", action="append", required=True, metavar="[이름:]LAT,LON",
                    help="직장 위치. 여러 번 줄 수 있다")
    sp.add_argument("--limit", action="append", type=int, metavar="분",
                    help="통근 한도. 1개면 전원 공통, 아니면 직장 수만큼")
    sp.add_argument("--objective", default="minimax", choices=["minimax", "total", "fair"],
                    help="minimax=더 힘든 쪽 우선(기본) / total=합 / fair=격차 최소")
    sp.add_argument("--pareto", action="store_true",
                    help="어느 쪽도 손해 없이 개선 불가능한 후보만")
    sp.add_argument("--spread", type=float, default=1000, metavar="M",
                    help="결과 간 최소 거리. 인접 역 중복 제거 (기본 1000m, 0이면 끔)")
    sp.add_argument("--access-walk", type=int, default=0, metavar="분",
                    help="집→역 도보시간. 모든 후보에 일괄 가산")
    sp.add_argument("--top", type=int, default=15)
    sp.add_argument("--json", action="store_true", help="JSON으로 출력 (프론트 연동용)")
    sp.set_defaults(func=cmd_recommend)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
