"""실시간 실행 예시: 웹캠/영상 → 전처리 파이프라인 → 상태 표시, 키포인트만 저장(선택)

사용법
  python run_realtime.py                       # 웹캠 0번
  python run_realtime.py --source video.mp4    # 영상 파일
  python run_realtime.py --save session01.npz  # 키포인트·특징 저장 (원본 영상은 저장 안 함, 9-1)
  키: q 종료 / c 재캘리브레이션
"""
import argparse
import time
import cv2
import numpy as np
from posture_preprocess import PosturePipeline
from posture_preprocess.backends import YoloPoseBackend
from posture_preprocess.features import FEATURE_NAMES


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="0")
    ap.add_argument("--weights", default="yolov8n-pose.pt")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--save", default=None)
    ap.add_argument("--no-display", action="store_true")
    args = ap.parse_args()

    src = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise SystemExit(f"입력을 열 수 없습니다: {args.source}")
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    file_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    is_file = not isinstance(src, int)

    pipe = PosturePipeline(YoloPoseBackend(args.weights, args.imgsz), (w, h))
    log = {"t": [], "raw_kpts": [], "raw_conf": [], "features": []}
    idx, t0 = 0, time.monotonic()

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = idx / file_fps if is_file else time.monotonic() - t0
        idx += 1
        r = pipe.process(frame, t)
        if r is None:
            continue
        if args.save:
            log["t"].append(t)
            log["raw_kpts"].append(r["raw_kpts"])
            log["raw_conf"].append(r["raw_conf"])
            log["features"].append([r["features"][k] for k in FEATURE_NAMES])
        if r.get("alert"):
            print(f"[{t:7.1f}s] 자세 알림: 흐트러진 자세가 {r['bad_duration']:.0f}초 지속")
        if args.no_display:
            continue
        vis = r["frame"]
        if r["roi"] is not None:
            x1, y1, x2, y2 = r["roi"]
            cv2.rectangle(vis, (x1, y1), (x2, y2), (255, 200, 0), 2)
        for x, y in r["kpts"]:
            if not np.isnan(x):
                cv2.circle(vis, (int(x), int(y)), 3, (0, 255, 255), -1)
        if r["status"] == "calibrating":
            text, color = f"CALIBRATING {r['calib_progress'] * 100:.0f}% - sit straight", (255, 255, 255)
        else:
            ratio = "-" if r["bad_ratio"] is None else f"{r['bad_ratio']:.2f}"
            text = f"{r['state'].upper()}  ratio={ratio}  bad={r['bad_duration']:.0f}s"
            color = (0, 0, 255) if r["state"] == "bad" else (0, 200, 0)
        cv2.putText(vis, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        cv2.imshow("posture", vis)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("c"):
            pipe.recalibrate()

    cap.release()
    cv2.destroyAllWindows()
    if args.save and log["t"]:
        np.savez(args.save, t=np.array(log["t"]), raw_kpts=np.array(log["raw_kpts"]),
                 raw_conf=np.array(log["raw_conf"]), features=np.array(log["features"]),
                 feature_names=np.array(FEATURE_NAMES))
        print(f"저장 완료: {args.save} ({len(log['t'])} 프레임)")


if __name__ == "__main__":
    main()
