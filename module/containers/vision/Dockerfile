# vision: 카메라 영상 → 포즈 추정 → 3D 복원. 영상을 다루는 유일한 컨테이너 (네트워크 차단)
# TODO: 호스트 JetPack 버전과 맞는 태그로 바꾸고, 배포 시에는 digest(@sha256:...)로 고정
ARG L4T_IMAGE=nvcr.io/nvidia/l4t-jetpack:r36.4.0
FROM ${L4T_IMAGE}
WORKDIR /app
COPY libs/posture_preprocess/requirements.txt /tmp/req.txt
RUN pip3 install --no-cache-dir -r /tmp/req.txt
# TODO: JetPack용 onnxruntime-gpu 휠 설치 (TensorRT 실행 공급자 포함 빌드)
COPY shared /app/shared
COPY libs/posture_preprocess/posture_preprocess /app/posture_preprocess
COPY containers/vision/src /app/src
RUN useradd -m app
USER app
CMD ["python3", "-m", "src.main"]
