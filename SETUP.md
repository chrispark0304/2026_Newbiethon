# 로컬 실행

`git pull` 후 **환경변수 파일 두 개를 복사**하면 됩니다. `.env` 자체는 gitignore라 저장소로
전달되지 않지만, 양식(`.env.example`)에 팀 공용 키가 들어 있어 값을 따로 채울 필요는 없습니다.

## 1. 백엔드

```bash
pip install -r api/requirements.txt

cp api/.env.example api/.env      # 키가 이미 들어 있습니다

uvicorn api.main:app --port 8000
```

확인: http://127.0.0.1:8000/api/health → `{"ok": true, "listings": 8317, ...}`
문서: http://127.0.0.1:8000/docs

## 2. 프론트엔드

```bash
cp Frontend/.env.example Frontend/.env.local   # 키가 이미 들어 있습니다

cd Frontend
npm install
npx vite --port 8443 --host localhost
```

→ http://localhost:8443

> ⚠️ **포트 8443, 주소는 `localhost`** 여야 합니다.
> 카카오 콘솔에 그 도메인만 등록돼 있어서, 5173으로 띄우거나 `127.0.0.1`로 접속하면
> 지도가 `AccessDeniedError`로 뜨지 않습니다. 다른 포트를 쓰려면 카카오 개발자 콘솔 >
> 내 애플리케이션 > 플랫폼 > Web > 사이트 도메인에 먼저 추가하세요.

## 키 두 개는 서로 다릅니다

| | 어디에 | 용도 |
|---|---|---|
| **REST API 키** | `api/.env` | 대중교통 경로 조회, 주소 지오코딩 (서버에서만 사용) |
| **JavaScript 키** | `Frontend/.env.local` | 지도 타일, 장소검색 자동완성 (브라우저에 노출됨) |

카카오 개발자 콘솔의 같은 애플리케이션 안에 둘 다 있습니다.

> 해커톤 편의상 두 키를 `.env.example`에 그대로 넣어 뒀습니다.
> 저장소가 공개면 키도 공개된 상태이니, **행사가 끝나면 콘솔에서 재발급**하세요.

## 자주 겪는 증상

| 증상 | 원인 |
|---|---|
| 매물이 0건, "서버에 연결할 수 없어요" | 백엔드가 안 떠 있음 |
| 지도만 안 뜸 (목록은 정상) | JS 키 없음, 또는 포트/도메인 불일치 |
| 상세 화면 경로가 "engine"으로 표시 | REST 키 없음 → 자체 엔진 폴백 (지하철만, 동작은 함) |
| 검색은 되는데 통근시간이 이상 | `api/data/address_coords.json` 누락 — 저장소에 있어야 정상 |

`.env` 값을 바꾸면 **양쪽 다 재시작**해야 합니다. Vite도 HMR로는 안 잡습니다.
