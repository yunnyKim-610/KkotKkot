# ml: 모델 학습

메인 모델은 **YOLO11s-pose** 하나다. 학습 5단계(수집 → 라벨링 → 분할 → 2단계 미세조정 → 오류 분석)와
검증 4단계(오프라인 정확도 → 각도 실측 → 로봇 탑재 성능 → 현장 섀도 운영)를 따른다.

```
ml/
├── pose/configs/data.yaml    데이터셋 정의 (COCO-17, flip_idx)
├── pose/configs/train.yaml   하이퍼파라미터 (2단계 학습, 배포 conf)
├── pose/scripts/train.py     2단계 미세조정
├── pose/scripts/export_onnx.py  ONNX 내보내기 (640 고정)
└── datasets/                 실제 데이터 (git 제외)
```

- 데이터 분할은 이미지가 아니라 **촬영 세션·사람·장소 단위**로 한다.
- 이미지·가중치(.pt/.onnx/.engine)는 저장소에 올리지 않는다.
