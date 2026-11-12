---
name: gameart-troubleshoot
description: |
  ComfyUI 美术产线出问题时的体检顺序与对症表：ComfyUI 没起来、底模对不上、
  节点 schema 过期、显存不足、提交被拒、执行报错、轮询超时、桥接层拿不到结果。
  任何 gameart_* 工具返回 ok=false，或用户说「出不来图 / 报错 / 卡住」时读这篇。
  触发词：报错, 失败, 出不来, 卡住, 超时, 显存, OOM, 连不上, ComfyUI 没起, 模型不对, schema。
---

# 排障

## 第一件事：分清是「环境问题」还是「图的问题」

调 `gameart_status`。三行就能定位：

| 字段 | 不对时说明 | 处理 |
|------|-----------|------|
| `online: false` | ComfyUI 进程没在 8188 上 | **让用户启动**（见下） |
| `ckpt_ready: false` | 底模名对不上 | 让用户补模型/改名 |
| `schema_nodes` < 1500 | 节点 schema 快照过期/缺 custom_nodes | 见「schema」一节 |

三个都对，问题才在图本身。

## ComfyUI 没起来

`online: false`，`error` 里通常是 `URLError: <urlopen error [WinError 10061] 由于目标计算机积极拒绝…>`。

**不要自己去 shell 里拉 ComfyUI。** 让用户启动：

```
E:\AAAKI\ComfyUI-aki\ComfyUI-aki-v3\绘世启动器.exe
```

启动后确认 8188 通了再继续。如果用户说「已经在跑了」但还是连不上：
- 端口被改了（看启动器里的端口设置，用 `comfyBase` 配置覆盖默认的 `http://127.0.0.1:8188`）；
- 装在另一台机器上（`comfyBase` 指过去）；
- 启动器开了「仅本机」之外的绑定限制。

## 底模对不上

`ckpt_ready: false` 意思是 `<ComfyUI>/models/checkpoints/` 里没有
`animagine-xl-3.1.safetensors` 这个名字。

**不要改代码里的 `CKPT` 常量**。两条正路：
1. 让用户补装 `animagine-xl-3.1.safetensors`；
2. 用户手上是别的文件名（比如 `animagineXL31.safetensors`）时，让用户改名成
   `animagine-xl-3.1.safetensors`，这样 SDXL 那几条产线都不用动；00~07 另需 SD1.5 底模 `anything-v5-PrtRE.safetensors`。

换底模是另一回事：换成别的 SDXL 动漫模型大多能跑，但风格和 `no humans` 那套负向词
是照着 animagine 调的，需要重新试。

## schema 不对

`gameart_status` 返回的 `schema_nodes` 明显偏小（正常 1800 上下），或者
`gameart_build` 报「节点类型不存在」：

1. 产线优先读包内的 `objinfo_latest.json`（离线快照）。它过期了就跟当前 ComfyUI 对不上。
2. 设 `COMFY_OBJINFO=` 空字符串可以强制走在线 `/object_info`。
3. 也可能是 `custom_nodes` 没装全——看 `plugin.json` 里 `requires.custom_nodes` 那 7 个。

## 显存不足

8.5 GB（RTX 5060 Laptop）。症状：`stage: exec`，error 里带 `out of memory` / `CUDA`。

- 08 的 `batch_size` 从 2 降到 1；
- 11 的 `batch_size` 从 3 降到 2（或 1），分两次跑；
- 10 的 SAM 链本身就吃显存，别同时跑别的产线；
- 关掉 ComfyUI 里别的工作流，或重启 ComfyUI 清缓存。

**不要**去调小 `steps` 或 `cfg` 来省显存——那不省显存，只会让图变差。

## 提交被拒（stage: submit）

ComfyUI 收到 `/prompt` 但返回了错误。最常见三种：

1. **模型名不存在** —— `ckpt_name` 跟实际文件名不一致（同「底模对不上」）；
2. **节点类型不存在** —— `custom_nodes` 缺（`stage: validate` 会更早报出来）；
3. **输入类型不匹配** —— 某个 widget 的值类型/枚举不对，多半是 `sampler_name` / `scheduler`
   写了个当前 ComfyUI 不认识的字符串。

## 执行报错（stage: exec）

`error` 里带 `node_errors`，指明是哪个节点。常见：
- `RMBG-2.0` / `SAMDetectorCombined` 模型文件没下（10 产线依赖）；
- `AILab_*` 节点版本不兼容（09/10 用的）。

按节点名去 `custom_nodes` 目录里确认那个包在不在、版本对不对。

## 轮询超时（stage: timeout）

**先别重提。** ComfyUI 很可能还在跑：

1. `gameart_status` 看还连得上吗；
2. 连得上就等一下再看 `output/GameArt/` 目录有没有新文件；
3. 确实没动静了再重提。

超时线是 560 秒，09/10 正常也就 3–5 分钟，超到 560 说明真的卡住了。
`timeout` 参数**不要为了「快点失败」而调小**。

## 桥接层拿不到结果（stage: bridge）

`error` 说「桥接脚本没有输出结果」，看返回里的 `stderr`：

- `ModuleNotFoundError: No module named 'numpy'` / `PIL` —— 解释器选错了。
  设 `GAMEART_PYTHON` 环境变量，或插件配置 `pythonPath`，指到一个装了 numpy + Pillow 的 Python。
- `ModuleNotFoundError: gameart_pipeline` —— `plugin_root` 指错了，
  那个目录下必须有 `gameart_pipeline/runner.py`。
- 中文乱码 / `UnicodeEncodeError` —— 桥接层已经强制 UTF-8；如果还出，检查是不是
  用户自己包了一层脚本没带 `PYTHONUTF8=1`。

## 找不到产线包

`error` 说「找不到 gameart_pipeline 包」。三种给法（优先级从高到低）：
1. 调用时传 `plugin_root`；
2. 插件配置 `pluginRoot`；
3. 用本 bundle 自带的那份（默认就是这个，通常不会失败）。

package.json 里 `files` 如果漏了 `gameart_pipeline`，装成 node_modules 之后就会缺——检查一下。

## 出图但质量不对

这是**提示词问题，不是环境问题**。转 `gameart-prompting` 的「画风不对体检顺序」。
最常见的三个：中文写进了 prompt、质量词/负向词被替换掉了、
要的东西这套底模出不了（像素风 / 3D / 写实）。
