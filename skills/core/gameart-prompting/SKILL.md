---
name: gameart-prompting
description: |
  给 animagine-xl-3.1（SDXL 日式萌系）写提示词的规程：Danbooru 标签写法、质量词与负向词基线、
  四条产线各自的构图配方、seed 复现、以及「用户说的中文怎么翻成标签」。
  要写或改 prompt / negative，或出图风格不对、构图不听话、人物崩坏时读这篇。
  触发词：提示词、prompt、tag、标签、负向词、反向提示词、画风不对、构图不对、danbooru、animagine。
---

# 提示词规程（animagine-xl-3.1）

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
- 出 12 张一套，从里面挑 3–4 张能用的。不要指望 12 张都可用。

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
