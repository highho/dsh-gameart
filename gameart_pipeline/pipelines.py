# -*- coding: utf-8 -*-
"""08~11 四条产线：场景背景 / UI九宫格元素板 / 角色部件分层(SAM拆件) / 光效粒子贴图
统一日式萌系风格。用两代底模：00~07 走 SD1.5(anything-v5-PrtRE)，
08/09/11 走 SDXL(animagine-xl-3.1)，10 走 SAM 分割不加载底模。
用法:
  python pipelines2.py build          # 生成 API+UI JSON 并本地校验
  python pipelines2.py run 08 09      # 提交实测
"""
import os, sys, json, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    from . import wf_lib
    from .wf_lib import Graph
except ImportError:  # 允许 python pipelines.py 独立运行
    import wf_lib
    from wf_lib import Graph

# 输出位置：默认写插件包内的 workflows/ 与 api/，可用环境变量改写
WF_DIR = os.environ.get("COMFY_WF_DIR", os.path.join(ROOT, "workflows"))
API_DIR = os.environ.get("COMFY_API_DIR", os.path.join(ROOT, "api"))
CKPT = "animagine-xl-3.1.safetensors"
# 03/06 依赖 SD1.5 ControlNet（本机无对应 SDXL 权重），必须配套 SD1.5 底模，不能混用 SDXL
CKPT_SD15 = "anything-v5-PrtRE.safetensors"
SEED = 20261111

NEG = ("lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, "
       "fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, "
       "signature, watermark, username, blurry, artist name, ugly, deformed")

QUALITY = "masterpiece, best quality, amazing quality, very aesthetic, absurdres"

# 00~07（SD1.5 时代）共用的一套提示词前缀/负面词，与原始工作流逐字一致
POS_BASE = ("masterpiece, best quality, highly detailed, official art, clean lineart, "
            "anime game art, cel shading, sharp focus, vibrant colors")
NEG_BASE = ("lowres, worst quality, low quality, normal quality, blurry, jpeg artifacts, "
            "bad anatomy, bad hands, bad proportions, extra digits, fewer digits, "
            "missing fingers, watermark, signature, username, text, logo, cropped, "
            "out of frame, border, frame, multiple views, multiple girls, sketch, "
            "monochrome, greyscale")


# ============================================================ 08 场景背景
def build_08():
    g = Graph("08_Background")
    pos_text = (QUALITY + ", no humans, scenery, japanese fantasy village at sunset, "
                "cherry blossom trees, stone lantern, torii gate, wooden houses, "
                "warm golden sunlight, volumetric light, lens flare, depth of field, "
                "detailed background, anime style, colorful, game background art")
    neg_text = (NEG + ", humans, person, character, 1girl, 1boy, portrait, "
                "text, logo, ui, frame, border, split screen, collage")

    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": CKPT})
    pos = g.add("CLIPTextEncode", {"text": pos_text}, {"clip": ckpt.out(1)})
    neg = g.add("CLIPTextEncode", {"text": neg_text}, {"clip": ckpt.out(1)})
    lat = g.add("EmptyLatentImage", {"width": 1344, "height": 768, "batch_size": 2})
    ks = g.add("KSampler", {"seed": SEED, "steps": 28, "cfg": 7.0, "sampler_name": "dpmpp_2m",
                            "scheduler": "karras", "denoise": 1.0},
               {"model": ckpt.out(0), "positive": pos.out(0), "negative": neg.out(0),
                "latent_image": lat.out(0)})
    dec = g.add("VAEDecode", {"samples": ks.out(0), "vae": ckpt.out(2)})
    # 等比放大到 1920 宽后中心裁到 1920x1080（16:9 交付尺寸）
    sc = g.add("ImageScale", {"upscale_method": "lanczos", "width": 1920, "height": 1080,
                              "crop": "center"}, {"image": dec.out(0)})
    g.add("SaveImage", {"filename_prefix": "GameArt/08_Background/bg_scene"}, {"images": sc.out(0)})

    g.notes.append({
        "title": "08 场景背景产线",
        "text": ("用途：游戏场景背景（16:9 交付 1920x1080）。\n"
                 "链路：SDXL 1344x768 直出(batch2) → lanczos 等比放大并中心裁到 1920x1080。\n"
                 "调参：dpmpp_2m+karras / steps 26~30 / cfg 6.5~7.5。\n"
                 "换场景：改 positive 中的 scenery 描述（森林/雪原/和风街道/地牢…），保留 no humans + 无 UI 负面词。\n"
                 "可选增强：接 LoadImage→Canny(0.4/0.8)→ControlNetLoader(controlnet-union-sdxl-promax)"
                 "→ControlNetApplyAdvanced(strength 0.5, end_percent 0.7) 锁构图，把结果接到 KSampler 的 positive/negative。\n"
                 "禁止：negative 里务必保留 humans/portrait，避免出人物。"),
        "x": -1400, "y": 80, "w": 520, "h": 240})
    return g


# ============================================================ 09 UI 元素板 + 九宫格面板
DIAG09 = False


def build_09():
    g = Graph("09_UI_NineSlice")
    clip = None
    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": CKPT})
    clip = ckpt.out(1)

    def gen(pos_text, neg_text, seed, steps):
        p = g.add("CLIPTextEncode", {"text": pos_text}, {"clip": clip})
        n = g.add("CLIPTextEncode", {"text": neg_text}, {"clip": clip})
        lat = g.add("EmptyLatentImage", {"width": 1024, "height": 1024, "batch_size": 1})
        ks = g.add("KSampler", {"seed": seed, "steps": steps, "cfg": 7.0, "sampler_name": "dpmpp_2m",
                                "scheduler": "karras", "denoise": 1.0},
                   {"model": ckpt.out(0), "positive": p.out(0), "negative": n.out(0),
                    "latent_image": lat.out(0)})
        return g.add("VAEDecode", {"samples": ks.out(0), "vae": ckpt.out(2)})

    def to_rgba(dec):
        r = g.add("RMBG", {"model": "RMBG-2.0", "sensitivity": 1.0, "process_res": 1024,
                           "mask_blur": 0, "mask_offset": 0, "invert_output": False,
                           "refine_foreground": True, "background": "Alpha",
                           "background_color": "#222222"}, {"image": dec.out(0)})
        # JoinImageWithAlpha 内部执行 alpha = 1 - mask
        i = g.add("InvertMask", {}, {"mask": r.out(1)})
        return g.add("JoinImageWithAlpha", {"image": r.out(0), "alpha": i.out(0)})

    # ---------- A. UI 元素板：一板多控件，供美术直接切片用 ----------
    pos_a = (QUALITY + ", game ui element sheet, japanese fantasy ui kit, "
             "several separate ui widgets arranged on one canvas: rounded button, progress bar, "
             "small icon frame, slider track, tooltip box, "
             "gold trim, cherry blossom ornament, semi transparent dark panel, "
             "flat color, clean vector-like shapes, crisp edges, evenly spaced, pure white background")
    neg_a = (NEG + ", character, person, 1girl, face, hands, text, letters, kanji, "
             "watermark, photo, 3d render, noisy texture, overlapping widgets, collage of photos, "
             "single large panel filling the canvas")
    sheet = to_rgba(gen(pos_a, neg_a, SEED + 1, 28))
    g.add("SaveImage", {"filename_prefix": "GameArt/09_UI/ui_element_sheet"}, {"images": sheet.out(0)})

    # ---------- B. 九宫格面板：满幅方正结构，专供 9-slice 拉伸 ----------
    pos_b = (QUALITY + ", game ui dialog panel, ONE single square panel, nine-slice template, "
             "perfectly rectangular and centered, fills the whole canvas edge to edge, "
             "uniform thick ornamental border on all four sides, border width about one sixth of canvas, "
             "corner radius 64, the entire interior filled with solid dark navy blue, "
             "the interior is clearly much darker than the pure white background, "
             "no pattern and no illustration inside, "
             "gold trim and cherry blossom ornament only along the border, "
             "flat color, clean vector-like shapes, crisp straight edges, pure white background around the panel")
    neg_b = (NEG + ", character, person, 1girl, face, text, letters, kanji, watermark, photo, "
             "3d render, noisy texture, multiple panels, collage, bevel, drop shadow, "
             "white margin, white frame ring, off center, tilted, perspective, "
             "pattern in the center, illustration inside panel, picture frame with photo, "
             "white interior, white fill, light gray fill, hollow frame, empty white box, outline only")
    dec_b = gen(pos_b, neg_b, SEED + 2, 30)
    # 面板内部对白底色键不敏感（模型给的背景并非纯白），改用 RMBG 出前景 mask
    rmbg_b = g.add("RMBG", {"model": "RMBG-2.0", "sensitivity": 1.0, "process_res": 1024,
                            "mask_blur": 0, "mask_offset": 0, "invert_output": False,
                            "refine_foreground": True, "background": "Alpha",
                            "background_color": "#222222"}, {"image": dec_b.out(0)})
    # 强制四边留白，保证面板描边不贴着画布出血
    # JoinImageWithAlpha 内部 alpha=1-mask，所以这里要喂「背景 mask」：RMBG 前景取反 + 外环 26px 强制当背景
    INSET = 26
    fg = rmbg_b.out(1)
    bg = g.add("InvertMask", {}, {"mask": fg})
    base0 = g.add("SolidMask", {"value": 0.0, "width": 1024, "height": 1024})
    inner = g.add("SolidMask", {"value": 1.0, "width": 1024 - 2 * INSET, "height": 1024 - 2 * INSET})
    inset_fg = g.add("MaskComposite", {"x": INSET, "y": INSET, "operation": "add"},
                     {"destination": base0.out(0), "source": inner.out(0)})
    inset_bg = g.add("InvertMask", {}, {"mask": inset_fg.out(0)})
    # 面板是规整矩形时，几何 alpha 比 RMBG 更可靠（RMBG 在个别角会误判为背景），直接用内缩矩形
    a_panel = inset_bg
    panel = g.add("JoinImageWithAlpha", {"image": dec_b.out(0), "alpha": a_panel.out(0)})
    if DIAG09:
        g.add("SaveImage", {"filename_prefix": "GameArt/diag/d09_dec"}, {"images": dec_b.out(0)})
        g.add("SaveImage", {"filename_prefix": "GameArt/diag/d09_cmask"},
              {"images": g.add("MaskToImage", {}, {"mask": fg}).out(0)})
        g.add("SaveImage", {"filename_prefix": "GameArt/diag/d09_amask"},
              {"images": g.add("MaskToImage", {}, {"mask": a_panel.out(0)}).out(0)})
    g.add("SaveImage", {"filename_prefix": "GameArt/09_UI/ui_panel_9slice"}, {"images": panel.out(0)})

    # 九宫格切分：角/边块取 C=160，保证落在边框带内（边框约 1/6 画布宽）
    S, C = 1024, 160
    M = S - 2 * C
    tiles = [
        ("tl", 0, 0, C, C), ("tc", C, 0, M, C), ("tr", S - C, 0, C, C),
        ("ml", 0, C, C, M), ("mc", C, C, M, M), ("mr", S - C, C, C, M),
        ("bl", 0, S - C, C, C), ("bc", C, S - C, M, C), ("br", S - C, S - C, C, C),
    ]
    # 中心块必须绝对纯色才能双向拉伸：取边框内侧一小块 → 缩到 1x1 得平均色 → 放大回 M
    core = g.add("ImageCrop", {"width": 64, "height": 64, "x": S // 2 - 96, "y": S // 2 - 96},
                 {"image": panel.out(0)})
    c1 = g.add("ImageScale", {"upscale_method": "bilinear", "width": 1, "height": 1, "crop": "disabled"},
               {"image": core.out(0)})
    flat = g.add("ImageScale", {"upscale_method": "bilinear", "width": M, "height": M, "crop": "disabled"},
                 {"image": c1.out(0)})
    ones = g.add("SolidMask", {"value": 1.0, "width": M, "height": M})
    zero = g.add("InvertMask", {}, {"mask": ones.out(0)})
    mc_img = g.add("JoinImageWithAlpha", {"image": flat.out(0), "alpha": zero.out(0)})

    for name, x, y, w, h in tiles:
        if name == "mc":
            src = mc_img
        else:
            src = g.add("ImageCrop", {"width": w, "height": h, "x": x, "y": y},
                        {"image": panel.out(0)})
        g.add("SaveImage", {"filename_prefix": "GameArt/09_UI/9slice_%s_%dx%d" % (name, w, h)},
              {"images": src.out(0)})

    g.notes.append({
        "title": "09 UI 元素板 + 九宫格面板（双分支）",
        "text": ("【09 UI 元素板 + 九宫格面板（两条分支）】\n用途：日式萌系 UI。分支 A 出一张「UI 元素板」（按钮/进度条/图标框/滑块/提示框排一板，供美术直接切片）；分支 B 出一张「九宫格面板」并切成 9 块，供引擎 9-slice 拉伸。\n为什么要分两条：实测把元素板直接按九宫格硬切，切块会穿过板内各控件的图案，tl/mc 全是断裂线条、无法平铺。9-slice 必须用「结构规整的单一面板」才切得对。\n分支 B 最终链路：SDXL 1024 出面板 → 几何 alpha（SolidMask 全 0 + 内缩 INSET=26 的实心矩形，MaskComposite add 后 InvertMask）→ JoinImageWithAlpha → ImageCrop 按 3x3 切 9 块；中心块取面板中心区域平均色重建为绝对纯色。\n为什么不用抠图：1) 白底色键（AILab_ColorToMask threshold 12/22）实测失效——SDXL 不保证纯白背景，实测面板图角落 RGB≈0.228 是深色，全图被判成背景、面板输出全透明（nz=0.0000）；2) RMBG 也不稳——实测 00005 那张左下角块被误判为背景（bl nz=0.0012）。面板是规整矩形时，几何 alpha 才是唯一可靠解。\n切块规则：C=160，tc/bc 704x160 横向拉伸，ml/mr 160x704 纵向拉伸，mc 704x704 双向拉伸；中心块 alpha 铺满、RGB 唯一色数=1（可任意拉伸不变形）。\n实测(00006)：面板 nz=0.8481，四角块 nz=0.7014、四边块 nz=0.8375、中心块 nz=1.0000 且唯一色数=1；用 9 块合成 1280x720 后中心 alpha=1.000、边框连贯无接缝、目检合格。\n已知限制：几何 alpha 出来是直角，四角不再带圆角；需要圆角请在引擎侧叠一张圆角遮罩。面板若生成得偏上偏右，切块会有一侧偏薄，重出即可。\n验收标准：9 块全部有内容（nz>0.5）、mc 唯一色数=1、1280x720 合成图边框连贯。"),
        "x": -1400, "y": 80, "w": 580, "h": 300})
    return g


# ============================================================ 10 角色部件分层（SAM 拆件）
def build_10():
    g = Graph("10_Character_Parts")
    INPUT_IMG = "sprite_alpha_00002_.png"

    img = g.add("LoadImage", {"image": INPUT_IMG})
    sam = g.add("SAMLoader", {"model_name": "sam_vit_b_01ec64.pth", "device_mode": "Prefer GPU"})

    def det_block(model, segs_cls_key, threshold, dilation, sam_thr):
        det = g.add("UltralyticsDetectorProvider", {"model_name": model})
        if segs_cls_key == "bbox":
            segs = g.add("BboxDetectorSEGS",
                         {"threshold": threshold, "dilation": dilation, "crop_factor": 3.0,
                          "drop_size": 10, "labels": "all"},
                         {"bbox_detector": det.out(0), "image": img.out(0)})
        else:
            segs = g.add("SegmDetectorSEGS",
                         {"threshold": threshold, "dilation": dilation, "crop_factor": 3.0,
                          "drop_size": 10, "labels": "all"},
                         {"segm_detector": det.out(1), "image": img.out(0)})
        return g.add("SAMDetectorCombined",
                     {"detection_hint": "center-1", "dilation": 0, "threshold": sam_thr,
                      "bbox_expansion": 0, "mask_hint_threshold": 0.7,
                      "mask_hint_use_negative": "False"},
                     {"sam_model": sam.out(0), "segs": segs.out(0), "image": img.out(0)})

    # hand_yolov8s 是 COCO 真人手模型，对二次元立绘误检率高（实测把领口装饰当成手），默认关闭
    ENABLE_HAND = False
    m_head = det_block("bbox/face_yolov8m.pt", "bbox", 0.30, 12, 0.88)
    m_hand = det_block("bbox/hand_yolov8s.pt", "bbox", 0.45, 8, 0.85) if ENABLE_HAND else None

    # 前景 = 源图 alpha ∪ RMBG 前景。源图已是透明 PNG，其 alpha 最忠实；
    # 实测单用 RMBG 会把左下裙摆整块 (x0-160,y560-780，源 alpha 0.996) 判成背景，漏掉 7.97% 前景。
    rmbg = g.add("RMBG", {"model": "RMBG-2.0", "sensitivity": 1.0, "process_res": 1024,
                          "mask_blur": 0, "mask_offset": 0, "invert_output": False,
                          "refine_foreground": True, "background": "Alpha",
                          "background_color": "#222222"}, {"image": img.out(0)})
    # LoadImage 的 out1 是 MASK = 1-alpha，取反才是正向前景
    src_a = g.add("InvertMask", {}, {"mask": img.out(1)})
    fg = g.add("MaskComposite", {"x": 0, "y": 0, "operation": "add"},
               {"destination": src_a.out(0), "source": rmbg.out(1)})
    # 头部外扩 70px 覆盖头发：SAM 只会沿脸部轮廓分割，不扩拿不到发梢
    m_head_g = g.add("GrowMask", {"expand": 25, "tapered_corners": True}, {"mask": m_head.out(0)})

    # 身体 = 前景 - 头（- 手）
    body = g.add("MaskComposite", {"x": 0, "y": 0, "operation": "subtract"},
                 {"destination": fg.out(0), "source": m_head_g.out(0)})
    parts = [("head", m_head_g)]
    if m_hand is not None:
        body = g.add("MaskComposite", {"x": 0, "y": 0, "operation": "subtract"},
                     {"destination": body.out(0), "source": m_hand.out(0)})
        parts.append(("hand", m_hand))
    parts.append(("body", body))

    # 蒙版外 RGB 清成黑色：否则透明区仍残留全身体像素，Spine/引擎做边缘插值时会拉出色晕
    empty = g.add("EmptyImage", {"width": 640, "height": 896, "batch_size": 1, "color": 0})

    for tag, amask in parts:
        # 与前景求交，防蒙版出界
        mm = g.add("MaskComposite", {"x": 0, "y": 0, "operation": "multiply"},
                   {"destination": amask.out(0), "source": fg.out(0)})
        cut = g.add("ImageCompositeMasked", {"x": 0, "y": 0, "resize_source": False},
                    {"destination": empty.out(0), "source": img.out(0), "mask": mm.out(0)})
        # JoinImageWithAlpha 内部执行 alpha = 1 - mask，故合成前必须 InvertMask
        inv = g.add("InvertMask", {}, {"mask": mm.out(0)})
        j = g.add("JoinImageWithAlpha", {"image": cut.out(0), "alpha": inv.out(0)})
        g.add("SaveImage", {"filename_prefix": "GameArt/10_Parts/part_%s" % tag},
              {"images": j.out(0)})

    g.notes.append({
        "title": "10 角色部件分层（SAM 拆件，对接 Spine）",
        "text": ("用途：把透明立绘拆成 head / body 两层 RGBA（可选加 hand），供 Spine/DragonBones 直接绑定骨骼。\n"
                 "链路：LoadImage(RGBA立绘) → 前景 = InvertMask(源alpha) ∪ RMBG-2.0 out1 → face bbox 检测 → SAM 精修 → GrowMask+25 覆盖发梢 "
                 "→ body = 前景 - 头 → 各层再与前景求交防出界 → InvertMask → JoinImageWithAlpha 出 RGBA。\n"
                 "实测(00010/00011)：head 1.91%、body 51.85%，并集 53.76%，两层 overlap=0 完全互斥，透明区 RGB 已清零（最大 0），可直接进 Spine 建 slot。\n"
                 "关键参数：face bbox threshold 0.30 / dilation 12；SAMDetectorCombined threshold 0.88，detection_hint center-1；GrowMask expand 25。\n"
                 "必读踩坑：1) LoadImage 输出的 MASK 是 1-alpha（背景=1），取反后才是正向前景；"
                 "2) 只信 RMBG 会漏抠：左下裙摆整块 (x0-160, y560-780，源 alpha 0.996) 被 RMBG 判成背景，单用 RMBG 丢 7.97% 前景，故前景取源 alpha ∪ RMBG；"
                 "3) JoinImageWithAlpha 内部执行 alpha = 1 - mask，接前景蒙版前必须先过 InvertMask；"
                 "4) GrowMask 不能太大：expand 70 时头部件会吃到颈部与肩部装甲（目检不合格），降到 25 才只剩头+发；"
                 "5) face bbox dilation 不能过大：dilation 64 时 SAM 反而只切出纯脸（5851px），要拿发梢必须靠 GrowMask 而不是 bbox 膨胀。\n"
                 "手部开关：ENABLE_HAND 默认 False。hand_yolov8s 是 COCO 真人手模型，实测把领口装饰 (358,220)-(393,260) 误判成手（583px），"
                 "拆出来是垃圾还会挖坏 body；确实需要手层时置 True，并把 threshold 提到 0.5 以上逐张目检。\n"
                 "输入要求：input 目录下透明 PNG 立绘（当前 sprite_alpha_00002_.png，640x896 RGBA）。\n"
                 "已知限制：戴帽子/大刘海时 face 可能漏检，可把 face threshold 降到 0.2、GrowMask 提到 60。"),
        "x": -1400, "y": 80, "w": 600, "h": 270})
    return g


# ============================================================ 11 光效粒子贴图
def build_11():
    g = Graph("11_FX_Particle")
    pos_text = (QUALITY + ", glowing energy effect, bright white core with cyan and violet glow, "
                "magic particles, sparkles, light streaks, swirling aura, "
                "pure black background, high contrast, isolated effect, "
                "game visual effect asset, anime style, volumetric glow")
    neg_text = (NEG + ", character, person, 1girl, 1boy, face, scenery, background, landscape, "
                "text, watermark, frame, border, grid, gray background, white background")

    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": CKPT})
    pos = g.add("CLIPTextEncode", {"text": pos_text}, {"clip": ckpt.out(1)})
    neg = g.add("CLIPTextEncode", {"text": neg_text}, {"clip": ckpt.out(1)})
    lat = g.add("EmptyLatentImage", {"width": 1024, "height": 1024, "batch_size": 3})
    ks = g.add("KSampler", {"seed": SEED + 2, "steps": 26, "cfg": 7.5, "sampler_name": "dpmpp_2m",
                            "scheduler": "karras", "denoise": 1.0},
               {"model": ckpt.out(0), "positive": pos.out(0), "negative": neg.out(0),
                "latent_image": lat.out(0)})
    dec = g.add("VAEDecode", {"samples": ks.out(0), "vae": ckpt.out(2)})

    # 亮度→alpha：三通道相乘，黑底 0.1^3≈0.001 被压到近乎全黑，只有真发光区域才留下
    mr = g.add("ImageToMask", {"channel": "red"}, {"image": dec.out(0)})
    mg = g.add("ImageToMask", {"channel": "green"}, {"image": dec.out(0)})
    mb = g.add("ImageToMask", {"channel": "blue"}, {"image": dec.out(0)})
    m1 = g.add("MaskComposite", {"x": 0, "y": 0, "operation": "multiply"},
               {"destination": mr.out(0), "source": mg.out(0)})
    m2 = g.add("MaskComposite", {"x": 0, "y": 0, "operation": "multiply"},
               {"destination": m1.out(0), "source": mb.out(0)})
    # 自乘一次升对比：lum^2 让暗部更透、亮核更实
    m3 = g.add("MaskComposite", {"x": 0, "y": 0, "operation": "multiply"},
               {"destination": m2.out(0), "source": m2.out(0)})

    # JoinImageWithAlpha 内部执行 alpha = 1 - mask，故合成前必须 InvertMask
    inv = g.add("InvertMask", {}, {"mask": m3.out(0)})
    j = g.add("JoinImageWithAlpha", {"image": dec.out(0), "alpha": inv.out(0)})
    g.add("SaveImage", {"filename_prefix": "GameArt/11_FX/fx_energy"}, {"images": j.out(0)})

    g.notes.append({
        "title": "11 光效/粒子贴图",
        "text": ("用途：黑底光效转透明 RGBA，直接用于粒子系统/打击特效（一次性出 3 张变体）。\n"
                 "链路：SDXL 1024x1024 出黑底发光（batch3）→ 拆 R/G/B 三通道 → MaskComposite multiply 连乘得亮度 → 自乘一次升对比 → InvertMask → JoinImageWithAlpha 成 RGBA。\n"
                 "为什么用连乘而非相加：相加会把黑底 0.1+0.1+0.1=0.3 也保留，alpha 发灰；连乘 0.1^3≈0.001 直接压没，只有真发光区留下。\n"
                 "必读踩坑：JoinImageWithAlpha 内部执行 alpha = 1 - mask，接亮度蒙版前必须先过 InvertMask，否则输出整体反相。\n"
                 "调参：steps 26 / cfg 7.5；想让光更实就提高 positive 里 bright white core 的权重，想更飘就加 sparkles, thin wisps。\n"
                 "换类型：把 energy/cyan/violet 换成 fire(orange red)/ice(blue white)/lightning(purple white)/heal(green gold)。\n"
                 "注意：negative 必须保留 white background、gray background，否则底不黑、alpha 会脏。"),
        "x": -1400, "y": 80, "w": 580, "h": 240})
    return g


# ============================================================ 00 角色概念设计
def build_00():
    g = Graph("00_Character_Concept")
    pos_text = ("masterpiece, best quality, highly detailed, official art, clean lineart, "
                "anime game art, cel shading, sharp focus, vibrant colors, "
                "game character concept art, character design, full body, standing, "
                "front view, facing viewer, 1girl, silver hair, long hair, blue eyes, "
                "fantasy knight, silver plate armor, blue cape, holding longsword, "
                "determined expression, soft rim light, plain white background, "
                "high detail armor, symmetrical design")
    neg_text = ("lowres, worst quality, low quality, normal quality, blurry, jpeg artifacts, "
                "bad anatomy, bad hands, bad proportions, extra digits, fewer digits, "
                "missing fingers, watermark, signature, username, text, logo, cropped, "
                "out of frame, border, frame, multiple views, multiple girls, sketch, "
                "monochrome, greyscale")

    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": CKPT_SD15})
    pos = g.add("CLIPTextEncode", {"text": pos_text}, {"clip": ckpt.out(1)})
    neg = g.add("CLIPTextEncode", {"text": neg_text}, {"clip": ckpt.out(1)})
    lat = g.add("EmptyLatentImage", {"width": 640, "height": 896, "batch_size": 4})
    ks = g.add("KSampler", {"seed": SEED - 1, "steps": 28, "cfg": 7.0, "sampler_name": "dpmpp_2m",
                            "scheduler": "karras", "denoise": 1.0},
               {"model": ckpt.out(0), "positive": pos.out(0), "negative": neg.out(0),
                "latent_image": lat.out(0)})
    dec = g.add("VAEDecode", {"samples": ks.out(0), "vae": ckpt.out(2)})
    g.add("SaveImage", {"filename_prefix": "GameArt/00_Concept/char_concept"},
          {"images": dec.out(0)})

    g.notes.append({
        "title": "00 角色概念设计",
        "text": ("用途：出方案阶段快速铺量，一次 4 张 640x896。\\n"
                 "链路：SD1.5 640x896 batch4 → VAEDecode → SaveImage。\\n"
                 "操作位：正向按「风格标签 → 主体 → 服饰道具 → 表情 → 光照 → 背景」顺序写。\\n"
                 "batch_size：铺量建议 4，定稿前改 1 并锁 seed 微调。\\n"
                 "seed：确认构图后固定 seed，只改提示词细节做强控制。\\n"
                 "定稿后接 01 立绘透明底工作流出正式资产。"),
        "x": -1400, "y": 80, "w": 580, "h": 200})
    return g


# ============================================================ 01 立绘透明底
def build_01():
    g = Graph("01_Sprite_Alpha")
    pos_text = ("masterpiece, best quality, highly detailed, official art, clean lineart, "
                "anime game art, cel shading, sharp focus, vibrant colors, "
                "game character sprite, full body, standing, front view, 1girl, silver hair, "
                "blue eyes, fantasy knight armor, blue cape, longsword in right hand, "
                "neutral expression, T-pose ready, feet visible, soft even lighting, "
                "plain white background")
    neg_text = ("lowres, worst quality, low quality, normal quality, blurry, jpeg artifacts, "
                "bad anatomy, bad hands, bad proportions, extra digits, fewer digits, "
                "missing fingers, watermark, signature, username, text, logo, cropped, "
                "out of frame, border, frame, multiple views, multiple girls, sketch, "
                "monochrome, greyscale")

    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": CKPT_SD15})
    pos = g.add("CLIPTextEncode", {"text": pos_text}, {"clip": ckpt.out(1)})
    neg = g.add("CLIPTextEncode", {"text": neg_text}, {"clip": ckpt.out(1)})
    lat = g.add("EmptyLatentImage", {"width": 640, "height": 896, "batch_size": 1})
    ks = g.add("KSampler", {"seed": SEED, "steps": 30, "cfg": 7.5, "sampler_name": "dpmpp_2m",
                            "scheduler": "karras", "denoise": 1.0},
               {"model": ckpt.out(0), "positive": pos.out(0), "negative": neg.out(0),
                "latent_image": lat.out(0)})
    dec = g.add("VAEDecode", {"samples": ks.out(0), "vae": ckpt.out(2)})

    # BiRefNet_toonout：动漫立绘专用抠图。background=Alpha 时 out(0) 已是 RGBA，直接存
    rmbg = g.add("BiRefNetRMBG",
                 {"model": "BiRefNet_toonout", "sensitivity": 1.0, "mask_blur": 0,
                  "mask_offset": 0, "invert_output": False, "refine_foreground": True,
                  "background": "Alpha"},
                 {"image": dec.out(0)})
    g.add("SaveImage", {"filename_prefix": "GameArt/01_Sprite/sprite_alpha"},
          {"images": rmbg.out(0)})

    g.notes.append({
        "title": "01 立绘透明底",
        "text": ("用途：直接产出带 Alpha 通道的透明 PNG，可直接进引擎/UI。\\n"
                 "关键参数：\\n"
                 "- BiRefNet_toonout：动漫/游戏立绘专用抠图模型（本机已装），比通用模型边缘干净。\\n"
                 "- background = Alpha：输出 RGBA，不要改成 Color。\\n"
                 "- refine_foreground = 开启：修复半透明边缘与发丝。\\n"
                 "- 若有白边：mask_offset 调 -1 ~ -2；若吞掉发丝：mask_offset 调 +1。\\n"
                 "⚠ 本产线不要再接 InvertMask/JoinImageWithAlpha：background=Alpha 时 "
                 "BiRefNetRMBG 的 out(0) 已经是 RGBA，重复合成会引入第二次反相，把前景清空。\\n"
                 "导出规范：PNG-24 带 Alpha，尺寸与 01 产线一致 640x896（02 表情差分的脸块坐标依赖这个尺寸，改尺寸必须同步改 02 的 ImageCrop/ImageCompositeMasked 坐标）。"),
        "x": -1400, "y": 80, "w": 580, "h": 260})
    return g


# ============================================================ 02 表情差分
def build_02():
    g = Graph("02_Expression_Diff")
    INPUT_IMG = "example.png"
    # 01 立绘是 640x896，头框取顶部约 1/3；脸块 300 见方，落在 (170,70)
    CROP_W, CROP_H, CROP_X, CROP_Y = 300, 300, 170, 70
    SEED_02 = SEED + 1

    img = g.add("LoadImage", {"image": INPUT_IMG})
    crop = g.add("ImageCrop", {"width": CROP_W, "height": CROP_H, "x": CROP_X, "y": CROP_Y},
                 {"image": img.out(0)})
    up = g.add("ImageScale", {"upscale_method": "lanczos", "width": 512, "height": 512,
                              "crop": "disabled"}, {"image": crop.out(0)})

    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": CKPT_SD15})
    pos = g.add("CLIPTextEncode",
                {"text": "masterpiece, best quality, highly detailed, official art, "
                         "clean lineart, anime game art, cel shading, sharp focus, "
                         "vibrant colors, close-up face, 1girl, silver hair, blue eyes, "
                         "smiling, happy expression, open mouth, blushing cheeks, "
                         "looking at viewer, soft lighting"}, {"clip": ckpt.out(1)})
    neg = g.add("CLIPTextEncode",
                {"text": "multiple faces, cropped face, helmet covering face, deformed eyes, "
                         "distorted mouth, lowres, worst quality, low quality, "
                         "normal quality, blurry, jpeg artifacts, bad anatomy, bad hands, "
                         "bad proportions, extra digits, fewer digits, missing fingers, "
                         "watermark, signature, username, text, logo, cropped, out of frame, "
                         "border, frame, multiple views, multiple girls, sketch, "
                         "monochrome, greyscale"}, {"clip": ckpt.out(1)})
    enc = g.add("VAEEncode", {"pixels": up.out(0)}, {"vae": ckpt.out(2)})
    ks = g.add("KSampler", {"seed": SEED_02, "steps": 24, "cfg": 6.5,
                            "sampler_name": "dpmpp_2m", "scheduler": "karras",
                            "denoise": 0.35},
               {"model": ckpt.out(0), "positive": pos.out(0), "negative": neg.out(0),
                "latent_image": enc.out(0)})
    dec = g.add("VAEDecode", {"samples": ks.out(0), "vae": ckpt.out(2)})

    dn = g.add("ImageScale", {"upscale_method": "lanczos", "width": CROP_W, "height": CROP_H,
                              "crop": "disabled"}, {"image": dec.out(0)})
    # 贴回遮罩：实心矩形 → GrowMask 内缩 8px（避开块边缘重采样脏边）→ 高斯羽化
    solid = g.add("SolidMask", {"value": 1.0, "width": CROP_W, "height": CROP_H})
    grow = g.add("GrowMask", {"expand": -8, "tapered_corners": True},
                 {"mask": solid.out(0)})
    blur = g.add("ImpactGaussianBlurMask", {"kernel_size": 40, "sigma": 20.0},
                 {"mask": grow.out(0)})
    comp = g.add("ImageCompositeMasked",
                 {"x": CROP_X, "y": CROP_Y, "resize_source": False},
                 {"destination": img.out(0), "source": dn.out(0), "mask": blur.out(0)})
    g.add("SaveImage", {"filename_prefix": "GameArt/02_Expression/expr_diff"},
          {"images": comp.out(0)})

    g.notes.append({
        "title": "02 表情差分",
        "text": ("用途：同一张立绘批量出 6~12 个表情，身体像素 100% 不变，只改脸。\\n"
                 "链路：LoadImage 立绘 → ImageCrop 取脸块 → ImageScale 放大到 512 → VAEEncode → "
                 "KSampler → VAEDecode → ImageScale 缩回 300 → "
                 "ImageCompositeMasked 用【SolidMask → GrowMask(-8) → ImpactGaussianBlurMask】羽化贴回原位。\\n"
                 "⚠ 三处坐标必须一致：ImageCrop 的 x/y、ImageScale 的目标尺寸、"
                 "ImageCompositeMasked 的 x/y —— 全部 (300,300) @ (170,70)。\\n"
                 "⚠ 贴回遮罩不要换成 FeatherMask：FeatherMask 居中对齐到目标画布，"
                 "这里必须让遮罩自己贴在 (170,70)，所以走 SolidMask 定尺寸 + GrowMask 内缩 + 高斯羽化。\\n"
                 "参数：denoise 0.35~0.55（本图 0.35），越低越保脸型，越高表情变化越大；\\n"
                 "正向提示词只写表情（smile, angry, shy, surprised...），不要重复外貌描述；\\n"
                 "GrowMask expand -8：内缩 8px 避开脸块边缘，出现脏边就再减；"
                 "模糊 kernel 40/sigma 20：越大过渡越柔，出现重影就调小。\\n"
                 "表情表：neutral/smile/angry/sad/shy/surprised。\\n"
                 "⚠ 输入图用 01 产线出的 640x896 立绘；换尺寸必须同步改本图三处坐标。"),
        "x": -1400, "y": 80, "w": 580, "h": 360})
    return g


# ============================================================ 03 线稿上色
def build_03():
    g = Graph("03_Lineart_Colorize")
    INPUT_IMG = "gameart_concept_sample.png"

    img = g.add("LoadImage", {"image": INPUT_IMG})
    # 线稿预处理：统一线宽，避免原图细线在去噪中被抹掉
    pre = g.add("LineArtPreprocessor", {"coarse": "disable", "resolution": 1024},
                {"image": img.out(0)})

    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": CKPT_SD15})
    # 底模换成 SD1.5 线稿特化，ControlNet 才与权重同源
    cn = g.add("ControlNetLoader", {"control_net_name": "control_v11p_sd15_lineart_fp16.safetensors"})
    cn2 = g.add("ControlNetLoader", {"control_net_name":
                                     "control_v11p_sd15s2_lineart_anime_fp16.safetensors"})

    pos = g.add("CLIPTextEncode",
                {"text": "masterpiece, best quality, highly detailed, official art, "
                         "clean lineart, anime game art, cel shading, sharp focus, "
                         "vibrant colors, game art, anime style, flat colors, "
                         "clean shading, 1girl, fantasy warrior, full body, "
                         "detailed armor, plain background"},
                {"clip": ckpt.out(1)})
    neg = g.add("CLIPTextEncode",
                {"text": "lowres, worst quality, low quality, normal quality, blurry, "
                         "jpeg artifacts, bad anatomy, bad hands, bad proportions, "
                         "extra digits, fewer digits, missing fingers, watermark, "
                         "signature, username, text, logo, cropped, out of frame, "
                         "border, frame, multiple views, multiple girls, sketch, "
                         "monochrome, greyscale"}, {"clip": ckpt.out(1)})

    # 双层 ControlNet：第一层锁线（全程 1.0），第二层前 70% 只给结构、后段放开让颜色主导
    a1 = g.add("ControlNetApplyAdvanced",
               {"strength": 1.0, "start_percent": 0.0, "end_percent": 1.0},
               {"positive": pos.out(0), "negative": neg.out(0), "control_net": cn.out(0),
                "image": pre.out(0), "vae": ckpt.out(2)})
    a2 = g.add("ControlNetApplyAdvanced",
               {"strength": 0.6, "start_percent": 0.0, "end_percent": 0.7},
               {"positive": a1.out(0), "negative": a1.out(1), "control_net": cn2.out(0),
                "image": pre.out(0), "vae": ckpt.out(2)})

    lat = g.add("EmptyLatentImage", {"width": 640, "height": 896, "batch_size": 1})
    ks = g.add("KSampler", {"seed": SEED + 2, "steps": 30, "cfg": 7.0, "sampler_name": "dpmpp_2m",
                            "scheduler": "karras", "denoise": 1.0},
               {"model": ckpt.out(0), "positive": a2.out(0), "negative": a2.out(1),
                "latent_image": lat.out(0)})
    dec = g.add("VAEDecode", {"samples": ks.out(0), "vae": ckpt.out(2)})
    g.add("SaveImage", {"filename_prefix": "GameArt/03_Lineart/colorized"},
          {"images": dec.out(0)})

    g.notes.append({
        "title": "03 线稿上色",
        "text": ("用途：把线稿/草图快速铺成彩色稿。\\n"
                 "⚠ 本产线用 SD1.5 线稿 ControlNet（control_v11p_sd15_lineart + sd15s2_lineart_anime），"
                 "因此底模必须走 anything-v5-PrtRE，不能换 animagine-xl-3.1（跨代不兼容）。\\n"
                 "双层 ControlNet：第一层 strength 1.0 全程锁线；"
                 "第二层 strength 0.6 / end_percent 0.7，前 70% 只约束结构、后段放开让颜色自由。\\n"
                 "想保留原始线稿：改用 VAEEncode 图生图 + denoise 0.75，线稿不会被重画。\\n"
                 "denoise：0.75 保线，>0.85 会把线稿重画掉。\\n"
                 "验收：线稿结构不塌、色块干净、不出现灰蒙蒙的水洗感。"),
        "x": -1400, "y": 80, "w": 580, "h": 240})
    return g


# ============================================================ 04 三视图
def build_04():
    g = Graph("04_Turnaround_3View")
    pos_text = ("masterpiece, best quality, character turnaround sheet, "
                "three views on one canvas, front view, side profile view, "
                "back view arranged left to right, same character in all three views, "
                "identical outfit and hairstyle, full body, standing straight, t-pose, "
                "arms slightly away from body, plain flat white background, "
                "even flat lighting, no shadow, 1girl, silver hair, blue eyes, "
                "blue and white fantasy adventurer outfit, clean lineart, cel shading, "
                "game character design reference sheet")
    neg_text = ("lowres, worst quality, low quality, normal quality, blurry, jpeg artifacts, "
                "bad anatomy, bad hands, bad proportions, extra digits, fewer digits, "
                "missing fingers, watermark, signature, username, text, logo, cropped, "
                "out of frame, border, frame, multiple views, multiple girls, sketch, "
                "monochrome, greyscale, different characters, different outfits, "
                "inconsistent design, cropped, text, watermark")

    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": CKPT_SD15})
    pos = g.add("CLIPTextEncode", {"text": pos_text}, {"clip": ckpt.out(1)})
    neg = g.add("CLIPTextEncode", {"text": neg_text}, {"clip": ckpt.out(1)})

    # 一张宽画布单次出图：三个 KSampler 并行会让模型把同一角色画成三个人（已实测）
    lat = g.add("EmptyLatentImage", {"width": 768, "height": 512, "batch_size": 1})
    ks = g.add("KSampler", {"seed": SEED - 1, "steps": 30, "cfg": 7.5, "sampler_name": "dpmpp_2m",
                            "scheduler": "karras", "denoise": 1.0},
               {"model": ckpt.out(0), "positive": pos.out(0), "negative": neg.out(0),
                "latent_image": lat.out(0)})
    # 潜空间放大 1.5x 后二段低 denoise 补细节，最终 1152x768
    up = g.add("LatentUpscale", {"upscale_method": "nearest-exact", "width": 1152,
                                 "height": 768, "crop": "disabled"}, {"samples": ks.out(0)})
    ks2 = g.add("KSampler", {"seed": SEED - 1, "steps": 20, "cfg": 7.0, "sampler_name": "dpmpp_2m",
                             "scheduler": "karras", "denoise": 0.45},
                {"model": ckpt.out(0), "positive": pos.out(0), "negative": neg.out(0),
                 "latent_image": up.out(0)})
    dec = g.add("VAEDecode", {"samples": ks2.out(0), "vae": ckpt.out(2)})
    g.add("SaveImage", {"filename_prefix": "GameArt/04_Turnaround/turnaround"},
          {"images": dec.out(0)})

    g.notes.append({
        "title": "04 三视图",
        "text": ("用途：给建模/动作用的三视图设定稿（正/侧/背）。\\n"
                 "关键：必须一张宽画布单次出图。三个独立 KSampler 并行会把同一角色画成三个人（已实测确认）。\\n"
                 "链路：768x512 一次成图 → LatentUpscale ×1.5 到 1152x768 → 二段 denoise 0.45 补细节。\\n"
                 "正向必须硬写：character turnaround sheet, same character, front view / side view / back view；\\n"
                 "负向必须硬写：different characters, inconsistent design。\\n"
                 "复现同一角色：固定 seed，或把 00 选定稿作为图生图输入（denoise 0.5~0.6）。\\n"
                 "验收：三视图服装/发色/配饰一致，无第 4 个视角。"),
        "x": -1400, "y": 80, "w": 580, "h": 240})
    return g


# ============================================================ 05 道具图标
def build_05():
    g = Graph("05_Prop_Icon")
    pos_text = ("masterpiece, best quality, highly detailed, official art, clean lineart, "
                "anime game art, cel shading, sharp focus, vibrant colors, "
                "game item icon, inventory icon, one single object, centered, front view, "
                "3/4 isometric angle, magic healing potion bottle, red liquid, "
                "cork stopper, glass reflection, subtle glow, clean silhouette, "
                "plain white background, no text")
    neg_text = ("lowres, worst quality, low quality, normal quality, blurry, jpeg artifacts, "
                "bad anatomy, bad hands, bad proportions, extra digits, fewer digits, "
                "missing fingers, watermark, signature, username, text, logo, cropped, "
                "out of frame, border, frame, multiple views, multiple girls, sketch, "
                "monochrome, greyscale, multiple objects, pattern, background detail")

    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": CKPT_SD15})
    pos = g.add("CLIPTextEncode", {"text": pos_text}, {"clip": ckpt.out(1)})
    neg = g.add("CLIPTextEncode", {"text": neg_text}, {"clip": ckpt.out(1)})
    lat = g.add("EmptyLatentImage", {"width": 768, "height": 768, "batch_size": 4})
    ks = g.add("KSampler", {"seed": SEED + 3, "steps": 26, "cfg": 7.0, "sampler_name": "dpmpp_2m",
                            "scheduler": "karras", "denoise": 1.0},
               {"model": ckpt.out(0), "positive": pos.out(0), "negative": neg.out(0),
                "latent_image": lat.out(0)})
    dec = g.add("VAEDecode", {"samples": ks.out(0), "vae": ckpt.out(2)})

    # 抠图后收回到 512x512 统一图标尺寸；background=Alpha 时 out(0) 已是 RGBA
    rmbg = g.add("BiRefNetRMBG",
                 {"model": "BiRefNet_toonout", "sensitivity": 1.0, "mask_blur": 0,
                  "mask_offset": 0, "invert_output": False, "refine_foreground": True,
                  "background": "Alpha"},
                 {"image": dec.out(0)})
    sc = g.add("ImageScale", {"upscale_method": "lanczos", "width": 512, "height": 512,
                              "crop": "center"}, {"image": rmbg.out(0)})
    g.add("SaveImage", {"filename_prefix": "GameArt/05_Icon/item_icon"},
          {"images": sc.out(0)})

    g.notes.append({
        "title": "05 道具图标",
        "text": ("用途：装备/道具/材料图标，512x512 RGBA，一次 4 张候选。\\n"
                 "构图：主体占画布 70~80%，四周留 10~15% 安全边，单个物体、3/4 等距视角。\\n"
                 "正向必须写 single object；负向必须写 multiple objects, pattern, background detail。\\n"
                 "链路：SD1.5 768x768 batch4 → VAEDecode → BiRefNetRMBG(background=Alpha) "
                 "→ ImageScale lanczos 512x512 center → SaveImage。\\n"
                 "⚠ 抠图链路同 01：background=Alpha 时 out(0) 已是 RGBA，"
                 "不要再接 InvertMask/JoinImageWithAlpha（会二次反相把主体清空）。\\n"
                 "命名：GameArt/05_Icon/item_{道具名}_{品质}.png，品质用 n/r/sr/ssr。\\n"
                 "验收：主体完整不出界、背景全透（alpha==0 区域 RGB 归一）、无多余物体。"),
        "x": -1400, "y": 80, "w": 580, "h": 300})
    return g


# ============================================================ 06 无缝贴图
def build_06():
    g = Graph("06_Seamless_Tile")
    pos_text = ("masterpiece, best quality, highly detailed, official art, clean lineart, "
                "anime game art, cel shading, sharp focus, vibrant colors, "
                "seamless tileable texture, top-down view, hand-painted game texture, "
                "mossy stone bricks, cracked stone floor, green moss, subtle dirt, "
                "even lighting, no shadow gradient, no vignette")
    neg_text = ("lowres, worst quality, low quality, normal quality, blurry, jpeg artifacts, "
                "bad anatomy, bad hands, bad proportions, extra digits, fewer digits, "
                "missing fingers, watermark, signature, username, text, logo, cropped, "
                "out of frame, border, frame, multiple views, multiple girls, sketch, "
                "monochrome, greyscale, border, frame, vignette, gradient")

    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": CKPT_SD15})
    pos = g.add("CLIPTextEncode", {"text": pos_text}, {"clip": ckpt.out(1)})
    neg = g.add("CLIPTextEncode", {"text": neg_text}, {"clip": ckpt.out(1)})
    cn = g.add("ControlNetLoader",
               {"control_net_name": "control_v11f1e_sd15_tile_fp16.safetensors"})

    # 步骤 1：先生成普通材质
    lat = g.add("EmptyLatentImage", {"width": 512, "height": 512, "batch_size": 1})
    ks = g.add("KSampler", {"seed": SEED + 4, "steps": 26, "cfg": 7.0, "sampler_name": "dpmpp_2m",
                            "scheduler": "karras", "denoise": 1.0},
               {"model": ckpt.out(0), "positive": pos.out(0), "negative": neg.out(0),
                "latent_image": lat.out(0)})
    dec = g.add("VAEDecode", {"samples": ks.out(0), "vae": ckpt.out(2)})

    # 步骤 2：水平环绕滚动 50%——左右半换位，原左右边缘接缝被移到中央竖线 x=256
    base = g.add("EmptyImage", {"width": 512, "height": 512, "batch_size": 1, "color": 0})
    crop_l = g.add("ImageCrop", {"width": 256, "height": 512, "x": 0, "y": 0},
                   {"image": dec.out(0)})
    crop_r = g.add("ImageCrop", {"width": 256, "height": 512, "x": 256, "y": 0},
                   {"image": dec.out(0)})
    half_r = g.add("ImageCompositeMasked", {"x": 0, "y": 0, "resize_source": False},
                   {"destination": base.out(0), "source": crop_r.out(0)})
    shifted_h = g.add("ImageCompositeMasked", {"x": 256, "y": 0, "resize_source": False},
                      {"destination": half_r.out(0), "source": crop_l.out(0)})

    # 步骤 3：tile ControlNet 重绘全图，但只把中央 128px 竖带羽化贴回，两侧边缘像素不动
    cn_apply = g.add("ControlNetApplyAdvanced",
                     {"strength": 0.85, "start_percent": 0.0, "end_percent": 1.0},
                     {"positive": pos.out(0), "negative": neg.out(0), "control_net": cn.out(0),
                      "image": shifted_h.out(0), "vae": ckpt.out(2)})
    enc_h = g.add("VAEEncode", {"pixels": shifted_h.out(0)}, {"vae": ckpt.out(2)})
    ks_h = g.add("KSampler", {"seed": SEED + 5, "steps": 26, "cfg": 6.5,
                              "sampler_name": "dpmpp_2m", "scheduler": "karras",
                              "denoise": 0.62},
                 {"model": ckpt.out(0), "positive": cn_apply.out(0),
                  "negative": cn_apply.out(1), "latent_image": enc_h.out(0)})
    dec_h = g.add("VAEDecode", {"samples": ks_h.out(0), "vae": ckpt.out(2)})
    band_v = g.add("ImageCrop", {"width": 128, "height": 512, "x": 192, "y": 0},
                   {"image": dec_h.out(0)})
    mask_v_src = g.add("SolidMask", {"value": 1.0, "width": 128, "height": 512})
    mask_v = g.add("FeatherMask", {"left": 28, "top": 0, "right": 28, "bottom": 0},
                   {"mask": mask_v_src.out(0)})
    fixed_h = g.add("ImageCompositeMasked", {"x": 192, "y": 0, "resize_source": False},
                    {"destination": shifted_h.out(0), "source": band_v.out(0),
                     "mask": mask_v.out(0)})

    # 步骤 4：垂直方向重复——上下半换位 + 中央 128px 横带贴回
    crop_t = g.add("ImageCrop", {"width": 512, "height": 256, "x": 0, "y": 0},
                   {"image": fixed_h.out(0)})
    crop_b = g.add("ImageCrop", {"width": 512, "height": 256, "x": 0, "y": 256},
                   {"image": fixed_h.out(0)})
    base2 = g.add("EmptyImage", {"width": 512, "height": 512, "batch_size": 1, "color": 0})
    half_b = g.add("ImageCompositeMasked", {"x": 0, "y": 0, "resize_source": False},
                   {"destination": base2.out(0), "source": crop_b.out(0)})
    shifted_v = g.add("ImageCompositeMasked", {"x": 0, "y": 256, "resize_source": False},
                      {"destination": half_b.out(0), "source": crop_t.out(0)})

    cn_apply2 = g.add("ControlNetApplyAdvanced",
                      {"strength": 0.85, "start_percent": 0.0, "end_percent": 1.0},
                      {"positive": pos.out(0), "negative": neg.out(0), "control_net": cn.out(0),
                       "image": shifted_v.out(0), "vae": ckpt.out(2)})
    enc_v = g.add("VAEEncode", {"pixels": shifted_v.out(0)}, {"vae": ckpt.out(2)})
    ks_v = g.add("KSampler", {"seed": SEED + 6, "steps": 26, "cfg": 6.5,
                              "sampler_name": "dpmpp_2m", "scheduler": "karras",
                              "denoise": 0.58},
                 {"model": ckpt.out(0), "positive": cn_apply2.out(0),
                  "negative": cn_apply2.out(1), "latent_image": enc_v.out(0)})
    dec_v = g.add("VAEDecode", {"samples": ks_v.out(0), "vae": ckpt.out(2)})
    band_h = g.add("ImageCrop", {"width": 512, "height": 128, "x": 0, "y": 192},
                   {"image": dec_v.out(0)})
    mask_h_src = g.add("SolidMask", {"value": 1.0, "width": 512, "height": 128})
    mask_h = g.add("FeatherMask", {"left": 0, "top": 28, "right": 0, "bottom": 28},
                   {"mask": mask_h_src.out(0)})
    fixed_v = g.add("ImageCompositeMasked", {"x": 0, "y": 192, "resize_source": False},
                    {"destination": shifted_v.out(0), "source": band_h.out(0),
                     "mask": mask_h.out(0)})

    g.add("SaveImage", {"filename_prefix": "GameArt/06_Tile/tile_seamless_512"},
          {"images": fixed_v.out(0)})

    g.notes.append({
        "title": "06 无缝贴图（四向平铺）",
        "text": ("用途：地块/墙面/地面等可平铺材质，512x512 四向无缝，可直接进引擎 Tilemap。\\n"
                 "四步原理（节点别删）：\\n"
                 "1) 先生成普通材质；\\n"
                 "2) 水平环绕滚动 50%%（左右半换位）——原左右边缘的接缝被移到画面中央竖线 x=256；\\n"
                 "3) tile ControlNet 重绘全图，但只把中央 128px 竖带羽化贴回，两侧边缘像素一个不动 "
                 "→ 此时左右边缘天然连续，水平方向无缝；\\n"
                 "4) 垂直方向重复同样操作（上下半换位 + 中央 128px 横带贴回）→ 四向无缝。\\n"
                 "⚠ 为什么必须只贴窄带：整图贴回会重新采样边缘像素，第一遍修好的无缝会被破坏。"
                 "这是上一版失败的原因，务必保留 FeatherMask 与 band 裁剪。\\n"
                 "调参：重绘 denoise 横 0.62 / 纵 0.58——低于 0.5 缝补不掉，高于 0.7 图案糊；\\n"
                 "band 宽 128、羽化 28——接缝必须落在羽化后的实心区内；tile ControlNet strength 0.85。\\n"
                 "⚠ 本产线依赖 SD1.5 tile ControlNet，底模必须 anything-v5-PrtRE。\\n"
                 "验收：3x3 平铺看是否出现网格线；或算接缝梯度比，≤1.5 视为无缝。"),
        "x": -1400, "y": 80, "w": 580, "h": 340})
    return g


# ============================================================ 07 高清放大
def build_07():
    g = Graph("07_HD_Upscale")
    INPUT_IMG = "example.png"
    TARGET_W, TARGET_H = 1536, 1536

    img = g.add("LoadImage", {"image": INPUT_IMG})
    up = g.add("UpscaleModelLoader", {"model_name": "RealESRGAN_x4plus_anime_6B.pth"})
    iu = g.add("ImageUpscaleWithModel", {}, {"upscale_model": up.out(0), "image": img.out(0)})
    # 4x 出来后用 lanczos 收回到目标尺寸，不上采样重绘（保原图锐度，适合已定稿资产）
    sc = g.add("ImageScale", {"upscale_method": "lanczos", "width": TARGET_W,
                              "height": TARGET_H, "crop": "disabled"}, {"image": iu.out(0)})
    g.add("SaveImage", {"filename_prefix": "GameArt/07_Upscale/hd_sharp"},
          {"images": sc.out(0)})

    # ---- B 分支 hd_detail：分块重绘加细节 ----
    # ⚠ denoise 必须 < 0.25；实测 0.30 + seam_fix 0.35 会把整图糊掉，seam_fix 必须关掉
    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": CKPT_SD15})
    pos = g.add("CLIPTextEncode",
                {"text": POS_BASE + ", game art, 1girl, silver hair, fantasy armor, "
                         "high detail, sharp lines"}, {"clip": ckpt.out(1)})
    neg = g.add("CLIPTextEncode", {"text": NEG_BASE}, {"clip": ckpt.out(1)})
    ud = g.add("UltimateSDUpscale",
               {"upscale_by": 2.0, "seed": SEED + 6, "steps": 18, "cfg": 6.0,
                "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 0.22,
                "mode_type": "Linear", "tile_width": 768, "tile_height": 768,
                "mask_blur": 8, "tile_padding": 32, "seam_fix_mode": "None",
                "seam_fix_denoise": 0.3, "seam_fix_width": 64,
                "seam_fix_mask_blur": 8, "seam_fix_padding": 16,
                "force_uniform_tiles": True, "tiled_decode": False, "batch_size": 1},
               {"image": img.out(0), "model": ckpt.out(0), "positive": pos.out(0),
                "negative": neg.out(0), "vae": ckpt.out(2),
                "upscale_model": up.out(0)})
    g.add("SaveImage", {"filename_prefix": "GameArt/07_Upscale/hd_detail"},
          {"images": ud.out(0)})

    g.notes.append({
        "title": "07 高清放大（A/B 双分支）",
        "text": ("用途：已定稿资产放大，两条分支二选一，按需要删掉另一条 SaveImage 即可。\\n"
                 "【A 分支 hd_sharp｜保真】LoadImage → UpscaleModelLoader"
                 "(RealESRGAN_x4plus_anime_6B) → ImageUpscaleWithModel 4x → "
                 "ImageScale lanczos 收到目标尺寸。纯超分不重绘，不引入新细节、不改变画面内容。\\n"
                 "【B 分支 hd_detail｜补细节】UltimateSDUpscale 分块重绘 2x，tile 768x768。\\n"
                 "⚠ B 分支 denoise 必须 < 0.25（本图 0.22）。实测 0.30 + seam_fix 0.30 会把整图糊掉，"
                 "所以 seam_fix_mode 必须是 None，别开。\\n"
                 "选型：要保真走 A；要补细节走 B。UI 图标与小尺寸素材一律走 A。\\n"
                 "A 分支 target 尺寸在 ImageScale 的 width/height 上调（当前 1536x1536）。"),
        "x": -1400, "y": 80, "w": 580, "h": 300})
    return g


BUILDERS = {"00": build_00, "01": build_01, "02": build_02, "03": build_03,
            "04": build_04, "05": build_05, "06": build_06, "07": build_07,
            "08": build_08, "09": build_09, "10": build_10, "11": build_11}
NAMES = {"00": "00_Character_Concept", "01": "01_Sprite_Alpha",
         "02": "02_Expression_Diff", "03": "03_Lineart_Colorize",
         "04": "04_Turnaround_3View", "05": "05_Prop_Icon",
         "06": "06_Seamless_Tile", "07": "07_HD_Upscale",
         "08": "08_Background", "09": "09_UI_NineSlice",
         "10": "10_Character_Parts", "11": "11_FX_Particle"}


def cmd_build(keys):
    ok = True
    for k in keys:
        g = BUILDERS[k]()
        errs = g.validate()
        if errs:
            ok = False
            print("[%s] 校验失败:" % k)
            for e in errs:
                print("   ", e)
            continue
        ui = g.to_ui()
        api = g.to_api()
        os.makedirs(WF_DIR, exist_ok=True)
        p_ui = os.path.join(WF_DIR, NAMES[k] + ".json")
        p_api = os.path.join(API_DIR, "api_%s.json" % k)
        json.dump(ui, open(p_ui, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        json.dump(api, open(p_api, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("[%s] OK  nodes=%d  ui=%s  api=%s" % (k, len(ui["nodes"]), os.path.basename(p_ui), os.path.basename(p_api)))
    print("ALL_OK" if ok else "HAS_ERROR")


def cmd_run(keys):
    for k in keys:
        g = BUILDERS[k]()
        errs = g.validate()
        if errs:
            print("[%s] 校验失败，跳过" % k)
            for e in errs:
                print("   ", e)
            continue
        t0 = time.time()
        r = g.submit(timeout=560)
        print("[%s] %s  %.1fs" % (k, json.dumps(r, ensure_ascii=False), time.time() - t0))
        sys.stdout.flush()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "build"
    keys = sys.argv[2:] or sorted(BUILDERS)
    if mode == "build":
        cmd_build(keys)
    else:
        cmd_run(keys)
