---
name: gameart-prompting
description: |
  给 animagine-xl-3.1（SDXL 日式萌系）写提示词的规程：Danbooru 标签写法、质量词与负向词基线、
  十二条产线各自的构图配方、seed 复现、以及「用户说的中文怎么翻成标签」。
  要写或改 prompt / negative，或出图风格不对、构图不听话、人物崩坏时读这篇。
  触发词：提示词、prompt、tag、标签、负向词、反向提示词、画风不对、构图不对、danbooru、animagine。
---

# 提示词规程（animagine-xl-3.1）

> **00~07 跑 SD1.5 `anything-v5-PrtRE`，08/09/11 跑 SDXL `animagine-xl-3.1`。** 两代都用
> Danbooru 标签，但质量词前缀不同：SD1.5 那批用 `masterpiece, best quality, highly detailed,
> official art` 这一族；SDXL 那批用 `masterpiece, best quality, amazing quality, very aesthetic,
> absurdres`。产线里都已内置（`pipelines.py` 的 `POS_BASE` / `QUALITY`），照抄即可，别混用。

## 语言

**英文 Danbooru 标签，逗号分隔。** 这是 animagine 系列训练数据的形态。写中文整句、
写自然语言长句、写「a beautiful scene of...」这种文学描述，都会明显掉质量。

标签顺序有影响，从前往后权重递减：

```
质量词 → 主体/场景 → 动作/姿态 → 服饰/道具 → 光照/氛围 → 构图/镜头 → 画风词
```

## 质量词基线

产线已经内置了，你自己拼的时候抄这个：

```
masterpiece, best quality, amazing quality, very aesthetic, absurdres
```

负向基线（`NEG`）：

```
lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit,
fewer digits, cropped, worst quality, low quality, normal quality,
jpeg artifacts, signature, watermark, username, blurry, artist name, ugly, deformed
```

**不要删这几项**：`bad anatomy` / `bad hands` / `worst quality` / `low quality` 是保底的，
删了之后手和脸崩的概率立刻上去。`watermark` / `signature` / `username` 也别删，
animagine 很喜欢在角落签名。

## 各产线配方

### 00 角色概念设计

正向结构：`质量词, <画风词>, <角色定位>, <发型/发色/瞳色>, <服装>, <武器/道具>, <表情>, <光照>, <背景>`

产线内置模板（银发蓝瞳骑士，可直接替换主体段）：

```
masterpiece, best quality, highly detailed, official art, clean lineart,
anime game art, cel shading, sharp focus, vibrant colors,
game character concept art, character design, full body, standing,
front view, facing viewer, 1girl, silver hair, long hair, blue eyes,
fantasy knight, silver plate armor, blue cape, holding longsword,
determined expression, soft rim light, plain white background, high quality
```

- `full body, standing, front view, facing viewer` 是**构图锚**，不要删——删了会随机出半身或侧身。
- `plain white background` 让 01 抠图更稳。
- 铺量阶段一次 4 张同 seed 不同构图：不建议，直接跑 batch=4 就是 4 个不同构图。
- 负向必须含 `multiple views, multiple girls, sketch, monochrome, greyscale`。

### 01 立绘透明底

正向沿用 00 定稿的原句即可（这张图是 00 的延续，不是新设计）。

- `plain white background` 或 `simple background` 越干净，`BiRefNetRMBG` 抠得越准。
- 想要纯色底：`white background`；想要无背景：`no background`（后者 SD1.5 常画成灰底，不如白底稳）。
- 负向额外加 `multiple views, border, frame`。
- 背景全透靠 `background=Alpha`，**不靠提示词**。别在正向里写 `transparent background`——它只会被画成棋盘格。

### 02 表情差分

**正向只描述表情，不要重复外貌。** 外貌由输入图提供，重复写会跟原图打架。

```
质量词, close-up face, 1girl, <表情>, soft lighting
```

表情标签对照：

| 表情 | 标签 |
|---|---|
| neutral | `neutral expression, closed mouth, looking at viewer` |
| smile | `smiling, happy expression, open mouth, blushing cheeks` |
| angry | `angry, frown, furrowed brow, gritted teeth` |
| sad | `sad, tears, trembling lips, downcast eyes` |
| shy | `shy, blushing, embarrassed, averting eyes, covering mouth` |
| surprised | `surprised, wide eyes, open mouth, exclamation` |

- 负向必须含 `multiple faces, cropped face, helmet covering face, deformed eyes, distorted mouth`。
- `denoise 0.35` 起步；改不出效果先加 denoise（最高 0.55），不要靠堆标签。

### 03 线稿上色

正向结构：`质量词, <画风>, <配色倾向>, <主体>, <服饰>, plain background`

```
masterpiece, best quality, highly detailed, official art, clean lineart,
anime game art, cel shading, sharp focus, vibrant colors,
game art, anime style, flat colors, clean shading,
1girl, fantasy warrior, full body, detailed armor, plain background
```

- **不要写 `lineart` / `sketch` 当正向词**——那会让模型往上加线而不是上色。线稿由 ControlNet 提供。
- 负向必须含 `monochrome, greyscale, sketch`。
- 想要特定配色就写具体颜色词（`blue and gold color scheme`），比写「华丽」有效。

### 04 三视图设定稿

正向必须同时含三组短语，缺一个就少一个视角：

```
character turnaround sheet, three views on one canvas,
front view, side profile view, back view arranged left to right,
same character in all three views, identical outfit and hairstyle
```

完整模板：

```
masterpiece, best quality, character turnaround sheet, three views on one canvas,
front view, side profile view, back view arranged left to right,
same character in all three views, identical outfit and hairstyle,
full body, standing straight, t-pose, arms slightly away from body,
plain flat white background, even flat lighting, no shadow,
1girl, silver hair, blue eyes, blue and white fantasy adventurer outfit,
clean lineart, cel shading, game character design reference sheet
```

- **负向必须含 `different characters, different outfits, inconsistent design`**，这是三视图一致性的关键。
- `t-pose, arms slightly away from body` 避免手臂贴躯干导致建模时切不开。
- `plain flat white background, no shadow` 让三视图轮廓干净。

### 05 道具图标

正向结构：`质量词, game item icon, inventory icon, one single object, centered, <视角>, <道具描述>, <材质/光效>, plain white background, no text`

```
masterpiece, best quality, highly detailed, official art, clean lineart,
anime game art, cel shading, sharp focus, vibrant colors,
game item icon, inventory icon, one single object, centered, front view,
3/4 isometric angle, magic healing potion bottle, red liquid,
cork stopper, glass reflection, subtle glow, clean silhouette,
plain white background, no text
```

- `one single object` 是硬约束，负向必须配 `multiple objects`。
- `3/4 isometric angle` 出的是游戏图标惯用视角；要正面平视就换 `front view, orthographic`。
- 别写 `shadow`——图标带投影会让抠图边缘发脏。

### 06 无缝贴图

正向结构：`质量词, seamless tileable texture, top-down view, hand-painted game texture, <材质描述>, even lighting, no shadow gradient, no vignette`

```
masterpiece, best quality, highly detailed, official art, clean lineart,
anime game art, cel shading, sharp focus, vibrant colors,
seamless tileable texture, top-down view, hand-painted game texture,
mossy stone bricks, cracked stone floor, green moss, subtle dirt,
even lighting, no shadow gradient, no vignette
```

- **负向必须含 `seam, border, frame, edge, vignette, gradient, perspective`**。
- `top-down view` 避免画出透视，透视贴图无法无缝。
- 无缝的真正保证是产线的四步算法（环绕位移 + tile ControlNet 重绘接缝），提示词只是辅助。

### 07 高清放大

分支 A 不用提示词（纯超分）。分支 B 只需补细节词：

```
质量词, anime style, highly detailed, sharp focus, clean lineart, detailed texture
```

- 分支 B 负向加 `blurry, soft focus, washed out`。
- **不要写「8k, ultra detailed」这类堆叠**——`denoise 0.20` 下它们几乎不起作用，反而可能引入噪点。
- 放大保真的是 `denoise ≤ 0.25`，不是提示词。

### 08 场景背景（无人物）

正向结构：`质量词, no humans, scenery, <场景>, <地标/道具>, <光照>, <氛围>, detailed background, anime style, colorful, game background art`

产线内置的那条可以当模板：

```
no humans, scenery, japanese fantasy village at sunset, cherry blossom trees,
stone lantern, torii gate, wooden houses, warm golden sunlight, volumetric light,
lens flare, depth of field, detailed background, anime style, colorful, game background art
```

- **`no humans` 必须留在前面**，别只靠负向词。
- 负向会自动追加 `humans, person, character, 1girl, 1boy, portrait, text, logo, ui, frame, border, split screen, collage`。
  这几项保证出来的是「一张干净背景」而不是「带角色的插画」或「拼贴」。
- 想要 16:9 稳一点：`width: 1344, height: 768`（默认），产线再 lanczos 放大到 1920×1080。
  直接把 width/height 写成 1920/1080 反而容易出重复构图，不推荐。
- 横版关卡用，构图偏「远景 + 地平线略高」，加 `scenery, wide shot` 有帮助。

### 09 UI 九宫格（面板 + 元素）

- 主题词：`ui, game ui, interface, panel, ornate, <材质/纹样>`，比如
  `gold trim, dark blue, magic circle, fantasy`。
- **不要写具体文字内容**（按钮上写什么字）。SDXL 出不了可用文字，只会糊成乱码。
  文字留给引擎里的 Text 控件。
- 想要「能切九宫格」的面板，构图要**居中、对称、有明确边框**：
  加 `centered, symmetrical, border, frame, flat design`。
  斜构图、景深、渐变背景都会让切图变难。
- 元素板那张是「一板小控件」，`ui elements, icons, buttons, simple background` 一类词就够。

### 10 角色部件分层

- 主体词：`1girl, solo, upper body, looking at viewer, <发型/发色>, <瞳色>, <服饰>`。
- **要 `upper body` 或 `portrait`**，不要 `full body`——产线是 640×896 竖图拆 head/body，
  全身图会让「body」那层几乎吞掉整张，拆件没意义。
- `simple background, white background` 有助于后续 SAM 分割。
- 手部检测默认关（`ENABLE_HAND`），因为 `hand_yolov8s` 在动漫人像上不可靠。
  用户要求拆手时，明说这条链现在拆不准，建议手动补。

### 11 光效粒子

- 关键词：`energy, glow, particles, light sparks, <颜色>, <形态>`，比如
  `blue energy, glowing particles, light sparks, magic, black background`。
- **`black background` 要写**。加色混合要求底是黑的，产线也是这么出的。
- 需要「边缘完全透明」时靠的是 alpha，不是把它画白。
- 一次出 3 张，从里面挑能用的；不够就改 seed 再跑。

## seed 与复现

- 不传 `seed` 就是产线的默认种子（20261111）。**同 seed + 同参数 = 同图**。
- 用户说「就这个再来一张」「微调一下这个」时，先固定 seed 再动 prompt，
  这样能看出到底是哪一句起了作用。
- 想探索风格：一次只改一处，seed 固定；想随机找灵感：seed 交出去。
- 交付时**把 seed 写进回复**。这是用户回头能复现的唯一钥匙。

## 显存

8.5 GB（RTX 5060 Laptop）。`batch_size` 别乱加：08 默认 2、11 默认 12 已经是调过的。
把 11 的 batch 提到 24 会爆显存；真要更多张，分两次跑。

## 常见「画风不对」的体检顺序

1. 是不是中文/自然语言写进了 prompt？→ 换标签。
2. 质量词和负向词还在不在？→ 补回来。
3. 是不是要了这套底模出不了的东西（像素风 / 3D / 写实）？→ 停下来说明。
4. 主体词太靠后？→ 挪到质量词后面。
5. 构图词跟产线用途打架？（08 里写了人物、10 里写了 full body）→ 去掉。
