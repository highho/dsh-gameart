# -*- coding: utf-8 -*-
"""gameart_pipeline —— ComfyUI 游戏美术工作流组插件包。

对外只有 runner 的 5 个函数：
    list_pipelines() / build() / run() / slice_panel() / info()
"""
from .runner import list_pipelines, build, run, slice_panel, info  # noqa: F401

__version__ = "1.0.0"
__all__ = ["list_pipelines", "build", "run", "slice_panel", "info"]
