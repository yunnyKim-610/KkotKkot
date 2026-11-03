"""YOLOE 3가지 프롬프트 모드 실습.

    python yoloe_demo.py text   --classes person bus glasses
    python yoloe_demo.py visual                      # 예시 박스 사용
    python yoloe_demo.py visual --select             # 마우스로 박스 직접 그리기
    python yoloe_demo.py free

결과 이미지는 runs/segment/predict*/ 에 저장된다.
"""
import argparse
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLOE
from ultralytics.models.yolo.yoloe import YOLOEVPSegPredictor

SAMPLE_URL = "https://ultralytics.com/images/bus.jpg"


def load_source(source):
    """URL이면 내려받아 로컬 경로로 바꾼다 (visual 모드의 박스 선택에 필요)."""
    if source.startswith("http"):
        path = Path(source).name
        if not Path(path).exists():
            urllib.request.urlretrieve(source, path)
        return path
    return source


def print_results(results):
    r = results[0]
    names = r.names
    print(f"\n검출 {len(r.boxes)}개")
    for cls, conf, box in zip(r.boxes.cls, r.boxes.conf, r.boxes.xyxy):
        print(f"  {names[int(cls)]:<20} conf={conf:.2f}  box={box.int().tolist()}")
    print(f"저장 위치: {r.save_dir}")


# 1) 텍스트 프롬프트: 찾고 싶은 클래스 이름을 글자로 지정
def run_text(args):
    model = YOLOE("yoloe-11s-seg.pt")
    names = args.classes
    # 텍스트 인코더(MobileCLIP)로 클래스 이름을 임베딩해 모델의 분류 헤드에 심는다
    model.set_classes(names, model.get_text_pe(names))
    results = model.predict(args.source, conf=args.conf, save=True)
    print_results(results)


# 2) 이미지(비주얼) 프롬프트: 이미지 안의 예시 물체를 박스로 지정
def run_visual(args):
    source = load_source(args.source)
    refer = load_source(args.refer) if args.refer else None
    model = YOLOE("yoloe-11s-seg.pt")

    if args.select:
        # 참조 이미지가 있으면 거기에, 없으면 source에 박스를 그린다
        img = cv2.imread(refer or source)
        print("마우스로 박스를 그리고 Enter/Space, 다 그렸으면 Esc")
        rois = cv2.selectROIs("draw prompt boxes", img)
        cv2.destroyAllWindows()
        if len(rois) == 0:
            print("박스를 그리지 않아 종료합니다.")
            return
        bboxes = np.array([[x, y, x + w, y + h] for x, y, w, h in rois], dtype=float)
        cls = np.arange(len(bboxes))  # 박스마다 다른 클래스로 취급
    else:
        # bus.jpg 기준 예시: 사람 1명(클래스 0), 안경(클래스 1)
        bboxes = np.array([[221.52, 405.8, 344.98, 857.54],
                           [120, 425, 160, 445]])
        cls = np.array([0, 1])

    visual_prompts = dict(bboxes=bboxes, cls=cls)
    # refer_image를 주면 "그 이미지의 박스"를 프롬프트로 삼아 source에서 찾는다
    results = model.predict(
        source,
        visual_prompts=visual_prompts,
        predictor=YOLOEVPSegPredictor,
        refer_image=refer,
        conf=args.conf,
        save=True,
    )
    print_results(results)


# 3) 프롬프트 프리: 프롬프트 없이 내장 어휘(약 4,500개 클래스)로 전부 찾기
def run_free(args):
    model = YOLOE("yoloe-11s-seg-pf.pt")
    results = model.predict(args.source, conf=args.conf, save=True)
    print_results(results)


def main():
    p = argparse.ArgumentParser(description="YOLOE prompt mode demo")
    p.add_argument("mode", choices=["text", "visual", "free"])
    p.add_argument("--source", default=SAMPLE_URL, help="이미지/영상 경로 또는 URL, 웹캠은 0")
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--classes", nargs="+", default=["person", "bus", "glasses"],
                   help="[text] 찾을 클래스 이름들")
    p.add_argument("--select", action="store_true", help="[visual] 박스를 마우스로 직접 지정")
    p.add_argument("--refer", default=None, help="[visual] 프롬프트 박스가 있는 참조 이미지")
    args = p.parse_args()

    {"text": run_text, "visual": run_visual, "free": run_free}[args.mode](args)


if __name__ == "__main__":
    main()
