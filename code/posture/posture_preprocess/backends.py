"""포즈 추정 백엔드. 모델을 바꾸려면 Person 리스트를 반환하는 callable만 새로 만들면 됩니다."""
from dataclasses import dataclass
import numpy as np


@dataclass
class Person:
    box: np.ndarray      # (4,) x1, y1, x2, y2 [px]
    score: float         # 사람 검출 신뢰도
    kpts: np.ndarray     # (17, 2) COCO-17 키포인트 [px]
    kconf: np.ndarray    # (17,) 키포인트 신뢰도


class YoloPoseBackend:
    """Ultralytics YOLO pose (COCO-17). Jetson/PC 권장. 라즈베리파이는 imgsz=320 권장."""

    def __init__(self, weights="yolov8n-pose.pt", imgsz=640, device=None):
        from ultralytics import YOLO  # 지연 import
        self.model = YOLO(weights)
        self.imgsz = imgsz
        self.device = device

    def __call__(self, frame):
        r = self.model(frame, imgsz=self.imgsz, device=self.device, verbose=False)[0]
        if r.keypoints is None or r.boxes is None or len(r.boxes) == 0:
            return []
        boxes = r.boxes.xyxy.cpu().numpy()
        scores = r.boxes.conf.cpu().numpy()
        kxy = r.keypoints.xy.cpu().numpy()
        kc = r.keypoints.conf
        kc = kc.cpu().numpy() if kc is not None else np.ones(kxy.shape[:2], dtype=np.float32)
        return [Person(boxes[i], float(scores[i]), kxy[i].astype(np.float64), kc[i].astype(np.float64))
                for i in range(len(boxes))]
