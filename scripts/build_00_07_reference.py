"""游戏美术素材生产线 —— 工作流定义（以当前环境已装模型/节点为准）。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wf_lib import Graph

CKPT = "anything-v5-PrtRE.safetensors"

# ---------------- 提示词规范 ----------------
NEG_BASE = ("lowres, worst quality, low quality, normal quality, blurry, jpeg artifacts, "
            "bad anatomy, bad hands, bad proportions, extra digits, fewer digits, missing fingers, "
            "watermark, signature, username, text, logo, cropped, out of frame, border, frame, "
            "multiple views, multiple girls, sketch, monochrome, greyscale")

STYLE_TAG = ("masterpiece, best quality, highly detailed, official art, "
             "clean lineart, anime game art, cel shading, sharp focus, vibrant colors")

CONCEPT_POS = (f"{STYLE_TAG}, game character concept art, character design, full body, standing, "
               "front view, facing viewer, 1girl, silver hair, long hair, blue eyes, fantasy knight, "
               "silver plate armor, blue cape, holding longsword, determined expression, "
               "soft rim light, plain white background, high detail armor, symmetrical design")

SPRITE_POS = (f"{STYLE_TAG}, game character sprite, full body, standing, front view, "
              "1girl, silver hair, blue eyes, fantasy knight armor, blue cape, longsword in right hand, "
              "neutral expression, T-pose ready, feet visible, soft even lighting, plain white background")

EXPR_POS = (f"{STYLE_TAG}, close-up face, 1girl, silver hair, blue eyes, smiling, happy expression, "
            "open mouth, blushing cheeks, looking at viewer, soft lighting")

LINEART_POS = (f"{STYLE_TAG}, game art, anime style, flat colors, clean shading, "
               "1girl, fantasy warrior, full body, detailed armor, plain background")

TURNAROUND_POS = {"front": f"{STYLE_TAG}, character turnaround sheet, front view, full body, standing, "
                            "1girl, silver hair, blue eyes, fantasy knight armor, arms relaxed, plain white background",
                  "side": f"{STYLE_TAG}, character turnaround sheet, side view profile, full body, standing, "
                          "1girl, silver hair, blue eyes, fantasy knight armor, plain white background",
                  "back": f"{STYLE_TAG}, character turnaround sheet, back view, full body, standing, "
                          "1girl, silver hair, long hair from behind, fantasy knight armor, blue cape, plain white background"}

ICON_POS = (f"{STYLE_TAG}, game item icon, inventory icon, one single object, centered, "
            "front view, 3/4 isometric angle, magic healing potion bottle, red liquid, cork stopper, "
            "glass reflection, subtle glow, clean silhouette, plain white background, no text")

TILE_POS = (f"{STYLE_TAG}, seamless tileable texture, top-down view, hand-painted game texture, "
            "mossy stone bricks, cracked stone floor, green moss, subtle dirt, even lighting, "
            "no shadow gradient, no vignette")

UPSCALE_POS = (f"{STYLE_TAG}, game art, 1girl, silver hair, fantasy armor, high detail, sharp lines")

EXPR_NEG = "multiple faces, cropped face, helmet covering face, deformed eyes, distorted mouth, " + NEG_BASE


def note(g, text, x=-480, y=60, w=420, h=260, title="使用说明"):
    g.notes.append({"text": text, "x": x, "y": y, "w": w, "h": h, "title": title})


# ============ 00 角色概念设计 ============
def w00():
    g = Graph("00_Character_Concept")
    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": CKPT})
    pos = g.add("CLIPTextEncode", {"text": CONCEPT_POS}, {"clip": ckpt.out(1)})
    neg = g.add("CLIPTextEncode", {"text": NEG_BASE}, {"clip": ckpt.out(1)})
    lat = g.add("EmptyLatentImage", {"width": 640, "height": 896, "batch_size": 4})
    ks = g.add("KSampler", {"seed": 20261110, "steps": 28, "cfg": 7.0, "sampler_name": "dpmpp_2m",
                            "scheduler": "karras", "denoise": 1.0},
               {"model": ckpt.out(0), "positive": pos.out(0), "negative": neg.out(0), "latent_image": lat.out(0)})
    dec = g.add("VAEDecode", {"samples": ks.out(0), "vae": ckpt.out(2)})
    g.add("SaveImage", {"filename_prefix": "GameArt/00_Concept/char_concept"}, {"images": dec.out(0)})
    note(g, """【00 角色概念设计 / Character Concept】
用途：出方案阶段快速铺量，一次 4 张 640x896。

操作位：
- 正向提示词：按「风格标签 → 主体 → 服饰道具 → 表情 → 光照 → 背景」顺序写。
- batch_size：铺量建议 4，定稿前改 1 并锁 seed 微调。
- seed：确认构图后固定 seed，只改提示词细节做强控制。

产出：ComfyUI/output/GameArt/00_Concept/
命名建议：char_{角色名}_{方案号}.png

定稿后接 01 立绘透明底工作流出正式资产。""")
    return g


# ============ 01 立绘透明底 ============
TURNAROUND_SHEET_POS = (
    "masterpiece, best quality, character turnaround sheet, three views on one canvas, "
    "front view, side profile view, back view arranged left to right, same character in all three views, "
    "identical outfit and hairstyle, full body, standing straight, t-pose, arms slightly away from body, "
    "plain flat white background, even flat lighting, no shadow, "
    "1girl, silver hair, blue eyes, blue and white fantasy adventurer outfit, "
    "clean lineart, cel shading, game character design reference sheet"
)

def w01():
    g = Graph("01_Sprite_Alpha")
    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": CKPT})
    pos = g.add("CLIPTextEncode", {"text": SPRITE_POS}, {"clip": ckpt.out(1)})
    neg = g.add("CLIPTextEncode", {"text": NEG_BASE}, {"clip": ckpt.out(1)})
    lat = g.add("EmptyLatentImage", {"width": 640, "height": 896, "batch_size": 1})
    ks = g.add("KSampler", {"seed": 20261111, "steps": 30, "cfg": 7.5, "sampler_name": "dpmpp_2m",
                            "scheduler": "karras", "denoise": 1.0},
               {"model": ckpt.out(0), "positive": pos.out(0), "negative": neg.out(0), "latent_image": lat.out(0)})
    dec = g.add("VAEDecode", {"samples": ks.out(0), "vae": ckpt.out(2)})
    cut = g.add("BiRefNetRMBG", {"model": "BiRefNet_toonout", "sensitivity": 1.0, "mask_blur": 0,
                                 "mask_offset": 0, "invert_output": False, "refine_foreground": True,
                                 "background": "Alpha", "background_color": "#222222"},
                {"image": dec.out(0)})
    g.add("SaveImage", {"filename_prefix": "GameArt/01_Sprite/sprite_alpha"}, {"images": cut.out(0)})
    note(g, """【01 立绘透明底 / Sprite with Alpha】
用途：直接产出带 Alpha 通道的透明 PNG，可直接进引擎/UI。

关键参数：
- BiRefNet_toonout：动漫/游戏立绘专用抠图模型（本机已装），比通用模型边缘干净。
- background = Alpha：输出 RGBA，不要改成 Color。
- refine_foreground = 开启：修复半透明边缘与发丝。
- 若有白边：mask_offset 调 -1 ~ -2；若吞掉发丝：mask_offset 调 +1。

导出规范：PNG-24 带 Alpha，最终尺寸统一 1024x1536（用 07 放大后裁切）。
产出：ComfyUI/output/GameArt/01_Sprite/
命名：char_{角色名}_{动作}_{表情}.png""")
    return g


# ============ 02 表情差分 ============
def w02():
    g = Graph("02_Expression_Diff")
    src = g.add("LoadImage", {"image": "example.png"})
    # 头部区域（按立绘比例 26% 高定位，x/y/w/h 需按实际图微调）
    crop = g.add("ImageCrop", {"width": 300, "height": 300, "x": 170, "y": 70}, {"image": src.out(0)})
    up = g.add("ImageScale", {"upscale_method": "lanczos", "width": 512, "height": 512, "crop": "disabled"},
               {"image": crop.out(0)})
    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": CKPT})
    pos = g.add("CLIPTextEncode", {"text": EXPR_POS}, {"clip": ckpt.out(1)})
    neg = g.add("CLIPTextEncode", {"text": EXPR_NEG}, {"clip": ckpt.out(1)})
    enc = g.add("VAEEncode", {"pixels": up.out(0), "vae": ckpt.out(2)})
    ks = g.add("KSampler", {"seed": 20261112, "steps": 24, "cfg": 6.5, "sampler_name": "dpmpp_2m",
                            "scheduler": "karras", "denoise": 0.35},
               {"model": ckpt.out(0), "positive": pos.out(0), "negative": neg.out(0), "latent_image": enc.out(0)})
    dec = g.add("VAEDecode", {"samples": ks.out(0), "vae": ckpt.out(2)})
    back = g.add("ImageScale", {"upscale_method": "lanczos", "width": 300, "height": 300, "crop": "disabled"},
                 {"image": dec.out(0)})
    # 遮罩内缩 8px + 大半径羽化：解决贴回矩形硬边与色调跳变
    sMask = g.add("SolidMask", {"value": 1.0, "width": 300, "height": 300})
    grow = g.add("GrowMask", {"expand": -8, "tapered_corners": True}, {"mask": sMask.out(0)})
    blur = g.add("ImpactGaussianBlurMask", {"kernel_size": 40, "sigma": 20.0}, {"mask": grow.out(0)})
    comp = g.add("ImageCompositeMasked", {"x": 170, "y": 70, "resize_source": False},
                 {"destination": src.out(0), "source": back.out(0), "mask": blur.out(0)})
    g.add("SaveImage", {"filename_prefix": "GameArt/02_Expression/expr_diff"}, {"images": comp.out(0)})
    note(g, """【02 表情差分 / Expression Diff】
用途：同一张立绘批量出 6~12 个表情，身体像素 100% 不变，只改脸。

必须按顺序调 3 个坐标（都在 ImageCrop / ImageCompositeMasked 里）：
1. width/height：脸部方块边长（立绘 1024 高时约 300~360）。
2. x/y：脸块左上角。定位法：立绘高度取顶部 26% 作为头框，脸块中心略低于头框中心。
3. 贴回节点的 x/y 必须与裁切 x/y 完全一致。

参数：
- denoise 0.35~0.55：越低越保脸型，越高表情变化越大。改表情幅度大时用 0.5。
- 正向提示词只写表情（smile, angry, shy, surprised...），不要重复外貌描述。
- ImpactGaussianBlurMask kernel 28 / sigma 14：越大过渡越柔，出现重影就调小。

产出：ComfyUI/output/GameArt/02_Expression/
命名：char_{角色名}_{表情名}.png（表情表：neutral/smile/angry/sad/shy/surprised）""")
    return g


# ============ 03 线稿上色 ============
def w03():
    g = Graph("03_Lineart_Colorize")
    src = g.add("LoadImage", {"image": "gameart_concept_sample.png"})
    pre = g.add("LineArtPreprocessor", {"coarse": "disable", "resolution": 1024}, {"image": src.out(0)})
    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": CKPT})
    pos = g.add("CLIPTextEncode", {"text": LINEART_POS}, {"clip": ckpt.out(1)})
    neg = g.add("CLIPTextEncode", {"text": NEG_BASE}, {"clip": ckpt.out(1)})
    cnet = g.add("ControlNetLoader", {"control_net_name": "control_v11p_sd15_lineart_fp16.safetensors"})
    cnet_anime = g.add("ControlNetLoader", {"control_net_name": "control_v11p_sd15s2_lineart_anime_fp16.safetensors"})
    ca = g.add("ControlNetApplyAdvanced", {"strength": 1.0, "start_percent": 0.0, "end_percent": 1.0},
               {"positive": pos.out(0), "negative": neg.out(0), "control_net": cnet.out(0),
                "image": pre.out(0), "vae": ckpt.out(2)})
    ca2 = g.add("ControlNetApplyAdvanced", {"strength": 0.6, "start_percent": 0.0, "end_percent": 0.7},
                {"positive": ca.out(0), "negative": ca.out(1), "control_net": cnet_anime.out(0),
                 "image": pre.out(0), "vae": ckpt.out(2)})
    lat = g.add("EmptyLatentImage", {"width": 640, "height": 896, "batch_size": 1})
    ks = g.add("KSampler", {"seed": 20261113, "steps": 30, "cfg": 7.0, "sampler_name": "dpmpp_2m",
                            "scheduler": "karras", "denoise": 1.0},
               {"model": ckpt.out(0), "positive": ca2.out(0), "negative": ca2.out(1), "latent_image": lat.out(0)})
    dec = g.add("VAEDecode", {"samples": ks.out(0), "vae": ckpt.out(2)})
    g.add("SaveImage", {"filename_prefix": "GameArt/03_Lineart/colorized"}, {"images": dec.out(0)})
    note(g, """【03 线稿上色 / Lineart Colorize】
用途：策划/外包给的线稿一键上色，或自己画线稿后上色。

链路：载入线稿 → LineArtPreprocessor 强化线 → 双 ControlNet（lineart + anime lineart）→ 出图。
- 第一层 strength 1.0 保证线不漏；
- 第二层 0.6 / end_percent 0.7 只在前半程锁线，后半程放给模型上色，避免线条发死。

上色准确度靠提示词写清部位颜色（hair: silver, cape: blue...）。
若要保留原线稿像素：把 denoise 降到 0.75 并接 VAEEncode 走 img2img。

产出：ComfyUI/output/GameArt/03_Lineart/""")
    return g


# ============ 04 三视图 ============
def w04():
    g = Graph("04_Turnaround_3View")
    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": CKPT})
    pos = g.add("CLIPTextEncode", {"text": TURNAROUND_SHEET_POS}, {"clip": ckpt.out(1)})
    neg = g.add("CLIPTextEncode", {"text": NEG_BASE + ", different characters, different outfits, "
                                           "inconsistent design, cropped, text, watermark"},
                {"clip": ckpt.out(1)})
    lat = g.add("EmptyLatentImage", {"width": 768, "height": 512, "batch_size": 1})
    ks1 = g.add("KSampler", {"seed": 20261110, "steps": 30, "cfg": 7.5, "sampler_name": "dpmpp_2m",
                             "scheduler": "karras", "denoise": 1.0},
                {"model": ckpt.out(0), "positive": pos.out(0), "negative": neg.out(0), "latent_image": lat.out(0)})
    up = g.add("LatentUpscale", {"upscale_method": "nearest-exact", "width": 1152, "height": 768,
                                 "crop": "disabled"}, {"samples": ks1.out(0)})
    ks2 = g.add("KSampler", {"seed": 20261110, "steps": 20, "cfg": 7.0, "sampler_name": "dpmpp_2m",
                             "scheduler": "karras", "denoise": 0.45},
                {"model": ckpt.out(0), "positive": pos.out(0), "negative": neg.out(0), "latent_image": up.out(0)})
    dec = g.add("VAEDecode", {"samples": ks2.out(0), "vae": ckpt.out(2)})
    g.add("SaveImage", {"filename_prefix": "GameArt/04_Turnaround/turnaround"}, {"images": dec.out(0)})
    note(g, """【04 三视图 / Character Turnaround】
用途：交付建模/3D 还原用的正-侧-背三视图设定板。

为什么是单张宽幅一次生成，而不是分三个 KSampler 各出一张：
分三次生成即使锁同一个 seed，模型也会把"同一个角色"重新诠释成三个人（实测已翻车）。
必须让它在同一张画布上一次性画出三联，角色一致性才有保证。

链路：768x512 一次出三联 → LatentUpscale x1.5 → 第二次采样 denoise 0.45（hires fix）
→ 输出 1152x768 设定板。

调参：
- 提示词必须写死 "character turnaround sheet, same character, front view / side view / back view"，
  负向要压 "different characters, inconsistent design"。
- 想要更高一致性：装上 IPAdapter + CLIP Vision 后，把 00 产出的概念图作为参考图接入
  （见待配置清单），这是目前 SD1.5 下最强的角色锁定手段。
- 比例要精确到 3D 可还原：建议再接 Openpose ControlNet 固定 T-pose（节点已装）。

产出：ComfyUI/output/GameArt/04_Turnaround/""")
    return g


# ============ 05 道具图标 ============
def w05():
    g = Graph("05_Prop_Icon")
    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": CKPT})
    pos = g.add("CLIPTextEncode", {"text": ICON_POS}, {"clip": ckpt.out(1)})
    neg = g.add("CLIPTextEncode", {"text": NEG_BASE + ", multiple objects, pattern, background detail"},
               {"clip": ckpt.out(1)})
    lat = g.add("EmptyLatentImage", {"width": 768, "height": 768, "batch_size": 4})
    ks = g.add("KSampler", {"seed": 20261114, "steps": 26, "cfg": 7.0, "sampler_name": "dpmpp_2m",
                            "scheduler": "karras", "denoise": 1.0},
               {"model": ckpt.out(0), "positive": pos.out(0), "negative": neg.out(0), "latent_image": lat.out(0)})
    dec = g.add("VAEDecode", {"samples": ks.out(0), "vae": ckpt.out(2)})
    cut = g.add("BiRefNetRMBG", {"model": "BiRefNet_toonout", "sensitivity": 1.0, "mask_blur": 0,
                                 "mask_offset": 0, "invert_output": False, "refine_foreground": True,
                                 "background": "Alpha", "background_color": "#222222"},
                {"image": dec.out(0)})
    fin = g.add("ImageScale", {"upscale_method": "lanczos", "width": 512, "height": 512, "crop": "center"},
                {"image": cut.out(0)})
    g.add("SaveImage", {"filename_prefix": "GameArt/05_Icon/item_icon"}, {"images": fin.out(0)})
    note(g, """【05 道具图标 / Item Icon】
用途：背包/商店/掉落物图标，统一 512x512 透明底。

规范（游戏 UI 通用）：
- 主体居中，占画布 70%~80%，四周留 10%~15% 安全边，避免 UI 框裁切。
- 单一物体，不能出现多个同类物（已写入负向）。
- 3/4 等距视角比纯正面更有体积感。
- 输出统一 RGBA，禁止带背景色，防止暗色 UI 出现白方块。

产出：ComfyUI/output/GameArt/05_Icon/
命名：item_{道具名}_{品质}.png（common/rare/epic/legendary 用 06 后处理换描边色）""")
    return g


# ============ 06 无缝贴图 ============
def w06():
    g = Graph("06_Seamless_Tile")
    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": CKPT})
    pos = g.add("CLIPTextEncode", {"text": TILE_POS}, {"clip": ckpt.out(1)})
    neg = g.add("CLIPTextEncode", {"text": NEG_BASE + ", border, frame, vignette, gradient"},
                {"clip": ckpt.out(1)})
    lat = g.add("EmptyLatentImage", {"width": 512, "height": 512, "batch_size": 1})
    ks = g.add("KSampler", {"seed": 20261115, "steps": 26, "cfg": 7.0, "sampler_name": "dpmpp_2m",
                            "scheduler": "karras", "denoise": 1.0},
               {"model": ckpt.out(0), "positive": pos.out(0), "negative": neg.out(0), "latent_image": lat.out(0)})
    dec = g.add("VAEDecode", {"samples": ks.out(0), "vae": ckpt.out(2)})
    cnet = g.add("ControlNetLoader", {"control_net_name": "control_v11f1e_sd15_tile_fp16.safetensors"})

    # ---- 第一遍：水平环绕滚动 50%，接缝移到 x=256 竖线 ----
    left = g.add("ImageCrop", {"width": 256, "height": 512, "x": 0, "y": 0}, {"image": dec.out(0)})
    right = g.add("ImageCrop", {"width": 256, "height": 512, "x": 256, "y": 0}, {"image": dec.out(0)})
    cv1 = g.add("EmptyImage", {"width": 512, "height": 512, "batch_size": 1, "color": 0})
    h1 = g.add("ImageCompositeMasked", {"x": 0, "y": 0, "resize_source": False},
               {"destination": cv1.out(0), "source": right.out(0)})
    h2 = g.add("ImageCompositeMasked", {"x": 256, "y": 0, "resize_source": False},
               {"destination": h1.out(0), "source": left.out(0)})
    enc1 = g.add("VAEEncode", {"pixels": h2.out(0), "vae": ckpt.out(2)})
    ca1 = g.add("ControlNetApplyAdvanced", {"strength": 0.85, "start_percent": 0.0, "end_percent": 1.0},
                {"positive": pos.out(0), "negative": neg.out(0), "control_net": cnet.out(0),
                 "image": h2.out(0), "vae": ckpt.out(2)})
    ks1 = g.add("KSampler", {"seed": 20261116, "steps": 26, "cfg": 6.5, "sampler_name": "dpmpp_2m",
                             "scheduler": "karras", "denoise": 0.62},
                {"model": ckpt.out(0), "positive": ca1.out(0), "negative": ca1.out(1), "latent_image": enc1.out(0)})
    dec1 = g.add("VAEDecode", {"samples": ks1.out(0), "vae": ckpt.out(2)})
    # 只把重绘结果的中央 128px 竖带羽化贴回，边缘像素一律不动（这是无缝能成立的关键）
    band1 = g.add("ImageCrop", {"width": 128, "height": 512, "x": 192, "y": 0}, {"image": dec1.out(0)})
    m1 = g.add("SolidMask", {"value": 1.0, "width": 128, "height": 512})
    f1 = g.add("FeatherMask", {"left": 28, "top": 0, "right": 28, "bottom": 0}, {"mask": m1.out(0)})
    fixH = g.add("ImageCompositeMasked", {"x": 192, "y": 0, "resize_source": False},
                 {"destination": h2.out(0), "source": band1.out(0), "mask": f1.out(0)})

    # ---- 第二遍：垂直环绕滚动 50%，接缝移到 y=256 横线 ----
    top = g.add("ImageCrop", {"width": 512, "height": 256, "x": 0, "y": 0}, {"image": fixH.out(0)})
    bot = g.add("ImageCrop", {"width": 512, "height": 256, "x": 0, "y": 256}, {"image": fixH.out(0)})
    cv2 = g.add("EmptyImage", {"width": 512, "height": 512, "batch_size": 1, "color": 0})
    v1 = g.add("ImageCompositeMasked", {"x": 0, "y": 0, "resize_source": False},
               {"destination": cv2.out(0), "source": bot.out(0)})
    v2 = g.add("ImageCompositeMasked", {"x": 0, "y": 256, "resize_source": False},
               {"destination": v1.out(0), "source": top.out(0)})
    enc2 = g.add("VAEEncode", {"pixels": v2.out(0), "vae": ckpt.out(2)})
    ca2 = g.add("ControlNetApplyAdvanced", {"strength": 0.85, "start_percent": 0.0, "end_percent": 1.0},
                {"positive": pos.out(0), "negative": neg.out(0), "control_net": cnet.out(0),
                 "image": v2.out(0), "vae": ckpt.out(2)})
    ks2 = g.add("KSampler", {"seed": 20261117, "steps": 26, "cfg": 6.5, "sampler_name": "dpmpp_2m",
                             "scheduler": "karras", "denoise": 0.58},
                {"model": ckpt.out(0), "positive": ca2.out(0), "negative": ca2.out(1), "latent_image": enc2.out(0)})
    dec2 = g.add("VAEDecode", {"samples": ks2.out(0), "vae": ckpt.out(2)})
    band2 = g.add("ImageCrop", {"width": 512, "height": 128, "x": 0, "y": 192}, {"image": dec2.out(0)})
    m2 = g.add("SolidMask", {"value": 1.0, "width": 512, "height": 128})
    f2 = g.add("FeatherMask", {"left": 0, "top": 28, "right": 0, "bottom": 28}, {"mask": m2.out(0)})
    fixV = g.add("ImageCompositeMasked", {"x": 0, "y": 192, "resize_source": False},
                 {"destination": v2.out(0), "source": band2.out(0), "mask": f2.out(0)})
    g.add("SaveImage", {"filename_prefix": "GameArt/06_Tile/tile_seamless_512"}, {"images": fixV.out(0)})
    note(g, """【06 无缝贴图 / Seamless Tile】
用途：地块、墙面、地面等可平铺材质，512x512 四向无缝，可直接进引擎 Tilemap。

原理（四步，节点别删）：
1. 先生成普通材质；
2. 水平环绕滚动 50%（左右半换位）——原左右边缘的接缝被移到画面中央竖线 x=256；
3. 用 tile ControlNet 重绘全图，但只把中央 128px 竖带羽化贴回，两侧边缘像素一个不动
   → 此时左右边缘天然连续，水平方向无缝；
4. 垂直方向重复同样操作（上下半换位 + 中央 128px 横带贴回）→ 四向无缝。

为什么必须只贴窄带：整图贴回会重新采样边缘像素，第一遍修好的无缝会被破坏。
这是上一版失败的原因，务必保留 FeatherMask 与 band 的裁剪。

调参：
- 重绘 denoise 0.62 / 0.58：低于 0.5 缝补不掉，高于 0.7 图案糊。
- band 宽度 128、羽化 28：接缝必须落在羽化后的实心区内。
- tile ControlNet strength 0.85。

验收：3x3 平铺看是否出现网格线；或算接缝梯度比，≤1.5 视为无缝。
产出：ComfyUI/output/GameArt/06_Tile/""")
    return g


# ============ 07 高清放大 ============
def w07():
    g = Graph("07_HD_Upscale")
    src = g.add("LoadImage", {"image": "example.png"})
    um = g.add("UpscaleModelLoader", {"model_name": "RealESRGAN_x4plus_anime_6B.pth"})

    # 分支 A：纯模型放大（保锐度，边缘忠实原图，正式资产首选）
    esr = g.add("ImageUpscaleWithModel", {}, {"upscale_model": um.out(0), "image": src.out(0)})
    sharp = g.add("ImageScale", {"upscale_method": "lanczos", "width": 1536, "height": 1536,
                                 "crop": "disabled"}, {"image": esr.out(0)})
    g.add("SaveImage", {"filename_prefix": "GameArt/07_Upscale/hd_sharp"}, {"images": sharp.out(0)})

    # 分支 B：SD 分块重绘补细节（画面更丰富，适合宣传图；会有轻微柔化）
    ckpt = g.add("CheckpointLoaderSimple", {"ckpt_name": CKPT})
    pos = g.add("CLIPTextEncode", {"text": UPSCALE_POS}, {"clip": ckpt.out(1)})
    neg = g.add("CLIPTextEncode", {"text": NEG_BASE}, {"clip": ckpt.out(1)})
    us = g.add("UltimateSDUpscale", {"upscale_by": 2.0, "seed": 20261117, "steps": 18, "cfg": 6.0,
                                     "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 0.22,
                                     "mode_type": "Linear", "tile_width": 768, "tile_height": 768,
                                     "mask_blur": 8, "tile_padding": 32, "seam_fix_mode": "None",
                                     "seam_fix_denoise": 0.3, "seam_fix_width": 64,
                                     "seam_fix_mask_blur": 8, "seam_fix_padding": 16,
                                     "force_uniform_tiles": True, "tiled_decode": False, "batch_size": 1},
               {"image": src.out(0), "model": ckpt.out(0), "positive": pos.out(0), "negative": neg.out(0),
                "vae": ckpt.out(2), "upscale_model": um.out(0)})
    g.add("SaveImage", {"filename_prefix": "GameArt/07_Upscale/hd_detail"}, {"images": us.out(0)})
    note(g, """【07 高清放大 / HD Upscale】双分支输出，按用途二选一

分支 A hd_sharp：纯 RealESRGAN anime 4x 模型放大 → lanczos 缩到 1536。
  · 边缘锐利、线条忠实，不做任何重绘，适合要进引擎的正式资产、UI 贴图、像素要求高的素材。
  · 缺点：不会凭空补出细节。

分支 B hd_detail：UltimateSDUpscale 分块重绘（2x，denoise 0.22）。
  · 会补出细节，适合宣传图/展示图。
  · 源图质量决定上限：整合包自带的 example.png 本身就是低清涂鸦风，放大后只会变平滑、不会变清晰，验收请换成真实产出图再评。
  · denoise 必须压在 0.25 以下：上一版用 0.30 且开了 seam_fix 0.35，
    等于接缝处再重绘一遍，实测整图发糊、线条涂抹，已修正。
  · tile 512→768 减少分块痕迹，seam_fix_mode 关掉避免二次柔化。

目标尺寸：分支 A 改 ImageScale 的 width/height；分支 B 改 upscale_by。
原图 768 → A 出 1536、B 出 1536，都是 1:1 方图；非方图请按原比例填宽高。

产出：ComfyUI/output/GameArt/07_Upscale/""")
    return g


ALL = {"00_Character_Concept": w00, "01_Sprite_Alpha": w01, "02_Expression_Diff": w02,
       "03_Lineart_Colorize": w03, "04_Turnaround_3View": w04, "05_Prop_Icon": w05,
       "06_Seamless_Tile": w06, "07_HD_Upscale": w07}
