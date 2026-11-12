# 第三方资产声明 / Third-Party Notices

本包（`dsh-gameart`）的**自有代码**以 [MIT License](LICENSE) 授权。

本文件说明的是**运行时依赖的第三方资产**。这些资产**不在本仓库内**，也不随包分发；
使用者需自行取得合法授权，并自行承担相应的许可义务。

The package's **own code** is licensed under the [MIT License](LICENSE).
This file covers **third-party assets used at runtime**. None of them are bundled
in this repository or distributed with the package.

---

## 模型权重 / Model weights

**仓库内不含任何模型权重。** 本包只包含工作流 JSON（ComfyUI 的 API 格式）与调用逻辑，
权重需由使用者自行下载并放置到 ComfyUI 的 `models/` 目录。

This repository contains **no model weights**. It ships workflow JSON (ComfyUI API
format) and call logic only; you must obtain the weights yourself.

| 资产 | 用途 | 许可 |
| --- | --- | --- |
| **animagine-xl-3.1** — Cagliostro Lab | SDXL 底模，用于 08/09/11 产线 | CreativeML Open RAIL++-M（见 [模型卡](https://huggingface.co/cagliostrolab/animagine-xl-3.1)） |
| **anything-v5-PrtRE** | SD1.5 底模，用于 00–07 产线 | 遵循其发布方声明的许可 |

使用、再分发与商用前，请阅读对应模型的许可原文。
CreativeML Open RAIL++-M 包含**使用限制条款**（Attachment A），
对用途有约束，不只是一份开源声明。

## 软件 / Software

| 项目 | 许可 |
| --- | --- |
| **ComfyUI** — comfyanonymous | GPL-3.0（https://github.com/comfyanonymous/ComfyUI） |
| 产线依赖的各 `custom_nodes` 插件 | 各自遵循其仓库声明的许可 |

本包通过 HTTP 调用本地 ComfyUI，**不链接也不分发** ComfyUI 本体或其插件。

## 生成内容 / Generated output

`workflows/` 与 `api/` 下的工作流 JSON 由本包的 `gameart_pipeline` 生成，可自由修改。
`gameart_pipeline/objinfo_latest.json` 是 ComfyUI `/object_info` 的离线快照，
仅用于离线校验节点 schema。

`samples/` 下的图片为本产线实际生成结果的样例，仅用于测试与验收回归。

**生成图的著作权归属**依所在地法律与底模许可而定。本包不对生成结果主张任何权利，
也不对其可用性、独创性或可商用性作任何担保。
