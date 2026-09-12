"""전역 설정. 튜닝 파라미터는 전부 여기 모아둔다."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RAW, MANUAL, FEED = DATA / "raw", DATA / "manual", DATA / "feed"

for _d in (RAW, MANUAL, FEED):
    _d.mkdir(parents=True, exist_ok=True)

# --- 도보 ---
WALK_SPEED_MPS = 1.11          # 4.0 km/h
WALK_DETOUR_FACTOR = 1.30      # 직선거리 → 실제 보행거리 보정
MAX_TRANSFER_WALK_M = 400      # 정류장 간 도보 환승 최대 반경
MAX_ACCESS_WALK_M = 900        # 출발지/목적지 ↔ 정류장 최대 도보 반경

# --- 승차 ---
#: 허용 환승 횟수 상한. 탑승 횟수로는 MAX_TRANSFERS + 1 이다.
#: 3회 이상 갈아타는 경로는 실제로 잘 안 쓰이고, 우리 엔진이 가장 부정확한 구간이기도 하다.
#: 제한을 걸면 다익스트라가 "환승 적고 조금 느린" 경로를 대신 찾아 준다.
MAX_TRANSFERS = 2

BOARD_PENALTY_SEC = 50         # 개찰구 통과 등 고정 오버헤드.
                               # 승강장까지의 도보는 route_stops.transfer_sec이 따로 담당하므로
                               # 여기에 환승 통로 시간을 넣으면 이중계상된다.
                               # 표본 11건에서 30~90초 구간 MAE가 1.5~1.8분으로 거의 평평했다.
DWELL_SEC = 25                 # 역당 정차시간.
                               # OA-12034의 '소요시간'은 30초 단위로 떨어지는 순수 주행시간이라
                               # 정차시간이 빠져 있다. 구간마다 이만큼 더해 준다.
SUBWAY_DEFAULT_HEADWAY_SEC = 210   # 출근시간대 3.5분. 노선별 오버라이드는 feeds/subway.py

# --- 피드 파일 ---
STOPS_CSV = FEED / "stops.csv"
ROUTES_CSV = FEED / "routes.csv"
ROUTE_STOPS_CSV = FEED / "route_stops.csv"
TRANSFERS_CSV = FEED / "transfers.csv"
