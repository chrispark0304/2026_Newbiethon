# 백엔드 컨테이너.
#
# 매물 CSV·지오코딩 캐시·노선망이 모두 저장소에 들어 있어 외부 의존이 없다.
# 기동 0.2초 / RSS 41MB라 가장 작은 인스턴스로도 충분하다.
FROM python:3.12-slim

WORKDIR /app

# 의존성을 먼저 넣어 소스만 바뀔 때 레이어 캐시가 살아 있게 한다.
COPY api/requirements.txt ./api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

# 런타임에 필요한 것만 넣는다. Frontend/·.git/ 등은 .dockerignore가 막는다.
COPY api ./api
COPY transit ./transit
COPY rtms_연립다세대_전월세_서울_202608.csv ./

# 그래프·매물을 미리 한 번 올려 보고, 못 읽는 파일이 있으면 빌드에서 바로 실패시킨다.
RUN python -c "import api.listings, transit.graph; print('데이터 로드 OK')"

ENV PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8000

# PORT는 플랫폼이 주입한다(Fly·Railway·Render 공통).
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
