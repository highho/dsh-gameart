"""9-slice 切图工具：把任意一张 UI 面板图切成标准 9 块。

背景：SDXL 出的 UI 面板尺寸、位置、长宽比都不固定，按 1024 固定坐标硬切会切空/切歪。
本工具按 alpha 求面板实际包围盒，裁到面板本体后直接按 3x3 切分（支持宽扁对话框等非正方形面板）。

用法：
    python slice9.py <面板png> [输出目录] [C]

C 为角/边块边长上限，实际取 min(C, w//4, h//4)，防止小面板被切穿。
中心块 mc 用面板中心区域的平均色重新填充，保证双向拉伸时不出现断裂纹样。
"""
import os
import sys

import numpy as np
from PIL import Image


def trim_alpha(im, thr=8):
    a = im.getchannel("A")
    bbox = a.point(lambda v: 255 if v > thr else 0).getbbox()
    return im.crop(bbox) if bbox else im


def slice9(src, outdir, C=160):
    im = Image.open(src).convert("RGBA")
    panel = trim_alpha(im)
    w, h = panel.size
    c = min(C, max(16, w // 4), max(16, h // 4))

    os.makedirs(outdir, exist_ok=True)
    base = os.path.splitext(os.path.basename(src))[0]
    panel.save(os.path.join(outdir, "%s_panel_trim_%dx%d.png" % (base, w, h)))

    # 中心块：取面板中心的实测平均色，铺成纯色，避免十字线/装饰被拉伸
    arr = np.array(panel).astype(np.float32)
    cx0, cy0 = int(w * 0.35), int(h * 0.35)
    cx1, cy1 = int(w * 0.65), int(h * 0.65)
    patch = arr[cy0:cy1, cx0:cx1]
    mask = patch[:, :, 3] > 200
    mean = patch[mask][:, :3].mean(axis=0) if mask.any() else np.array([32, 32, 40])
    mc = Image.new("RGBA", (w - 2 * c, h - 2 * c), tuple(int(v) for v in mean) + (255,))

    parts = {
        "tl": panel.crop((0, 0, c, c)),
        "tc": panel.crop((c, 0, w - c, c)),
        "tr": panel.crop((w - c, 0, w, c)),
        "ml": panel.crop((0, c, c, h - c)),
        "mc": mc,
        "mr": panel.crop((w - c, c, w, h - c)),
        "bl": panel.crop((0, h - c, c, h)),
        "bc": panel.crop((c, h - c, w - c, h)),
        "br": panel.crop((w - c, h - c, w, h)),
    }
    made = []
    for name, img in parts.items():
        f = os.path.join(outdir, "%s_9slice_%s_%dx%d.png" % (base, name, img.size[0], img.size[1]))
        img.save(f)
        made.append(f)
    return panel, made, c, tuple(int(v) for v in mean)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    src = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(src)
    C = int(sys.argv[3]) if len(sys.argv) > 3 else 160
    p, files, c, mean = slice9(src, outdir, C)
    a = np.array(p)[:, :, 3]
    print("面板 bbox %dx%d | 角块边长 C=%d | 中心填充色 RGB=%s | alpha 覆盖=%.4f"
          % (p.size[0], p.size[1], c, mean, (a > 5).mean()))
    for f in files:
        print(" ->", os.path.basename(f))
