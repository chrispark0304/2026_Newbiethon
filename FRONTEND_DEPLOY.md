# 프론트엔드 Vercel 배포 안내

백엔드는 이미 떠 있습니다: **https://gachisaljip-api.onrender.com**

## 1. Vercel 프로젝트 설정

이 저장소는 모노레포라 **Root Directory를 반드시 지정**해야 합니다.

| 항목 | 값 |
|---|---|
| **Root Directory** | `Frontend` ← 이걸 빼면 빌드가 실패합니다 |
| Framework Preset | Vite |
| Build Command | `npm run build` (기본값) |
| Output Directory | `dist` (기본값) |
| Install Command | `npm install` (기본값) |

## 2. 환경변수 (Settings → Environment Variables)

**두 값 모두 빌드 시점에 번들로 들어갑니다.** 나중에 값만 바꾸면 반영되지 않고,
반드시 **재배포(Redeploy)** 해야 합니다.

| 키 | 값 |
|---|---|
| `VITE_API_BASE` | `https://gachisaljip-api.onrender.com` |
| `VITE_KAKAO_JS_KEY` | `fd961237305b08edd8ed4700fe6ed248` |

`VITE_API_BASE`를 안 넣으면 `http://127.0.0.1:8000`(각자 노트북)으로 요청이 가서
매물이 하나도 안 뜹니다.

## 3. 배포 후 — 이 두 가지를 안 하면 화면이 비어 보입니다

### (a) 카카오 콘솔에 도메인 등록 → 지도가 뜹니다

카카오 개발자 콘솔 > 내 애플리케이션 > **플랫폼 > Web > 사이트 도메인**에 추가:

```
https://<프로젝트명>.vercel.app
```

빠지면 지도 타일이 `AccessDeniedError`로 막힙니다. 목록·통근시간은 정상이라
"지도만 안 나오는" 상태가 됩니다.

> Vercel은 배포마다 프리뷰 URL(`<프로젝트명>-<해시>.vercel.app`)을 새로 만드는데,
> 그건 매번 등록할 수 없습니다. **프로덕션 도메인으로만 데모하세요.**

### (b) 백엔드 CORS 허용 → 데이터가 뜹니다

Render 대시보드 > 이 서비스 > Environment 에서:

```
CORS_ORIGINS = https://<프로젝트명>.vercel.app
```

로컬 개발도 계속 할 거면 쉼표로 이어 붙입니다:

```
CORS_ORIGINS = https://<프로젝트명>.vercel.app,http://localhost:8443
```

값을 넣는 순간 기본값(localhost)은 **대체**되므로, 로컬 주소가 필요하면 같이 적어야 합니다.
저장하면 Render가 자동 재시작합니다(재배포 불필요).

**배포 주소가 나오면 알려주세요. CORS는 이쪽에서 설정하겠습니다.**

## 4. 확인

| 증상 | 원인 |
|---|---|
| 매물 0건 + "서버에 연결할 수 없어요" | `VITE_API_BASE` 미설정, 또는 CORS 미등록 |
| 지도만 안 뜸 (목록은 정상) | 카카오 콘솔에 Vercel 도메인 미등록 |
| 첫 요청이 30초~1분 | Render 무료 플랜 콜드 스타트. 정상입니다 |

브라우저 콘솔(F12)에 `AccessDeniedError`면 (a), `CORS policy`면 (b) 문제입니다.

## 5. 데모 직전 체크

Render 무료 플랜은 15분 유휴 시 잠듭니다. **발표 5분 전에 한 번 깨워 두세요.**

```
https://gachisaljip-api.onrender.com/api/health
```
