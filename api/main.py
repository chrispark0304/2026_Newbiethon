"""같이살집 백엔드.

    uvicorn api.main:app --reload --port 8000
    문서: http://localhost:8000/docs

transit 엔진은 프로세스 기동 시 한 번만 올린다(그래프 상주).
요청마다 드는 비용은 **직장 수만큼의 다익스트라뿐**이라 매물이 몇 건이든 같다.
"""
from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from transit.geo import haversine_m, walk_sec
from transit.router import INF, CommuteRouter

from .kakao import KakaoTransit
from .listings import RtmsListings
from .schemas import (Assignment, Leg, ListingResult, PersonCommute,
                      ScoreBreakdown, SearchRequest, SearchResponse, SearchStats,
                      Station)
from .scoring import evaluate

log = logging.getLogger("gachisaljip")

#: 매물에서 이 반경 안에 역이 없으면 "가장 가까운 역" 표시를 생략한다.
MAX_STATION_WALK_M = 1200

#: 매물 → 승차역 최대 도보 반경(m).
#: 지번주소 실좌표로 바꾼 뒤에도 엔진 기본값(900m)에서는 106건이 unreachable이다.
#: 연립다세대가 실제로 역에서 먼 경우가 많다는 뜻이고, 그런 집은 보통 버스를 탄다.
#: 자체 엔진에는 버스가 없으므로 긴 도보가 그 대역이다. 넓게 잡으면 도보시간이 그만큼
#: 더해져 순위에서 알아서 밀리고, 상위에 올라오면 카카오가 실제 버스 경로로 바로잡는다.
#: 조용히 버리는 것보다 낫다. 1,600m에서 unreachable은 8건.
LISTING_ACCESS_WALK_M = 1600

#: 통근시간 출처.
#:   engine  자체 지하철 그래프만. 외부 호출 0회
#:   kakao   전부 카카오맵 대중교통 경로. 정확하지만 쿼터(1,000/일)를 빨리 먹는다
#:   hybrid  자체 엔진으로 전부 랭킹하고, **화면에 나가는 상위 N개만** 카카오로 정밀화 (기본)
#:
#: 매물 좌표가 동네 대표점 35개뿐이라 kakao 모드도 검색당 70콜이면 되지만,
#: 1,000/일 ÷ 70 = 하루 14회 검색이라 데모 중에 말라붙는다.
#: hybrid는 검색당 ~20콜이고 캐시가 쌓이면 0에 수렴한다.
COMMUTE_PROVIDER = os.environ.get("COMMUTE_PROVIDER", "hybrid")

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["router"] = CommuteRouter()
    state["listings"] = RtmsListings()
    state["kakao"] = KakaoTransit()
    # 최근접 역은 매물당 한 번만 구하면 되므로 기동 시 전부 계산해 둔다.
    # 결과 카드 표시에도 쓰고, 결과 쏠림을 막는 그룹 키로도 쓴다.
    state["stations"] = {
        l.id: _nearest_station(state["router"], l.lat, l.lon)
        for l in state["listings"].all()
    }
    log.info("그래프 %d노드 / 매물 %d건(좌표없어 제외 %d) / 통근 출처 %s (카카오 %s)",
             state["router"].g.n_nodes, len(state["listings"].all()),
             state["listings"].skipped, COMMUTE_PROVIDER,
             "사용 가능" if state["kakao"].enabled else "키 없음")
    yield
    state.clear()


app = FastAPI(title="같이살집 API", version="0.1.0", lifespan=lifespan)

# 개발 중 프론트(Vite 등)에서 바로 부를 수 있게 열어 둔다.
# 배포 시에는 실제 도메인으로 좁힐 것.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.get("/api/health")
def health():
    r = state.get("router")
    return {
        "ok": r is not None,
        "stops": r.g.n_stops if r else 0,
        "listings": len(state["listings"].all()) if state.get("listings") else 0,
        "coords": state["listings"].coord_stats if state.get("listings") else None,
        "skipped_no_coords": state["listings"].skipped if state.get("listings") else 0,
        "commute_provider": COMMUTE_PROVIDER,
        "kakao": state["kakao"].stats() if state.get("kakao") else None,
    }


def _nearest_station(router: CommuteRouter, lat: float, lon: float) -> Station | None:
    best = None
    for stop_id, dist_m in router.g.grid.within(lat, lon, MAX_STATION_WALK_M):
        if best is None or dist_m < best[1]:
            best = (stop_id, dist_m)
    if best is None:
        return None
    stop = router.g.stops[router.g.stop_index[best[0]]]
    return Station(name=stop.stop_name,
                   lines=router.lines_at(stop.stop_name),
                   walk_min=max(1, walk_sec(best[1]) // 60))


def _person_commute(person, engine_result, minutes: int, kakao_result, include_legs: bool):
    """카카오 결과가 있으면 그쪽 시간을 쓰고, 없으면 자체 엔진 값을 쓴다.

    경로 상세(legs)는 자체 엔진 것만 있다. 카카오 응답에도 steps가 오지만
    여기서는 소요시간만 쓴다 — 출처가 섞이면 표시가 헷갈린다.
    """
    if kakao_result:
        return PersonCommute(
            name=person.name, minutes=kakao_result.minutes,
            boarding_stop=engine_result.access_stop, legs=[],
            source="kakao", transfers=kakao_result.transfers, fare=kakao_result.fare,
        )
    return PersonCommute(
        name=person.name, minutes=minutes, boarding_stop=engine_result.access_stop,
        legs=[Leg(kind=g.kind, detail=g.detail, minutes=max(1, g.seconds // 60))
              for g in engine_result.legs] if include_legs else [],
        source="engine",
    )


@app.post("/api/search", response_model=SearchResponse)
def search(req: SearchRequest):
    router: CommuteRouter = state["router"]
    items = state["listings"].all()

    # ① 직장 수만큼만 역방향 다익스트라. 매물 수와 무관하다.
    fields = []
    for person in req.people:
        try:
            dist, parent = router.times_to(person.work.lat, person.work.lon)
        except ValueError:
            raise HTTPException(
                422, f"'{person.name}'의 직장 반경에 역이 없습니다. 좌표를 확인해 주세요.")
        fields.append((dist, parent))

    stats = {"total": len(items)}

    # ② 가격·면적 필터 (좌표 계산 전에 걸러 낸다)
    pool = [l for l in items if req.price.min <= l.rent_total <= req.price.max]
    stats["after_price"] = len(pool)
    pool = [l for l in pool if req.area.min <= l.area_total <= req.area.max]
    stats["after_area"] = len(pool)

    # ③ 매물별 통근시간. 필드를 재사용하므로 매물당 비용은 반경 질의 한 번뿐.
    #    지오코딩 후 고유 좌표가 1,167개라 메모이즈 효과는 줄었지만(같은 건물 다른 층),
    #    호출 자체가 8ms/1,329건이라 문제가 되지 않는다.
    cache: dict[tuple[float, float], list] = {}

    def commutes_for(lat: float, lon: float):
        key = (lat, lon)
        if key not in cache:
            cache[key] = [router.commute(lat, lon, dist,
                                         parent if req.include_legs else None,
                                         radius_m=LISTING_ACCESS_WALK_M)
                          for dist, parent in fields]
        return cache[key]

    scored = []
    unreachable = 0
    for l in pool:
        commutes = commutes_for(l.lat, l.lon)
        if any(not c.reachable for c in commutes):
            unreachable += 1
            continue
        minutes = [c.minutes for c in commutes]
        if req.commute_limit_min and max(minutes) > req.commute_limit_min:
            continue
        score = evaluate(l, minutes,
                         (req.price.min, req.price.max), (req.area.min, req.area.max),
                         req.weights)
        scored.append((l, commutes, minutes, score))

    stats["unreachable"] = unreachable
    stats["after_commute"] = len(scored)
    scored.sort(key=lambda x: -x[3].joint)

    # ④ 다양성 제한 — 같은 건물·같은 지역이 목록을 덮는 걸 막는다
    if req.max_per_building or req.max_per_group:
        stations = state["stations"]

        def group_key(l):
            if req.group_by == "dong":
                return l.dong or l.hood
            if req.group_by == "gu":
                return l.gu
            st = stations.get(l.id)
            return st.name if st else (l.dong or l.hood)

        per_building: dict[tuple, int] = {}
        per_group: dict[str, int] = {}
        kept = []
        for row in scored:
            l = row[0]
            bkey = (l.address, l.building)
            gkey = group_key(l)
            if req.max_per_building and per_building.get(bkey, 0) >= req.max_per_building:
                continue
            if req.max_per_group and per_group.get(gkey, 0) >= req.max_per_group:
                continue
            per_building[bkey] = per_building.get(bkey, 0) + 1
            per_group[gkey] = per_group.get(gkey, 0) + 1
            kept.append(row)
            if len(kept) >= req.top:
                break
        scored = kept
    scored = scored[: req.top]
    stats["returned"] = len(scored)

    # ⑤ 카카오 정밀화 — 화면에 나가는 것만. 버스를 포함한 실제 소요시간으로 덮어쓴다.
    #    쿼터(1,000/일)를 아끼려고 좌표 단위로 묶어 부른다.
    #    실패·쿼터소진이면 조용히 자체 엔진 값을 그대로 쓴다.
    kakao: KakaoTransit = state["kakao"]
    refined: dict[tuple[float, float, int], object] = {}
    if COMMUTE_PROVIDER in ("hybrid", "kakao") and kakao.enabled:
        wanted = {(l.lat, l.lon) for l, _, _, _ in scored}
        for lat, lon in wanted:
            for i, person in enumerate(req.people):
                got = kakao.travel_time((lat, lon), (person.work.lat, person.work.lon),
                                        s_name="집", e_name=person.name)
                if got:
                    refined[(lat, lon, i)] = got
        if refined:
            # 시간이 바뀌었으니 점수와 순서를 다시 매긴다.
            rescored = []
            for l, commutes, minutes, score in scored:
                merged = [refined[(l.lat, l.lon, i)].minutes
                          if (l.lat, l.lon, i) in refined else m_
                          for i, m_ in enumerate(minutes)]
                rescored.append((l, commutes, merged,
                                 evaluate(l, merged,
                                          (req.price.min, req.price.max),
                                          (req.area.min, req.area.max), req.weights)))
            rescored.sort(key=lambda x: -x[3].joint)
            scored = rescored
        stats["kakao_calls"] = kakao.stats()["calls_today"]

    results = []
    for l, commutes, minutes, score in scored:
        results.append(ListingResult(
            id=l.id, hood=l.hood, gu=l.gu, dong=l.dong, desc=l.desc, lat=l.lat, lon=l.lon,
            coord_source=l.coord_source,
            rent_total=l.rent_total, rooms=l.rooms, area_total=l.area_total,
            lease_type=l.lease_type, deposit=l.deposit, monthly_rent=l.monthly_rent,
            area_sqm=l.area_sqm, address=l.address, building=l.building,
            floor=l.floor, built_year=l.built_year,
            nearest_station=state["stations"].get(l.id),
            commute=[
                _person_commute(p, c, minutes[i], refined.get((l.lat, l.lon, i)),
                                req.include_legs)
                for i, (p, c) in enumerate(zip(req.people, commutes))
            ],
            commute_worst=max(minutes), commute_gap=max(minutes) - min(minutes),
            joint_score=score.joint,
            per_person=[ScoreBreakdown(**vars(b)) for b in score.per_person],
            assignment=[
                Assignment(name=p.name, room_sqm=sqm, rent=rent)
                for p, sqm, rent in zip(req.people, score.room_sqm, score.share)
            ],
        ))

    hint = None
    if not results:
        if stats["after_price"] == 0:
            hint = "가격 범위를 넓혀 보세요."
        elif stats["after_area"] == 0:
            hint = "면적 범위를 넓혀 보세요."
        else:
            hint = "통근 한도를 늘려 보세요."

    return SearchResponse(stats=SearchStats(**stats), results=results, hint=hint)
