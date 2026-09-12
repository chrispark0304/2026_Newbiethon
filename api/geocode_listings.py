"""매물 지번주소 → 좌표 캐시 생성.

    export KAKAO_REST_API_KEY=...
    python -m api.geocode_listings

실거래가 CSV의 좌표는 **동네 대표점**이라 실제 지번주소에서 중앙값 741m 떨어져 있다.
그 탓에 매물 절반의 통근시간이 5분 넘게 틀어진다. 주소는 CSV에 그대로 있으므로
카카오 로컬 `search/address`로 실좌표를 얻는다. 쿼터가 100,000건/일이라 1,167건은 부담이 없다.

결과는 `api/data/address_coords.json`에 쌓이고 저장소에 커밋한다.
이미 있는 주소는 건너뛰므로 재실행해도 호출이 늘지 않는다.
"""
from __future__ import annotations
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from .listings import ADDRESS_COORDS, RTMS_CSV, RtmsListings

ENDPOINT = "https://dapi.kakao.com/v2/local/search/address.json"
SLEEP_SEC = 0.03


def geocode(query: str, key: str) -> list[float] | None:
    url = f"{ENDPOINT}?" + urllib.parse.urlencode({"query": query, "size": 1})
    req = urllib.request.Request(url, headers={"Authorization": f"KakaoAK {key}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            docs = json.load(resp).get("documents") or []
    except Exception as exc:                      # noqa: BLE001 - 어떤 실패든 건너뛴다
        print(f"  실패 {query}: {exc}")
        return None
    return [float(docs[0]["y"]), float(docs[0]["x"])] if docs else None


def main() -> int:
    key = os.environ.get("KAKAO_REST_API_KEY")
    if not key:
        print("KAKAO_REST_API_KEY 환경변수를 설정하세요.")
        return 1

    cache = json.loads(ADDRESS_COORDS.read_text(encoding="utf-8")) if ADDRESS_COORDS.exists() else {}
    addresses = sorted({l.address for l in RtmsListings(RTMS_CSV).all()})

    todo = [a for a in addresses if a not in cache]
    print(f"주소 {len(addresses)}개 · 캐시 {len(cache)}개 · 조회 {len(todo)}개")
    start = time.time()
    for i, addr in enumerate(todo, 1):
        cache[addr] = geocode(addr, key)
        if i % 150 == 0:
            ADDRESS_COORDS.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            print(f"  {i}/{len(todo)} … {time.time() - start:.0f}s")
        time.sleep(SLEEP_SEC)

    ADDRESS_COORDS.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    ok = sum(1 for v in cache.values() if v)
    print(f"완료: 성공 {ok}/{len(cache)} · {time.time() - start:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
