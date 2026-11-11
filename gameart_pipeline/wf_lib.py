"""ComfyUI 工作流构建器：以 API 格式为唯一真源，生成 UI 格式 + 校验 + 提交实测。

插件化改造点（相对原始 wf_lib.py）：
1. BASE 由环境变量 COMFY_BASE 覆盖，默认 http://127.0.0.1:8188；
2. object_info 查找顺序：COMFY_OBJINFO 环境变量 -> 同目录 objinfo_latest.json
   -> 同目录 object_info.json -> 上一级 objinfo_latest.json -> 在线拉取并缓存。
   这样插件在不带 schema 快照的机器上也能自举。
"""
import json, os, time, urllib.request, urllib.error

TEMP = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("COMFY_BASE", "http://127.0.0.1:8188").rstrip("/")

_OBJINFO_CANDIDATES = [
    os.environ.get("COMFY_OBJINFO"),
    os.path.join(TEMP, "objinfo_latest.json"),
    os.path.join(TEMP, "object_info.json"),
    os.path.join(os.path.dirname(TEMP), "objinfo_latest.json"),
]


def load_object_info():
    """按候选路径加载节点 schema；全部缺失时向 ComfyUI 拉取并缓存。"""
    for p in _OBJINFO_CANDIDATES:
        if p and os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    try:
        with urllib.request.urlopen(BASE + "/object_info", timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        raise RuntimeError(
            "未找到节点 schema（object_info）。请用环境变量 COMFY_OBJINFO 指向导出的 "
            "object_info.json，或先启动 ComfyUI 后重试。原始错误: %s" % e)
    cache = os.path.join(TEMP, "objinfo_latest.json")
    try:
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass
    return data


OI = load_object_info()

WIDGET_LITERAL = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO", "COMFY_DYNAMICCOMBO_V3"}


def spec_of(ctype, name):
    d = OI[ctype]["input"]
    for sec in ("required", "optional"):
        if name in d.get(sec, {}):
            return d[sec][name], sec
    return None, None


def is_widget(ctype, name):
    sp, _ = spec_of(ctype, name)
    if sp is None:
        return False
    t = sp[0]
    if isinstance(t, list):
        return True
    return t in WIDGET_LITERAL


def ordered_inputs(ctype):
    d = OI[ctype]["input"]
    out = []
    for sec in ("required", "optional"):
        for k, v in d.get(sec, {}).items():
            out.append((k, v, sec))
    return out


class Node:
    def __init__(self, g, nid, ctype):
        self.g, self.nid, self.ctype = g, nid, ctype

    def out(self, slot=0):
        return (self.nid, slot)


class Graph:
    def __init__(self, name):
        self.name = name
        self.nodes = {}      # nid -> {"type":..., "widgets":{}, "links":{}}   links: name -> (src_nid, slot)
        self._seq = 0
        self.notes = []      # dict(text, x, y, w, h) 前端专用 Note

    def add(self, ctype, widgets=None, links=None, _id=None):
        assert ctype in OI, f"节点不存在: {ctype}"
        self._seq += 1
        nid = _id or str(self._seq)
        self.nodes[nid] = {"type": ctype, "widgets": dict(widgets or {}), "links": dict(links or {})}
        # 立即校验 widget 名称
        for k in self.nodes[nid]["widgets"]:
            assert not is_widget(ctype, k) is False or True
        for k in self.nodes[nid]["widgets"]:
            sp, _ = spec_of(ctype, k)
            assert sp is not None, f"{ctype} 无输入 {k}"
        for k in self.nodes[nid]["links"]:
            sp, _ = spec_of(ctype, k)
            assert sp is not None, f"{ctype} 无输入 {k}"
        return Node(self, nid, ctype)

    # ---------- API 格式 ----------
    def to_api(self):
        api = {}
        for nid, n in self.nodes.items():
            inputs = {}
            for k, v in n["widgets"].items():
                inputs[k] = v
            for k, (sid, slot) in n["links"].items():
                inputs[k] = [str(sid), slot]
            api[str(nid)] = {"class_type": n["type"], "inputs": inputs}
        return api

    # ---------- 校验 ----------
    def validate(self):
        errs = []
        for nid, n in self.nodes.items():
            ctype = n["type"]
            for k, v in n["links"].items():
                sp, _ = spec_of(ctype, k)
                if sp is None:
                    errs.append(f"[{nid}] {ctype}: 连线输入 {k} 不存在")
                    continue
                want = sp[0]
                sid, slot = v
                if sid not in self.nodes:
                    errs.append(f"[{nid}] {ctype}.{k}: 源节点 {sid} 不存在")
                    continue
                stype = self.nodes[sid]["type"]
                outs = OI[stype].get("output") or []
                names = OI[stype].get("output_name") or []
                if slot >= len(outs):
                    errs.append(f"[{nid}] {ctype}.{k}: {stype} 只有 {len(outs)} 个输出")
                    continue
                got = outs[slot]
                if isinstance(want, str) and isinstance(got, str) and want != got:
                    if not (want == "COMBO"):
                        errs.append(f"[{nid}] {ctype}.{k}: 需要 {want}，{stype}[{slot}] 给的是 {got}")
            # 必填检查
            req = OI[ctype]["input"].get("required", {})
            for k, v in req.items():
                if k in n["widgets"] or k in n["links"]:
                    continue
                t = v[0]
                # 有默认值的可省略；LATENT/IMAGE 等 socket 必填
                if isinstance(t, list) or t in WIDGET_LITERAL:
                    continue
                errs.append(f"[{nid}] {ctype}: 必填输入 {k} ({t}) 未提供")
        return errs

    # ---------- UI 格式 ----------
    def to_ui(self):
        api = self.to_api()
        ids = list(self.nodes.keys())
        # 拓扑深度
        depth = {nid: 0 for nid in ids}
        for _ in range(len(ids) + 2):
            for nid, n in self.nodes.items():
                for k, (sid, slot) in n["links"].items():
                    depth[nid] = max(depth[nid], depth[sid] + 1)

        # 第一遍：构建每个节点的 inputs/widgets 骨架
        prepared = {}
        for nid in ids:
            n = self.nodes[nid]
            ctype = n["type"]
            inputs_ui, widgets_vals = [], []
            for k, v, sec in ordered_inputs(ctype):
                tl = v[0] if isinstance(v[0], str) else "COMBO"
                if is_widget(ctype, k):
                    widgets_vals.append(n["widgets"].get(k, v[1].get("default") if len(v) > 1 else None))
                    extra = v[1] if len(v) > 1 else {}
                    if extra.get("control_after_generate"):
                        widgets_vals.append("randomize")
                    if k in n["links"]:
                        inputs_ui.append({"name": k, "type": tl, "link": None})
                else:
                    inputs_ui.append({"name": k, "type": tl, "link": None})
            prepared[nid] = {"inputs": inputs_ui, "widgets": widgets_vals}

        # 第二遍：连线（target_slot 必须落在真实 inputs 索引上）
        link_id = 0
        links_ui = []
        out_links = {nid: {} for nid in ids}
        for nid in ids:
            for k, (sid, slot) in self.nodes[nid]["links"].items():
                link_id += 1
                stype = self.nodes[sid]["type"]
                t = (OI[stype].get("output") or ["*"])[slot]
                ins = prepared[nid]["inputs"]
                tslot = next(i for i, x in enumerate(ins) if x["name"] == k)
                ins[tslot]["link"] = link_id
                links_ui.append([link_id, int(sid), slot, int(nid), tslot, t])
                out_links[sid].setdefault(slot, []).append(link_id)

        # 布局：按深度分列
        col_y = {}
        nodes_ui = []
        order = 0
        for nid in sorted(ids, key=lambda x: (depth[x], int(x))):
            n = self.nodes[nid]
            ctype = n["type"]
            x = 40 + depth[nid] * 400
            y = col_y.get(depth[nid], 80)
            inputs_ui = prepared[nid]["inputs"]
            widgets_vals = prepared[nid]["widgets"]

            outs = OI[ctype].get("output") or []
            names = OI[ctype].get("output_name") or []
            outputs_ui = []
            for i, ot in enumerate(outs):
                nm = names[i] if i < len(names) else ot
                outputs_ui.append({"name": nm, "type": ot, "links": out_links[nid].get(i, []), "slot_index": i})

            h = 46 + max(len(widgets_vals), len(inputs_ui)) * 26
            w = 380 if ctype not in ("Note", "MarkdownNote") else 460
            node_ui = {
                "id": int(nid), "type": ctype, "pos": [x, y], "size": [w, max(h, 80)],
                "flags": {}, "order": order, "mode": 0,
                "inputs": inputs_ui, "outputs": outputs_ui,
                "properties": {"Node name for S&R": ctype},
                "widgets_values": widgets_vals,
            }
            if ctype in ("Note", "MarkdownNote"):
                node_ui["title"] = "说明"
                node_ui["color"] = "#432"
                node_ui["bgcolor"] = "#653"
            nodes_ui.append(node_ui)
            col_y[depth[nid]] = y + max(h, 80) + 40
            order += 1

        # 前端专用 Note 节点（不进入 API）
        note_nodes = []
        nid_note = 900
        for nt in self.notes:
            note_nodes.append({
                "id": nid_note, "type": "Note", "pos": [nt.get("x", 40), nt.get("y", 40)],
                "size": [nt.get("w", 420), nt.get("h", 180)], "flags": {}, "order": -1, "mode": 0,
                "inputs": [], "outputs": [], "title": nt.get("title", "说明"),
                "properties": {"text": ""}, "widgets_values": [nt["text"]],
                "color": "#1f3a2f", "bgcolor": "#1a2b23",
            })
            nid_note += 1
        nodes_ui.extend(note_nodes)

        return {
            "id": "gameart-" + self.name,
            "revision": 0,
            "last_node_id": max([int(i) for i in ids] + [nid_note - 1]),
            "last_link_id": link_id,
            "nodes": nodes_ui,
            "links": links_ui,
            "groups": [],
            "config": {},
            "extra": {"ds": {"scale": 0.75, "offset": [0, 0]}},
            "version": 0.4,
        }

    # ---------- 提交 ----------
    def submit(self, timeout=900):
        data = json.dumps({"prompt": self.to_api(), "client_id": "marvis-gameart"}).encode()
        req = urllib.request.Request(BASE + "/prompt", data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            return {"ok": False, "stage": "submit", "error": body}
        pid = res.get("prompt_id")
        t0 = time.time()
        while time.time() - t0 < timeout:
            time.sleep(3)
            with urllib.request.urlopen(BASE + f"/history/{pid}", timeout=20) as r:
                h = json.loads(r.read().decode())
            if pid in h:
                entry = h[pid]
                st = entry.get("status", {})
                if st.get("status_str") == "error":
                    msgs = [m for m in st.get("messages", []) if m[0] == "execution_error"]
                    return {"ok": False, "stage": "exec", "error": msgs, "elapsed": round(time.time() - t0, 1)}
                imgs = []
                for nid, o in (entry.get("outputs") or {}).items():
                    for im in o.get("images", []):
                        imgs.append(im.get("filename"))
                return {"ok": True, "elapsed": round(time.time() - t0, 1), "images": imgs}
        return {"ok": False, "stage": "timeout"}
