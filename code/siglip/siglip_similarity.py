"""SigLIP 이미지-텍스트 유사도 분석.

이미지와 텍스트를 각각 임베딩하고 두 가지 지표를 계산해 그래프와 CSV로 저장한다.
  - 코사인 유사도: L2 정규화된 임베딩의 내적 (-1 ~ 1)
  - SigLIP 시그모이드 확률: sigmoid(cos * exp(logit_scale) + logit_bias)
    SigLIP은 softmax가 아니라 쌍마다 독립적인 시그모이드로 학습되므로
    한 이미지에 대해 여러 텍스트의 확률 합이 1이 아니다.

사용 예:
  py siglip_similarity.py --images ../yoloe/bus.jpg --texts "a bus" "a person" "a dog"
  py siglip_similarity.py --images ./imgs --texts-file prompts.txt --out runs/exp1
"""

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image
from transformers import AutoModel, AutoProcessor

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# 순차(크기) 인코딩용 단일 색상 램프: 코사인=파랑, 확률=주황
BLUE = LinearSegmentedColormap.from_list("seq_blue", ["#f4f8fd", "#9ec5f4", "#3987e5", "#184f95", "#0d366b"])
ORANGE = LinearSegmentedColormap.from_list("seq_orange", ["#fdf6ee", "#f6c48f", "#e8853a", "#b4561c", "#7a3510"])
INK = "#2b2b28"
MUTED = "#6b6a66"
GRID = "#e4e2dd"

# Windows 기본 한글 폰트 (없으면 matplotlib 기본값)
for font in ("Malgun Gothic", "AppleGothic", "NanumGothic"):
    if any(font == f.name for f in matplotlib.font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = font
        break
plt.rcParams["axes.unicode_minus"] = False


def collect_images(paths):
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.suffix.lower() in IMAGE_EXTS)
        elif p.suffix.lower() in IMAGE_EXTS:
            files.append(p)
    if not files:
        raise SystemExit("이미지를 찾지 못했습니다: " + ", ".join(paths))
    return files


def load_texts(args):
    texts = list(args.texts or [])
    if args.texts_file:
        lines = Path(args.texts_file).read_text(encoding="utf-8").splitlines()
        texts += [t.strip() for t in lines if t.strip()]
    if not texts:
        raise SystemExit("--texts 또는 --texts-file 로 텍스트를 지정하세요.")
    return texts


def _as_tensor(out):
    # transformers 버전에 따라 텐서 또는 pooler_output을 가진 출력 객체를 반환한다
    return out if isinstance(out, torch.Tensor) else out.pooler_output


@torch.no_grad()
def embed(model, processor, images, texts, device, batch_size):
    img_feats = []
    for i in range(0, len(images), batch_size):
        batch = [Image.open(p).convert("RGB") for p in images[i:i + batch_size]]
        inputs = processor(images=batch, return_tensors="pt").to(device)
        img_feats.append(_as_tensor(model.get_image_features(**inputs)))
    # SigLIP은 max_length 패딩으로 학습되었으므로 동일하게 맞춘다
    inputs = processor(text=texts, padding="max_length", truncation=True, return_tensors="pt").to(device)
    txt_feats = _as_tensor(model.get_text_features(**inputs))

    img = torch.nn.functional.normalize(torch.cat(img_feats).float(), dim=-1)
    txt = torch.nn.functional.normalize(txt_feats.float(), dim=-1)
    return img, txt


def heatmap(ax, data, rows, cols, cmap, vmin, vmax, fmt, title):
    im = ax.imshow(data, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(cols)), cols, rotation=35, ha="right", fontsize=9, color=INK)
    ax.set_yticks(range(len(rows)), rows, fontsize=9, color=INK)
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=10)
    # 셀 사이 2px 간격
    ax.set_xticks(np.arange(-.5, len(cols)), minor=True)
    ax.set_yticks(np.arange(-.5, len(rows)), minor=True)
    ax.grid(which="minor", color="white", linewidth=2)
    ax.tick_params(which="both", length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    # 셀 수가 많지 않을 때만 값 표기
    if data.size <= 400:
        mid = vmin + (vmax - vmin) * 0.55
        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                ax.text(j, i, format(data[i, j], fmt), ha="center", va="center", fontsize=8,
                        color="white" if data[i, j] > mid else INK)
    cb = plt.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=8, colors=MUTED, length=0)


def style_axis(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="both", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def plot_all(cos, prob, img_names, texts, scale, bias, out):
    h_sz = (max(6, 1.1 * len(texts) + 3), max(3.5, 0.45 * len(img_names) + 2))

    fig, ax = plt.subplots(figsize=h_sz)
    heatmap(ax, cos, img_names, texts, BLUE, cos.min(), cos.max(), ".3f", "코사인 유사도 (이미지 × 텍스트)")
    fig.tight_layout()
    fig.savefig(out / "cosine_heatmap.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=h_sz)
    heatmap(ax, prob, img_names, texts, ORANGE, 0.0, 1.0, ".3f", "SigLIP 시그모이드 확률 (이미지 × 텍스트)")
    fig.tight_layout()
    fig.savefig(out / "sigmoid_heatmap.png", dpi=150)
    plt.close(fig)

    # 코사인 → 확률 변환 곡선 위에 실제 쌍을 찍어 두 지표의 관계를 보여준다
    fig, ax = plt.subplots(figsize=(7, 4.5))
    lo, hi = min(cos.min(), -0.1) - 0.02, max(cos.max(), 0.3) + 0.02
    xs = np.linspace(lo, hi, 300)
    ax.plot(xs, 1 / (1 + np.exp(-(xs * scale + bias))), color=MUTED, linewidth=2,
            label=f"sigmoid(cos·{scale:.1f} {bias:+.1f})")
    ax.scatter(cos.ravel(), prob.ravel(), s=40, color="#2a78d6", edgecolor="white", linewidth=1.5,
               zorder=3, label="이미지-텍스트 쌍")
    ax.axhline(0.5, color=GRID, linewidth=1, linestyle="--")
    ax.axvline(-bias / scale, color=GRID, linewidth=1, linestyle="--")
    ax.text(-bias / scale, 0.52, f" p=0.5 @ cos={-bias / scale:.3f}", fontsize=8, color=MUTED)
    ax.set_xlabel("코사인 유사도", color=INK)
    ax.set_ylabel("시그모이드 확률", color=INK)
    ax.set_title("코사인 유사도와 SigLIP 확률의 관계", loc="left", fontsize=12, color=INK)
    style_axis(ax)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.tight_layout()
    fig.savefig(out / "cosine_vs_sigmoid.png", dpi=150)
    plt.close(fig)

    # 이미지별 텍스트 순위 (코사인 | 확률 두 패널, 축 공유 없음)
    for i, name in enumerate(img_names):
        order = np.argsort(cos[i])
        labels = [texts[k] for k in order]
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, max(2.5, 0.4 * len(texts) + 1.2)), sharey=True)
        a1.barh(labels, cos[i, order], color="#3987e5", height=0.6)
        a2.barh(labels, prob[i, order], color="#e8853a", height=0.6)
        a2.set_xlim(0, 1)
        for a, vals, fmt, t in ((a1, cos[i, order], ".3f", "코사인 유사도"), (a2, prob[i, order], ".3f", "시그모이드 확률")):
            style_axis(a)
            a.grid(axis="y", visible=False)
            a.set_title(t, loc="left", fontsize=10, color=INK)
            for y, v in enumerate(vals):
                a.text(v, y, f" {v:{fmt}} " , va="center", ha="left" if v >= 0 else "right", fontsize=8, color=INK)
        a1.axvline(0, color=MUTED, linewidth=1)
        lo, hi = cos[i].min(), cos[i].max()
        pad = (hi - min(lo, 0)) * 0.18
        a1.set_xlim(min(lo, 0) - (pad if lo < 0 else 0), hi + pad)
        a1.tick_params(axis="y", colors=INK)
        fig.suptitle(name, x=0.01, ha="left", fontsize=12, color=INK)
        fig.tight_layout()
        fig.savefig(out / f"rank_{i:02d}_{Path(name).stem}.png", dpi=150)
        plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images", nargs="+", required=True, help="이미지 파일 또는 폴더")
    ap.add_argument("--texts", nargs="*", help="비교할 텍스트들")
    ap.add_argument("--texts-file", help="한 줄에 하나씩 텍스트가 적힌 파일")
    ap.add_argument("--model", default="google/siglip-base-patch16-224",
                    help="HF 모델 ID (예: google/siglip2-base-patch16-224, google/siglip-so400m-patch14-384)")
    ap.add_argument("--out", default="runs/siglip", help="결과 저장 폴더")
    ap.add_argument("--batch-size", type=int, default=16)
    args = ap.parse_args()

    images = collect_images(args.images)
    texts = load_texts(args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"모델 로드: {args.model} ({device})")
    model = AutoModel.from_pretrained(args.model).to(device).eval()
    processor = AutoProcessor.from_pretrained(args.model)

    img, txt = embed(model, processor, images, texts, device, args.batch_size)
    cos = (img @ txt.T).cpu().numpy()
    scale = model.logit_scale.exp().item()
    bias = model.logit_bias.item()
    prob = 1 / (1 + np.exp(-(cos * scale + bias)))

    np.save(out / "image_embeddings.npy", img.cpu().numpy())
    np.save(out / "text_embeddings.npy", txt.cpu().numpy())

    img_names = [p.name for p in images]
    # 파일명이 겹치면 상위 폴더명을 붙여 구분한다
    if len(set(img_names)) < len(img_names):
        img_names = [f"{p.parent.name}/{p.name}" for p in images]
    with open(out / "results.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["image", "text", "cosine", "logit", "sigmoid_prob"])
        for i, name in enumerate(img_names):
            for j, t in enumerate(texts):
                w.writerow([name, t, f"{cos[i, j]:.6f}", f"{cos[i, j] * scale + bias:.4f}", f"{prob[i, j]:.6f}"])

    plot_all(cos, prob, img_names, texts, scale, bias, out)

    print(f"logit_scale(exp)={scale:.3f}, logit_bias={bias:.3f}")
    for i, name in enumerate(img_names):
        j = int(cos[i].argmax())
        print(f"{name}: 최고 일치 '{texts[j]}' cos={cos[i, j]:.3f} p={prob[i, j]:.3f}")
    print(f"저장 완료 → {out.resolve()}")


if __name__ == "__main__":
    main()
