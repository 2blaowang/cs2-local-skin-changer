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
  python skin_mod.py --skin ak47 gs_ak47_bloodsport   # AK47 换血竞
  python skin_mod.py --revert               # 还原默认涂装
  python skin_mod.py --audit                # 审计当前状态

注意: 与 knife_mod 共用同一份 pak01_dir.vpk 与原始备份, 补丁均从备份
出发、互不叠加。进 VAC 官方对局前务必 --revert。
"""
import struct, hashlib, sys, os, json, re
import knife_mod as km

SNAP = os.path.join(km.SCRIPT_DIR, "skin_mod_snapshot.json")
tree_cache = None  # vtex 读取用
RE_BASE = re.compile(r"^vmat_c:weapons/models/([^/]+)/materials/weapon_[^/]+$")
RE_VIEW = re.compile(r"^vmat_c:materials/models/weapons/v_models/([^/]+)/[^/]+$")
RE_PNG = re.compile(r"^vtex_c:panorama/images/econ/default_generated/weapon_(.+?)_(heavy|light|medium)_png$")
VMATS = "vmat_c:materials/models/weapons/customization/paints/vmats/"
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
}


def weapon_dirs(tree):
    """36 武器目录名 (世界模型基础材质所在目录)"""
    return {m.group(1) for k in tree if (m := RE_BASE.match(k))}


def build_map(tree):
    """{武器目录名: {皮肤kit名: 皮肤vmat条目key}}, 以 panorama 检视图解析 武器×皮肤"""
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
        w = ALIAS.get(ui, ui)  # 别名归一到目录名; kit 按 UI 名长度切分
        kit = rest[len(ui) + 1:]
        if kit and VMATS + kit in tree:
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


def vtex_refs(key):
    """解析 vmat 数据里引用的全部 .vtex 路径"""
    return sorted(set(s[:-5].decode() for s in
                      re.findall(rb"[\x20-\x7e]{6,}\.vtex", read_entry_raw(key))))


def tex_targets(tree, wmap, w, kit):
    """贴图模式: 武器默认 color 贴图条目 -> 皮肤主贴图条目"""
    vmats = targets_for(tree, w)
    if not vmats:
        return None, []
    src_key = wmap[w][kit]
    skin_texs = [t for t in vtex_refs(src_key)
                 if "paints/" in t and "/default_" not in t
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


def cmd_weapons(tree, wmap):
    print(f"可换肤武器 ({len(wmap)}):")
    for w in sorted(wmap):
        print(f"  {w:<14} {len(wmap[w])} 个皮肤")


def cmd_list(tree, wmap, w):
    if w not in wmap:
        print(f"[!] 武器 {w} 无皮肤数据; 可用: {', '.join(sorted(wmap))}")
        return
    print(f"{w} 可用皮肤 ({len(wmap[w])}):")
    for kit in sorted(wmap[w]):
        print(f"  --skin {w} {kit:<32} {COMMON.get(kit, '')}")


def cmd_apply(tree, wmap, w, kit, tex=False, stack=False):
    if w not in wmap or kit not in wmap[w]:
        print(f"[!] 未知组合 {w} + {kit}; 见 --list {w}")
        return False
    if tex:
        # v2 贴图模式: 保持武器原生 vmat/shader, 只换 color 贴图数据
        # (v1 整 vmat 重指向实测武器全透明: 皮肤 vmat 走合成管线 shader, 不适配武器渲染)
        src_tex, tgt_texs = tex_targets(tree, wmap, w, kit)
        if not tgt_texs:
            print(f"[!] 未找到 {w} 的默认 color 贴图条目")
            return False
        src_key = src_tex
        entries = {t: tree[t] for t in tgt_texs + [src_tex]}
        tgts = tgt_texs
    else:
        src_key = wmap[w][kit]
        tgts = targets_for(tree, w)
        entries = {t: tree[t] for t in tgts}
        if not tgts:
            print(f"[!] 未找到 {w} 的目标材质条目")
            return False
    src = entries[src_key]
    print(f"[*] {w} -> {kit} ({COMMON.get(kit, '皮肤')}){' [贴图模式]' if tex else ''}{' [叠加]' if stack else ''}")
    for t in tgts:
        print(f"    重指向: {t}  (pack {entries[t][3]:03d} -> {src[3]:03d}, {entries[t][5]}B -> {src[5]}B)")
    bak = open(km.BAK_DIR, "rb").read()
    if stack:
        base = km.read_dir()
        if len(base) != len(bak):
            print("[!] 当前文件大小与备份不符 (可能被 Steam 还原过), 拒绝叠加; 请先单独应用")
            return False
    else:
        base = bak
    cur = bytearray(base)
    for t in tgts:
        struct.pack_into("<IHHII", cur, entries[t][0], src[1], 0, src[3], src[4], src[5])
    data = bytes(cur)
    om = len(data) - km.SIG_BLOCK - 48
    data = data[:om] + km.compute_other_md5(data) + data[om + 32:]
    with open(km.DIR_PATH, "r+b") as f:
        f.write(data)
        f.truncate()
        f.flush()
        os.fsync(f.fileno())
    print(f"[+] 已应用 ({len(tgts)} 条目重指向)")
    return True


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
        import blake3  # noqa
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
    if "--weapons" in args:
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
    elif "--skin" in args:
        i = args.index("--skin")
        if len(args) < i + 3:
            print("[!] 用法: --skin <武器> <皮肤kit>  例: --skin ak47 gs_ak47_bloodsport")
            sys.exit(1)
        w, kit = args[i + 1], args[i + 2]
        if cmd_apply(tree, wmap, w, kit, tex="--tex" in args, stack="--stack" in args):
            sys.exit(0 if cmd_audit(tree) else 1)
        sys.exit(1)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
