# -*- coding: utf-8 -*-
"""插件对外接口层。宿主（DSH 或任意插件框架）只需依赖这里 4 个函数：

    list_pipelines()                  -> 产线清单（含能力描述、可覆盖参数）
    build(ids=None)                   -> 生成 UI JSON + API JSON 并做本地校验
    run(pipeline_id, overrides=None)  -> 提交 ComfyUI 执行并轮询结果
    info()                            -> 运行环境/模型/节点自检

设计约束：
- 不依赖 ComfyUI 前端，只用 HTTP（/prompt、/history、/object_info、/system_stats）；
- 不写任何插件目录以外的路径，输出统一落在包内 workflows/ 与 api/；
- 所有网络地址、目录都可用环境变量覆盖，便于宿主注入沙箱路径。
"""
import os
import json
import time

try:
    from . import pipelines as P
    from . import wf_lib
except ImportError:  # 允许脚本式调试
    import pipelines as P
    import wf_lib


# 允许宿主覆盖的全局数值参数（KV 型 widget）
OVERRIDABLE_WIDGETS = (
    "seed", "steps", "cfg", "denoise", "width", "height",
    "batch_size", "sampler_name", "scheduler", "ckpt_name",
)

META = {
    "08": {
        "title": "场景背景",
        "use": "横版关卡/大厅背景，无人物",
        "output": "1920x1080 RGB PNG，batch=2",
        "params": ["prompt", "negative", "seed", "steps", "cfg", "width", "height"],
    },
    "09": {
        "title": "UI 九宫格面板 + 元素板",
        "use": "UI 底板 9-slice 切图 + 一板式控件元素",
        "output": "1024x1024 RGBA，面板/元素板各一；切块由窗口脚本完成",
        "params": ["prompt", "negative", "seed", "steps", "cfg"],
    },
    "10": {
        "title": "角色部件分层",
        "use": "对接 Spine/DragonBones，输出 head/body 互斥两层",
        "output": "640x896 RGBA x2，透明区 RGB 已清零",
        "params": ["prompt", "negative", "seed", "steps", "cfg"],
    },
    "11": {
        "title": "光效粒子贴图",
        "use": "加色混合叠加的黑底能量/粒子贴图",
        "output": "1024x1024 RGBA，batch=12",
        "params": ["prompt", "negative", "seed", "steps", "cfg"],
    },
}


def list_pipelines():
    """返回产线清单，供插件 UI 生成菜单/参数表单。"""
    out = []
    for k in sorted(P.BUILDERS):
        m = META.get(k, {})
        out.append({
            "id": k,
            "name": P.NAMES[k],
            "title": m.get("title", P.NAMES[k]),
            "use": m.get("use", ""),
            "output": m.get("output", ""),
            "params": m.get("params", []),
            "workflow_file": os.path.join(P.WF_DIR, P.NAMES[k] + ".json"),
            "api_file": os.path.join(P.API_DIR, "api_%s.json" % k),
        })
    return out


def apply_overrides(graph, overrides):
    """把宿主传入的参数写入图。返回实际生效的键。

    prompt / negative 按 CLIPTextEncode 节点在图中出现的顺序取第 0 / 第 1 个，
    这是四条产线统一的构图约定（均为先正向后负向）。
    """
    overrides = dict(overrides or {})
    applied = []

    for key in ("prompt", "negative"):
        if key in overrides and overrides[key]:
            idx = 0 if key == "prompt" else 1
            hits = [nid for nid, n in graph.nodes.items() if n["type"] == "CLIPTextEncode"]
            if len(hits) > idx:
                graph.nodes[hits[idx]]["widgets"]["text"] = overrides.pop(key)
                applied.append(key)
            else:
                overrides.pop(key)

    for key, val in list(overrides.items()):
        if key not in OVERRIDABLE_WIDGETS:
            continue
        touched = False
        for node in graph.nodes.values():
            if key in node["widgets"]:
                node["widgets"][key] = val
                touched = True
        if touched:
            applied.append(key)
        overrides.pop(key)

    return applied


def build(ids=None, write=True):
    """构建工作流 JSON。write=False 时只做内存校验，不落盘。

    返回 {id: {"ok": bool, "nodes": int, "ui": path, "api": path, "errors": [...]}}
    """
    ids = ids or sorted(P.BUILDERS)
    result = {}
    for k in ids:
        if k not in P.BUILDERS:
            result[k] = {"ok": False, "errors": ["未知产线: %s" % k]}
            continue
        graph = P.BUILDERS[k]()
        errors = graph.validate()
        if errors:
            result[k] = {"ok": False, "errors": errors}
            continue
        ui = graph.to_ui()
        api = graph.to_api()
        item = {"ok": True, "nodes": len(ui["nodes"])}
        if write:
            os.makedirs(P.WF_DIR, exist_ok=True)
            os.makedirs(P.API_DIR, exist_ok=True)
            p_ui = os.path.join(P.WF_DIR, P.NAMES[k] + ".json")
            p_api = os.path.join(P.API_DIR, "api_%s.json" % k)
            with open(p_ui, "w", encoding="utf-8") as f:
                json.dump(ui, f, ensure_ascii=False, indent=1)
            with open(p_api, "w", encoding="utf-8") as f:
                json.dump(api, f, ensure_ascii=False, indent=1)
            item["ui"] = p_ui
            item["api"] = p_api
        result[k] = item
    return result


def run(pipeline_id, overrides=None, timeout=560):
    """提交一条产线并等待完成。返回 submit 结果 + 实际生效参数。"""
    if pipeline_id not in P.BUILDERS:
        return {"ok": False, "stage": "input", "error": "未知产线: %s" % pipeline_id}
    graph = P.BUILDERS[pipeline_id]()
    errors = graph.validate()
    if errors:
        return {"ok": False, "stage": "validate", "error": errors}
    applied = apply_overrides(graph, overrides)
    t0 = time.time()
    res = graph.submit(timeout=timeout)
    res["pipeline"] = pipeline_id
    res["applied_overrides"] = applied
    res.setdefault("elapsed", round(time.time() - t0, 1))
    return res


def slice_panel(src, out_dir=None, C=160):
    """把 09 产线出的面板图切成 9 块（9-slice 素材）。

    C 为角块边长上限，实际取 min(C, w//4, h//4)；中心块用面板中心均色重建纯色，
    避免双向拉伸时出现断裂纹样。返回 {ok, panel, size, corner, center_rgb, files}。
    """
    try:
        from .slicing import slice9, trim_alpha  # noqa: F401
    except ImportError:
        from slicing import slice9, trim_alpha  # noqa: F401

    if not os.path.isfile(src):
        return {"ok": False, "error": "文件不存在: %s" % src}
    out_dir = out_dir or os.path.join(os.path.dirname(src), "nineslice")
    try:
        panel, files, c, mean = slice9(src, out_dir, C)
    except Exception as e:
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    return {
        "ok": True,
        "panel": os.path.join(out_dir, "%s_panel_trim_%dx%d.png" % (
            os.path.splitext(os.path.basename(src))[0], panel.size[0], panel.size[1])),
        "size": list(panel.size),
        "corner": c,
        "center_rgb": list(mean),
        "files": files,
    }


def info():
    """环境自检：ComfyUI 是否在线、schema 是否可用、关键模型是否落盘。"""
    import urllib.request

    out = {"comfy_base": wf_lib.BASE, "workflow_dir": P.WF_DIR, "api_dir": P.API_DIR}

    try:
        with urllib.request.urlopen(wf_lib.BASE + "/system_stats", timeout=10) as r:
            stats = json.loads(r.read().decode("utf-8"))
        dev = (stats.get("devices") or [{}])[0]
        out["online"] = True
        out["comfyui"] = {
            "version": stats.get("system", {}).get("comfyui_version"),
            "python": stats.get("system", {}).get("python_version"),
            "torch": dev.get("torch_version"),
            "device": dev.get("name"),
            "vram_total": dev.get("vram_total"),
        }
    except Exception as e:
        out["online"] = False
        out["error"] = "%s: %s" % (type(e).__name__, e)

    out["schema_nodes"] = len(wf_lib.OI)
    required_ckpt = wf_lib.OI.get("CheckpointLoaderSimple", {}) \
        .get("input", {}).get("required", {}).get("ckpt_name", [None, {}])
    choices = required_ckpt[0] if isinstance(required_ckpt, list) and required_ckpt else []
    out["ckpt_ready"] = P.CKPT in (choices or [])
    out["pipelines"] = sorted(P.BUILDERS)
    return out


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        print(json.dumps(list_pipelines(), ensure_ascii=False, indent=2))
    elif cmd == "info":
        print(json.dumps(info(), ensure_ascii=False, indent=2))
    elif cmd == "build":
        print(json.dumps(build(sys.argv[2:] or None), ensure_ascii=False, indent=2))
    elif cmd == "run":
        pid = sys.argv[2]
        ov = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
        print(json.dumps(run(pid, ov), ensure_ascii=False, indent=2))
    elif cmd == "slice":
        src = sys.argv[2]
        out = sys.argv[3] if len(sys.argv) > 3 else None
        c = int(sys.argv[4]) if len(sys.argv) > 4 else 160
        print(json.dumps(slice_panel(src, out, c), ensure_ascii=False, indent=2))
    else:
        print("用法: python -m gameart_pipeline.runner [list|info|build|run|slice]")
