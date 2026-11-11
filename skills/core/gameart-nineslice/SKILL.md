---
name: gameart-nineslice
description: |
  UI 九宫格（9-slice）从出图到进引擎的完整验收流程：为什么要按 alpha 包围盒裁边、
  为什么中间块必须用单一纯色重建、角块边长的夹取规则、切图后怎么逐张检查接缝、
  以及导入 Unity / Godot / Cocos 时 border 该怎么填。
  09 产线出完面板后必读；也用于「九宫格拉伸后糊了 / 接缝有缝 / 圆角变形」的排查。
  触发词：九宫格、9-slice、nine patch、nineslice、UI 面板、切图、拉伸糊、border、圆角。
---

# 九宫格：切图与验收

## 为什么要切

一张 UI 对话框面板，如果整张拉伸到不同尺寸，圆角和描边会被横向拉糊。
九宫格把图切成 9 块（四角固定、四边单向拉伸、中间双向铺开），引擎按 border 内边距
重新拼装，任何尺寸下圆角都是原样。

## 流程

1. `gameart_run` 跑 `09`，拿到 `ui_panel_9slice_*.png`（1024×1024 RGBA）。
2. `gameart_slice9` 切图，参数：
   - `src`：面板 PNG 绝对路径；
   - `corner`：角块边长，默认 160。会被夹到 `[16, min(w,h)/4]`。
3. 检查返回的 `corner`、`center_rgb`、`files`。
4. 逐张看切块，尤其是四角。
5. 告诉用户 border 怎么填（见下）。

## 三个必须理解的设计决定

### 1. 先按 alpha 包围盒裁边，再切

产线出的 1024×1024 面板，实际有内容的区域往往比画布小（四周是透明留白）。
如果直接按画布切，九宫格的 160px 角块里可能一半是透明，切出来的边会「缺一块」。
所以 `slice9` 第一步是 `trim_alpha(im, thr=8)` 把透明边去掉（返回的文件名带
`_trim_<w>x<h>`，就是裁后的实际尺寸）。

### 2. 中间块必须用**单一纯色**重建

中间块在引擎里是要被双向平铺/拉伸的。如果直接裁原图中部，那里往往带着渐变、高光、
噪点、或者和边框对齐的纹样——拉伸之后就是一条一条的脏纹。

所以 `slice9` 取中心 35%–65% 区域的**有效像素（alpha>200）平均色**，
重建成一块 `(w-2c, h-2c)` 的纯色 RGBA（alpha=255）。返回里的 `center_rgb` 就是这个颜色。

**这是刻意的取舍**：面板有真实渐变/纹理时，纯色中间块会显得比原图平。
遇到这种情况别去改 `slice9`，正确做法是让美术给中间单独一张可平铺的贴图，
或者接受纯色。硬拉伸原图中部一定更糟。

### 3. 角块边长会被夹取

`c = min(C, max(16, w//4), max(16, h//4))`。传 160 但面板裁完只有 600 宽时，
`w//4 = 150`，实际角块就是 150。**返回里的 `corner` 是实际用的值，以它为准**，
不要拿你传进去的 160 去填引擎的 border。

## 输出文件

```
<src 同级>/nineslice/
  <base>_panel_trim_<w>x<h>.png          裁边后的完整面板（先看这张）
  <base>_9slice_tl_<w>x<h>.png           左上
  <base>_9slice_tc_<w>x<h>.png           上边（横向拉伸）
  <base>_9slice_tr_<w>x<h>.png
  <base>_9slice_ml_<w>x<h>.png           左边（纵向拉伸）
  <base>_9slice_mc_<w>x<h>.png           中间（双向，纯色）
  <base>_9slice_mr_<w>x<h>.png
  <base>_9slice_bl_<w>x<h>.png
  <base>_9slice_bc_<w>x<h>.png
  <base>_9slice_br_<w>x<h>.png
```

`out_dir` 不传就落在 `nineslice/`；想放别处显式给。

## 导入引擎

主流引擎都是「一张整图 + 四个 border 数值」，不是九张贴图。所以：

- **优先把裁边后的整张 `_panel_trim_*.png` 拖进引擎**，border 填 `corner` 那个实际值。
- 只有在引擎不支持九宫格、或要手工拼 UI 时，才用九张散块。

| 引擎 | 怎么设 |
|------|--------|
| Unity | Sprite Editor → Border 填 L/R/T/B = corner；Image 组件 Type = Sliced，Pixels Per Unit Multiplier 调密度 |
| Godot | `NinePatchRect`，`texture` 指向整图，`patch_margin_left/right/top/bottom` = corner |
| Cocos | Sprite 组件 `type = SLICED`，`border` 四值 = corner |

## 验收清单

- [ ] 四角（tl/tr/bl/br）尺寸都是 `corner × corner`，不是被裁歪的矩形；
- [ ] 四角内容完整——圆角没缺、描边没断；
- [ ] `mc` 是纯色，`read_image` 看它没有纹理；
- [ ] 四条边（tc/bc/ml/mr）是「可拉伸的一段」，不是半个角；
- [ ] 引擎里实际拉一个超宽 + 超高尺寸试一遍，圆角不变形、没有缝。

## 排查

| 现象 | 原因 | 怎么办 |
|------|------|--------|
| 角块里有透明缺口 | 没裁边就切，或面板本身留白不均 | 先看 `_panel_trim_*`，再看返回的 `corner` 对不对 |
| 拉伸后中间有竖条脏纹 | 用了原图中部当中间块（不是本工具的行为） | 确认走的是 `gameart_slice9` |
| 圆角被压扁 | 引擎 border 填得比 `corner` 大 | 按返回的 `corner` 重填 |
| 边缘有 1px 亮线 | 缩放插值 | 引擎里关掉 filter，或用 point 采样 |
| 面板本身四角不对称 | 出图问题，不是切图问题 | 回去用 `09` 重出，prompt 加 `symmetrical, centered, border` |
