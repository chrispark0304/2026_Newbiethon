# 백엔드 배포

기동 0.2초 · RSS 41MB · 이미지 약 5.6MB(데이터 포함)라 가장 작은 인스턴스로 충분하다.
매물 CSV·지오코딩 캐시·노선망이 전부 저장소에 있어 외부 스토리지가 필요 없다.

## 왜 서버리스가 아니라 상시 프로세스인가

기동이 빨라 Lambda/Vercel Functions에서도 "돌긴" 한다. 문제는 두 가지다.

- 요청마다 컨테이너가 새로 뜨면 4MB 데이터를 매번 읽는다.
- **카카오 쿼터 카운터(`api/data/kakao_cache.json`)가 인스턴스마다 따로 논다.**
  하루 1,000건 제한을 넘겨도 아무도 모른다.

상시 프로세스 하나가 훨씬 단순하고 싸다.

## Render (현재 설정)

`render.yaml` 이 있으므로 대시보드에서 저장소만 연결하면 된다. CLI가 필요 없다.

1. https://dashboard.render.com → **New** → **Blueprint**
2. GitHub 저장소(`2026_Newbiethon`) 연결 → `render.yaml` 자동 인식
3. **Environment** 에서 값 두 개 입력
   - `KAKAO_REST_API_KEY` — 카카오 REST 키
   - `CORS_ORIGINS` — 프론트 배포 도메인 (아직 없으면 나중에)
4. **Apply** → 빌드·배포 → `https://gachisaljip-api.onrender.com` 발급

확인:

```bash
curl https://<발급된주소>/api/health
# {"ok": true, "listings": 8317, ...}
```

`main` 에 push 하면 자동으로 재배포된다(`autoDeploy: true`).

### 무료 플랜의 제약

**15분 동안 요청이 없으면 잠들고, 깨어나는 데 30초~1분 걸린다.**
심사위원이 처음 눌렀을 때 멈춘 것처럼 보일 수 있으니, 발표 직전에 한 번 호출해
깨워 두는 것이 안전하다.

```bash
curl https://<발급된주소>/api/health    # 발표 5분 전
```

상시 가동이 필요하면 Starter 플랜(유료)이나 아래 Fly.io를 쓴다.

## Fly.io (대안)

```bash
brew install flyctl            # 또는 curl -L https://fly.io/install.sh | sh
fly auth login

fly launch --no-deploy         # 앱 생성. fly.toml 의 app 이름을 본인 것으로 맞춘다
fly secrets set KAKAO_REST_API_KEY=...
fly deploy

fly open /api/health           # {"ok": true, "listings": 8317, ...}
fly logs
```

프론트를 배포한 뒤 출처를 좁힌다:

```bash
fly secrets set CORS_ORIGINS=https://your-app.pages.dev
```

## 다른 선택지

| | 비고 |
|---|---|
| **Railway** | `railway up`. Dockerfile 자동 인식. 무료 크레딧 소진 후 유료 |
| **Render** | 무료 티어는 15분 유휴 후 잠들고 깨는 데 30초~1분. 데모 중 멈춘 것처럼 보인다 |
| **Cloud Run** | `gcloud run deploy --source .` 로 바로 된다. 최소 인스턴스 1로 둘 것 |

## 배포 전 체크리스트

- [ ] `fly secrets set KAKAO_REST_API_KEY=...` — 없으면 지오코딩 503, 통근은 자체 엔진으로 폴백
- [ ] `CORS_ORIGINS` 에 프론트 도메인 (안 넣으면 로컬 주소만 허용돼 브라우저에서 막힌다)
- [ ] 카카오 콘솔 > 플랫폼 > Web 에 **프론트 배포 도메인** 등록 (지도 타일용)
- [ ] 프론트 `VITE_API_BASE` 를 배포된 백엔드 주소로

## 카카오 쿼터가 실질적 제약이다

대중교통 경로 조회는 **하루 1,000건**이고 배포하면 전 사용자가 나눠 쓴다.
상세 화면 진입마다 2건이라 하루 500명이 한 번씩만 봐도 소진된다.

- `KAKAO_DAILY_BUDGET` (기본 900) 소진 시 자동으로 자체 엔진 폴백 — 서비스는 죽지 않는다
- 공개 배포라면 `COMMUTE_PROVIDER=engine` 으로 두고 카카오를 아예 안 쓰는 것도 방법이다
  (버스 미포함, 실측 대비 평균 +5분)

## 캐시는 재시작하면 날아간다

`api/data/kakao_cache.json` 은 컨테이너 파일시스템에 쓰므로 재배포·재시작 시 사라진다.
기능상 문제는 없고(캐시일 뿐) 쿼터 카운터가 리셋될 뿐이다. 유지하려면 Fly 볼륨을 붙인다:

```bash
fly volumes create data --size 1 --region nrt
```
```toml
[[mounts]]
  source = "data"
  destination = "/app/api/data"
```
