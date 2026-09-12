"""공동 적합도 점수.

두 사람이 같이 사는 집이므로 **평균만 보면 안 된다.** 한쪽이 아주 만족하고 다른 쪽이
불만인 집은 둘 다 적당히 만족하는 집보다 나쁘다. 그래서 격차에 벌점을 준다.

    joint = 평균(개인 점수) − FAIRNESS_PENALTY × |개인 점수 차|

각 항목은 0~100으로 정규화한다. 슬라이더 범위가 그대로 정규화 기준이 된다.
(예산 상한에 가까우면 가격 점수 0, 하한이면 100)
"""
from __future__ import annotations
from dataclasses import dataclass

#: 통근 점수 0점이 되는 기준 시간(분). 이보다 오래 걸리면 0점.
COMMUTE_ZERO_MIN = 75
#: 개인 점수 격차 벌점 계수.
FAIRNESS_PENALTY = 0.30

DEFAULT_WEIGHTS = {"price": 1.0, "area": 1.0, "commute": 2.0}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _range_score(value: float, lo: float, hi: float, *, higher_is_better: bool) -> float:
    """[lo, hi] 안에서의 위치를 0~100으로. 범위가 0폭이면 만점."""
    if hi <= lo:
        return 100.0
    ratio = (value - lo) / (hi - lo)
    return _clamp(100.0 * (ratio if higher_is_better else 1.0 - ratio))


@dataclass
class Breakdown:
    price: float
    area: float
    commute: float
    total: float


@dataclass
class Score:
    joint: float
    per_person: list[Breakdown]
    #: 사람별 배정된 방 면적(㎡). 요청의 people 순서와 같다.
    room_sqm: list[int]
    #: 사람별 월세 분담(만원). 방 면적 비율로 나눈다.
    share: list[int]


def commute_score(minutes: int) -> float:
    return _clamp(100.0 * (1.0 - minutes / COMMUTE_ZERO_MIN))


def evaluate(listing, minutes: list[int], price_range, area_range,
             weights: dict | None = None) -> Score:
    """매물 하나에 대해 방 배정 2가지를 모두 보고 더 나은 쪽을 고른다."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    wsum = sum(w.values())
    price = _range_score(listing.rent_total, *price_range, higher_is_better=False)

    best: Score | None = None
    rooms = listing.rooms if len(listing.rooms) >= 2 else [listing.area_total, 0]
    for assign in (0, 1):
        mine = [rooms[assign], rooms[1 - assign]]
        people: list[Breakdown] = []
        for m, sqm in zip(minutes, mine):
            # 방 면적은 1인 기준이므로 총면적 슬라이더를 인원수로 나눠 비교한다.
            area = _range_score(sqm, area_range[0] / 2, area_range[1] / 2, higher_is_better=True)
            cm = commute_score(m)
            total = (price * w["price"] + area * w["area"] + cm * w["commute"]) / wsum
            people.append(Breakdown(round(price, 1), round(area, 1), round(cm, 1), round(total, 1)))

        avg = sum(p.total for p in people) / len(people)
        joint = avg - FAIRNESS_PENALTY * abs(people[0].total - people[1].total)

        # 월세는 방 면적 비율로 나눈다(넓은 방이 더 낸다).
        span = sum(mine) or 1
        s0 = round(listing.rent_total * mine[0] / span)
        share = [s0, listing.rent_total - s0]

        if best is None or joint > best.joint:
            best = Score(round(joint, 1), people, list(mine), share)
    return best
