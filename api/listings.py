"""매물 저장소.

실제 소스는 국토교통부 실거래가(RTMS) 연립다세대 전월세 자료다.
`ListingSource` 프로토콜(`all()` 하나)만 지키면 DB·크롤러로 갈아끼울 수 있다.

원본 데이터의 성질
------------------
1. **전세와 월세가 섞여 있다.** 전세는 월세=0, 보증금이 크다.
   가격 슬라이더 하나로 비교하려면 공통 척도가 필요해서 **환산월세**를 쓴다.
       환산월세 = 월세 + 보증금 × 전월세전환율 / 12
   원본 보증금·월세는 그대로 보존하므로 화면에는 "전세 2.7억"으로 표시할 수 있다.

2. **원본 좌표가 건물 단위가 아니라 동네 대표점이다.** 1,408건이 고유 좌표 35개를 공유한다.
   대표점은 실제 지번주소에서 **중앙값 741m, 최대 2.8km** 떨어져 있고,
   그 탓에 매물 절반의 통근시간이 5분 넘게 틀어진다(평균절대차 6.2분, 최대 32분).
   → 그래서 `시군구 + 번지`를 카카오 로컬로 지오코딩한 좌표를 우선 쓴다
     (`data/address_coords.json`, 고유 주소 1,167개 전부 해석됨).
   지오코딩에 없는 주소만 대표점으로 폴백하며, `coord_source`가 어느 쪽인지 알려 준다.

3. **방 개수 정보가 없다.** 전용면적 총합만 있다.
   두 사람이 나눠 쓴다는 전제로 ROOM_SPLIT 비율로 쪼개는데,
   이건 **데이터가 아니라 가정**이다. 실제 방 구성이 아니다.

4. **거래 건 단위라 같은 호실이 여러 번 나온다.** 주소·건물·층·면적이 모두 같은 행이
   69조 148건 있다. 같은 집의 여러 계약이므로 하나로 합친다(가장 싼 계약 기준).
   층이나 면적이 다르면 별개 호실이므로 남긴다.
"""
from __future__ import annotations
import collections
import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RTMS_CSV = PROJECT_ROOT / "rtms_같이살집_최종_202608.csv"

#: 지번주소 → 좌표 캐시. 카카오 로컬 search/address 결과를 저장해 둔 것.
#: 갱신은 `python -m api.geocode_listings`.
ADDRESS_COORDS = Path(__file__).resolve().parent / "data" / "address_coords.json"

#: 전월세전환율(연). 전세 보증금을 월세로 환산할 때 쓴다.
#: 한국부동산원 서울 연립다세대 기준 근사치. 시장에 따라 조정할 것.
JEONSE_CONVERSION_RATE = 0.055

#: 전용면적을 두 방으로 나누는 비율. **데이터가 아니라 가정이다.**
#: 원본에 방 구성이 없어서, 큰 방/작은 방이 있는 투룸을 상정했다.
ROOM_SPLIT = (0.55, 0.45)


def _num(raw: str) -> float:
    """'27,000' → 27000.0 / 빈 값·'-' → 0"""
    raw = (raw or "").replace(",", "").strip()
    if not raw or raw == "-":
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


@dataclass(frozen=True)
class Listing:
    id: str
    hood: str
    desc: str
    lat: float
    lon: float
    #: 비교용 환산월세(만원). 전세·월세를 한 축에 놓기 위한 값.
    rent_total: int
    #: 방별 전용면적(㎡). 큰 방부터. ROOM_SPLIT으로 추정한 값이다.
    rooms: list[int] = field(default_factory=list)
    #: address = 지번주소 지오코딩 / hood = 동네 대표점 폴백
    coord_source: str = "hood"

    # --- 원본 값 (화면 표시용) ---
    lease_type: str = ""          # 전세 | 월세
    deposit: int = 0              # 보증금(만원)
    monthly_rent: int = 0         # 월세(만원)
    area_sqm: float = 0.0         # 전용면적(㎡)
    address: str = ""
    building: str = ""
    floor: str = ""
    built_year: str = ""

    @property
    def area_total(self) -> int:
        return round(self.area_sqm)


def _dedupe_units(items: list["Listing"]) -> list["Listing"]:
    """같은 호실의 중복 계약을 하나로 합친다. 가장 싼 계약을 남긴다."""
    best: dict[tuple, Listing] = {}
    for l in items:
        key = (l.address, l.building, l.floor, round(l.area_sqm, 1))
        cur = best.get(key)
        if cur is None or l.rent_total < cur.rent_total:
            best[key] = l
    return list(best.values())


class ListingSource(Protocol):
    def all(self) -> list[Listing]:
        """전체 매물. 필터링은 호출 측에서 한다."""


class RtmsListings:
    """국토부 실거래가 CSV 기반 소스.

    컬럼: 동네, 시군구, 번지, 건물명, 위도, 경도, 전월세구분,
          전용면적(㎡), 층, 보증금(만원), 월세금(만원), 건축년도
    """

    def __init__(self, path: Path = RTMS_CSV,
                 conversion_rate: float = JEONSE_CONVERSION_RATE,
                 address_coords: Path = ADDRESS_COORDS):
        self.path = Path(path)
        self.conversion_rate = conversion_rate
        self._coords = self._load_coords(Path(address_coords))
        self._items = self._load()

    @staticmethod
    def _load_coords(path: Path) -> dict[str, list[float]]:
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return {k: v for k, v in raw.items() if v}

    @property
    def coord_stats(self) -> dict[str, int]:
        c = collections.Counter(l.coord_source for l in self._items)
        return {"address": c["address"], "hood": c["hood"]}

    def _load(self) -> list[Listing]:
        blob = self.path.read_bytes()
        for enc in ("utf-8-sig", "cp949"):
            try:
                text = blob.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise UnicodeDecodeError("unknown", blob, 0, 1, f"{self.path} 인코딩 판별 실패")

        out: list[Listing] = []
        for i, row in enumerate(csv.DictReader(io.StringIO(text))):
            lat, lon = _num(row["위도"]), _num(row["경도"])
            address = ((row.get("시군구") or "").strip() + " "
                       + (row.get("번지") or "").strip()).strip()
            # 지번주소 지오코딩이 있으면 그쪽을 쓴다. 대표점은 폴백일 뿐이다.
            geo = self._coords.get(address)
            coord_source = "hood"
            if geo:
                lat, lon, coord_source = geo[0], geo[1], "address"
            if not (lat and lon):
                continue
            area = _num(row["전용면적(㎡)"])
            deposit = int(_num(row["보증금(만원)"]))
            monthly = int(_num(row["월세금(만원)"]))
            lease = (row["전월세구분"] or "").strip()

            converted = monthly + deposit * self.conversion_rate / 12
            building = (row.get("건물명") or "").strip()
            floor = (row.get("층") or "").strip()

            bits = [b for b in (building, f"{floor}층" if floor else "",
                                f"{area:.0f}㎡" if area else "") if b]
            out.append(Listing(
                id=f"rtms-{i:05d}",
                hood=(row.get("동네") or "").strip(),
                desc=" · ".join(bits) or "연립다세대",
                lat=lat, lon=lon, coord_source=coord_source,
                rent_total=round(converted),
                rooms=[round(area * ROOM_SPLIT[0]), round(area * ROOM_SPLIT[1])],
                lease_type=lease, deposit=deposit, monthly_rent=monthly,
                area_sqm=area,
                address=address,
                building=building, floor=floor,
                built_year=(row.get("건축년도") or "").strip(),
            ))
        return _dedupe_units(out)

    def all(self) -> list[Listing]:
        return self._items


class SeedListings(RtmsListings):
    """이전 데모용 시드. 테스트에서만 쓴다."""

    def __init__(self, path: Path = Path(__file__).resolve().parent / "data" / "listings.seed.json"):
        import json
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        self._items = [
            Listing(rent_total=r["rent_total"], area_sqm=sum(r["rooms"]), **{
                k: v for k, v in r.items() if k not in ("rent_total",)
            }) for r in payload["listings"]
        ]

    def all(self) -> list[Listing]:
        return self._items
