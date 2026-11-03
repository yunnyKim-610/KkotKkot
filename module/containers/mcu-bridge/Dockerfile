# mcu-bridge: ESP32-S3 보조 MCU와 UART 통신. 가장 먼저 시작
FROM python:3.10-slim
WORKDIR /app
RUN pip install --no-cache-dir pyserial
COPY shared /app/shared
COPY containers/mcu-bridge/src /app/src
RUN useradd -m app && usermod -aG dialout app
USER app
CMD ["python", "-m", "src.main"]
