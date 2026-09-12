# 같이살집 Frontend

React + TypeScript + Vite로 만든 간단한 반응형 MVP 화면입니다. Backend 파일과 공통 API 계약은 포함하거나 수정하지 않습니다.

## 실행

Node.js 22.12 이상을 사용하세요.

```sh
cd frontend
npm install
npm run dev
```

첫 화면의 **예시 결과 보기**는 개발 가이드의 고정 응답 1건을 보여줍니다. 추천 알고리즘이나 실제 API 호출이 아니며 입력값을 반영하지 않습니다. 실제 입력 흐름의 **추천받기**는 반드시 Backend를 호출합니다. 실패 시 예시 결과로 대체하지 않습니다.

## Backend 연결

`.env.example`을 `.env`로 복사하고 `API_PROXY_TARGET`을 Backend 주소로 설정하세요. 기본값은 `http://localhost:8000`입니다. 환경변수 변경 후 개발 서버를 다시 실행하세요.

- 호출 위치: `src/api/houseApi.ts`
- 엔드포인트: `POST /api/match`
- 타입: `src/types.ts`, 제공된 가이드의 Request / Response 필드 유지
- 예산: 원, 이동시간: 분, 방 면적: ㎡
- 점수, 공평성 패널티, 월세 분담, 생활 궁합 및 추천 이유는 Backend 응답을 그대로 표시
- TOP 3 선정과 순서는 Backend가 결정하며, Frontend는 반환된 목록을 표시

가이드에 확정되지 않은 입력 범위는 UI에서 중요도·빈도 1~5, 취침 `early/normal/late`, 온도 `cool/normal/warm`으로 가정했습니다. Backend 담당자와 합의한 뒤 연결하세요. `stationDistance`는 도보 분으로 표시하므로 단위를 확인해야 합니다. `roomA/roomB`는 방 식별자이며 사용자 배정을 의미하지 않습니다.

공통 API 문서는 담당자와 협의해 별도로 작성하세요. 현재 Frontend가 새로운 공통 계약을 확정하지는 않습니다. 에러 응답 body에 의존하지 않고 HTTP 상태로 메시지를 표시합니다.

## 빌드 및 배포

```sh
npm run build
npm run preview
```

배포 대상은 `frontend/dist`입니다. Vite 개발 프록시는 배포 환경에서 동작하지 않습니다. 배포 시 `/api`를 Backend로 연결하거나 빌드 전에 `VITE_API_BASE_URL`에 Backend origin을 설정하세요. 별도 origin이면 Backend CORS 허용이 필요합니다. `VITE_` 환경변수에는 비밀값을 넣지 마세요.

## GitHub 업로드

프로젝트 루트에서 실행합니다. 먼저 `git status`로 포함할 파일을 확인하세요. 아래 URL은 실제 팀 저장소 주소로 바꾸세요. 기존 팀 저장소라면 먼저 팀 브랜치와 연결 방식을 확인하세요.

```sh
git add .gitignore frontend
git commit -m "feat: add initial frontend for house matching"
git remote add origin https://github.com/YOUR_TEAM/YOUR_REPOSITORY.git
git push -u origin codex/frontend
```

이미 origin이 등록되어 있으면 `git remote add`를 생략하세요. GitHub에서 팀의 기본 브랜치를 대상으로 Pull Request를 생성하세요. main에 직접 개발하거나 강제 push하지 마세요.

## 수동 확인

- 모바일과 데스크톱에서 시작 → A 조건 → B 조건 → 생활패턴 이동
- 빈 이름/목적지, 0 이하 예산/이동시간 제출 차단
- 이전 단계 이동 시 입력 유지
- 추천 요청 중 로딩 및 중복 클릭 방지
- Backend 미실행, 400/422, 500, 20초 초과 시 오류 표시 및 재시도
- 실제 API의 TOP 3, 만족도, 이동시간, 이유와 상세 방별 분담 표시
- 생활 궁합 및 경고 표시, 빈 추천 목록 표시
- 예시 결과와 실제 추천 구분
