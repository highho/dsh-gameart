# -*- coding: utf-8 -*-
"""DSH 桥接层：把 gameart_pipeline 的 5 个公开函数包成「一次调用 = 一个 JSON」。

为什么不直接跑 `python -m gameart_pipeline.runner`？
  1. 那个 CLI 的 build 分支打印的是人读文本（`[08] OK  nodes=9 …` / `ALL_OK`），
     不能稳定地被机器解析成结构化结果；
  2. 参数要经过 argv，而不是 shell 拼串，避免引号 / 中文 / JSON 被转义吃掉。

调用约定
    python -X utf8 lib/bridge.py <cmd> [arg ...]
        list
        info
        build [id ...]
        run   <pipeline_id> <overrides_json> [timeout_seconds]
        slice <src> <out_dir> [C]
        verify <kind> <path> [path2] [C]

输出约定（stdout，最后一行）
    __GAMEART_JSON__{"ok": true,  "data": ...}
    __GAMEART_JSON__{"ok": false, "error": "...", "traceback": "..."}

调用方只认最后一条带 `__GAMEART_JSON__` 前缀的行 —— 这样即使被调用链里
有人往 stdout 打了一行日志（wf_lib 里就有 for 循环里的 print），也不会污染结果。
"""
import json
import os
import sys
import traceback

MARKER = "__GAMEART_JSON__"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# ROOT 用来 import gameart_pipeline；HERE 用来 import 同目录的 imageqa
for _entry in (ROOT, HERE):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

try:  # Windows 默认 cp936，中文路径 / 中文错误信息会直接抛 UnicodeEncodeError
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover - 老解释器没有 reconfigure
    pass


def _json_default(value):
    """numpy 标量 / 数组不是 JSON 原生类型，这里统一降级。"""
    for attr in ("item", "tolist"):
        method = getattr(value, attr, None)
        if callable(method):
            try:
                return method()
            except Exception:  # pragma: no cover - 继续往下降级
                pass
    return str(value)


def emit(payload):
    sys.stdout.write(
        MARKER
        + json.dumps(payload, ensure_ascii=False, default=_json_default)
        + "\n"
    )
    sys.stdout.flush()


def _opt_str(argv, index):
    if len(argv) > index:
        value = argv[index]
        if value not in ("", "-", "null"):
            return value
    return None


def dispatch(cmd, rest):
    from gameart_pipeline import runner

    if cmd == "list":        return {"pipelines": runner.list_pipelines()}

    if cmd == "info":
        return runner.info()

    if cmd == "build":
        ids = [item for item in rest if item] or None
        return runner.build(ids=ids)

    if cmd == "run":
        pipeline_id = rest[0] if rest else ""
        if not pipeline_id:
            raise ValueError("run 需要 pipeline_id")
        overrides = {}
        if len(rest) > 1 and rest[1].strip() not in ("", "-", "null"):
            overrides = json.loads(rest[1])
        if not isinstance(overrides, dict):
            raise ValueError("overrides 必须是 JSON 对象")
        timeout = float(rest[2]) if len(rest) > 2 else 560.0
        return runner.run(pipeline_id, overrides=overrides, timeout=timeout)

    if cmd == "slice":
        src = rest[0] if rest else ""
        if not src:
            raise ValueError("slice 需要 src 路径")
        out_dir = _opt_str(rest, 1)
        corner = int(rest[2]) if len(rest) > 2 and rest[2].strip() else 160
        return runner.slice_panel(src, out_dir=out_dir, C=corner)

    if cmd == "verify":
        # 验收不碰 ComfyUI，也不进 gameart_pipeline，独立成一个只依赖 numpy/PIL 的模块
        kind = rest[0] if rest else ""
        if not kind:
            raise ValueError("verify 需要验收类型：alpha / flat / panel / mc / parts / fx")
        paths = [p for p in rest[1:] if p and p not in ("-", "null")]
        corner = 160
        if kind == "panel" and len(paths) > 1:
            # panel 允许尾部带一个 corner
            try:
                corner = int(paths[-1])
                paths = paths[:-1]
            except ValueError:
                pass
        import imageqa

        return imageqa.verify(kind, paths, corner=corner)

    raise ValueError("未知子命令: %s" % cmd)


def main(argv):
    if not argv:
        emit({"ok": False, "error": "缺少子命令；可用: list / info / build / run / slice"})
        return 2
    cmd, rest = argv[0], argv[1:]
    try:
        data = dispatch(cmd, rest)
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - 桥接层必须把任何异常翻成 JSON
        emit({
            "ok": False,
            "error": "%s: %s" % (type(exc).__name__, exc),
            "traceback": traceback.format_exc(limit=8),
        })
        return 1
    emit({"ok": True, "data": data})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
