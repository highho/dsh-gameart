---
name: gameart-pipeline
description: |
  游戏美术产线组的总入口与操作规程。接手任何「出游戏美术图」的任务时先读这一篇：
  十二条产线（00 角色概念 / 01 立绘透明底 / 02 表情差分 / 03 线稿上色 / 04 三视图 /
  05 道具图标 / 06 无缝贴图 / 07 高清放大 / 08 场景背景 / 09 UI 九宫格 /
  10 角色部件分层 / 11 光效粒子）各自的用途与输出规格、
  ComfyUI 开工前自检、工具调用顺序、输出文件落在哪、以及绝对不能做的事。
  触发词：出图、画一张、生成美术资源、游戏背景、UI 面板、角色立绘、概念设计、表情差分、
  线稿上色、三视图、道具图标、无缝贴图、高清放大、拆件、光效、粒子贴图、
  ComfyUI、SDXL、SD1.5、animagine、anything-v5、美术产线。
---

# 游戏美术产线组 · 总规程

## 这套东西是什么

十二条**已经调好的** ComfyUI 产线，统一日式萌系（japanese anime / moe）画风。底模用
两代并存：**00~07 全部跑 SD1.5 `anything-v5-PrtRE.safetensors`**，**08/09/11 跑 SDXL
`animagine-xl-3.1.safetensors`**（10 走 SAM 分割，不加载底模）。03/06 的 ControlNet 只有 SD1.5
权重，把 SDXL 底模配上去会直接加载失败。你要做的不是「想个提示词丢进去」，
而是**判断该用哪条产线、把用户的模糊需求翻译成标签、跑完验收、告诉用户下一步怎么接**。

| id | 产线 | 输出什么 | 什么时候用 |
|----|------|----------|-----------|
| 00 | 角色概念设计 | 640×896 RGB ×4（batch=4） | 出方案阶段铺量，定稿后进 01 |
| 01 | 立绘透明底 | 640×896 RGBA（BiRefNet 抠图） | 直接进引擎/UI；02 的输入 |
| 02 | 表情差分 | 与输入同尺寸 RGBA | 只改脸，身体像素 100% 不变 |
| 03 | 线稿上色 | 640×896 RGB | 线稿/草图上色，双层 ControlNet 锁线 |
| 04 | 三视图设定稿 | 1152×768 RGB | 给建模/动作用的正/侧/背 |
| 05 | 道具图标 | 512×512 RGBA ×4 | 装备/道具/材料图标 |
| 06 | 无缝贴图 | 512×512 RGB | 四向无缝地面/墙面材质 |
| 07 | 高清放大 | 双分支各一张 | A 纯超分保真 / B 分块重绘补细节 |
| 08 | 场景背景 | 1920×1080 RGB ×2（batch=2） | 横版关卡底、大厅、过场背景。**必须无人物** |
| 09 | UI 九宫格 | 1024×1024 RGBA：面板 + 一板式元素 | UI 底板 9-slice 切图、控件元素 |
| 10 | 角色部件分层 | 640×896 RGBA ×2：head / body 互斥两层 | 对接 Spine / DragonBones |
| 11 | 光效粒子 | 1024×1024 RGBA ×3（batch=3） | 加色混合的能量/粒子贴图 |

**典型串法**：00 铺量定稿 → 01 出透明立绘 → 02 刷表情 / 10 拆件 → 07 放大交付。
道具走 05，场景走 08，UI 走 09 再 `gameart_slice9`，材质走 06，特效走 11。

**风格边界是硬的**：只做日式动画萌系。用户要像素风（pixel art）、3D 渲染、写实照片、
欧美卡通、水墨——直说这套产线出不了，给替代方案，不要硬跑一条出一堆不对的图。

## 开工顺序（不要跳）

1. `gameart_status` —— 看 `ready`。
   - `online=false`：ComfyUI 没起来。**让用户去启动**（`E:\AAAKI\ComfyUI-aki\ComfyUI-aki-v3\`
     下的 `绘世启动器.exe`），不要自己去 shell 里拉起 ComfyUI。等用户确认端口 8188 通了再继续。
   - `ckpt_ready=false`：底模名字对不上。让用户补模型或改名，**不要改代码里的 `CKPT` 常量**。
   - `schema_nodes` 明显小于 1500：节点 schema 快照过期或 custom_nodes 没装全。
2. `gameart_list` —— 确认产线 id 与可覆盖参数（不访问 ComfyUI，很便宜）。
3. `gameart_run` —— 提交并等待。
4. 按产线做后处理：09 必须 `gameart_slice9`；10 验收 head/body 不重叠；11 确认是黑底；01/05 确认背景全透（alpha==0）；02 确认身体像素未变；06 确认能 3×3 平铺。
5. 告诉用户文件在哪、怎么接进引擎。

## 工具

| 工具 | 用途 | 代价 |
|------|------|------|
| `gameart_status` | ComfyUI 在线/版本/显存/底模/schema 自检 | 秒级，可随便调 |
| `gameart_list` | 产线清单与可覆盖参数 | 秒级，纯静态 |
| `gameart_build` | 重建工作流 JSON 并本地校验 | 秒级，只在改过代码时需要 |
| `gameart_run` | 提交产线、阻塞等出图 | 慢：08 约 1–2 分钟，09/10 最久 3–5 分钟 |
| `gameart_slice9` | 09 面板切九宫格 | 秒级 |

## 出图落在哪

全部在 ComfyUI 的 `output/` 下，按产线分子目录：

```
<ComfyUI>/output/GameArt/00_Concept/char_concept_*.png
<ComfyUI>/output/GameArt/01_Sprite/sprite_alpha_*.png
<ComfyUI>/output/GameArt/02_Expression/expr_diff_*.png
<ComfyUI>/output/GameArt/03_Lineart/colorized_*.png
<ComfyUI>/output/GameArt/04_Turnaround/turnaround_*.png
<ComfyUI>/output/GameArt/05_Icon/item_icon_*.png
<ComfyUI>/output/GameArt/06_Tile/tile_seamless_512_*.png
<ComfyUI>/output/GameArt/07_Upscale/hd_sharp_*.png
<ComfyUI>/output/GameArt/07_Upscale/hd_detail_*.png
<ComfyUI>/output/GameArt/08_Background/bg_scene_*.png
<ComfyUI>/output/GameArt/09_UI/ui_panel_9slice_*.png
<ComfyUI>/output/GameArt/09_UI/ui_element_sheet_*.png
<ComfyUI>/output/GameArt/10_Parts/part_head_*.png
<ComfyUI>/output/GameArt/10_Parts/part_body_*.png
<ComfyUI>/output/GameArt/11_FX/fx_energy_*.png
```

`gameart_run` 返回的 `images[].relative` 就是相对 `output/` 的路径，拼上 ComfyUI 安装目录
（默认 `E:\AAAKI\ComfyUI-aki\ComfyUI-aki-v3\ComfyUI\output\`）才是磁盘绝对路径。
要读图确认效果，用 `read_image` 打开那个路径。

## 硬规矩

- **`gameart_run` 是阻塞的**。08 一两分钟、09/10 三五分钟起步。等待期间不要重复提交同一条产线，
  也不要因为「感觉卡住了」就再发一次——两只手同时在 ComfyUI 队列里只会互相拖慢。
- **不要为了快点把 `timeout` 调小**。默认 560 秒是照着 09/10 最慢情况定的。超时先 `gameart_status`
  看队列，不要立刻重提。
- **`prompt` 写英文 Danbooru 标签**，逗号分隔。写中文整句几乎必然出废图。怎么写见 `gameart-prompting`。
- **不传 `prompt` 就用产线内置默认构图**。想要稳定就显式给 `prompt` + `seed`。
- **08 永远不出现人**。产线自带的负向提示词已经排除了 humans / person / 1girl / 1boy / portrait，
  你自己往正向里写「一个女孩站在村口」是会打架的——08 是纯背景。
- **09 面板那条分支故意不做抠图**。别想着「顺手加个 RMBG 更干净」：实测颜色键抠图会把面板
  抠成 `nz=0.0000`，RMBG 会把角块判成 `nz=0.0012`。现在走的几何 alpha（INSET=26）是对的。
- **10 的 `GrowMask expand` 保持 25**。调到 70 会把脖子和肩吃进去。
- **01/05 抠图后不要再接 `InvertMask` + `JoinImageWithAlpha`**。`BiRefNetRMBG` 在
  `background=Alpha` 时 `out(0)` 已经是 RGBA，重复合成会二次反相把主体清空。
- **02 的三处坐标必须同时改**（`ImageCrop` x/y、`ImageScale` 目标尺寸、`ImageCompositeMasked` x/y）。
  只改一处会让脸贴歪或缩放变形。
- **03/06 必须配 SD1.5 底模**。它们的 ControlNet 只有 SD1.5 权重，换 SDXL 会加载失败。
- **04 必须一张宽画布单次出图**。拆成三个 KSampler 会把同一角色画成三个人（已实测）。
- **07 分支 B 的 `denoise` 低于 0.25**。再高就会改动原设定稿的设计细节。
- **别硬按 1024 切图**。RGBA 图先按 alpha 包围盒裁边再切，否则透明边距会把九宫格算歪。
- **改了 `pipelines.py` 之后**才需要 `gameart_build`。只想出图不用 build。

## 交付习惯

跑完别只丢一个路径。给用户：
1. 出了几张、在哪（绝对路径）；
2. 用了哪些关键参数（prompt / seed），**记下 seed**——用户说「就这个再来一张」时要能复现；
3. 这张图在引擎里怎么用（九宫格怎么导入、Spine 怎么挂槽位、光效用什么混合模式）；
4. 不满意时往哪个方向改（加什么标签、换什么 seed），而不是笼统说「可以再调」。
