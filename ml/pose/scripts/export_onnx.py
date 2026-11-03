"""학습한 모델을 ONNX로 내보내기 (입력 640x640 고정 → TensorRT 엔진 재생성 방지)

사용: python ml/pose/scripts/export_onnx.py runs/pose/stage2/weights/best.pt
결과 파일은 Jetson의 /opt/kkotkkot/models/ 로 복사한다 (저장소에는 올리지 않음).
"""
import sys


def main():
    from ultralytics import YOLO
    weights = sys.argv[1]
    YOLO(weights).export(format="onnx", imgsz=640, dynamic=False, simplify=True, opset=17)


if __name__ == "__main__":
    main()
