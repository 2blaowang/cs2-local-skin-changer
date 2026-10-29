"""GUI 服务层 —— 纯 Python, 不依赖任何 GUI 框架。

设计原则
--------
界面只做展示与输入, 一切二进制操作仍由 scripts/ 下已验证的 CLI 逻辑完成。
本层不重写任何 VPK 逻辑, 只做三件事:

  1. 把 CLI 函数包装成"返回 dict"的形式 (CLI 靠 print, 这里统一捕获成 log 文本)
  2. 提供 UI 需要的只读查询 (武器 / kit / 贴图引用 / 刀型 / 状态)
  3. 每个写操作后自动跑审计, 失败结果如实上报

因此同一份服务层可以给 PySide6 直接用, 也可以套一层 HTTP 给
Electron / Tauri / WPF 用 —— 换前端不需要动这里。
"""
from __future__ import annotations

import contextlib
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import knife_mod as km          # noqa: E402
import skin_mod as sm           # noqa: E402

_ready = False
_cache: dict = {}


class ServiceError(RuntimeError):
    pass


# ---------------------------------------------------------------- 基础设施

def _capture(fn, *args, **kwargs):
    """跑一个会 print 的 CLI 函数, 返回 (返回值, 文本日志)"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ret = fn(*args, **kwargs)
    return ret, buf.getvalue()


def bootstrap(csgo: str | None = None) -> dict:
    """定位游戏目录 + 加载目录树。幂等, 重复调用只返回状态。"""
    global _ready
    if _ready:
        return state()
    path = csgo or km.find_csgo()
    if not path:
        raise ServiceError(
            "未找到 CS2 game/csgo 目录。请先用命令行跑一次：\n"
            '  python scripts/knife_mod.py --init --csgo "<...\\game\\csgo>"'
        )
    km.set_paths(path)
    tree = km.load_ref_tree()
    sm.tree_cache = tree
    _ready = True
    return state()


def _tree() -> dict:
    if not _ready:
        bootstrap()
    return sm.tree_cache


def state() -> dict:
    tree = _tree()
    bak_ok = os.path.exists(km.BAK_DIR)
    cur = km.read_dir()
    orig = open(km.BAK_DIR, "rb").read() if bak_ok else b""
    patched = bool(orig) and cur != orig
    return {
        "csgo": km.CSGO,
        "backup": bak_ok,
        "backup_path": km.BAK_DIR,
        "entries": len(tree),
        "size": len(cur),
        "patched": patched,
        "steam_updated": bool(orig) and len(cur) != len(orig),
    }


# ---------------------------------------------------------------- 只读查询

def weapon_map() -> dict:
    """{武器: {kit: vmat条目|None}} —— 含 composite-only kit (没有 vmat)"""
    if "wmap" in _cache:
        return _cache["wmap"]
    tree = _tree()
    full = {w: dict(v) for w, v in sm.build_map(tree).items()}
    kw = sm.kit_weapon_map(tree)
    for k in tree:
        if not k.startswith(sm.COMPMAT):
            continue
        kit = k.split("/")[-1]
        for w in kw.get(kit) or ():
            full.setdefault(w, {}).setdefault(kit, None)
    _cache["wmap"] = full
    return full


def _clean_cn(v: str | None) -> str:
    """本地化表里混着"值是另一个键"的别名 (如 PaintKit_cu_bizon_citizen),
    还有直接给 #Token 的, 这些都不能当名字显示"""
    if not v:
        return ""
    v = v.strip()
    if v.startswith("PaintKit_") or v.startswith("#") or v.startswith("SFUI_"):
        return ""
    return v


_BAG_CACHE: dict = {}
_WEAPON_TOKENS: set[str] = set()


def _bag(table: dict) -> dict:
    """按"词袋"建索引, 用来吃掉词序差异 (建一次缓存, 1418 个 kit 每次都重建太慢)

    材质目录和本地化键经常不是同一个顺序: 目录 `cu_rubber_ak47` 在表里是
    `cu_ak47_rubber`(火神), 目录 `sp_tape_short_sand` 在表里是
    `sp_short_tape_sand`(沙漠虚线)。纯靠精确匹配会漏掉几十个。
    """
    if not _BAG_CACHE:
        for k, v in table.items():
            _BAG_CACHE.setdefault(tuple(sorted(k.split("_"))), v)
    return _BAG_CACHE


def _weapon_tokens() -> set[str]:
    """全部武器目录名拆出来的词, 用于剥掉目录里多余的那段武器名"""
    if not _WEAPON_TOKENS:
        for w in weapon_map():
            for t in w.split("_"):
                if len(t) > 2:
                    _WEAPON_TOKENS.add(t)
    return _WEAPON_TOKENS


def _name(tree, kit: str) -> str:
    """kit -> 中文名, 逐级回落到内置常用表

    1. 精确命中 (已统一小写)
    2. 词袋命中 → 解决词序不同
    3. 剥掉武器词再查 → 解决目录带武器后缀而表里没有
    4. 内置 COMMON 表; 都不中返回空, 调用方显示 kit 原名
    """
    cn = sm.cn_names(tree)
    toks = kit.split("_")

    v = _clean_cn(cn.get(kit))
    if v:
        return v

    bag = _bag(cn)
    v = _clean_cn(bag.get(tuple(sorted(toks))))
    if v:
        return v

    wt = _weapon_tokens()
    stem = [t for t in toks if t not in wt]
    if stem and len(stem) < len(toks):
        v = _clean_cn(bag.get(tuple(sorted(stem))))
        if v:
            return v

    return sm.COMMON.get(kit, "")


def weapons() -> list[dict]:
    wmap = weapon_map()
    return [{"id": w, "kits": len(kits)} for w, kits in sorted(wmap.items())]


def _mat_keys(tree, kit: str) -> dict:
    """kit 的材质条目 {资源类型前缀: 树 key}

    **千万不要拼 `COMPMAT + kit`**: composite 皮肤的 vcompmat 放在
    `weapons/paints/community/community_35/<kit>` 这种子目录里, legacy 的放在
    `weapons/paints/legacy/<kit>`, 硬拼一律落空 —— 结果就是界面把全部
    composite 判成"没有材质资源条目"、换肤按钮全灰。
    """
    return sm._material_keys(tree, kit)


def _primary_key(tree, kit: str) -> str | None:
    """kit 的主材质条目, 贴图引用优先取 vmat

    legacy 的 vcompmat 只是一份"转交声明"(SPECIFIC_MATERIAL), 真正的
    albedo/mask/normal 引用都在 vmat 里; composite 没有 vmat, 只能看 vcompmat。
    """
    keys = _mat_keys(tree, kit)
    for p in (sm.VMATS, sm.COMPMAT):
        if p in keys:
            return keys[p]
    return None


def kits(weapon: str) -> list[dict]:
    """某武器的全部皮肤, 带中文名 / 形态 / style / 能否作为换肤入口"""
    tree = _tree()
    st = sm.kit_style(tree)
    out = []
    for kit in weapon_map().get(weapon, {}):
        has_entry = bool(_mat_keys(tree, kit))
        style, _cp = st.get(kit, ("?", None))
        out.append({
            "kit": kit,
            "cn": _name(tree, kit),
            "form": sm.form_of(tree, kit),
            "style": style,
            "entry": has_entry,
        })
    out.sort(key=lambda d: (d["cn"] or d["kit"]).lower())
    return out


def kit_detail(kit: str) -> dict:
    tree = _tree()
    key = _primary_key(tree, kit)
    if key is None:
        return {"kit": kit, "error": "该 kit 没有材质资源条目"}
    texs = []
    for p in sm.vtex_refs(key):
        k = "vtex_c:" + p
        if k not in tree:
            continue
        texs.append({"path": p, "name": p.split("/")[-1], "size": tree[k][5]})
    texs.sort(key=lambda d: -d["size"])
    return {
        "kit": kit,
        "cn": _name(tree, kit),
        "form": sm.form_of(tree, kit),
        "style": sm.kit_style(tree).get(kit, ("?", None))[0],
        "material": key.split(":", 1)[1],
        "material_size": tree[key][5],
        "textures": texs,
        "paint": paint_tex(kit),
    }


def paint_tex(kit: str) -> str | None:
    """kit 的主贴图 (皮肤图案本体), 排除引擎共享图后取最大那张"""
    tree = _tree()
    key = _primary_key(tree, kit)
    if key is None:
        return None
    best, best_size = None, -1
    for p in sm.vtex_refs(key):
        low = p.lower()
        if "/default_" in low or low.startswith("materials/default/"):
            continue
        if any(x in low for x in ("/shared/", "paintmask", "paintao", "_normal", "_rough")):
            continue
        k = "vtex_c:" + p
        if k in tree and tree[k][5] > best_size:
            best, best_size = p, tree[k][5]
    return best


def _icon_index() -> dict:
    """(武器目录名, kit, 尺寸) -> (vtex 相对路径, 检视图里的 UI 武器名)

    不能简单拼 `weapon_{武器}_{kit}`: M4A4 在 panorama 里叫 m4a1
    (ALIAS 表), 拼错就会 0 命中, 进而触发整目录兜底导出。这里按
    "最长 UI 名前缀" 反解, 和 skin_mod.kit_weapon_map 同一套规则。
    """
    if "icon_index" in _cache:
        return _cache["icon_index"]
    tree = _tree()
    names = set(sm.weapon_dirs(tree)) | set(sm.ALIAS) | set(sm.ALIAS.values())
    idx = {}
    for k in tree:
        m = sm.RE_PNG.match(k)
        if not m:
            continue
        rest, size = m.group(1), m.group(2)
        ui = max((w for w in names if rest.startswith(w + "_")), key=len, default=None)
        if not ui:
            continue
        kit = rest[len(ui) + 1:]
        idx.setdefault((sm.ALIAS.get(ui, ui), kit, size),
                       (k.split(":", 1)[1], ui))
    _cache["icon_index"] = idx
    return idx


def icon_rel(weapon: str, kit: str, size: str = "light") -> str | None:
    """kit 检视图在 VPK 里的相对路径 (thumbs 用它算缓存文件位置)"""
    hit = _icon_index().get((weapon, kit, size))
    return hit[0] if hit else None


def icon_key(weapon: str, kit: str, size: str = "light") -> str | None:
    rel = icon_rel(weapon, kit, size)
    return f"vtex_c:{rel}" if rel else None


def icon_prefixes(weapon: str, size: str = "light") -> list[str]:
    """该武器在检视图里用到的全部 UI 名 (M4A4 -> m4a1), 供批量导出用"""
    return sorted({ui for (w, _k, s), (_p, ui) in _icon_index().items()
                   if w == weapon and s == size})


def knives() -> list[dict]:
    tree = _tree()
    found = km.discover_knives(tree)
    out = []
    for k in sorted(found):
        model, graph, disp = found[k]
        _mv, mkind = km.main_var_for(tree, k)
        if mkind == "完整图":
            inspect = "留空 (完整图自管检视)"
        elif "inspects" in graph:
            inspect = "检视变体"
        else:
            inspect = "沿用默认刀"
        out.append({"id": k, "name": disp, "main": mkind or "缺失", "inspect": inspect})
    return out


def patches() -> list[dict]:
    return sm.load_patches()["patches"]


def patch_text() -> str:
    _r, log = _capture(sm.cmd_patches)
    return log


# ---------------------------------------------------------------- 写操作

def _finish(fn_ret, log: str) -> dict:
    """统一收尾: 跑审计, 合并日志"""
    ok_audit, audit_log = _capture(sm.cmd_audit, _tree())
    _cache.pop("state", None)
    return {"ok": bool(fn_ret) and bool(ok_audit),
            "log": log + "\n" + audit_log,
            "audit_ok": bool(ok_audit)}


def apply_swap(weapon: str, owned: str, want: str, force: bool = False) -> dict:
    """整材质换肤: 把已拥有的 owned 显示成 want (从当前状态叠加, 不覆盖其它补丁)"""
    ret, log = _capture(sm.cmd_swap, _tree(), weapon_map(),
                        weapon, owned, want, True, force)
    return _finish(ret, log)


def apply_knife(knife: str, no_inspect: bool = False, no_main: bool = False) -> dict:
    """换刀 + 按补丁清单整体重放 (换刀会重建文件, 必须重放, 故走 rebuild)"""
    ret, log = _capture(sm.cmd_rebuild, knife, False, no_main, no_inspect)
    return _finish(ret, log)


def revert() -> dict:
    ret, log = _capture(km.cmd_revert)
    return _finish(True, log)


def audit() -> dict:
    ret, log = _capture(sm.cmd_audit, _tree())
    return {"ok": bool(ret), "log": log, "audit_ok": bool(ret)}


def remove_patch(index: int) -> dict:
    """从清单里删一条 (只改清单, 不改盘上文件)"""
    d = sm.load_patches()
    if not (0 <= index < len(d["patches"])):
        return {"ok": False, "log": f"索引越界: {index}"}
    gone = d["patches"].pop(index)
    sm.save_patches(d)
    return {"ok": True, "log": f"已从清单移除: {gone}\n(盘上文件未变, 如需生效请 --revert 后重建)"}


if __name__ == "__main__":  # 自检: python gui/service.py
    print(bootstrap())
    print("weapons:", len(weapons()))
    ks = kits("ak47")
    print("ak47 kits:", len(ks), ks[:3])
    print("paint:", paint_tex("cu_ak_island_floral"))
    print("icon:", icon_key("ak47", "cu_ak_island_floral"))
    print("knives:", len(knives()))
