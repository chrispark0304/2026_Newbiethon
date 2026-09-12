"""프론트엔드 명세(`Frontend/BACKEND_INTEGRATION.md`) 호환 계층.

`/api/search`는 백엔드 내부 스키마(환산월세·㎡·문자열 id)를 그대로 쓴다.
프론트는 다른 형태(월세+보증금 분리·평·숫자 id)를 원하므로 여기서 변환한다.
내부 스키마를 프론트에 맞춰 뭉개지 않고 경계에서만 번역하는 편이 양쪽 다 깔끔하다.

  GET  /api/geocode?query=강남역
  POST /api/listings/search
  GET  /api/listings/{id}/commute
"""
from __future__ import annotations
import json
import os
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field
from typing import Literal

from transit.router import INF

from .scoring import evaluate

router = APIRouter()

SQM_PER_PYEONG = 3.3058
KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"

#: 명세의 mode는 subway/bus 둘뿐이다. 우리 노선명을 어느 쪽으로 볼지 판단한다.
BUS_HINT = ("버스", "마을")


def pyeong(sqm: float) -> int:
    return round(sqm / SQM_PER_PYEONG)


def _floor_num(raw: str) -> int:
    try:
        return int(float((raw or "0").strip()))
    except ValueError:
        return 0


def _listing_no(listing) -> int:
    """'rtms-01234' → 1234. 프론트 명세가 숫자 id를 요구한다."""
    tail = listing.id.rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else abs(hash(listing.id)) % 10**8


# --------------------------------------------------------------- (A) 지오코딩

@router.get("/api/geocode")
def geocode(query: str = Query(..., min_length=1, max_length=80)):
    """자유 텍스트 → 좌표. 카카오 로컬을 프록시한다.

    장소명("강남역")은 키워드 검색이, 주소("서울시 강남구 …")는 주소 검색이 잘 맞으므로
    키워드를 먼저 보고 없으면 주소로 넘어간다.
    """
    key = os.environ.get("KAKAO_REST_API_KEY")
    if not key:
        raise HTTPException(503, "KAKAO_REST_API_KEY가 설정돼 있지 않습니다.")

    for url, field in ((KAKAO_KEYWORD_URL, "place_name"), (KAKAO_ADDRESS_URL, "address_name")):
        req = urllib.request.Request(
            f"{url}?" + urllib.parse.urlencode({"query": query, "size": 1}),
            headers={"Authorization": f"KakaoAK {key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                docs = json.load(resp).get("documents") or []
        except Exception:                                    # noqa: BLE001
            continue
        if docs:
            d = docs[0]
            return {"name": d.get(field) or query,
                    "lat": float(d["y"]), "lng": float(d["x"])}
    raise HTTPException(404, f"'{query}' 위치를 찾지 못했습니다.")


# --------------------------------------------------------------- (B) 매물 검색

class PersonCriteria(BaseModel):
    workLat: float
    workLng: float
    #: 이 사람이 부담할 월세 범위(만원). 두 사람 값을 더해 매물 총액과 비교한다.
    priceMin: float = 0
    priceMax: float = Field(default=1e9)
    #: 원하는 집 크기 범위(평). 집은 같이 쓰므로 두 사람 범위의 교집합을 쓴다.
    areaMin: float = 0
    areaMax: float = Field(default=1e9)


#: 목록 정렬 기준. 다양성 제한·limit보다 **먼저** 적용해야 한다.
#: 잘라낸 뒤 프론트에서 다시 정렬하면 "추천 150건 중 싼 것"이지 "제일 싼 것"이 아니다.
#: 각 기준은 동점일 때 추천 점수로 되돌아간다 — 같은 가격이면 더 나은 집이 위로.
SORTS = {
    "recommended": lambda r: (-r[0],),                       # 종합 추천
    "balanced":    lambda r: (-r[3], -r[0]),                 # 통근시간이 고른 순
    "price":       lambda r: (r[2].rent_total, -r[0]),       # 환산월세 싼 순
    "commute":     lambda r: (max(r[1]), -r[0]),             # 더 오래 걸리는 쪽이 짧은 순
    "area":        lambda r: (-r[2].area_sqm, -r[0]),        # 넓은 순
}


class SearchBody(BaseModel):
    p1: PersonCriteria
    p2: PersonCriteria
    #: 오류 문구에 쓸 직장 표시명. 없어도 동작한다.
    p1Name: str = ""
    p2Name: str = ""
    limit: int = Field(default=100, ge=1, le=300)

    # --- 아래는 명세 밖. 프론트가 안 보내면 기본값으로 동작한다 ---
    #: 목록 정렬 기준. SORTS 참조.
    sortBy: Literal["recommended", "balanced", "price", "commute", "area"] = "recommended"
    #: 더 오래 걸리는 쪽 통근이 이 값을 넘으면 제외. 0이면 제한 없음.
    commuteLimitMin: int = Field(default=60, ge=0, le=180)
    #: 같은 건물 최대 노출 수. 실거래가는 호실별로 여러 건이 잡힌다. 0이면 제한 없음.
    maxPerBuilding: int = Field(default=1, ge=0, le=20)
    #: 같은 법정동 최대 노출 수. 두 직장 사이 동네로 목록이 덮이는 걸 막는다. 0이면 제한 없음.
    maxPerDong: int = Field(default=3, ge=0, le=50)


def _criteria_to_ranges(body: SearchBody) -> tuple[tuple[float, float], tuple[float, float]]:
    """1인 기준 조건 두 개 → 매물 전체에 적용할 범위.

    **돈은 나눠 내고 집은 같이 쓴다.** 그래서 둘을 다르게 합친다.

      가격: 합집합(더한다). p1이 70까지, p2가 80까지 내면 150만원짜리 집을 볼 수 있다.
      면적: 교집합. "이 집이 8~20평이면 좋겠다"는 집 전체에 대한 희망이므로,
            둘 다 만족하는 구간만 남긴다. 더하면 35~75평이 되어 연립다세대에는
            해당 매물이 거의 없다(8,317건 중 62건).

    **범위가 안 겹치면 빈 구간을 그대로 돌려준다.** 한쪽이 10평 이하를 원하고 다른 쪽이
    15평 이상을 원하면 둘 다 만족하는 집은 없다. 억지로 넓혀 주면 두 사람 조건을 모두
    어긴 매물이 나가므로, 결과 없음으로 두고 프론트에 이유를 알려 주는 편이 정직하다.
    """
    price = (body.p1.priceMin + body.p2.priceMin, body.p1.priceMax + body.p2.priceMax)
    lo = max(body.p1.areaMin, body.p2.areaMin) * SQM_PER_PYEONG
    hi = min(body.p1.areaMax, body.p2.areaMax) * SQM_PER_PYEONG
    return price, (lo, hi)


@router.post("/api/listings/search")
def listings_search(body: SearchBody, response: Response):
    from .main import LISTING_ACCESS_WALK_M, WORK_ACCESS_WALK_M, state

    router_ = state["router"]
    items = state["listings"].all()
    price, area = _criteria_to_ranges(body)
    if area[1] < area[0]:
        raise HTTPException(422, {
            "code": "AREA_RANGE_DISJOINT",
            "message": (f"두 사람의 평수 조건이 겹치지 않습니다 "
                        f"({body.p1.areaMin:g}~{body.p1.areaMax:g}평 / "
                        f"{body.p2.areaMin:g}~{body.p2.areaMax:g}평)."),
        })
    if price[1] < price[0]:
        raise HTTPException(422, {
            "code": "PRICE_RANGE_INVALID",
            "message": "가격 범위가 뒤집혀 있습니다.",
        })

    fields = []
    for label, p, text in (("p1", body.p1, body.p1Name), ("p2", body.p2, body.p2Name)):
        try:
            fields.append(router_.times_to(p.workLat, p.workLng, radius_m=WORK_ACCESS_WALK_M))
        except ValueError:
            where = f"'{text}' 주변" if text else f"{label} 직장 주변"
            raise HTTPException(422, {
                "code": "WORK_NO_STATION",
                "message": (f"{where}에 지하철역이 없어요. "
                            f"역 이름이나 더 구체적인 장소로 검색해 보세요."),
            })

    # 환산월세로 거른다. 전세는 월세가 0이라 월세만 보면 비교가 안 된다.
    pool = [l for l in items
            if price[0] <= l.rent_total <= price[1] and area[0] <= l.area_sqm <= area[1]]

    cache: dict[tuple[float, float], list[int]] = {}
    out = []
    for l in pool:
        key = (l.lat, l.lon)
        if key not in cache:
            cache[key] = [router_.commute(l.lat, l.lon, f, explain=False,
                                         radius_m=LISTING_ACCESS_WALK_M).total_sec
                          for f in fields]
        secs = cache[key]
        if any(s >= INF for s in secs):
            continue
        minutes = [(s + 30) // 60 for s in secs]
        if body.commuteLimitMin and max(minutes) > body.commuteLimitMin:
            continue
        # 통근시간만 보면 예산 상한에 붙은 비싼 집과 훨씬 싼 집이 동급이 된다.
        # 가격·면적·통근을 함께 보고, 두 사람 만족도 격차에 벌점을 준다.
        score = evaluate(l, minutes, price, (area[0], area[1]))
        out.append((score.joint, minutes, l, score.balance))

    out.sort(key=SORTS[body.sortBy])
    total_matched = len(out)          # 다양성 제한·limit으로 자르기 전 개수

    # 같은 건물·같은 동네가 목록을 덮는 걸 막는다. 상위 60건이 11개 동에 몰리던 문제.
    if body.maxPerBuilding or body.maxPerDong:
        per_building: dict[tuple, int] = {}
        per_dong: dict[str, int] = {}
        kept = []
        for row in out:
            l = row[2]
            bkey, dkey = (l.address, l.building), (l.dong or l.hood)
            if body.maxPerBuilding and per_building.get(bkey, 0) >= body.maxPerBuilding:
                continue
            if body.maxPerDong and per_dong.get(dkey, 0) >= body.maxPerDong:
                continue
            per_building[bkey] = per_building.get(bkey, 0) + 1
            per_dong[dkey] = per_dong.get(dkey, 0) + 1
            kept.append(row)
            if len(kept) >= body.limit:
                break
        out = kept

    # 응답 본문은 명세대로 배열 그대로 두고, 잘라내기 전 총 개수만 헤더로 알린다.
    # "매물 100개"라고만 쓰면 뒤에 1,400건이 더 있다는 걸 화면에서 알 수 없다.
    response.headers["X-Total-Matched"] = str(total_matched)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Matched"

    station = state["stations"]
    return [{
        "id": _listing_no(l),
        "price": l.monthly_rent,
        "deposit": l.deposit,
        "neighborhood": f"{l.gu} {l.dong}".strip(),
        "address": l.address,
        "floor": _floor_num(l.floor),
        "area": pyeong(l.area_sqm),
        "year": int(l.built_year) if l.built_year.isdigit() else 0,
        "lat": l.lat,
        "lng": l.lon,
        # --- 명세 밖 부가 필드. 쓰지 않아도 무방하다 ---
        "leaseType": l.lease_type,
        "monthlyEquivalent": l.rent_total,
        "buildingName": l.building,
        "nearestStation": (lambda s: {"name": s.name, "lines": s.lines, "walkMin": s.walk_min}
                           if s else None)(station.get(l.id)),
        "commuteMinutes": minutes,
        "jointScore": joint,
        "balanceScore": balance,
    } for joint, minutes, l, balance in out[: body.limit]]


# --------------------------------------------------------------- (C) 통근 경로

def _kakao_stops(home: tuple[float, float], work: tuple[float, float], kakao):
    """카카오 대중교통 응답 → 명세의 stops[] 형태.

    카카오는 구간(step)별로 `stops[].name`과 `path.points`(폴리라인, [lon, lat])를 준다.
    정류장 자체에는 좌표가 없으므로 **그 구간 폴리라인의 끝점**을 하차 지점 좌표로 쓴다.

    `stops`는 명세대로 환승 지점만 담고(도보 구간 제외), `path`에는 **도보까지 포함한
    모든 구간의 실제 선로 좌표**를 수단·노선과 함께 담는다. 정류장을 직선으로 이으면
    지하철이 강을 가로지르는 것처럼 그려지는데, 폴리라인을 쓰면 실제 노선 모양이 나온다.
    """
    raw = kakao.raw_route(home, work)
    if not raw:
        return None
    props = raw.get("properties", {})
    stops = [{"name": "집", "lat": home[0], "lng": home[1]}]
    paths = []
    for step in raw.get("steps", []):
        sp = step.get("properties", {})
        kind = sp.get("type")
        points = (step.get("path") or {}).get("points") or []
        names = sp.get("stops") or []
        vehicles = sp.get("vehicles") or []
        if points:
            paths.append({
                "mode": {"SUBWAY": "subway", "BUS": "bus"}.get(kind, "walk"),
                "line": vehicles[0].get("name") if vehicles else None,
                "points": [[p[1], p[0]] for p in points],     # [lon,lat] → [lat,lng]
            })
        if kind not in ("SUBWAY", "BUS") or not points:
            continue
        last = points[-1]
        stops.append({
            "name": names[-1].get("name") if names else sp.get("guidance", ""),
            "lat": last[1], "lng": last[0],
            "mode": "subway" if kind == "SUBWAY" else "bus",
            "line": vehicles[0].get("name", "") if vehicles else "",
        })
    if len(stops) < 2:
        return None
    return {"minutes": (props.get("totalTime", 0) + 30) // 60,
            "stops": stops, "path": paths, "source": "kakao",
            "transfers": props.get("transfers"), "fare": (props.get("fare") or {}).get("value")}


def _engine_stops(home: tuple[float, float], field, router_):
    """자체 엔진 경로 → 명세의 stops[] 형태. 카카오가 실패했을 때의 폴백.

    지하철만 다루므로 mode는 항상 subway다. 좌표는 우리 역 목록에서 이름으로 찾는다.
    """
    from .main import LISTING_ACCESS_WALK_M
    c = router_.commute(home[0], home[1], field, radius_m=LISTING_ACCESS_WALK_M)
    if not c.reachable:
        return None
    by_name = {s.stop_name: s for s in router_.g.stops}
    stops = [{"name": "집", "lat": home[0], "lng": home[1]}]
    for leg in c.legs:
        if leg.kind != "ride":
            continue
        st = by_name.get(leg.to_stop)
        if not st:
            continue
        stops.append({"name": st.stop_name, "lat": st.lat, "lng": st.lon,
                      "mode": "subway", "line": leg.route_name})
    if len(stops) < 2:
        return None
    return {"minutes": c.minutes, "stops": stops, "path": [], "source": "engine",
            "transfers": max(0, len(stops) - 2), "fare": None}


@router.get("/api/listings/{listing_id}/commute")
def listing_commute(listing_id: int,
                    p1WorkLat: float, p1WorkLng: float,
                    p2WorkLat: float, p2WorkLng: float):
    """매물 하나에 대한 두 사람의 통근 경로.

    화면 진입 시 매물 하나에만 호출되므로 카카오를 1순위로 쓴다(사람당 1콜).
    버스 구간까지 나오고 쿼터 부담도 적다. 실패하면 자체 엔진(지하철 전용)으로 폴백한다.
    """
    from .main import WORK_ACCESS_WALK_M, state

    listing = next((l for l in state["listings"].all() if _listing_no(l) == listing_id), None)
    if listing is None:
        raise HTTPException(404, f"매물 {listing_id}을(를) 찾을 수 없습니다.")

    kakao = state["kakao"]
    router_ = state["router"]
    home = (listing.lat, listing.lon)
    out = {}
    for label, work in (("p1", (p1WorkLat, p1WorkLng)), ("p2", (p2WorkLat, p2WorkLng))):
        got = _kakao_stops(home, work, kakao) if kakao.enabled else None
        if got is None:
            try:
                field = router_.times_to(*work, radius_m=WORK_ACCESS_WALK_M)
            except ValueError:
                raise HTTPException(422, f"{label} 직장 주변에 지하철역이 없어요.")
            got = _engine_stops(home, field, router_)
        if got is None:
            raise HTTPException(422, f"{label} 경로를 찾지 못했습니다.")
        out[label] = got
    return out
