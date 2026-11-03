# core: UWB-사람 매칭, 자세 판정, 알림 결정 (GPU 미사용)
FROM python:3.10-slim
WORKDIR /app
COPY libs/posture_preprocess/requirements.txt /tmp/req.txt
RUN pip install --no-cache-dir numpy
COPY shared /app/shared
COPY libs/posture_preprocess/posture_preprocess /app/posture_preprocess
COPY containers/core/src /app/src
RUN useradd -m app
USER app
CMD ["python", "-m", "src.main"]
