# -*- coding: utf-8 -*-
"""产线出图的确定性验收。

为什么要有这一层：README 的验收清单里写的是「head 占 1.91%、body 51.85%、
重叠 0 px」「面板中间块恰好 1 种 RGB」这类量。让模型去「看一眼图觉得差不多」
是不可靠的 —— 重叠几十个像素肉眼看不出来，但动画里就是一条缝。
这里用 numpy + PIL 把那些量真的算出来，并给出结构性判定。

判定只查**结构性不变量**，不比对那组样本数字（样本数字跟着 seed 变）：
  * 10 两层像素级互斥（overlap == 0）是硬要求；
  * 10 透明区 RGB 必须全 0（否则引擎双线性过滤会出黑边）；
  * 09 中间块必须单一 RGB 且 alpha 全不透明（否则拉伸出脏纹）；
  * 11 必须是 RGBA，且透明区 RGB 接近 0（加色混合的前提）。
"""
import os

import numpy as np
from PIL import Image

# 与 slicing.py 保持一致，避免两处各写一个常量
ALPHA_THR = 8
DEFAULT_CORNER = 160

__all__ = [
    "verify",
    "verify_alpha",
    "verify_flat",
    "verify_parts",
    "verify_panel",
    "verify_nineslice",
    "verify_fx",
]


def _load(path):
    im = Image.open(path)
    im.load()
    return im


def _require(path):
    if not os.path.isfile(path):
        raise FileNotFoundError("图片不存在: %s" % path)
    return path


def _rgba(im):
    return np.asarray(im.convert("RGBA"), dtype=np.uint8)


def _rgb(im):
    return np.asarray(im.convert("RGB"), dtype=np.uint8)


def _bbox_alpha(arr):
    """有内容的包围盒 (x0, y0, x1, y1)；全透明返回 None。"""
    alpha = arr[..., 3]
    rows = np.any(alpha > ALPHA_THR, axis=1)
    cols = np.any(alpha > ALPHA_THR, axis=0)
    if not rows.any() or not cols.any():
        return None
    y0, y1 = int(np.argmax(rows)), int(len(rows) - np.argmax(rows[::-1]))
    x0, x1 = int(np.argmax(cols)), int(len(cols) - np.argmax(cols[::-1]))
    return x0, y0, x1, y1


def _nz(fraction):
    return round(float(fraction), 4)


def verify_alpha(path):
    """通用 RGBA 体检：尺寸、模式、覆盖率、透明区 RGB。"""
    im = _load(path)
    arr = _rgba(im)
    h, w = arr.shape[:2]
    alpha = arr[..., 3]
    opaque = alpha > ALPHA_THR
    total = float(h * w)
    clear = alpha == 0
    transparent_rgb_max = int(arr[..., :3][clear].max()) if bool(clear.any()) else 0
    bbox = _bbox_alpha(arr)
    return {
        "path": str(path),
        "size": [w, h],
        "mode": im.mode,
        "has_alpha": im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info,
        "coverage": _nz(opaque.sum() / total),
        "transparent_ratio": _nz(clear.sum() / total),
        "transparent_rgb_max": transparent_rgb_max,
        "alpha_bbox": list(bbox) if bbox else None,
    }


def verify_flat(path):
    """08 背景这类不透明图：尺寸 + 是否真的没有 alpha。"""
    im = _load(path)
    arr = _rgb(im)
    h, w = arr.shape[:2]
    return {
        "path": str(path),
        "size": [w, h],
        "mode": im.mode,
        "has_alpha": False,
        "mean_rgb": [int(v) for v in arr.reshape(-1, 3).mean(axis=0)],
        "checks": {
            "is_16x9": abs(w / float(h) - 16 / 9.0) < 0.02,
            "is_1080p": (w, h) == (1920, 1080),
        },
    }


def verify_parts(head_path, body_path):
    """10 的两层：像素级互斥 + 并集覆盖 + 透明区 RGB。"""
    head_im, body_im = _load(head_path), _load(body_path)
    if head_im.size != body_im.size:
        return {
            "ok": False,
            "error": "两层尺寸不一致：head=%s body=%s" % (head_im.size, body_im.size),
        }
    ha, ba = _rgba(head_im), _rgba(body_im)
    h, w = ha.shape[:2]
    total = float(h * w)
    h_on = ha[..., 3] > ALPHA_THR
    b_on = ba[..., 3] > ALPHA_THR
    overlap = h_on & b_on
    union = h_on | b_on
    # 「透明区」只算两层 alpha 都严格为 0 的像素。0 < alpha <= 8 是软边羽化，
    # 那里 RGB 本来就该是有内容的颜色；把它们算进来会误报（实测 body 有 3260 个这种像素）。
    fully_clear = (ha[..., 3] == 0) & (ba[..., 3] == 0)
    union_rgb_max = (
        max(
            int(ha[..., :3][fully_clear].max()),
            int(ba[..., :3][fully_clear].max()),
        )
        if bool(fully_clear.any())
        else 0
    )
    overlap_px = int(overlap.sum())
    return {
        "ok": overlap_px == 0,
        "size": [w, h],
        "head_ratio": _nz(h_on.sum() / total),
        "body_ratio": _nz(b_on.sum() / total),
        "union_ratio": _nz(union.sum() / total),
        "sum_ratio": _nz((h_on.sum() + b_on.sum()) / total),
        "overlap_px": overlap_px,
        "overlap_ratio": _nz(overlap.sum() / total),
        "transparent_rgb_max": union_rgb_max,
        "head_bbox": list(_bbox_alpha(ha)) if _bbox_alpha(ha) else None,
        "body_bbox": list(_bbox_alpha(ba)) if _bbox_alpha(ba) else None,
        "checks": {
            # 硬要求：两层不能有任何一个像素同时不透明
            "no_overlap": overlap_px == 0,
            # 并集应该基本等于两层之和（互斥的直接推论）
            # bool(...) 是必须的：numpy 比较返回 np.bool_，json 序列化不了
            "union_matches_sum": bool(
                abs(union.sum() - (h_on.sum() + b_on.sum())) <= 0.001 * total
            ),
            # 透明区 RGB 必须全 0，否则引擎过滤会出黑边
            "clean_transparent_rgb": union_rgb_max == 0,
            # 头不能为空，也不能把整张吞掉
            "head_nonempty": bool(h_on.any()),
            "body_nonempty": bool(b_on.any()),
            "head_smaller_than_body": bool(h_on.sum() < b_on.sum()),
        },
    }


def verify_panel(path, corner=DEFAULT_CORNER):
    """09 面板：裁掉 alpha 边后量四角 / 四边覆盖率。

    注意**不要**在这里要求「中间块单一颜色」—— 原始面板的中间是画出来的渐变，
    本来就该有颜色变化。真正需要单色的是 slice9() 重建出来的 mc 切片，
    那个由 verify_nineslice() 负责。
    """
    im = _load(_require(path))
    arr = _rgba(im)
    bbox = _bbox_alpha(arr)
    if bbox is None:
        return {"ok": False, "error": "面板整张透明，没有可切的内容"}
    x0, y0, x1, y1 = bbox
    arr = arr[y0:y1, x0:x1]
    h, w = arr.shape[:2]
    c = min(int(corner), max(16, w // 4), max(16, h // 4))
    alpha = arr[..., 3]

    def nz(block):
        return _nz((block > ALPHA_THR).sum() / float(block.size))

    corners = {
        "tl": nz(alpha[:c, :c]),
        "tr": nz(alpha[:c, -c:]),
        "bl": nz(alpha[-c:, :c]),
        "br": nz(alpha[-c:, -c:]),
    }
    edges = {
        "top": nz(alpha[:c, c:-c]),
        "bottom": nz(alpha[-c:, c:-c]),
        "left": nz(alpha[c:-c, :c]),
        "right": nz(alpha[c:-c, -c:]),
    }
    center_alpha = alpha[c : h - c, c : w - c]
    center_opaque = center_alpha > 200
    checks = {
        # 四角必须有内容（否则切出来是缺角）
        "corners_filled": bool(all(v > 0.3 for v in corners.values())),
        # 四边也要有内容（否则拉伸出来是空条）
        "edges_filled": bool(all(v > 0.3 for v in edges.values())),
        # 中间必须整片不透明，拉伸时不会露出背景
        "center_opaque": bool(
            center_opaque.size
            and _nz(center_opaque.sum() / float(center_alpha.size)) > 0.999
        ),
        # 角块不能比边长小
        "corner_ok": bool(c >= 16),
        # 裁完之后应该接近正方形或至少不是极端长条
        "aspect_reasonable": bool(0.25 <= (w / float(h)) <= 4.0),
    }
    return {
        "ok": all(checks.values()),
        "path": str(path),
        "canvas": [int(im.size[0]), int(im.size[1])],
        "trimmed": [w, h],
        "trim_bbox": [x0, y0, x1, y1],
        "corner": c,
        "coverage": nz(alpha),
        "corners": corners,
        "edges": edges,
        "center_opaque_ratio": _nz(
            center_opaque.sum() / float(center_alpha.size)
        )
        if center_opaque.size
        else 0.0,
        "checks": checks,
    }


def verify_nineslice(mc_path, corner=None):
    """切好的九宫格中间块 mc：必须单色 + 全不透明 + 尺寸等于 trimmed - 2*corner。

    这是整个 9-slice 流程里唯一「必须人造」的一步（slice9 把中间重建成均值色），
    所以它是必须验的那一条。
    """
    im = _load(_require(mc_path))
    arr = _rgba(im)
    h, w = arr.shape[:2]
    alpha = arr[..., 3]
    opaque = alpha > 200
    rgb = arr[..., :3][opaque] if bool(opaque.any()) else np.zeros((0, 3), np.uint8)
    unique = int(np.unique(rgb.reshape(-1, 3), axis=0).shape[0]) if len(rgb) else 0
    mean_rgb = [int(v) for v in rgb.reshape(-1, 3).mean(axis=0)] if len(rgb) else [0, 0, 0]
    checks = {
        "single_rgb": unique == 1,
        "fully_opaque": bool(_nz(opaque.sum() / float(alpha.size)) > 0.999),
        "nonempty": bool(w >= 16 and h >= 16),
    }
    return {
        "ok": all(checks.values()),
        "path": str(mc_path),
        "size": [w, h],
        "unique_rgb": unique,
        "mean_rgb": mean_rgb,
        "checks": checks,
    }


def verify_fx(path):
    """11 光效：加色混合的前提 —— RGBA、黑底主导、加色成分够亮。

    实测这条产线出来的图，透明（alpha==0）区域里 RGB 常常不是 0：
    面板 00004 的 alpha==0 区域亮度中位 23、最高 134。原因是黑底周围那圈
    「快看不见的烟」被 alpha 压到 0 了，RGB 还留着。加色混合下 alpha 不参与
    计算，所以那圈会整块叠上去 —— 这就是为什么必须检查「透明区是否偏暗」，
    而不能只查 alpha。另外正式加色贴图应当整体偏暗底 + 少量亮核，
    如果大片像素既不透明又极亮，说明它是 Alpha Blend 素材，不是加色素材。
    """
    im = _load(_require(path))
    arr = _rgba(im)
    h, w = arr.shape[:2]
    alpha = arr[..., 3]
    rgb = arr[..., :3]
    lum = rgb.mean(axis=2)
    total = float(h * w)
    opaque = alpha > ALPHA_THR
    clear = alpha == 0
    bbox = _bbox_alpha(arr)

    ring = np.concatenate([alpha[0, :], alpha[-1, :], alpha[:, 0], alpha[:, -1]])
    edge_transparent = _nz(float((ring <= ALPHA_THR).sum()) / float(ring.size))
    # 边缘基本透明 = 是一张贴图（sprite），可以加色叠加；
    # 边缘不透明 = 满屏闪光（full-frame flash），那种只能 Alpha 混合，
    # 必须由调用方换一种合成方式，不能当 sprite 用。
    style = "sprite" if edge_transparent >= 0.5 else "full_frame"

    clear_lum_p90 = (
        float(np.percentile(lum[clear], 90)) if bool(clear.any()) else 0.0
    )
    clear_lum_max = float(lum[clear].max()) if bool(clear.any()) else 0.0
    # 加色素材：完全不透明的像素里，大部分应该已经很亮了（发光核），
    # 但完全不透明区域本身不该占满整张图（那样就没有「边缘散开」）。
    bright_and_opaque = (lum > 200) & opaque
    coverage = _nz(opaque.sum() / total)

    checks = {
        "has_alpha": bool(
            im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
        ),
        # 边缘要基本透明，否则贴上去是个方块（满屏闪光不算 sprite）
        "edge_transparent": bool(edge_transparent >= 0.5),
        # alpha==0 的地方必须够暗：加色混合会把它原样叠上去
        "clear_region_dark": bool(clear_lum_p90 <= 80.0),
        # 覆盖率落在合理区间
        "coverage_in_range": bool(0.02 <= coverage <= 0.75),
        # 要有真的亮核（不是一片灰）
        "has_bright_core": bool(float(bright_and_opaque.sum()) / total > 0.005),
    }
    hint = None
    if style == "full_frame":
        hint = (
            "这是满屏闪光而不是 sprite（四角 alpha=%d/%d/%d/%d，边缘 %.0f%% 不透明）。"
            "满屏闪光只能走 Alpha 混合整屏叠一次，当 sprite 反复加色叠加会把画面烧白。"
            "要 sprite 版请把构图收紧：光效主体居中、四周留出透明边。"
            % (
                int(alpha[0, 0]),
                int(alpha[0, -1]),
                int(alpha[-1, 0]),
                int(alpha[-1, -1]),
                (1.0 - edge_transparent) * 100,
            )
        )
    return {
        "ok": all(checks.values()),
        "path": str(path),
        "style": style,
        "size": [w, h],
        "mode": im.mode,
        "coverage": coverage,
        "edge_transparent_ratio": edge_transparent,
        "clear_region_lum_p90": round(clear_lum_p90, 2),
        "clear_region_lum_max": round(clear_lum_max, 2),
        "bright_core_ratio": _nz(float(bright_and_opaque.sum()) / total),
        "alpha_bbox": list(bbox) if bbox else None,
        "hint": hint,
        "checks": checks,
    }


def verify_icon(path):
    """05 道具图标：必须是正方形、背景全透、主体居中且占比合理。"""
    path = _require(path)
    im = _load(path)
    w, h = im.size
    arr = _rgba(im)
    rgb, alpha = arr[..., :3], arr[..., 3]
    total = w * h

    corner = alpha[: max(1, h // 20), : max(1, w // 20)]
    bg_clear = bool(corner.max() <= ALPHA_THR) if corner.size else False

    bbox = _bbox_alpha(arr)
    if bbox:
        bx0, by0, bx1, by1 = bbox
        subject = _nz(((alpha[by0:by1, bx0:bx1] > ALPHA_THR).sum()) / total)
        # 线性占比：README 说的「主体占画布 70~80%」指的是这个，不是面积
        extent = max((bx1 - bx0) / float(w), (by1 - by0) / float(h))
        # 主体中心相对画布中心的偏移（0 = 完全居中）
        cx = (bx0 + bx1) / 2.0 / w - 0.5
        cy = (by0 + by1) / 2.0 / h - 0.5
        offset = float((cx * cx + cy * cy) ** 0.5)
    else:
        subject = 0.0
        extent = 0.0
        offset = 1.0

    checks = {
        "has_alpha": bool(im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info),
        "square": bool(abs(w - h) <= max(2, int(0.02 * max(w, h)))),
        # 背景要真透（图标进 UI 不垫底）
        "bg_transparent": bg_clear,
        # 主体线性尺寸占画布 45%~98%：太小是缩放错了，太满是没抠图/出框
        "subject_extent": bool(0.45 <= extent <= 0.98),
        # 主体大致居中
        "centered": bool(offset <= 0.12),
        # 透明区 RGB 必须清零，否则引擎会出黑边
        "clear_rgb_zero": bool(int(rgb[alpha == 0].max()) == 0) if (alpha == 0).any() else True,
    }
    hint = None
    if not checks["bg_transparent"]:
        hint = "四角不透明：05 的抠图没生效，检查 BiRefNetRMBG 的 background 是否为 Alpha。"
    elif not checks["subject_extent"]:
        hint = (
            "主体线性占比 %.0f%%（应在 45%%~98%%）：太小说明裁剪/缩放错了（检查 ImageScale 是否 lanczos 到 512×512），"
            "太大说明主体出框或没抠净。prompt 里加 `one single object, centered`。" % (extent * 100)
        )
    elif not checks["centered"]:
        hint = "主体偏离中心 %.3f：prompt 加 `centered`，负向加 `off-center`。背景杂点也会把 alpha 包围盒拉偏。" % offset
    return {
        "ok": all(checks.values()),
        "path": str(path),
        "size": [w, h],
        "mode": im.mode,
        "subject_extent": round(extent, 4),
        "subject_ratio": subject,
        "center_offset": round(offset, 4),
        "alpha_bbox": list(bbox) if bbox else None,
        "hint": hint,
        "checks": checks,
    }


def verify_tile(path):
    """06 无缝贴图：环绕处（末列→首列）的跳变不能超过图内任意相邻列的跳变。

    为什么跟「图内最大跳变」比而不是平均值：真实材质有平缓区和细节区，
    平均值会被大片平缓区拉低，导致本来无缝的图误报。真正的接缝是**离群值**——
    它会比图内任何一处相邻列差都大得多；而无缝图的环绕处只是又一处普通相邻列。
    因此比值 = 环绕差 / 图内最大相邻差，≤1.2 视为看不出接缝。
    """
    path = _require(path)
    im = _load(path)
    w, h = im.size
    arr = _rgb(im).astype("float32")

    def diff(a, b):
        return float(abs(a - b).mean())

    # 水平：末列 → 首列 的环绕差；基线取图内所有相邻列差的最大值
    seam_h = diff(arr[:, w - 1, :], arr[:, 0, :])
    inner_h = max((diff(arr[:, x, :], arr[:, x + 1, :]) for x in range(w - 1)), default=0.0)
    # 垂直：末行 → 首行；基线取所有相邻行差的最大值
    seam_v = diff(arr[h - 1, :, :], arr[0, :, :])
    inner_v = max((diff(arr[y, :, :], arr[y + 1, :, :]) for y in range(h - 1)), default=0.0)

    def ratio(seam, inner):
        if inner > 1e-6:
            return seam / inner
        return 0.0 if seam <= 1e-6 else 999.0

    ratio_h = ratio(seam_h, inner_h)
    ratio_v = ratio(seam_v, inner_v)

    checks = {
        # 环绕处的跳变不得明显超过图内最剧烈的一处相邻跳变
        "seam_h_ok": bool(ratio_h <= 1.2),
        "seam_v_ok": bool(ratio_v <= 1.2),
        "square": bool(abs(w - h) <= max(2, int(0.02 * max(w, h)))),
        "not_blank": bool(float(arr.std()) > 2.0),
    }
    hint = None
    if not (checks["seam_h_ok"] and checks["seam_v_ok"]):
        worse = "水平" if ratio_h > ratio_v else "垂直"
        hint = (
            "%s方向有接缝（环绕差 %.1f，图内最大相邻差 %.1f，比值 %.2f，阈值 1.2）。"
            "检查四步算法是否只贴回了中央 128px 窄带（FeatherMask 28 羽化），"
            "整图贴回会把刚修好的接缝重新打散。"
            % (worse, seam_h if worse == "水平" else seam_v,
               inner_h if worse == "水平" else inner_v,
               ratio_h if worse == "水平" else ratio_v)
        )
    return {
        "ok": all(checks.values()),
        "path": str(path),
        "size": [w, h],
        "seam_grad_ratio_h": round(ratio_h, 3),
        "seam_grad_ratio_v": round(ratio_v, 3),
        "seam_abs_h": round(seam_h, 2),
        "seam_abs_v": round(seam_v, 2),
        "inner_max_h": round(inner_h, 2),
        "inner_max_v": round(inner_v, 2),
        "hint": hint,
        "checks": checks,
    }


def verify_upscale(path, min_side=None):
    """07 高清放大：尺寸必须比源图大，且不能是「放大了但糊」。"""
    path = _require(path)
    im = _load(path)
    w, h = im.size
    arr = _rgb(im).astype("float32")

    # 清晰度指标：拉普拉斯响应的方差，糊图会明显偏低
    gray = arr.mean(axis=2)
    lap = (
        -4.0 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
    )
    sharpness = float(lap.var())

    checks = {
        "big_side": bool(max(w, h) >= (min_side or 1024)),
        "not_blank": bool(float(arr.std()) > 2.0),
        # 放大图必须有真实高频细节，糊成一团的方差会很低
        "has_detail": bool(sharpness >= 20.0),
    }
    hint = None
    if not checks["has_detail"]:
        hint = (
            "拉普拉斯方差 %.1f 偏低（阈值 20），放大后像被抹平了。"
            "分支 A 检查是否误用了 ImageScale 而没走 ImageUpscaleWithModel；"
            "分支 B 检查 denoise 是否被调到 0.25 以上。" % sharpness
        )
    return {
        "ok": all(checks.values()),
        "path": str(path),
        "size": [w, h],
        "sharpness": round(sharpness, 2),
        "hint": hint,
        "checks": checks,
    }


def verify_turnaround(path):
    """04 三视图：宽画布、三段主体（正/侧/背）都要有内容。"""
    path = _require(path)
    im = _load(path)
    w, h = im.size
    arr = _rgb(im).astype("float32")
    gray = arr.mean(axis=2)

    # 背景通常是白/浅色：按「明显偏离背景亮度」找主体
    bg = float(np.median(gray))
    mask = np.abs(gray - bg) > 18.0
    coverage = _nz(mask.sum() / (w * h))

    # 三等分，每段都要有主体
    thirds = []
    for i in range(3):
        seg = mask[:, i * w // 3 : (i + 1) * w // 3]
        thirds.append(_nz(seg.sum() / max(1, seg.size)))

    checks = {
        "wide": bool(w > h),
        "three_panels": bool(all(t >= 0.02 for t in thirds)),
        "coverage_in_range": bool(0.02 <= coverage <= 0.85),
        "not_blank": bool(float(arr.std()) > 2.0),
    }
    hint = None
    missing = [("左", thirds[0]), ("中", thirds[1]), ("右", thirds[2])]
    gaps = [n for n, v in missing if v < 0.02]
    if gaps:
        hint = (
            "%s 三分之一几乎没有主体（各段占比 %s）。三视图必须一张宽画布单次出图；"
            "拆成多个 KSampler 会把同一角色画成不同的人，也会出现空段。"
            % ("/".join(gaps), [round(t, 3) for t in thirds])
        )
    elif not checks["wide"]:
        hint = "画布不是横版（%dx%d）：04 应为 1152x768 横版。" % (w, h)
    return {
        "ok": all(checks.values()),
        "path": str(path),
        "size": [w, h],
        "coverage": coverage,
        "thirds_coverage": [round(t, 4) for t in thirds],
        "background_lum": round(bg, 2),
        "hint": hint,
        "checks": checks,
    }



def verify_lineart(path):
    """03 线稿上色：必须真的上了色（有饱和度），且不能大面积留白纸。"""
    path = _require(path)
    im = _load(path)
    w, h = im.size
    rgb = _rgb(im).astype("float32")

    # 白纸残留在「线稿未覆盖」或「上色失败」时出现：近白像素占比过高就判不过
    paper = (rgb.min(axis=2) >= 238.0)
    paper_frac = _nz(paper.sum() / (w * h))

    # 上色成功必然有彩度：HSV 的 S 通道中位数
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    sat_med = _nz(float(np.median(sat)))
    sat_p90 = _nz(float(np.percentile(sat, 90)))

    checks = {
        "paper_low": bool(paper_frac <= 0.35),
        "colored": bool(sat_p90 >= 0.12),
        "not_blank": bool(float(rgb.std()) > 2.0),
    }
    hint = None
    if not checks["paper_low"]:
        hint = (
            "近白像素占 %.1f%%，超过 35%%：上色没铺开或线稿大面积留白。"
            "检查 03 的 ControlNet 强度（线稿两路应分别 1.0 / 0.6）与 denoise 是否被调低。" % (paper_frac * 100)
        )
    elif not checks["colored"]:
        hint = (
            "彩度 p90 只有 %.3f（需 >= 0.12）：输出接近灰度，等于没上色。"
            "正向词里补 flat colors / vibrant colors，并确认 LoadImage 喂的是线稿而不是彩色图。" % sat_p90
        )
    return {
        "ok": all(checks.values()),
        "path": str(path),
        "size": [w, h],
        "paper_frac": paper_frac,
        "sat_median": sat_med,
        "sat_p90": sat_p90,
        "hint": hint,
        "checks": checks,
    }


VERIFIERS = {
    "alpha": verify_alpha,
    "flat": verify_flat,
    "panel": verify_panel,
    "mc": verify_nineslice,
    "fx": verify_fx,
    "icon": verify_icon,
    "tile": verify_tile,
    "upscale": verify_upscale,
    "turnaround": verify_turnaround,
    "lineart": verify_lineart,
}


def verify(kind, paths, corner=DEFAULT_CORNER):
    if kind == "parts":
        if len(paths) < 2:
            return {"ok": False, "error": "parts 需要 head 和 body 两个路径"}
        return {"kind": kind, **verify_parts(paths[0], paths[1])}
    fn = VERIFIERS.get(kind)
    if fn is None:
        return {
            "ok": False,
            "error": "未知验收类型: %s；可用: %s"
            % (kind, " / ".join(sorted(list(VERIFIERS) + ["parts"]))),
        }
    if not paths:
        return {"ok": False, "error": "%s 需要一个图片路径" % kind}
    try:
        out = fn(paths[0]) if kind != "panel" else fn(paths[0], corner)
    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - 验收层不许把异常抛回宿主
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
    return {"kind": kind, **out}
