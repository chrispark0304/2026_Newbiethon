"""프론트 ↔ 백엔드 계약.

첫 화면이 보내는 것: 사람 2명의 직장 좌표 + 가격 범위 + 면적 범위.
"""
from __future__ import annotations
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class Coord(BaseModel):
    lat: Annotated[float, Field(ge=32.0, le=39.5, description="위도 (WGS84)")]
    lon: Annotated[float, Field(ge=124.0, le=132.0, description="경도 (WGS84)")]


class Person(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=20)] = "나"
    work: Coord


class Range(BaseModel):
    min: Annotated[float, Field(ge=0)]
    max: Annotated[float, Field(ge=0)]

    @model_validator(mode="after")
    def _ordered(self):
        if self.max < self.min:
            raise ValueError("max는 min보다 크거나 같아야 합니다.")
        return self


class SearchRequest(BaseModel):
    """첫 화면 '같이 살자' 버튼이 보내는 페이로드."""
    people: Annotated[list[Person], Field(min_length=2, max_length=4)]
    #: 총 월세(만원)
    price: Range
    #: 총 전용면적(㎡)
    area: Range
    #: 통근 한도(분). 주면 초과 매물을 아예 제외한다.
    commute_limit_min: int | None = Field(default=None, ge=5, le=180)
    top: Annotated[int, Field(ge=1, le=100)] = 20
    #: 한 건물에서 최대 몇 건까지 보여 줄지. 실거래가는 호실별로 여러 건이 잡힌다. 0이면 제한 없음
    max_per_building: Annotated[int, Field(ge=0, le=20)] = 1
    #: 결과 쏠림을 막을 그룹 기준.
    #:   station = 최근접 역 (기본). 통근이 축인 서비스라 이게 가장 자연스럽다
    #:   dong    = 법정동 (296개). 잘아서 결과가 한 동에 몰릴 수 있다
    #:   gu      = 자치구 (25개). 굵어서 구 안의 통근 편차가 묻힌다
    group_by: Literal["station", "dong", "gu"] = "station"
    #: 한 그룹에서 최대 몇 건까지. 0이면 제한 없음
    max_per_group: Annotated[int, Field(ge=0, le=50)] = 0
    #: 항목별 가중치 덮어쓰기 (price / area / commute)
    weights: dict[str, float] | None = None
    #: 경로 상세(환승 구간)를 포함할지
    include_legs: bool = True


class Leg(BaseModel):
    kind: str
    detail: str
    minutes: int


class PersonCommute(BaseModel):
    name: str
    minutes: int
    boarding_stop: str | None
    legs: list[Leg] = []
    #: engine = 자체 지하철 그래프 / kakao = 카카오맵 대중교통 경로(버스 포함)
    source: str = "engine"
    #: 카카오 응답에만 있는 부가 정보
    transfers: int | None = None
    fare: int | None = None


class Station(BaseModel):
    name: str
    lines: list[str]
    walk_min: int


class ScoreBreakdown(BaseModel):
    price: float
    area: float
    commute: float
    total: float


class Assignment(BaseModel):
    """누가 어느 방을 쓰고 월세를 얼마 내는지. 방 면적 비율로 나눈 결과."""
    name: str
    room_sqm: int
    rent: int


class ListingResult(BaseModel):
    id: str
    #: 표시용 지역명. 원본에 `동네`가 있으면 그것, 없으면 법정동.
    hood: str
    gu: str = ""
    dong: str = ""
    desc: str
    lat: float
    lon: float
    #: address = 지번주소 지오코딩 좌표 / hood = 동네 대표점 폴백
    coord_source: str = "hood"
    #: 비교용 환산월세(만원). 전세·월세를 한 축에 놓은 값.
    rent_total: int
    #: ROOM_SPLIT으로 추정한 방별 면적(㎡). 원본에 방 구성이 없어 가정한 값이다.
    rooms: list[int]
    area_total: int

    # --- 원본 값. 화면에는 이쪽을 표시할 것 ---
    lease_type: str          # 전세 | 월세
    deposit: int             # 보증금(만원)
    monthly_rent: int        # 월세(만원)
    area_sqm: float
    address: str = ""
    building: str = ""
    floor: str = ""
    built_year: str = ""
    nearest_station: Station | None
    commute: list[PersonCommute]
    #: 통근시간이 가장 긴 사람 기준(분). 정렬·표시용
    commute_worst: int
    commute_gap: int
    joint_score: float
    per_person: list[ScoreBreakdown]
    assignment: list[Assignment]


class SearchStats(BaseModel):
    total: int
    after_price: int
    after_area: int
    #: 반경 내 역이 없어 대중교통 통근을 계산할 수 없던 매물 수
    unreachable: int = 0
    after_commute: int
    returned: int
    #: 오늘 누적 카카오 호출 수 (쿼터 1,000/일). 하이브리드 모드에서만
    kakao_calls: int | None = None


class SearchResponse(BaseModel):
    stats: SearchStats
    results: list[ListingResult]
    #: 조건이 빡빡해 결과가 없을 때 프론트에 띄울 힌트
    hint: str | None = None
