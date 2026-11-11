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

# --- 错误路径 --------------------------------------------------------
missing = imageqa.verify("alpha", [os.path.join(S, "nope.png")])
check("missing file -> ok:false", missing, expect_ok=False)
print("    %s" % missing.get("error"))

unknown = imageqa.verify("bogus", [bg])
check("unknown kind -> ok:false", unknown, expect_ok=False)
print("    %s" % unknown.get("error"))

print()
if failures:
    print("FAILURES: %s" % ", ".join(failures))
    sys.exit(1)
print("ALL IMAGEPA CHECKS PASSED")
