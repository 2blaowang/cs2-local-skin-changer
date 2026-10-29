"""
CS2 武器皮肤本地替换工具 (paint kit 树条目重指向)
================================================
把指定武器的默认涂装材质重指向任意 CS2 原生皮肤材质 (同武器 UV 匹配)。
技术同 knife_mod: 只改 pak01_dir.vpk 目录树条目 16B 指针字段,
不碰数据包/哈希数组/签名块, 树大小不变, other_md5 重算, 可一键回滚。

原理: CS2 武器模型 vmdl 按路径引用基础材质条目; 皮肤系统在服务端,
但全部皮肤渲染资产 (vmat+贴图) 都在本地 pak01 中。把基础材质条目的
(arch/off/len/crc) 重指向皮肤 vmat 条目数据, 引擎加载默认涂装时
即得到皮肤材质。检视模型材质一并替换。

用法:
  python skin_mod.py --weapons              # 列出可换肤武器
  python skin_mod.py --list ak47            # 列出 ak47 可用皮肤
  python skin_mod.py --family doppler       # 按名字查同族皮肤 (多普勒/宝石系/渐变…) 及其形态
  python skin_mod.py --skin ak47 gs_ak47_bloodsport   # AK47 换血竞
  python skin_mod.py --skin ak47 gs_ak47_bloodsport --tex --layers   # 连带 rough/ao/normal
  python skin_mod.py --swap ak47 cu_ak47_mastery cu_fireserpent_ak47_bravo  # 已有皮肤整换材质
  python skin_mod.py --gloves               # 列出手套皮肤 (按家族分组)
  python skin_mod.py --glove sporty_hunter sporty_purple   # 手套整换材质 (同家族)
  python skin_mod.py --revert               # 还原默认涂装
  python skin_mod.py --audit                # 审计当前状态

注意: 与 knife_mod 共用同一份 pak01_dir.vpk 与原始备份, 补丁均从备份
出发、互不叠加。进 VAC 官方对局前务必 --revert。
"""
import struct, hashlib, sys, os, json, re
import knife_mod as km

SNAP = os.path.join(km.SCRIPT_DIR, "skin_mod_snapshot.json")
# 补丁清单: 每成功应用一条 --swap/--glove 就记一条, --rebuild 换刀后按它重放。
# 换刀会从原始备份整体重建文件, 会抹掉全部换肤补丁, 所以必须有一份可重放的清单。
PATCHES = os.path.join(km.SCRIPT_DIR, "patches.json")
tree_cache = None  # vtex 读取用
RE_BASE = re.compile(r"^vmat_c:weapons/models/([^/]+)/materials/weapon_[^/]+$")
RE_VIEW = re.compile(r"^vmat_c:materials/models/weapons/v_models/([^/]+)/[^/]+$")
RE_PNG = re.compile(r"^vtex_c:panorama/images/econ/default_generated/weapon_(.+?)_(heavy|light|medium)_png$")
VMATS = "vmat_c:materials/models/weapons/customization/paints/vmats/"
COMPMAT = "vcompmat_c:weapons/paints/"
# 手套皮肤: 与武器 legacy kit 同构 (每 kit 一份 7.8KB vmat + 1.6KB vcompmat 声明),
# 但目录是 gloves/paints/ 而非 weapons/.../paints/vmats/, 需独立前缀
GVMAT = "vmat_c:gloves/paints/"
GCOMP = "vcompmat_c:gloves/paints/"
RE_GFAM = re.compile(rb"arms/glove_([a-z0-9]+)/")  # vmat 内引用的家族模型目录 -> 家族名
ALIAS = {"m4a1": "m4a4"}  # panorama 武器名 -> 树内武器目录名 (M4A4 在 UI 层叫 m4a1)
VIEW_ALIAS = {"m4a4": ["rif_m4a1"], "m4a1_silencer": ["rif_m4a1_s"]}  # 检视目录名精确例外 (rif_m4a1=M4A4, rif_m4a1_s=消音版)
EXCLUDE = ("lens", "chargemeter", "digits", "sticker")  # 非主体材质不换
COMMON = {  # 常见皮肤中文备注 (缺省显示 kit 名)
    "gs_ak47_bloodsport": "血竞", "cu_ak47_asiimov": "二西莫夫",
    "cu_fireserpent_ak47_bravo": "火蛇", "gs_ak47_empress": "皇后",
    "cu_ak47_point_disarray": "点阵", "cu_ak47_nightwish": "霓虹革命",
    "aq_ak47_cartel": "卡特尔", "cu_ak47_winter_sport": "冬季运动",
    "cu_m4a1s_printstream": "打印流", "cu_m4a4_evil_daimyo": "杀意大名",
    "am_kimono_sunrise": "破晓", "cu_awp_asimov": "AWP二西莫夫",
    "cu_ak47_cobra": "眼镜蛇", "gs_ak47_professional": "职业杀手",
    "cu_ak47_mastery": "精英之作",
}


def weapon_dirs(tree):
    """36 武器目录名 (世界模型基础材质所在目录)"""
    return {m.group(1) for k in tree if (m := RE_BASE.match(k))}


def kit_weapon_map(tree):
    """{kit: {武器目录名}} 由 panorama 检视图名解析 (不要求该 kit 有 vmat, 新版 kit 也能认)"""
    dirs = weapon_dirs(tree)
    names = dirs | set(ALIAS)  # UI 层武器名可能是目录名的别名
    out = {}
    for k in tree:
        m = RE_PNG.match(k)
        if not m:
            continue
        rest = m.group(1)
        ui = None
        for w in names:  # 最长前缀匹配 UI 武器名
            if rest.startswith(w + "_") and (ui is None or len(w) > len(ui)):
                ui = w
        if not ui:
            continue
        out.setdefault(rest[len(ui) + 1:], set()).add(ALIAS.get(ui, ui))  # kit 按 UI 名长度切分
    return out


def build_map(tree):
    """{武器目录名: {皮肤kit名: 皮肤vmat条目key}}, 以 panorama 检视图解析 武器×皮肤"""
    out = {}
    for kit, ws in kit_weapon_map(tree).items():
        if VMATS + kit not in tree:
            continue
        for w in ws:
            out.setdefault(w, {})[kit] = VMATS + kit
    return out


def targets_for(tree, w):
    """武器 w 的基础材质 + 检视材质条目 (排除配件; 检视目录精确匹配 + 别名例外表)"""
    va = VIEW_ALIAS.get(w, [])
    ts = [k for k in tree if (m := RE_BASE.match(k)) and m.group(1) == w
          and not any(x in k for x in EXCLUDE)]
    ts += [k for k in tree if (m := RE_VIEW.match(k))
           and (m.group(1) == w or m.group(1).endswith("_" + w) or m.group(1) in va)
           and not any(x in k for x in EXCLUDE)]
    return sorted(set(ts))


def read_entry_raw(key):
    e = tree_cache[key]
    with open(os.path.join(km.CSGO, f"pak01_{e[3]:03d}.vpk"), "rb") as f:
        f.seek(e[4])
        return f.read(e[5])


_VTEX_ROOTS = None


def _vtex_roots(tree):
    """树内 vtex 条目的顶层目录集合 (materials/ items/assets/ stickers/ ...)

    自动推导, 不硬编码: 新版 kit 的贴图在 items/assets/paintkits/ 下,
    老版在 materials/ 下, 贴纸在 stickers/ 下。
    """
    global _VTEX_ROOTS
    if _VTEX_ROOTS is None:
        _VTEX_ROOTS = tuple(sorted({k.split(":", 1)[1].split("/")[0] + "/"
                                    for k in tree
                                    if k.startswith("vtex_c:") and "/" in k}))
    return _VTEX_ROOTS


def vtex_refs(key):
    """解析 vmat/vcompmat 里引用的全部 .vtex 路径

    二进制里的路径常被长度字节切碎, 正则会从残留片段起头, 匹配出
    "ao_tga_9627e701"、"_psd_25c027da" 这类伪路径 (全量统计约 36%
    是碎片)。只保留以树内真实顶层目录开头的完整路径。
    """
    roots = _vtex_roots(tree_cache) if tree_cache else ()
    out = set()
    for s in re.findall(rb"[\x20-\x7e]{6,}\.vtex", read_entry_raw(key)):
        p = s[:-5].decode()
        if not roots or p.startswith(roots):
            out.add(p)
    return sorted(out)


def tex_targets(tree, wmap, w, kit):
    """贴图模式: 武器默认 color 贴图条目 -> 皮肤主贴图条目"""
    vmats = targets_for(tree, w)
    if not vmats:
        return None, []
    src_key = wmap[w][kit]
    skin_texs = [t for t in vtex_refs(src_key)
                 if ("paints/" in t or "paintkits/" in t) and "/default_" not in t
                 and "/shared/" not in t and "vmat_g" not in t]
    if not skin_texs:
        return None, []
    # 智能选源: tga(单层满铺成品图)优先于 psd(图案元素层, 需引擎合成才有完整效果),
    # 同类型按文件大小降序 (大图 = 满铺成品概率高)
    def _src_rank(t):
        key = f"vtex_c:{t}"
        if key not in tree:
            return (2, 0)
        return (0 if "_tga_" in t else 1, -tree[key][5])
    skin_texs.sort(key=_src_rank)
    src_tex = f"vtex_c:{skin_texs[0]}"
    tgts = []
    for v in vmats:  # 每个材质里的 <武器>_color 贴图 (引擎共享 default_* 除外)
        for t in vtex_refs(v):
            if "_color" in t and not t.startswith("materials/default/") and f"vtex_c:{t}" in tree:
                tgts.append(f"vtex_c:{t}")
    return src_tex, sorted(set(tgts))


AUX_ROLES = (("rough", "_rough"), ("ao", "_ao"), ("normal", "_normal", "_tnormal"))


def aux_sources(tree, wmap, w, kit):
    """皮肤侧提供的专属辅助贴图 {角色: 贴图路径} (排除共享 default / 贴纸)"""
    pool = {}
    for m in re.finditer(rb"materials/[^\x00-\x1f]{6,}?\.vtex", read_entry_raw(wmap[w][kit])):
        t = m.group().decode()[:-5]
        low = t.lower()
        if "/default/" in low or "stickers" in low:
            continue
        for role, *pats in AUX_ROLES:
            if any(p in low for p in pats):
                pool.setdefault(role, []).append(t)
    return pool


def aux_targets(tree, wmap, w, kit):
    """武器专属 rough/ao/normal 贴图条目 <- 皮肤专属同角色贴图

    只动武器自己的贴图 (如 ak47_default_rough_*), 绝不碰 materials/default/ 下的
    共享贴图 (那是全武器共用的兜底图, 改了会波及所有武器)。
    """
    pool = aux_sources(tree, wmap, w, kit)
    if not pool:
        return []
    out = []
    for v in targets_for(tree, w):
        for t in vtex_refs(v):
            low = t.lower()
            if "/default/" in low or "stickers" in low:
                continue
            for role, *pats in AUX_ROLES:
                if any(p in low for p in pats) and role in pool:
                    key, src = f"vtex_c:{t}", f"vtex_c:{pool[role][0]}"
                    if key in tree and src in tree and key != src:
                        out.append((key, src, role))
    return sorted(set(out), key=lambda x: (x[2], x[0]))


def _material_keys(tree, kit):
    """kit 的全部材质资源条目 {资源类型前缀: 树条目 key}"""
    out = {}
    for pfx in (VMATS, COMPMAT):
        hits = [k for k in tree if k.startswith(pfx) and k.split("/")[-1] == kit]
        if hits:
            out[pfx] = hits[0]
    return out


ROLE_OF = {VMATS: "vmat", COMPMAT: "vcomp"}


def swap_targets(tree, w, owned, want):
    """整材质换肤: 已拥有皮肤的资源条目 -> 想显示皮肤的资源条目

    与 --tex 的根本区别: 引擎照旧按 paintindex 跑完整合成管线
    (蒙版裁剪/磨损/污渍/法线/paintseed), 我们只把"配方"换成目标皮肤的。

    返回 (plan, blockers):
      plan     可执行的配对 [(目标条目, 源条目, 角色)]
      blockers 阻断原因 (跨武器 / 缺资源), 空列表表示无风险

    两种形态 (见 form_of):
      legacy: 有 vmats/<kit>.vmat, vcompmat 是单节点图 —— 一个
              SPECIFIC_MATERIAL 节点把材质转交给该 vmat
      composite: 只有 vcompmat, 内含完整节点图 (albedo/ao/mask/normal/rough)
    入口始终是 vcompmat (items_game 的 composite_material_path 指向它),
    所以跨形态时只要换 vcompmat 这一个条目即可 —— 目标文档内部用绝对
    路径引它自己的 vmat/贴图, 不需要我们代劳。
    """
    a, b = _material_keys(tree, owned), _material_keys(tree, want)
    blockers = []
    if not a:
        blockers.append(f"{owned} 没有任何材质资源条目")
    if not b:
        blockers.append(f"{want} 没有任何材质资源条目")
    if blockers:
        return [], blockers
    kw = kit_weapon_map(tree)
    for kit, side in ((owned, "拥有侧"), (want, "目标侧")):
        ws = kw.get(kit) or set()
        if ws and w not in ws:
            blockers.append(f"{side} {kit} 的检视图归 {','.join(sorted(ws))}, 不是 {w}")
    plan = [(a[p], b[p], ROLE_OF[p]) for p in (COMPMAT, VMATS) if p in a and p in b]
    return plan, blockers


def kit_style(tree):
    """kit -> (style, composite_material_path) 从 items_game 读取 (只读缓存)"""
    if getattr(kit_style, "_cache", None) is not None:
        return kit_style._cache
    out = {}
    e = tree["txt:scripts/items/items_game"]
    with open(os.path.join(km.CSGO, f"pak01_{e[3]:03d}.vpk"), "rb") as f:
        f.seek(e[4])
        t = f.read(e[5]).decode("utf-8", "replace").replace("\r\n", "\n")
    for m in re.finditer(r"\n\t\t\{\n((?:[^\n]*\n){1,12}?)\t\t\}", t):
        bl = m.group(1)
        if '"style"' not in bl:
            continue
        n = re.search(r'"name"\t\t"([^"]+)"', bl)
        st = re.search(r'"style"\s+"(\d+)"', bl)
        cp = re.search(r'"composite_material_path"\s+"([^"]+)"', bl)
        if n:
            out[n.group(1)] = (st.group(1) if st else "?", cp.group(1) if cp else None)
    kit_style._cache = out
    return out


def form_of(tree, kit):
    """皮肤的资源形态: 'legacy' (有独立 vmat, vcompmat 只是转交声明)
    或 'composite' (只有 vcompmat, 内含完整合成节点图)

    实测: 两种形态的入口互不兼容 —— 把 composite 槽位指向 legacy 声明,
    合成器拿到的是不匹配的文档, 表现为图案错乱。整材质换肤必须同形态。
    """
    return "legacy" if VMATS + kit in tree else "composite"


def cn_names(tree):
    """kit -> 中文名, 由 resource/csgo_schinese 的 PaintKit_<kit>_tag 键解析 (只读缓存)

    武器和手套共用同一套本地化键, 比手写 COMMON 表可靠。
    """
    if getattr(cn_names, "_cache", None) is not None:
        return cn_names._cache
    out = {}
    key = "txt:resource/csgo_schinese"
    if key in tree:
        e = tree[key]
        with open(os.path.join(km.CSGO, f"pak01_{e[3]:03d}.vpk"), "rb") as f:
            f.seek(e[4])
            t = f.read(e[5]).decode("utf-8", "replace")
        # 本地化键用的是官方大小写 (cu_AK47_Anarchy), 而材质路径全小写,
        # 统一按小写存, 否则精确匹配会漏掉一大片
        for m in re.finditer(r'"PaintKit_([A-Za-z0-9_\-]+?)_tag"\s+"([^"]*)"', t, re.I):
            out[m.group(1).lower()] = m.group(2)
    cn_names._cache = out
    return out


def glove_family(tree, vmat_key):
    """手套家族名 (sporty/specialist/...) 取自 vmat 内引用的 arms/glove_<family>/ 路径"""
    m = RE_GFAM.search(read_entry_raw(vmat_key))
    return m.group(1).decode() if m else "?"


def glove_map(tree):
    """{kit: (家族, vmat条目, vcompmat条目|None)} 手套皮肤表 (72 个)"""
    out = {}
    for k in tree:
        if not k.startswith(GVMAT):
            continue
        kit = k.split("/")[-1]
        ck = GCOMP + kit
        out[kit] = (glove_family(tree, k), k, ck if ck in tree else None)
    return out


def swap_glove_targets(gmap, owned, want):
    """手套整换材质: (plan, 拥有侧家族, 目标侧家族)

    手套比武器更规整: 每个 kit 都是 legacy 形态 (vmat + vcompmat 声明),
    没有 composite 变体, 所以不存在形态错配问题。
    家族是硬约束 —— kit 自带的 mask/normal 按该家族手部 UV 绘制,
    跨家族指向会让花纹按错误 UV 展开 (要跨家族必须连模型一起换, 本工具不做)。
    """
    if owned not in gmap or want not in gmap:
        return None
    fo, fw = gmap[owned][0], gmap[want][0]
    plan = [(gmap[owned][1], gmap[want][1], "vmat")]
    if gmap[owned][2] and gmap[want][2]:
        plan.append((gmap[owned][2], gmap[want][2], "vcomp"))
    return plan, fo, fw


def cmd_gloves(tree):
    gmap = glove_map(tree)
    cn = cn_names(tree)
    fams = {}
    for kit, (fam, _, _) in gmap.items():
        fams.setdefault(fam, []).append(kit)
    print(f"手套皮肤 ({len(gmap)} 个 / {len(fams)} 家族):")
    for fam in sorted(fams):
        print(f"\n  [{fam}]  {len(fams[fam])} 个")
        for kit in sorted(fams[fam]):
            print(f"    {kit:<36} {cn.get(kit, '')}")
    print("\n用法: --glove <你拥有的kit> <想显示的kit>   (必须同家族, 加 --stack 保留其他补丁)")


def cmd_glove(tree, owned, want, stack=False, force=False):
    gmap = glove_map(tree)
    cn = cn_names(tree)
    r = swap_glove_targets(gmap, owned, want)
    if r is None:
        print(f"[!] 未找到手套皮肤 {owned} 或 {want}; 见 --gloves")
        return False
    plan, fo, fw = r
    print(f"[*] 手套整换材质: {owned} ({cn.get(owned, '已拥有')})"
          f"  ==>  {want} ({cn.get(want, '想显示')})")
    print(f"    家族 {fo} -> {fw}")
    if fo != fw and not force:
        print(f"[!] 跨家族 ({fo} -> {fw}): kit 自带的 mask/normal 按 {fw} 手部 UV 绘制,")
        print("    而手部模型仍是 " + fo + " 的, 花纹会错位。跨家族必须连模型一起换,")
        print("    本工具只换材质; 确要尝试请加 --force。")
        return False
    for t, s, role in plan:
        te, se = tree[t], tree[s]
        print(f"    [{role:<6}] {t.split(':', 1)[1].split('/')[-1]:<40}"
              f" pack {te[3]:03d} -> {se[3]:03d}   {te[5]}B -> {se[5]}B")
    if not _commit(plan, stack):
        return False
    e = {"type": "glove", "owned": owned, "want": want}
    if force:
        e["force"] = True
    record_patch(e)
    return True


def load_patches():
    if os.path.exists(PATCHES):
        try:
            with open(PATCHES, encoding="utf-8") as f:
                d = json.load(f)
            d.setdefault("patches", [])
            return d
        except Exception:
            pass
    return {"patches": []}


def save_patches(d):
    with open(PATCHES, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)


def record_patch(entry):
    """记一条补丁; 同槽位 (type+weapon+owned) 覆盖而非重复"""
    d = load_patches()
    key = (entry["type"], entry.get("weapon"), entry["owned"])
    d["patches"] = [p for p in d["patches"]
                    if (p["type"], p.get("weapon"), p["owned"]) != key]
    d["patches"].append(entry)
    save_patches(d)


def cmd_patches():
    d = load_patches()
    ps = d["patches"]
    if not ps:
        print("[!] 补丁清单为空; 先跑几条 --swap / --glove 会自动记录")
        return
    print(f"补丁清单 ({len(ps)} 条, {os.path.basename(PATCHES)}):")
    for i, p in enumerate(ps, 1):
        if p["type"] == "swap":
            f = " --force" if p.get("force") else ""
            print(f"  {i:>2}. swap   {p['weapon']:<14} {p['owned']:<30} -> {p['want']}{f}")
        else:
            f = " --force" if p.get("force") else ""
            print(f"  {i:>2}. glove  {'(手套)':<14} {p['owned']:<30} -> {p['want']}{f}")
    print("\n换刀后用它整体重放:  python scripts/skin_mod.py --rebuild <刀型>")


def _commit(plan, stack=False):
    """把 plan 里的重指向写入 pak01_dir.vpk (树大小不变, other_md5 重算)"""
    bak = open(km.BAK_DIR, "rb").read()
    if stack:
        base = km.read_dir()
        if len(base) != len(bak):
            print("[!] 当前文件大小与备份不符 (可能被 Steam 还原过), 拒绝叠加; 请先单独应用")
            return False
    else:
        base = bak
    cur = bytearray(base)
    for t, s, _ in plan:
        te, se = tree_cache[t], tree_cache[s]
        struct.pack_into("<IHHII", cur, te[0], se[1], 0, se[3], se[4], se[5])
    data = bytes(cur)
    om = len(data) - km.SIG_BLOCK - 48
    data = data[:om] + km.compute_other_md5(data) + data[om + 32:]
    with open(km.DIR_PATH, "r+b") as f:
        f.write(data)
        f.truncate()
        f.flush()
        os.fsync(f.fileno())
    print(f"[+] 已应用 ({len(plan)} 条目重指向)")
    return True


def cmd_swap(tree, wmap, w, owned, want, stack=False, force=False):
    plan, blockers = swap_targets(tree, w, owned, want)
    cn = cn_names(tree)
    fo, fw = form_of(tree, owned), form_of(tree, want)
    st = kit_style(tree)
    print(f"[*] 整材质换肤 {w}: {owned} ({cn.get(owned) or COMMON.get(owned, '已拥有')})"
          f"  ==>  {want} ({cn.get(want) or COMMON.get(want, '想显示')})")
    for k, fm in ((owned, fo), (want, fw)):
        style, cp = st.get(k, ("?", None))
        print(f"    {k:<34} style {style:<2} {fm:<9} {cp or '(默认 legacy 路径)'}")
    if not plan:
        print(f"[!] {owned} 与 {want} 没有可配对的同类材质资源; 见 --list {w}")
        return False
    risky = list(blockers)
    if fo != fw:
        risky.append(f"形态不同 ({fo} -> {fw}): 只换 vcompmat 入口文档, "
                     f"目标文档内以绝对路径引用自己的 "
                     f"{'vmat' if fw == 'legacy' else '节点图'}与贴图")
    for r in risky:
        print(f"[!] {r}")
    if risky and not force:
        print("    实测跨形态/跨武器都不保证效果 (合成器按目标 UV 展开别人的图案)。")
        print("    确要尝试请加 --force。")
        return False
    for x in blockers:
        print(f"[!] 跨武器风险: {x} —— 图案会按 {w} 的 UV 重新展开, 不是原皮肤的样子")
    for t, s, role in plan:
        te, se = tree[t], tree[s]
        print(f"    [{role:<6}] {t.split(':', 1)[1].split('/')[-1]:<44}"
              f" pack {te[3]:03d} -> {se[3]:03d}   {te[5]}B -> {se[5]}B")
    if not _commit(plan, stack):
        return False
    e = {"type": "swap", "weapon": w, "owned": owned, "want": want}
    if force:
        e["force"] = True
    record_patch(e)
    return True


def cmd_rebuild(knife, force_inspect=False, no_main=False, no_inspect=False):
    """换刀 + 按补丁清单整体重放, 一条命令回到完整状态

    换刀 (km.cmd_apply) 是从原始备份整体重建文件, 会抹掉全部换肤补丁,
    所以换完必须重放。清单里的每条都用 --stack 叠加到当前文件。
    """
    ps = load_patches()["patches"]
    print(f"[*] 重建: 刀 = {knife}, 待重放补丁 {len(ps)} 条")
    km.cmd_apply(knife, force_inspect, no_main, no_inspect)
    tree, wmap = tree_cache, build_map(tree_cache)
    ok = True
    for i, p in enumerate(ps, 1):
        tag = f"[{i}/{len(ps)}]"
        if p["type"] == "swap":
            print(f"\n--- {tag} {p['weapon']} {p['owned']} -> {p['want']} ---")
            r = cmd_swap(tree, wmap, p["weapon"], p["owned"], p["want"],
                         stack=True, force=p.get("force", False))
        else:
            print(f"\n--- {tag} 手套 {p['owned']} -> {p['want']} ---")
            r = cmd_glove(tree, p["owned"], p["want"],
                          stack=True, force=p.get("force", False))
        if not r:
            ok = False
            print(f"[!] 重放失败: {p}")
    print(f"\n{'[+]' if ok else '[!]'} 重建完成: 刀 = {knife}, "
          f"补丁 {'全部成功' if ok else '有失败项 (见上)'}")
    return ok


def cmd_weapons(tree, wmap):
    """武器清单: build_map 只收有 vmat 的 legacy kit, 纯 composite 武器会整把漏掉"""
    kits = {w: set(v) for w, v in wmap.items()}
    comp = {k.split("/")[-1] for k in tree if k.startswith(COMPMAT)}
    for kit, ws in kit_weapon_map(tree).items():
        if kit in comp:
            for w in ws:
                kits.setdefault(w, set()).add(kit)
    print(f"可换肤武器 ({len(kits)}):")
    for w in sorted(kits):
        tag = "" if w in wmap else "  (全 composite, 只能 --swap)"
        print(f"  {w:<14} {len(kits[w])} 个皮肤{tag}")


def cmd_family(tree, pat):
    """按 kit 名正则列出同族皮肤 (如 doppler|sapphire), 标形态/材质大小/是否可整换"""
    rx = re.compile(pat, re.I)
    kits = sorted({k.split("/")[-1] for pfx in (VMATS, COMPMAT, GVMAT, GCOMP)
                   for k in tree if k.startswith(pfx) and rx.search(k)})
    if not kits:
        print(f"[!] 没有 kit 名匹配 /{pat}/")
        return
    cn, st = cn_names(tree), kit_style(tree)
    print(f"匹配 /{pat}/ 的 kit ({len(kits)}):")
    for kit in kits:
        v, c = VMATS + kit, COMPMAT + kit
        sz = f"vmat {tree[v][5]}B" if v in tree else ""
        sz += ("  " if sz and c in tree else "") + (f"vcomp {tree[c][5]}B" if c in tree else "")
        print(f"  {kit:<34} [{form_of(tree, kit):<9}] style {st.get(kit, ('?',))[0]:<2}"
              f" {sz:<26} {cn.get(kit, '')}")
    print("\n用法: --swap <武器> <你拥有的kit> <上面任一kit>   (形态不同时加 --force)")


def cmd_list(tree, wmap, w):
    kw = kit_weapon_map(tree)
    kits = set(wmap.get(w, {}))
    for k in tree:  # composite kit 没有 vmat, 不在 build_map 里, 但 --swap 可以用
        if k.startswith(COMPMAT) and w in (kw.get(k.split("/")[-1]) or set()):
            kits.add(k.split("/")[-1])
    if not kits:
        print(f"[!] 武器 {w} 无皮肤数据; 可用: {', '.join(sorted(wmap))}")
        return
    cn = cn_names(tree)
    print(f"{w} 可用皮肤 ({len(kits)}):")
    for kit in sorted(kits):
        fm = form_of(tree, kit)
        tag = "" if kit in wmap.get(w, {}) else "  (composite, 仅 --swap)"
        print(f"  --skin {w} {kit:<34} [{fm:<9}] {cn.get(kit) or COMMON.get(kit, '')}{tag}")
    print("注: 整材质换肤 (--swap) 要求入口与目标同形态 (legacy/composite)")


def cmd_apply(tree, wmap, w, kit, tex=False, stack=False, layers=False):
    if w not in wmap or kit not in wmap[w]:
        # 区分"根本没有这个组合"和"这个 kit 是 composite, 天生不能走 --skin":
        # 后者报"未知组合"会让人以为拼错了名字
        if _material_keys(tree, kit) and form_of(tree, kit) == "composite":
            print(f"[!] {kit} 是 composite 形态: 只有 vcompmat 节点图, 没有可指向的 vmat。")
            print("    默认涂装槽不是物品 (服务端不下发 paintindex), 合成器不会启动,")
            print("    所以它只能挂进一个你已拥有的皮肤槽位 —— 改用整材质换肤:")
            print(f"    python skin_mod.py --swap {w} <你已拥有的皮肤> {kit}")
        else:
            print(f"[!] 未知组合 {w} + {kit}; 见 --list {w}")
        return False
    plan = []  # (目标条目, 源条目, 角色)
    if tex:
        # v2 贴图模式: 保持武器原生 vmat/shader, 只换 color 贴图数据
        # (v1 整 vmat 重指向实测武器全透明: 皮肤 vmat 走合成管线 shader, 不适配武器渲染)
        src_tex, tgt_texs = tex_targets(tree, wmap, w, kit)
        if not tgt_texs:
            print(f"[!] 未找到 {w} 的默认 color 贴图条目")
            return False
        plan = [(t, src_tex, "color") for t in tgt_texs]
    else:
        src_key = wmap[w][kit]
        tgts = targets_for(tree, w)
        if not tgts:
            print(f"[!] 未找到 {w} 的目标材质条目")
            return False
        plan = [(t, src_key, "vmat") for t in tgts]
    if layers:
        aux = aux_targets(tree, wmap, w, kit)
        if aux:
            plan += aux
        else:
            print(f"[*] {kit} 无专属 rough/ao/normal 贴图, 辅助层跳过 (该皮肤用的是全局共享图)")
    print(f"[*] {w} -> {kit} ({COMMON.get(kit, '皮肤')})"
          f"{' [贴图模式]' if tex else ''}{' [叠加]' if stack else ''}"
          f"{' [含辅助层]' if layers else ''}")
    for t, s, role in plan:
        te, se = tree[t], tree[s]
        print(f"    [{role:<6}] {t.split(':', 1)[1].split('/')[-1]:<46}"
              f" pack {te[3]:03d} -> {se[3]:03d}   {te[5]}B -> {se[5]}B")
    return _commit(plan, stack)


def cmd_audit(tree):
    print("========== 皮肤补丁审计 ==========")
    ok = True
    cur = km.read_dir()
    orig = open(km.BAK_DIR, "rb").read()
    good = len(cur) == len(orig)
    print(f"{'[+]' if good else '[!]'} 文件大小不变: {len(cur)}")
    ok &= good
    diffs = [i for i in range(min(len(orig), len(cur))) if orig[i] != cur[i]]
    tree_size = struct.unpack_from("<I", cur, 8)[0]
    h0 = 28 + tree_size
    om0 = len(orig) - km.SIG_BLOCK - 48
    in_tree = all(d < h0 or d >= om0 for d in diffs)
    print(f"{'[+]' if in_tree else '[!]'} 差异 {len(diffs)}B 全部位于树区/other_md5: {in_tree}")
    ok &= in_tree
    if good:
        good = orig[h0:om0] == cur[h0:om0]
        print(f"{'[+]' if good else '[!]'} 哈希数组区未变: {good}")
        ok &= good
    om_off = len(cur) - km.SIG_BLOCK - 48
    good = cur[om_off:om_off + 32] == km.compute_other_md5(cur)
    print(f"{'[+]' if good else '[!]'} other_md5 自洽: {good}")
    ok &= good
    # 找出被改的条目 -> 校验涉及的数据包窗口
    cur_tree = km.parse_tree(cur)
    changed = []
    for key, e in km.parse_tree(orig).items():
        if key in cur_tree and cur_tree[key][1:] != e[1:]:
            changed.append((key, e, cur_tree[key]))
    packs = set()
    for key, e0, e1 in changed:
        print(f"  改动: {key}")
        packs.update((e0[3], e1[3]))
    if changed:
        try:
            import blake3  # noqa: F401
        except ImportError:
            print("  [!] 缺少 blake3, BLAKE3 类型窗口校验将跳过 (pip install blake3)")
    hsz = struct.unpack_from("<I", cur, 16)[0]
    harr = cur[h0:h0 + hsz]
    for p in sorted(packs):
        path = os.path.join(km.CSGO, f"pak01_{p:03d}.vpk")
        if os.path.exists(path):
            ok &= km.audit_pack(path, p, harr)
    json.dump({"time": __import__("datetime").datetime.now().isoformat(),
               "audit_ok": ok, "changed": [k for k, *_ in changed]}, open(SNAP, "w"), indent=2)
    print("==========", "审计通过" if ok else "审计失败!", "==========")
    return ok


def main():
    global tree_cache
    args = sys.argv[1:]
    km.require_paths()
    tree = km.load_ref_tree()
    tree_cache = tree
    wmap = build_map(tree)
    if "--rebuild" in args:
        i = args.index("--rebuild")
        if len(args) <= i + 1 or args[i + 1].startswith("--"):
            print("[!] 用法: --rebuild <刀型>   (换刀 + 重放补丁清单, 见 --patches)")
            sys.exit(1)
        ok = cmd_rebuild(args[i + 1], "--force-inspect" in args,
                         "--no-main" in args, "--no-inspect" in args)
        sys.exit(0 if (ok and km.cmd_audit()) else 1)
    elif "--patches" in args:
        cmd_patches()
    elif "--family" in args:
        i = args.index("--family")
        if len(args) < i + 2:
            print("[!] 用法: --family <kit名正则>   例: --family doppler")
            sys.exit(1)
        cmd_family(tree, args[i + 1])
    elif "--weapons" in args:
        cmd_weapons(tree, wmap)
    elif "--list" in args:
        i = args.index("--list")
        if len(args) > i + 1:
            cmd_list(tree, wmap, args[i + 1])
        else:
            cmd_weapons(tree, wmap)
    elif "--revert" in args:
        km.cmd_revert()
        sys.exit(0 if km.cmd_audit() else 1)
    elif "--audit" in args:
        sys.exit(0 if cmd_audit(tree) else 1)
    elif "--gloves" in args:
        cmd_gloves(tree)
    elif "--glove" in args:
        i = args.index("--glove")
        if len(args) < i + 3:
            print("[!] 用法: --glove <你拥有的手套kit> <想显示的kit>   (见 --gloves)")
            sys.exit(1)
        if cmd_glove(tree, args[i + 1], args[i + 2],
                     stack="--stack" in args, force="--force" in args):
            sys.exit(0 if cmd_audit(tree) else 1)
        sys.exit(1)
    elif "--swap" in args:
        i = args.index("--swap")
        if len(args) < i + 4:
            print("[!] 用法: --swap <武器> <你拥有的kit> <想显示的kit>")
            print("    例: --swap ak47 cu_ak47_mastery cu_fireserpent_ak47_bravo")
            sys.exit(1)
        if cmd_swap(tree, wmap, args[i + 1], args[i + 2], args[i + 3],
                    stack="--stack" in args, force="--force" in args):
            sys.exit(0 if cmd_audit(tree) else 1)
        sys.exit(1)
    elif "--skin" in args:
        i = args.index("--skin")
        if len(args) < i + 3:
            print("[!] 用法: --skin <武器> <皮肤kit>  例: --skin ak47 gs_ak47_bloodsport")
            sys.exit(1)
        w, kit = args[i + 1], args[i + 2]
        if cmd_apply(tree, wmap, w, kit, tex="--tex" in args, stack="--stack" in args,
                     layers="--layers" in args):
            sys.exit(0 if cmd_audit(tree) else 1)
        sys.exit(1)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
