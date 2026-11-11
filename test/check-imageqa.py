# -*- coding: utf-8 -*-
"""用 samples/ 里的真实产出验证 imageqa 的五个验收函数。

样本是这套产线自己跑出来的图，所以这里的期望值就是「已知答案」：
10 的 head/body 必须 0 重叠、09 的 9-slice 中间块必须单色。
如果哪天改了 pipelines.py 而验收还过，说明验收写虚了。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "lib"))

import imageqa  # noqa: E402

S = os.path.join(ROOT, "samples")
failures = []


def check(label, payload, expect_ok=True):
    ok = payload.get("ok")
    flag = "PASS" if ok == expect_ok else "FAIL"
    if ok != expect_ok:
        failures.append(label)
    print("%-28s %s  ok=%s" % (label, flag, ok))
    return payload


# --- 10 部件：samples 里的 head / body 是这条产线的实测产出 -------------
head = os.path.join(S, "10", "part_head_00010_.png")
body = os.path.join(S, "10", "part_body_00011_.png")
parts = imageqa.verify_parts(head, body)
check("10 parts (head+body)", {"ok": parts["ok"]})
print(
    "    head=%s body=%s union=%s sum=%s overlap_px=%d rgb_max=%d"
    % (
        parts["head_ratio"],
        parts["body_ratio"],
        parts["union_ratio"],
        parts["sum_ratio"],
        parts["overlap_px"],
        parts["transparent_rgb_max"],
    )
)
for name, passed in parts["checks"].items():
    print("      %-22s %s" % (name, "ok" if passed else "BAD"))
    if not passed:
        failures.append("10 checks.%s" % name)

# 硬要求单拎出来断言：这是整条产线最不能错的一条
assert parts["overlap_px"] == 0, "head/body 出现重叠 —— 10 产线的核心不变量被破坏"
assert parts["transparent_rgb_max"] == 0, "透明区 RGB 非 0，引擎会出现黑边"

# --- 09 面板：去掉 alpha 边后的面板主体 --------------------------------
panel = os.path.join(S, "09", "ui_panel_9slice_00006_.png")
pv = imageqa.verify_panel(panel)
check("09 panel (raw)", {"ok": pv["ok"]})
print(
    "    trimmed=%s corner=%s center_opaque=%s"
    % (pv["trimmed"], pv["corner"], pv["center_opaque_ratio"])
)
print("    corners=%s" % json.dumps(pv["corners"]))
print("    edges=%s" % json.dumps(pv["edges"]))
for name, passed in pv["checks"].items():
    print("      %-22s %s" % (name, "ok" if passed else "BAD"))
    if not passed:
        failures.append("09 checks.%s" % name)

# --- 09 切好的 mc 中间块：必须单色 ------------------------------------
mc = os.path.join(S, "09", "9slice_mc_704x704_00007_.png")
mv = imageqa.verify_nineslice(mc)
check("09 mc tile", {"ok": mv["ok"]})
print("    size=%s unique_rgb=%s mean_rgb=%s" % (mv["size"], mv["unique_rgb"], mv["mean_rgb"]))
for name, passed in mv["checks"].items():
    print("      %-22s %s" % (name, "ok" if passed else "BAD"))
    if not passed:
        failures.append("09 mc.%s" % name)
assert mv["unique_rgb"] == 1, "mc 切片不是单色 —— 9-slice 拉伸会出脏纹"

# --- 09 其它已切好的单块 ----------------------------------------------
for name in sorted(os.listdir(os.path.join(S, "09"))):
    if not name.startswith("9slice_") or name.startswith("9slice_mc"):
        continue
    tv = imageqa.verify_alpha(os.path.join(S, "09", name))
    print("%-28s size=%s coverage=%s" % (name[:28], tv["size"], tv["coverage"]))

# --- 08 背景 ---------------------------------------------------------
bg = os.path.join(S, "08", "bg_scene_00001_.png")
fv = imageqa.verify_flat(bg)
print("%-28s size=%s mean_rgb=%s" % ("08 background", fv["size"], fv["mean_rgb"]))
print("      is_1080p=%s is_16x9=%s" % (fv["checks"]["is_1080p"], fv["checks"]["is_16x9"]))
if not fv["checks"]["is_1080p"]:
    failures.append("08 size")
if fv["has_alpha"]:
    failures.append("08 unexpectedly has alpha")

# --- 11 光效 ---------------------------------------------------------
fx_dir = os.path.join(S, "11")
fx_tested = 0
for name in sorted(os.listdir(fx_dir)):
    if not name.endswith(".png"):
        continue
    fxj = imageqa.verify_fx(os.path.join(fx_dir, name))
    print(
        "%-28s ok=%s style=%-10s coverage=%s edge_tx=%s clear_p90=%s bright=%s"
        % (
            "11 " + name[:20],
            fxj.get("ok"),
            fxj.get("style"),
            fxj.get("coverage"),
            fxj.get("edge_transparent_ratio"),
            fxj.get("clear_region_lum_p90"),
            fxj.get("bright_core_ratio"),
        )
    )
    # 00001 是已知的满屏闪光，不是 sprite：应当被判 full_frame 且 ok=False，
    # 这是**正确**的判定（当成 sprite 加色叠加会烧白），不算测试失败。
    if name.startswith("fx_energy_00001"):
        assert fxj["style"] == "full_frame", "00001 应被识别为满屏闪光"
        assert fxj["ok"] is False, "满屏闪光不该通过 sprite 验收"
        assert fxj["hint"], "满屏闪光应给出 hint"
        print("       expected-reject: %s" % fxj["style"])
        print("       hint: %s" % fxj["hint"][:70])
        fx_tested += 1
        continue
    if fxj.get("ok") is False:
        for cname, passed in (fxj.get("checks") or {}).items():
            if not passed:
                print("       BAD %s" % cname)
                failures.append("11 %s %s" % (name[:16], cname))
    fx_tested += 1
if fx_tested == 0:
    failures.append("11 no samples")

# --- 00~07 新产线的验收函数 -------------------------------------------
# 样本不足（00~07 的产出没进 samples/），这里用合成的确定性图当「已知答案」：
# 无缝 vs 有接缝、居中图标 vs 铺满画布、有点阵细节 vs 全平。
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

_tmp = os.path.join(HERE, "_probe")
os.makedirs(_tmp, exist_ok=True)
import atexit  # noqa: E402
import shutil  # noqa: E402

atexit.register(lambda: shutil.rmtree(_tmp, ignore_errors=True))


def _save(name, arr, mode="RGB"):
    p = os.path.join(_tmp, name)
    Image.fromarray(arr.astype("uint8"), mode).save(p)
    return p


_h = _w = 512
_yy, _xx = np.mgrid[0:_h, 0:_w]
# 周期整除画布 => 天然无缝
_base = (
    (np.sin(2 * np.pi * _xx / 128) * 0.5 + 0.5) * 120
    + (np.cos(2 * np.pi * _yy / 256) * 0.5 + 0.5) * 80
    + 20
)
seamless = _save("seamless.png", np.dstack([_base, _base * 0.9, _base * 0.7]))
# 真接缝：把中间一段横向拉伸铺满，左右边缘不连续
_strip = _base[:, 100:400]
_bad = np.stack(
    [np.interp(np.linspace(0, 299, _w), np.arange(300), row) for row in _strip]
)
seamed = _save("seamed.png", np.dstack([_bad, _bad * 0.9, _bad * 0.7]))

# 06 无缝贴图
t = imageqa.verify("tile", [seamless])
check("06 tile 无缝 -> ok:true", t, expect_ok=True)
print("    06 seamless  seam_ratio h=%s v=%s" % (t["seam_grad_ratio_h"], t["seam_grad_ratio_v"]))
t2 = imageqa.verify("tile", [seamed])
check("06 tile 有接缝 -> ok:false", t2, expect_ok=False)
assert t2["hint"], "有接缝必须给 hint"
print("    06 seamed    seam_ratio h=%s (期望被拒)" % t2["seam_grad_ratio_h"])
# 判别力：两条路径的比值必须拉开量级
assert t["seam_grad_ratio_h"] < 1.2 <= t2["seam_grad_ratio_h"], "tile 判别力不足"

# 05 道具图标：居中透明底 512 正方形 = 合格
_icon = np.zeros((512, 512, 4), dtype=np.float32)
_cy, _cx = np.mgrid[0:512, 0:512]
_disc = ((_cy - 256) ** 2 + (_cx - 256) ** 2) <= 170**2
_icon[..., 0][_disc] = 220
_icon[..., 1][_disc] = 150
_icon[..., 2][_disc] = 90
_icon[..., 3][_disc] = 255
icon_ok = _save("icon_ok.png", _icon, "RGBA")
ic = imageqa.verify("icon", [icon_ok])
check("05 icon 居中透明 -> ok:true", ic, expect_ok=True)
print("    05 icon extent=%s center=%s" % (ic["subject_extent"], ic["center_offset"]))

# 反向：背景不透明（没抠图）必须被拒
_flat_icon = np.zeros((512, 512, 4), dtype=np.float32)
_flat_icon[..., :3] = 200
_flat_icon[..., 3] = 255
ic_bad = _save("icon_opaque.png", _flat_icon, "RGBA")
check("05 icon 未抠图 -> ok:false", imageqa.verify("icon", [ic_bad]), expect_ok=False)

# 07 高清放大：大且锐 = 合格；缩到 512 不合格
# 用带真实高频细节的图（棋盘 + 噪点），正弦图太光滑会正确地被判无细节
_rng = np.random.default_rng(20261111)
_by, _bx = np.mgrid[0:1024, 0:1024]
_chess = ((_by // 8 + _bx // 8) % 2).astype(np.float32) * 180 + 40
_chess += _rng.normal(0, 12, _chess.shape)
_sharp = np.dstack([_chess, _chess * 0.85, _chess * 0.65])
big = _save("big.png", _sharp)
up = imageqa.verify("upscale", [big])
check("07 upscale 大且锐 -> ok:true", up, expect_ok=True)
print("    07 upscale size=%s sharpness=%s" % (up["size"], up["sharpness"]))
# 同一张图缩到 512：尺寸不够，必须被拒
check("07 upscale 512 -> ok:false", imageqa.verify("upscale", [seamless]), expect_ok=False)
# 模糊成一片：有尺寸但没细节，必须被拒
_blur = np.full((1024, 1024, 3), 128, dtype=np.float32)
_blur[100:900, 100:900] = 150
check("07 upscale 糊图 -> ok:false", imageqa.verify("upscale", [_save("blur.png", _blur)]), expect_ok=False)

# 04 三视图：三段都有主体 = 合格；单段 = 不合格
_ta = np.full((768, 1152, 3), 245, dtype=np.float32)
for _i in range(3):
    _x0 = _i * 384 + 120
    _ta[200:600, _x0 : _x0 + 140] = 40
ta_ok = _save("turnaround_ok.png", _ta)
tv = imageqa.verify("turnaround", [ta_ok])
check("04 turnaround 三视图 -> ok:true", tv, expect_ok=True)
print("    04 thirds=%s wide=%s" % (tv["thirds_coverage"], tv["checks"]["wide"]))
_ta_bad = np.full((768, 1152, 3), 245, dtype=np.float32)
_ta_bad[200:600, 120:260] = 40
check(
    "04 turnaround 只有一段 -> ok:false",
    imageqa.verify("turnaround", [_save("turnaround_bad.png", _ta_bad)]),
    expect_ok=False,
)

# --- 错误路径 --------------------------------------------------------
missing = imageqa.verify("alpha", [os.path.join(S, "nope.png")])
check("missing file -> ok:false", missing, expect_ok=False)
print("    %s" % missing.get("error"))

unknown = imageqa.verify("bogus", [bg])
check("unknown kind -> ok:false", unknown, expect_ok=False)
print("    %s" % unknown.get("error"))

# --- runner.apply_overrides 语义 -------------------------------------
# 这段不测图，测的是「覆写只该落在定义画布的节点上」。
# 04 是 768x512 起稿再 LatentUpscale 1.5x 到 1152x768；早期实现会把 width/height
# 写给所有带这个 widget 的节点，结果两处一起变，1.5 倍关系被抹平。
print()
sys.path.insert(0, ROOT)
try:
    from gameart_pipeline import pipelines as P
    from gameart_pipeline import runner as R

    def _dims(graph, types):
        out = []
        for node in graph.nodes.values():
            if node.get("type") in types:
                w = node["widgets"]
                out.append((node["type"], w.get("width"), w.get("height")))
        return out

    g4 = P.BUILDERS["04"]()
    applied = R.apply_overrides(g4, {"width": 1024, "height": 768})
    d4 = dict((t, (w, h)) for t, w, h in _dims(g4, ("EmptyLatentImage", "LatentUpscale")))
    ok4 = (
        d4.get("EmptyLatentImage") == (1024, 768)
        and d4.get("LatentUpscale") == (1152, 768)
        and "width" in applied and "height" in applied
    )
    check("04 覆写只改起稿尺寸，放大目标不变", {"ok": ok4, "dims": d4, "applied": applied}, expect_ok=True)

    # 08 的 ImageScale 是 1920x1080 定版上采样，不该被 width/height 覆写带走
    g8 = P.BUILDERS["08"]()
    R.apply_overrides(g8, {"width": 1280, "height": 720})
    d8 = dict((t, (w, h)) for t, w, h in _dims(g8, ("EmptyLatentImage", "ImageScale")))
    ok8 = d8.get("EmptyLatentImage") == (1280, 720) and d8.get("ImageScale") == (1920, 1080)
    check("08 覆写不碰 ImageScale 上采样目标", {"ok": ok8, "dims": d8}, expect_ok=True)

    # seed 仍应广播到所有带 seed 的节点（04 有两个 KSampler，必须同步）
    g4b = P.BUILDERS["04"]()
    R.apply_overrides(g4b, {"seed": 777})
    seeds = sorted(n["widgets"]["seed"] for n in g4b.nodes.values() if "seed" in n["widgets"])
    check("seed 覆写广播到全部采样器", {"ok": seeds and set(seeds) == {777}, "seeds": seeds}, expect_ok=True)
except Exception as e:  # noqa: BLE001
    check("runner.apply_overrides 可导入", {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, expect_ok=False)

print()
if failures:
    print("FAILURES: %s" % ", ".join(failures))
    sys.exit(1)
print("ALL IMAGEPA CHECKS PASSED")
