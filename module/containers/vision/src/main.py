"""vision 컨테이너 진입점 (뼈대)

흐름: 카메라 → 전처리(A) → ONNX Runtime 포즈 추정 → 3D 복원 → KeypointFrame 전송
원칙: 영상은 메모리에서만 처리하고 저장·전송하지 않는다. 밖으로는 좌표만 보낸다.
"""
import os
import socket

from shared.messages import SOCK_VISION_TO_CORE

MODEL_PATH = os.environ.get("POSE_MODEL", "/models/yolo11s-pose-640.onnx")
TRT_CACHE = os.environ.get("TRT_CACHE_DIR", "/cache/trt")


def make_session():
    import onnxruntime as ort  # Jetson 이미지에서만 설치됨
    providers = [
        ("TensorrtExecutionProvider", {"trt_fp16_enable": True, "trt_engine_cache_enable": True,
                                        "trt_engine_cache_path": TRT_CACHE}),
        "CUDAExecutionProvider",
        "CPUExecutionProvider",
    ]
    return ort.InferenceSession(MODEL_PATH, providers=providers)


def main():
    session = make_session()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(SOCK_VISION_TO_CORE)
    # TODO: 카메라 SDK 연결, posture_preprocess 영상 단계 적용, 추론, 깊이 기반 3D 변환
    # TODO: KeypointFrame(...)을 encode()해서 sock.sendall()
    raise NotImplementedError("vision 파이프라인 구현 예정", session, sock)


if __name__ == "__main__":
    main()
