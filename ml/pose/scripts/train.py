"""YOLO11s-pose 2단계 미세조정

사용: python ml/pose/scripts/train.py --data ml/pose/configs/data.yaml
주의: Ultralytics는 AGPL-3.0. 상용 배포 전 라이선스 결정 필요 (docs/decisions.md 참고)
"""
import argparse
from pathlib import Path

import yaml


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="ml/pose/configs/data.yaml")
    ap.add_argument("--cfg", default="ml/pose/configs/train.yaml")
    ap.add_argument("--project", default="runs/pose")
    args = ap.parse_args()

    from ultralytics import YOLO  # 학습 환경에서만 설치
    cfg = yaml.safe_load(Path(args.cfg).read_text(encoding="utf-8"))
    common = dict(cfg["common"])
    model_name = common.pop("model")

    stage1 = YOLO(model_name).train(data=args.data, project=args.project, name="stage1",
                                    **common, **cfg["stage1"])
    best1 = Path(stage1.save_dir) / "weights" / "best.pt"
    YOLO(str(best1)).train(data=args.data, project=args.project, name="stage2",
                           **common, **cfg["stage2"])


if __name__ == "__main__":
    main()
