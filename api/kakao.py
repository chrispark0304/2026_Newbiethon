"""카카오맵 대중교통 경로 조회 클라이언트.

    GET https://dapi.kakao.com/v2/routing/publictraffic
        ?start_x&start_y&end_x&end_y[&s_name&e_name]
        Authorization: KakaoAK {REST_API_KEY}

    → { "status": "OK", "properties": {...},
        "routes": [ { "properties": { "type", "totalDistance", "totalTime",
                                      "transfers", "fare" } } ] }

쿼터가 **하루 1,000건**이라 이 파일의 절반은 쿼터를 아끼는 코드다.
  · 좌표를 반올림해 캐시 키로 쓴다 (실거래가 좌표는 동네 대표점이라 재사용률이 높다)
  · 캐시를 디스크에 남겨 재시작해도 유지한다
  · 일일 예산을 넘으면 조용히 None을 돌려주고 호출 측이 자체 엔진으로 폴백한다
"""
from __future__ import annotations
import json
import logging
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date

from transit.config import MAX_TRANSFERS
from pathlib import Path

log = logging.getLogger("gachisaljip.kakao")

ENDPOINT = "https://dapi.kakao.com/v2/routing/publictraffic"
CACHE_PATH = Path(__file__).resolve().parent / "data" / "kakao_cache.json"

#: 하루 쿼터 1,000건에서 여유를 둔 값.
DEFAULT_DAILY_BUDGET = int(os.environ.get("KAKAO_DAILY_BUDGET", "900"))

#: 캐시 키로 쓸 좌표 소수점 자리. 4자리 ≈ 11m.
COORD_PRECISION = 4

#: 재시도하지 않을 응답. 좌표가 문제라 다시 불러도 같은 결과다.
TERMINAL_STATUS = {"STARTNODES_NULL", "ENDNODES_NULL", "EQUAL_POINTS",
                   "INVALID_REQUEST", "NO_RESULTS"}


def _pick_route(routes: list) -> dict | None:
    """환승 MAX_TRANSFERS회 이하 중 가장 빠른 경로.

    조건을 만족하는 게 없으면 환승이 가장 적은 것을 쓴다. 자체 엔진도 같은 상한을
    걸어 두었으므로, 두 출처가 서로 다른 기준으로 경로를 고르는 일이 없게 맞춘다.
    """
    if not routes:
        return None
    t = lambda r: r.get("properties", {}).get("totalTime", 1 << 30)
    x = lambda r: r.get("properties", {}).get("transfers", 99)
    ok = [r for r in routes if x(r) <= MAX_TRANSFERS]
    return min(ok, key=t) if ok else min(routes, key=lambda r: (x(r), t(r)))


@dataclass
class TransitResult:
    total_sec: int
    transfers: int
    fare: int
    mode: str          # BUS | SUBWAY | BUS_AND_SUBWAY
    distance_m: int

    @property
    def minutes(self) -> int:
        return (self.total_sec + 30) // 60


class KakaoTransit:
    def __init__(self, api_key: str | None = None,
                 cache_path: Path = CACHE_PATH,
                 daily_budget: int = DEFAULT_DAILY_BUDGET):
        self.api_key = api_key or os.environ.get("KAKAO_REST_API_KEY")
        self.cache_path = Path(cache_path)
        self.daily_budget = daily_budget
        self._lock = threading.Lock()
        self._cache: dict[str, dict | None] = {}
        self._day = date.today().isoformat()
        self._calls = 0
        self._load_cache()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def remaining(self) -> int:
        self._roll_day()
        return max(0, self.daily_budget - self._calls)

    # ------------------------------------------------------------ 캐시
    def _load_cache(self) -> None:
        if not self.cache_path.exists():
            return
        try:
            blob = json.loads(self.cache_path.read_text(encoding="utf-8"))
            self._cache = blob.get("entries", {})
            if blob.get("day") == self._day:
                self._calls = blob.get("calls", 0)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("카카오 캐시 로드 실패, 새로 시작: %s", exc)

    def _save_cache(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(
                {"day": self._day, "calls": self._calls, "entries": self._cache},
                ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            log.warning("카카오 캐시 저장 실패: %s", exc)

    def _roll_day(self) -> None:
        today = date.today().isoformat()
        if today != self._day:
            self._day, self._calls = today, 0

    @staticmethod
    def _key(origin, dest) -> str:
        p = COORD_PRECISION
        return (f"{origin[0]:.{p}f},{origin[1]:.{p}f}"
                f">{dest[0]:.{p}f},{dest[1]:.{p}f}")

    # ------------------------------------------------------------ 조회
    def travel_time(self, origin: tuple[float, float], dest: tuple[float, float],
                    *, s_name: str = "출발", e_name: str = "도착") -> TransitResult | None:
        """(lat, lon) → (lat, lon) 대중교통 소요시간.

        캐시 미스이고 예산도 남아 있을 때만 실제로 호출한다.
        실패·쿼터초과·경로없음은 전부 None이다. 호출 측이 자체 엔진으로 폴백할 것.
        """
        if not self.enabled:
            return None
        key = self._key(origin, dest)

        with self._lock:
            if key in self._cache:
                hit = self._cache[key]
                return TransitResult(**hit) if hit else None
            self._roll_day()
            if self._calls >= self.daily_budget:
                log.warning("카카오 일일 예산 소진 (%d건)", self._calls)
                return None
            self._calls += 1

        result = self._request(origin, dest, s_name, e_name)
        with self._lock:
            self._cache[key] = vars(result) if result else None
            self._save_cache()
        return result

    def _fetch(self, origin, dest, s_name, e_name) -> dict | None:
        """HTTP 호출 한 번. 파싱하지 않은 원본 JSON을 돌려준다."""
        params = urllib.parse.urlencode({
            "start_x": f"{origin[1]:.7f}", "start_y": f"{origin[0]:.7f}",
            "end_x": f"{dest[1]:.7f}", "end_y": f"{dest[0]:.7f}",
            "s_name": s_name, "e_name": e_name,
        })
        req = urllib.request.Request(
            f"{ENDPOINT}?{params}",
            headers={"Authorization": f"KakaoAK {self.api_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            log.warning("카카오 HTTP %s: %s", exc.code, exc.read()[:200])
            return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            log.warning("카카오 요청 실패: %s", exc)
            return None

    def _request(self, origin, dest, s_name, e_name) -> TransitResult | None:
        payload = self._fetch(origin, dest, s_name, e_name)
        if not payload:
            return None
        status = payload.get("status")
        if status != "OK":
            if status not in TERMINAL_STATUS:
                log.warning("카카오 예상 못한 status: %s", status)
            return None

        best = _pick_route(payload.get("routes") or [])
        if not best:
            return None
        prop = best.get("properties", {})
        fare = prop.get("fare") or {}
        return TransitResult(
            total_sec=int(prop.get("totalTime", 0)),
            transfers=int(prop.get("transfers", 0)),
            fare=int(fare.get("value", 0) if isinstance(fare, dict) else fare or 0),
            mode=str(prop.get("type", "")),
            distance_m=int(prop.get("totalDistance", 0)),
        )

    def raw_route(self, origin: tuple[float, float], dest: tuple[float, float]):
        """가장 빠른 경로의 **원본 route 객체**를 돌려준다(steps 포함).

        travel_time()은 요약만 캐싱하므로 구간별 정류장·폴리라인이 필요할 때는 이쪽을 쓴다.
        상세 화면에서 매물 하나에만 호출되므로 캐시 없이 매번 요청한다.
        """
        if not self.enabled:
            return None
        with self._lock:
            self._roll_day()
            if self._calls >= self.daily_budget:
                log.warning("카카오 일일 예산 소진 (%d건)", self._calls)
                return None
            self._calls += 1
        payload = self._fetch(origin, dest, "집", "직장")
        with self._lock:
            self._save_cache()
        if not payload or payload.get("status") != "OK":
            return None
        return _pick_route(payload.get("routes") or [])

    def stats(self) -> dict:
        self._roll_day()
        return {"enabled": self.enabled, "calls_today": self._calls,
                "budget": self.daily_budget, "remaining": self.remaining,
                "cached": len(self._cache)}
