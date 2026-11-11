import numpy as np
from PIL import Image
import glob, os

base = r"E:\AAAKI\ComfyUI-aki\ComfyUI-aki-v3\ComfyUI\output\GameArt\06_Tile"


def ratio(p):
    a = np.asarray(Image.open(p).convert("RGB"), dtype=np.float32)
    sh = a.shape
    seam_h = np.abs(a[:, 0, :] - a[:, -1, :]).mean()
    adj_h = np.abs(a[:, 0, :] - a[:, 1, :]).mean()
    seam_v = np.abs(a[0, :, :] - a[-1, :, :]).mean()
    adj_v = np.abs(a[0, :, :] - a[1, :, :]).mean()
    return seam_h / max(adj_h, 1e-6), seam_v / max(adj_v, 1e-6)


for f in sorted(glob.glob(os.path.join(base, "*.png"))):
    rh, rv = ratio(f)
    ok = "PASS" if (rh <= 1.3 and rv <= 1.3) else "FAIL"
    print(f"{os.path.basename(f):32s} 水平={rh:5.2f} 垂直={rv:5.2f}  {ok}")
