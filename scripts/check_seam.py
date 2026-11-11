import os, glob
import numpy as np
from PIL import Image

base = r"E:\AAAKI\ComfyUI-aki\ComfyUI-aki-v3\ComfyUI\output\GameArt\06_Tile"
p = max(glob.glob(os.path.join(base, "*.png")), key=os.path.getmtime)
a = np.asarray(Image.open(p).convert("RGB")).astype(np.float32)
seam = np.abs(a[:, 0, :] - a[:, -1, :]).mean()
inner = np.abs(a[:, 1:, :] - a[:, :-1, :]).mean()
vseam = np.abs(a[0, :, :] - a[-1, :, :]).mean()
vinner = np.abs(a[1:, :, :] - a[:-1, :, :]).mean()
print("文件:", os.path.basename(p))
print("水平接缝比 %.2f  (接缝 %.2f / 内部 %.2f)" % (seam / inner, seam, inner))
print("垂直接缝比 %.2f  (接缝 %.2f / 内部 %.2f)" % (vseam / vinner, vseam, vinner))
print("判定:", "无缝通过" if max(seam / inner, vseam / vinner) <= 1.5 else "仍有接缝")
