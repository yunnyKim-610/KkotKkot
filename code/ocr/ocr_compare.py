"""무료 OCR 모델 비교 실습.

한 이미지를 여러 OCR 엔진으로 인식하고 결과를 나란히 비교한다.
  - EasyOCR   : PyTorch 기반 CRAFT(검출) + CRNN(인식). pip 설치만으로 동작
  - RapidOCR  : PaddleOCR(PP-OCRv5) 모델을 ONNX Runtime으로 실행. 가볍고 빠름
  - Tesseract : 전통적인 LSTM 엔진. 별도 프로그램 설치 시에만 사용
                (https://github.com/UB-Mannheim/tesseract/wiki , 한국어 데이터 kor 체크)

엔진마다 박스를 그린 이미지, 인식 텍스트, 처리 시간을 저장하고
정답 텍스트(--gt)를 주면 CER(문자 오류율)도 계산한다.

사용 예:
  py ocr_compare.py --make-sample                      # 정답을 아는 테스트 이미지 생성 후 비교
  py ocr_compare.py --image sign.jpg                   # 내 이미지로 비교
  py ocr_compare.py --image sign.jpg --gt "출입금지 KEEP OUT" --engines easyocr rapidocr
"""

import argparse
import csv
import shutil
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = ["C:/Windows/Fonts/malgun.ttf", "/System/Library/Fonts/AppleSDGothicNeo.ttc",
                   "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"]
SAMPLE_LINES = ["피지컬 AI 실습", "OCR Test 2026-10-12", "로봇 작업 구역 출입 금지", "Battery: 87% / Temp 36.5C"]

for font in ("Malgun Gothic", "AppleGothic", "NanumGothic"):
    if any(font == f.name for f in matplotlib.font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = font
        break
plt.rcParams["axes.unicode_minus"] = False


def load_font(size):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def make_sample(path):
    """정답을 아는 테스트 이미지를 만든다 (약간의 회전·노이즈로 실제 사진처럼)."""
    img = Image.new("RGB", (900, 420), "#f3efe6")
    draw = ImageDraw.Draw(img)
    for i, (line, size) in enumerate(zip(SAMPLE_LINES, (56, 40, 44, 36))):
        draw.text((40, 30 + i * 95), line, fill="#1d1d1b", font=load_font(size))
    img = img.rotate(2, expand=False, fillcolor="#f3efe6")
    arr = np.asarray(img).astype(np.int16)
    arr += np.random.default_rng(0).normal(0, 12, arr.shape).astype(np.int16)
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(path)
    return " ".join(SAMPLE_LINES)


# ---------------- 엔진별 래퍼: 모두 [(box(4점), text, score), ...] 형태로 반환 ----------------

def build_easyocr():
    import easyocr
    reader = easyocr.Reader(["ko", "en"], gpu=False, verbose=False)

    def run(path):
        return [(np.array(box), text, float(score)) for box, text, score in reader.readtext(str(path))]
    return run


def build_rapidocr():
    from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR
    # 한국어 인식 모델은 PP-OCRv5 mobile만 제공된다 (검출 모델은 기본값 사용)
    engine = RapidOCR(params={"Rec.lang_type": LangRec.KOREAN, "Rec.ocr_version": OCRVersion.PPOCRV5,
                              "Rec.model_type": ModelType.MOBILE, "Global.log_level": "error"})

    def run(path):
        out = engine(str(path))
        if out.boxes is None:
            return []
        return [(np.array(b), t, float(s)) for b, t, s in zip(out.boxes, out.txts, out.scores)]
    return run


def build_tesseract():
    import pytesseract
    if not shutil.which("tesseract"):
        default = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
        if not default.exists():
            raise RuntimeError("tesseract 실행 파일이 없습니다 (설치 후 다시 시도)")
        pytesseract.pytesseract.tesseract_cmd = str(default)
    langs = "kor+eng" if "kor" in pytesseract.get_languages() else "eng"

    def run(path):
        d = pytesseract.image_to_data(Image.open(path), lang=langs, output_type=pytesseract.Output.DICT)
        # 단어 단위 결과를 줄 단위로 묶는다
        lines = {}
        for i, word in enumerate(d["text"]):
            if not word.strip() or float(d["conf"][i]) < 0:
                continue
            key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
            lines.setdefault(key, []).append(i)
        results = []
        for idx in lines.values():
            x0 = min(d["left"][i] for i in idx)
            y0 = min(d["top"][i] for i in idx)
            x1 = max(d["left"][i] + d["width"][i] for i in idx)
            y1 = max(d["top"][i] + d["height"][i] for i in idx)
            text = " ".join(d["text"][i] for i in idx)
            score = np.mean([float(d["conf"][i]) for i in idx]) / 100
            results.append((np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]), text, score))
        return results
    return run


ENGINES = {"easyocr": build_easyocr, "rapidocr": build_rapidocr, "tesseract": build_tesseract}


# ---------------- 평가 · 시각화 ----------------

def cer(pred, gt):
    """문자 오류율 = 편집거리 / 정답 길이 (공백 무시)."""
    p, g = pred.replace(" ", ""), gt.replace(" ", "")
    dp = list(range(len(g) + 1))
    for i in range(1, len(p) + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, len(g) + 1):
            prev, dp[j] = dp[j], min(dp[j] + 1, dp[j - 1] + 1, prev + (p[i - 1] != g[j - 1]))
    return dp[len(g)] / max(len(g), 1)


def sort_reading_order(results):
    # 위→아래, 같은 줄이면 왼→오른쪽
    return sorted(results, key=lambda r: (round(r[0][:, 1].mean() / 20), r[0][:, 0].min()))


def draw_results(path, results, out_path):
    img = Image.open(path).convert("RGB")
    draw = ImageDraw.Draw(img)
    font = load_font(max(14, img.height // 30))
    for box, text, score in results:
        pts = [tuple(map(float, p)) for p in box]
        draw.polygon(pts, outline="#e8533a", width=3)
        draw.text((pts[0][0], pts[0][1] - font.size - 2), f"{text} ({score:.2f})", fill="#1f6fd1", font=font)
    img.save(out_path)


def plot_summary(rows, out_path, has_gt):
    names = [r["engine"] for r in rows]
    panels = [("time_s", "처리 시간 (초, 낮을수록 좋음)")]
    if has_gt:
        panels.append(("cer", "CER 문자 오류율 (낮을수록 좋음)"))
    fig, axes = plt.subplots(1, len(panels), figsize=(5 * len(panels), 3.2))
    for ax, (key, title) in zip(np.atleast_1d(axes), panels):
        vals = [r[key] for r in rows]
        bars = ax.barh(names, vals, color="#3987e5", height=0.5)
        ax.bar_label(bars, fmt="%.3f", padding=3)
        ax.set_title(title, fontsize=11, loc="left")
        ax.spines[["top", "right"]].set_visible(False)
        ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", help="인식할 이미지 경로")
    ap.add_argument("--gt", help="정답 텍스트 (주면 CER 계산)")
    ap.add_argument("--make-sample", action="store_true", help="테스트 이미지를 생성해서 사용")
    ap.add_argument("--engines", nargs="+", default=list(ENGINES), choices=list(ENGINES))
    ap.add_argument("--out", default="runs/ocr")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.make_sample:
        image = out / "sample.png"
        args.gt = args.gt or make_sample(image)
    elif args.image:
        image = Path(args.image)
    else:
        ap.error("--image 또는 --make-sample 중 하나를 지정하세요.")

    rows = []
    for name in args.engines:
        print(f"\n===== {name} =====")
        try:
            run = ENGINES[name]()          # 모델 로딩 (첫 실행 시 가중치 다운로드)
            run(image)                     # 워밍업: 처리 시간 측정에서 초기화 비용 제외
            t0 = time.perf_counter()
            results = sort_reading_order(run(image))
            elapsed = time.perf_counter() - t0
        except Exception as e:
            print(f"  건너뜀: {e}")
            continue

        text = " ".join(t for _, t, _ in results)
        for _, t, s in results:
            print(f"  [{s:.2f}] {t}")
        row = {"engine": name, "time_s": round(elapsed, 3), "boxes": len(results),
               "mean_score": round(float(np.mean([s for *_, s in results])) if results else 0, 3), "text": text}
        if args.gt:
            row["cer"] = round(cer(text, args.gt), 3)
            print(f"  CER = {row['cer']:.3f}")
        print(f"  시간 = {elapsed:.3f}s")
        draw_results(image, results, out / f"{name}.png")
        rows.append(row)

    if not rows:
        raise SystemExit("실행된 엔진이 없습니다.")
    with open(out / "summary.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    plot_summary(rows, out / "summary.png", bool(args.gt))

    print("\n===== 요약 =====")
    if args.gt:
        print(f"  정답: {args.gt}")
    for r in rows:
        extra = f"  CER {r['cer']:.3f}" if "cer" in r else ""
        print(f"  {r['engine']:<10} {r['time_s']:.3f}s  박스 {r['boxes']:>2}{extra}")
    print(f"\n결과 저장: {out.resolve()}")


if __name__ == "__main__":
    main()
