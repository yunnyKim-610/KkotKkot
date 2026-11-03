# telemetry: 공정 단위 통계만 DB(Supabase)로 전송
FROM python:3.10-slim
WORKDIR /app
COPY shared /app/shared
COPY containers/telemetry/src /app/src
RUN useradd -m app
USER app
CMD ["python", "-m", "src.main"]
