# gameart_pipeline —— 游戏美术产线插件包

本地 ComfyUI + SDXL（animagine-xl-3.1）驱动的游戏美术素材生产线，本次精修并实测通过 4 条产线：

| 产线 | 能力 | 产物 |
|---|---|---|
| 08 场景背景 | 无人物横版场景 | 1920×1080 RGB PNG |
| 09 UI 九宫格 | UI 元素板 + 可 9-slice 拉伸面板 | 1024×1024 RGBA PNG + 9 块切图 |
| 10 角色部件 | SAM 拆件，head/body 互斥分层 | 640×896 RGBA ×2 |
| 11 光效粒子 | 黑底加色混合特效贴图 | 1024×1024 RGBA PNG |

风格固定为日式萌系，不含像素风、不含 3D 模型。

---

## 1. 目录结构

```
dsh_plugin_gameart/
├─ plugin.json                     # 插件 manifest（能力/参数/依赖/环境变量）
├─ README.md                       # 本文
├─ gameart_pipeline/               # Python 包（宿主唯一需要 import 的东西）
│  ├─ __init__.py                  # 导出 list_pipelines / build / run / slice_panel / info
│  ├─ runner.py                    # 对外接口层
│  ├─ pipelines.py                 # 08~11 四条产线的图定义（Graph DSL）
│  ├─ wf_lib.py                    # 工作流构建器：API 真源 → UI JSON + 校验 + 提交
│  ├─ slicing.py                   # 9-slice 切图（按 alpha 求 bbox，中心块均色重建）
│  └─ objinfo_latest.json          # 节点 schema 快照（3MB，离线自举用）
├─ workflows/                      # 12 个 UI 格式工作流，ComfyUI 前端可直接拖入
├─ api/                            # 08~11 的 API 格式（提交 /prompt 的形态）
├─ samples/                        # 本次实跑产物，按产线分目录 08/ 09/ 10/ 11/
└─ scripts/
   ├─ build_00_07_reference.py     # 00~07 的构建脚本（参考，未注册进插件 API）
   ├─ slice9.py                    # 切图 CLI 版
   └─ check_seam.py / check_seam2.py  # 9 块合成接缝校验
```

`workflows/` 里的 00~07 是第一版（底模 anything-v5，SD1.5），与本插件注册的 08~11（SDXL）不是同一代。它们只作为参考随包提供，**未注册进 `run()`**，因为本轮没有对它们做实测复验。要启用请自行跑 `scripts/build_00_07_reference.py` 重新构建并验证。

---

## 2. 快速开始

```bash
# 用 ComfyUI 自带的 python 解释器（环境里要有 torch / numpy / Pillow）
cd dsh_plugin_gameart

# 1) 自检：服务是否在线、schema 是否可用、底模是否落盘
python -m gameart_pipeline.runner info

# 2) 列出产线与可覆盖参数
python -m gameart_pipeline.runner list

# 3) 只校验不落盘（CI 可用）
python -m gameart_pipeline.runner build

# 4) 出图
python -m gameart_pipeline.runner run 08 '{"seed": 42, "prompt": "..."}'

# 5) 09 面板切九宫格
python -m gameart_pipeline.runner slice "D:/out/ui_panel_00006_.png" "D:/out/nineslice" 160
```

宿主里最省事的接法：

```python
from gameart_pipeline import list_pipelines, run, slice_panel, info

for p in list_pipelines():
    print(p["id"], p["title"], p["params"])

res = run("08", {"seed": 1234, "steps": 30})
if res["ok"]:
    print(res["images"])          # ComfyUI 输出文件名列表
else:
    print(res["stage"], res.get("error"))
```

---

## 3. 接口契约

### `list_pipelines() -> list[dict]`

```json
{
  "id": "09",
  "name": "09_UI_NineSlice",
  "title": "UI 九宫格面板 + 元素板",
  "use": "UI 底板 9-slice 切图 + 一板式控件元素",
  "output": "1024x1024 RGBA，面板/元素板各一",
  "params": ["prompt", "negative", "seed", "steps", "cfg"],
  "workflow_file": ".../workflows/09_UI_NineSlice.json",
  "api_file": ".../api/api_09.json"
}
```

### `build(ids=None, write=True) -> dict`

按 id 构建并做本地校验（输入名存在性 + 输出 slot 类型匹配）。`write=False` 只校验不落盘。

```json
{"08": {"ok": true, "nodes": 9,
        "ui": ".../workflows/08_Background.json",
        "api": ".../api/api_08.json"}}
```

失败时返回 `{"ok": false, "errors": ["..."]}`，不会写半成品文件。

### `run(pipeline_id, overrides=None, timeout=560) -> dict`

提交 `/prompt` 并轮询 `/history/{prompt_id}`。

| 字段 | 说明 |
|---|---|
| `ok` | 是否成功出图 |
| `stage` | 失败阶段：`input` / `validate` / `exec` / `timeout` / 网络错误 |
| `images` | ComfyUI 输出文件名列表（相对 output 目录） |
| `elapsed` | 耗时秒 |
| `applied_overrides` | 实际生效的覆盖键，宿主可据此回显 |

可覆盖参数（`OVERRIDABLE_WIDGETS`）：
`prompt` `negative` `seed` `steps` `cfg` `denoise` `width` `height` `batch_size` `sampler_name` `scheduler` `ckpt_name`

> `prompt` / `negative` 按图中 `CLIPTextEncode` 出现的**顺序**取第 0 / 第 1 个，四条产线统一先正向后负向。新增产线请沿用该约定，否则覆盖会打到错误节点。

> `seed` 这类带 `control_after_generate` 的整数控件，`to_ui()` 时会在 `widgets_values` 末尾追加 `"randomize"` 占位——UI 格式要求，API 格式不需要。

### `slice_panel(src, out_dir=None, C=160) -> dict`

```json
{"ok": true, "panel": "..._panel_trim_972x972.png", "size": [972, 972],
 "corner": 160, "center_rgb": [159, 144, 145], "files": ["...共 9 块..."]}
```

切块规则（`c = min(C, w//4, h//4)`，防止小面板被切穿）：

| 块 | 尺寸 | 拉伸方向 |
|---|---|---|
| tl / tr / bl / br | c × c | 不拉伸 |
| tc / bc | (w-2c) × c | 仅横向 |
| ml / mr | c × (h-2c) | 仅纵向 |
| mc | (w-2c) × (h-2c) | 双向（中心均色重建，纯色） |

### `info() -> dict`

`online` / `comfyui{version,python,torch,device,vram_total}` / `schema_nodes` / `ckpt_ready` / `pipelines`。服务未启动时 `online=false` 并带 `error`，不抛异常，宿主可安全地当健康检查用。

---

## 4. 各产线细节

### 08 场景背景（9 节点）

- 正/负提示词 + `EmptyLatentImage(1344×768, batch=2)` → KSampler(dpmpp_2m / karras，28 步，cfg 7.0) → VAE 解码 → 保存。
- 负面词显式排除 `humans, person, character, 1girl, 1boy, portrait, text, logo, ui, frame, border, split screen, collage`，这是它稳定出“纯场景”的原因。
- 验收：构图完整、无畸变、无文字水印。样本见 `samples/08/`（1920×1080 RGB）。

### 09 UI 九宫格（47 节点，双分支）

- 分支 A：UI 元素板（按钮 / 进度条 / 图标框 / 滑块 / 提示框排一板）。
- 分支 B：面板 + 几何 alpha —— `SolidMask(0)` 全覆盖 → `SolidMask(1)` 内缩矩形（INSET=26）→ `MaskComposite(add)` → `InvertMask` → `JoinImageWithAlpha`。
- 实测（样本 00006）：面板 `nz=0.8481`，四角块 `0.7014`，四边块 `0.8375`；中心块 `nz=1.0000` 且 RGB 唯一色数 = 1；9 块合成 1280×720 后中心 alpha=1.000、边框连贯无接缝。
- **面板分支刻意不做抠图**：白底色键（`AILab_ColorToMask`）因 SDXL 不保证纯白背景而整图失效（面板全透明 nz=0.0000）；RMBG 会把个别角误判成背景（左下块 nz=0.0012）。
- 已知限制：几何 alpha 是直角，四角不带圆角。要圆角请在引擎侧叠圆角遮罩，或用 9-slice 的 corner scale 补偿。

### 10 角色部件分层（22 节点）

- 链路：前景 = `InvertMask(源 alpha)` ∪ `RMBG-2.0 out1` → face bbox 检测（threshold 0.30 / dilation 12）→ `SAMDetectorCombined`（threshold 0.88，detection_hint `center-1`）→ `GrowMask expand 25` → head；body = 前景 − head；各层与前景求交防出界 → `InvertMask` → `JoinImageWithAlpha`。
- 实测：head 占 1.91%、body 51.85%、并集 53.76%、两层重叠像素 **0**（完全互斥）、透明区 RGB 最大 0（已清零，Spine 不会出黑边）。
- 关键参数：`GrowMask expand=25`。**不要调到 70**——会吃到颈部与肩部装甲，目检不合格。
- 已知限制：`hand_yolov8s` 对二次元立绘误检率高（把领口装饰当手），`ENABLE_HAND` 默认 False。要做手部动画请换模型或人工分件。

### 11 光效粒子（16 节点）

- 黑底辐射 / 粒子爆发，batch=12，输出 1024×1024 RGBA。
- 实测：`nz 0.237~0.252`，全透明边缘占比约 0.75，中心发散紫蓝光线，边缘干净可直接加色叠加。
- 用法：引擎里混合模式设 Additive / Linear Dodge，不要用 Alpha Blend 压暗底层。

---

## 5. 工作流 JSON 的两种形态

`wf_lib.py` 的做法是**以 API 格式为唯一真源**，UI 格式由转换器生成：

```
Graph(name) → add(ctype, widgets, links) → validate() → to_api() / to_ui() → submit()
```

- `to_api()`：`{node_id: {class_type, inputs}}`，直接 POST 给 `/prompt`。
- `to_ui()`：带 `nodes/links/last_node_id/version` 的前端格式，可拖进 ComfyUI 面板。
- 转 UI 时按 `object_info` 里 `required` + `optional` 的**声明顺序**生成 `widgets_values`，区分 widget 与 socket 输入；socket 输入生成 `inputs` 数组并按输出 slot 生成 `links`。
- Note 说明节点只存在于 UI 格式，不进 API，不影响执行——但它们是参数与踩坑的现场记录，改参数前先读 Note。

加新产线：在 `pipelines.py` 写 `def build_12(): g = Graph("12_XXX") ... return g`，注册进 `BUILDERS` / `NAMES`，`runner` 会自动带上（记得补 `META` 里的中文标题与可覆盖参数）。

---

## 6. 环境与依赖

- ComfyUI 0.33.2，Python 3.13.11，torch 2.9.1+cu130，RTX 5060 Laptop（vram 8.5 GB）。
- 自定义节点：Impact-Pack（SAM / Bbox / Segm）、Inspire-Pack（几何 Mask）、IPAdapter_plus、was-node-suite、UltimateSDUpscale、ComfyUI-RMBG、controlnet_aux。
- 模型（均已落盘校验）：

| 类别 | 文件 |
|---|---|
| checkpoints | animagine-xl-3.1.safetensors |
| vae | sdxl_vae_fp16_fix.safetensors |
| clip_vision | CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors |
| ipadapter | ip-adapter-plus_sdxl_vit-h.safetensors |
| controlnet | controlnet-union-sdxl-promax.safetensors |
| RMBG | RMBG-2.0.safetensors |
| embeddings | EasyNegative.safetensors |
| ultralytics bbox | face_yolov8m.pt / hand_yolov8s.pt |
| sams | sam_vit_b_01ec64.pth |
| upscale | RealESRGAN_x4plus_anime_6B.pth |

### 环境变量

| 变量 | 默认 | 作用 |
|---|---|---|
| `COMFY_BASE` | `http://127.0.0.1:8188` | ComfyUI 地址 |
| `COMFY_WF_DIR` | `<plugin>/workflows` | UI JSON 输出目录；可指向 ComfyUI 的 `user/default/workflows`，让面板直接可见 |
| `COMFY_API_DIR` | `<plugin>/api` | API JSON 输出目录 |
| `COMFY_OBJINFO` | 空 | schema 快照路径；留空则依次找包内 `objinfo_latest.json`，再退化到在线 `/object_info` |

---

## 7. 接入 DSH 的映射建议

`plugin.json` 已是自描述 manifest，字段与常见插件框架一一对应：

| manifest 字段 | 宿主侧用途 |
|---|---|
| `python.entry_module` / `entry_file` | 插件加载入口（`import gameart_pipeline`）与源码位置 |
| `actions[].entry` | 注册可调用动作（`gameart_pipeline.run` 等），反射到 Python 函数 |
| `actions[].inputs` | 生成参数表单 / JSON Schema 校验 |
| `env` | 启动前注入或校验环境变量 |
| `pipelines[]` | 生成素材产线菜单，`workflow` 用于“在面板中打开” |
| `requires` | 安装前置检查（缺模型时给出明确提示，而不是跑到一半报错） |
| `art_direction` | 画风约束，可用于生成侧提示词拼装或结果校验 |

分层建议：**manifest 只做描述，业务逻辑全在 `runner.py`**。如果 DSH 有自己的 manifest 规范（字段名 / 目录约定 / 生命周期钩子），只需重写 `plugin.json` 这一层，`gameart_pipeline/` 包不动——`runner.py` 不依赖任何宿主 API，只用标准库 + 本地 HTTP。

两个接入注意点：

1. **首次调用前先 `info()`**。`ckpt_ready=false` 说明底模名字对不上（换过版本 / 改过文件名），此时 `run()` 会在 ComfyUI 侧报节点错误，不如提前拦。
2. **`run()` 是同步阻塞的**（08 约 1~2 分钟，09 双分支最长约 5 分钟，10 的 SAM 链 2~3 分钟）。宿主侧放工作线程或独立进程，不要卡 UI 主线程；超时默认 560s，别往下压。

---

## 8. 踩坑记录（复现前必读）

1. **schema 必须来自真实服务**。`/object_info` 里的枚举（`ckpt_name`、`sampler_name`、ControlNet 列表）才准，手写枚举必然生成打不开的 JSON。
2. **09 别用生成模型抠图**。SDXL 出的 UI 底板背景不可控，色键和 RMBG 都会翻车，规整矩形用几何 alpha 才稳。
3. **10 的 GrowMask 要克制**。expand 70 吃颈肩，25 才干净——这值是目检调出来的，不是公式。
4. **二次元立绘的手部检测不可信**。hand_yolov8s 会把手饰、领口装饰识别成手。
5. **切图不能按 1024 硬切**。SDXL 出的面板尺寸 / 位置不固定，必须先按 alpha 求 bbox 再切，否则切空切歪。
6. **中心块必须重建纯色**。直接裁面板中心会带十字线 / 纹样，双向拉伸时出现断裂。
7. **Note 节点不进 API**。写进 UI JSON 只是给人看的，`to_api()` 已过滤。
8. **`control_after_generate`**：UI 格式的 seed 控件要在 `widgets_values` 末尾追加 `"randomize"`，否则前端加载后控件错位。

---

## 9. 联调自检清单

- [ ] `python -m gameart_pipeline.runner info` → `online=true`、`ckpt_ready=true`、`schema_nodes>1500`
- [ ] `build` 四条全部 `ok=true`（08=9 / 09=47 / 10=22 / 11=16 节点）
- [ ] `workflows/` 与 `api/` 下的 JSON 能被 ComfyUI 前端拖入且不报错
- [ ] 先用 `run("11")` 冒烟（16 节点最快）
- [ ] `run("08")` 出图 1920×1080 RGB
- [ ] `run("09")` 出图后接 `slice_panel()`，9 块齐全、中心块纯色
- [ ] `run("10")` 输出两层，alpha 互斥、无黑边
- [ ] `samples/` 里的样本图与当前环境出图风格一致（底模没被换过）

---

## 10. 已知限制

- 09 面板四角为直角，无圆角；需要在引擎侧叠遮罩。
- 10 只拆 head / body 两层，没有四肢与手部分件；要做骨骼动画请在引擎里继续分件。
- 10 的 SAM 依赖 `sam_vit_b`，8.5G 显存下 640×896 是安全区，上 1024 容易 OOM。
- 11 是黑底 RGBA，必须加色混合使用。
- 00~07 未纳入插件 API（历史一版，未复验）。
- 全部产线固定日式萌系风格，切换画风需换底模 + 全部提示词，不是调一个参数的事。
