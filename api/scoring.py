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

#: 두 사람 통근시간 격차가 이만큼 벌어지면 균형 점수 0점. 0분 차이면 100점.
#: 실제 분포가 중앙 16분 · 90퍼센타일 23~32분이라 35분이면 대부분이 0점 위에 놓인다.
BALANCE_ZERO_GAP_MIN = 35

#: 개인 점수 격차 벌점 계수.
#: 통근 불균형은 아래 balance가 따로 보므로, 여기서는 방 배정 같은 나머지 불균형만 잡는다.
#: (balance 도입 전에는 0.30이었는데 통근 격차를 이중으로 세게 된다.)
FAIRNESS_PENALTY = 0.20

DEFAULT_WEIGHTS = {"price": 1.0, "area": 1.0, "commute": 2.0}

#: 최종 점수에서 "평균 개인 만족도"와 "통근 균형"의 배분.
AVG_WEIGHT, BALANCE_WEIGHT = 3.0, 0.75


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
    #: 두 사람 통근시간이 얼마나 비슷한가 (0~100). 0분 차이면 100점.
    balance: float = 100.0


def commute_score(minutes: int) -> float:
    return _clamp(100.0 * (1.0 - minutes / COMMUTE_ZERO_MIN))


def balance_score(minutes: list[int]) -> float:
    """통근시간이 얼마나 고른가. 한 명만 가까운 집을 걸러내기 위한 값.

    평균만 보면 [10분, 50분]과 [30분, 30분]이 같은 집으로 취급된다.
    같이 사는 집에서는 후자가 분명히 낫다.
    """
    if len(minutes) < 2:
        return 100.0
    gap = max(minutes) - min(minutes)
    return _clamp(100.0 * (1.0 - gap / BALANCE_ZERO_GAP_MIN))


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
        bal = balance_score(minutes)
        base = (avg * AVG_WEIGHT + bal * BALANCE_WEIGHT) / (AVG_WEIGHT + BALANCE_WEIGHT)
        joint = base - FAIRNESS_PENALTY * abs(people[0].total - people[1].total)

        # 월세는 방 면적 비율로 나눈다(넓은 방이 더 낸다).
        span = sum(mine) or 1
        s0 = round(listing.rent_total * mine[0] / span)
        share = [s0, listing.rent_total - s0]

        if best is None or joint > best.joint:
            best = Score(round(joint, 1), people, list(mine), share, round(bal, 1))
    return best
