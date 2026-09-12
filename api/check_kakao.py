"""카카오 대중교통 API 연결 확인. **쿼터를 1~2건만 쓴다.**

    export KAKAO_REST_API_KEY=발급받은_REST_API_키
    python -m api.check_kakao

자체 엔진 결과와 나란히 찍어 주므로, 오차가 얼마나 나는지 바로 볼 수 있다.
"""
from __future__ import annotations
import sys

from .kakao import KakaoTransit

#: (설명, 집 좌표, 직장 좌표)
SAMPLES = [
    ("흑석 → 강남역", (37.508, 126.963), (37.4979, 127.0276)),
    ("신림 → 여의도", (37.484, 126.929), (37.5216, 126.9243)),
]


def main() -> int:
    kakao = KakaoTransit()
    if not kakao.enabled:
        print("KAKAO_REST_API_KEY 환경변수가 없습니다.")
        print("  export KAKAO_REST_API_KEY=...")
        return 1

    from transit.router import CommuteRouter
    router = CommuteRouter()

    print(f"{'구간':<18}{'카카오':>8}{'자체엔진':>10}{'차이':>8}   부가정보")
    print("-" * 72)
    for label, home, work in SAMPLES:
        got = kakao.travel_time(home, work, s_name="집", e_name="직장")
        dist, _ = router.times_to(*work)
        ours = router.commute(*home, dist)
        if got is None:
            print(f"{label:<18}{'실패':>8}{ours.minutes:>10}{'':>8}   "
                  f"(응답 없음 — 키·쿼터·좌표 확인)")
            continue
        diff = ours.minutes - got.minutes
        print(f"{label:<18}{got.minutes:>8}{ours.minutes:>10}{diff:>+8}   "
              f"{got.mode} 환승{got.transfers}회 {got.fare:,}원")

    print()
    print("쿼터:", kakao.stats())
    return 0


if __name__ == "__main__":
    sys.exit(main())
