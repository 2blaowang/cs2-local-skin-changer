"""
CS2 皮肤层结构诊断 (只读)
================================================
回答一个问题: 某个 武器×皮肤 在贴图重指向方案下, 为什么看起来"不完整"。

官方皮肤材质是多层合成材质 (底色 / 图案 / 蒙版 / 磨损 / 污渍 / 法线 / 粗糙 / AO),
由引擎 CompositeMaterialSystem 在运行时按 paintseed 多 pass 烘焙成成品贴图。
本项目的贴图重指向只接管其中一层 (武器 _color), 因此:
  - 主图案是 tga (编译期烘焙的满铺成品图, 不透明) -> 图案完整, 但铺满全枪无蒙版分色
  - 主图案是 psd (合成输入的元素层, 底色/蒙版靠引擎补) -> 直接当 albedo 用, 残缺

用法:
  python diagnose_skin.py ak47                          # 该武器全部皮肤评级
  python diagnose_skin.py ak47 gs_ak47_bloodsport       # 单个皮肤层清单
  python diagnose_skin.py --weapons                     # 哪些武器有完整可用皮肤

只读, 不修改任何游戏文件。
"""
import sys, os, re, collections
import knife_mod as km
import skin_mod as sm

# 皮肤材质的层角色 (按贴图路径关键字识别)
ROLES = [
    ("tnormal", "法线层"),
    ("weapon_color", "底色层"),
    ("paintmask", "蒙版层"),
    ("paintao", "AO 层"),
    ("default_rough", "粗糙度层"),
    ("paint_wear", "磨损层"),
    ("gun_grunge", "污渍层"),
    ("_normal", "法线层"),
    ("_rough", "粗糙度层"),
    ("_ao", "AO 层"),
    ("_mask", "蒙版层"),
    ("glitter", "闪粉法线"),
]
AUX = (b"_normal_", b"_tnormal_", b"_rough_", b"_ao_", b"_mask_", b"_grunge_", b"_wear_", b"composite")


def tree_entry(path):
    """vmat 里引用的是带 .vtex 的路径; 树内条目名不带后缀"""
    return tree.get(f"vtex_c:{path[:-5] if path.endswith('.vtex') else path}")


def raw(key):
    e = tree[key]
    with open(os.path.join(km.CSGO, f"pak01_{e[3]:03d}.vpk"), "rb") as f:
        f.seek(e[4])
        return f.read(e[5])


def role_of(name):
    low = name.lower()
    for pat, label in ROLES:
        if pat in low:
            return label
    if "paints/" in low or "workshop" in low:
        return "主图案层"
    return "其他"


def split_layers(vmat_key):
    """把皮肤 vmat 引用的贴图拆成 主图案 / 辅助层 两类"""
    blob = raw(vmat_key)
    texs = sorted(set(m.group().decode() for m in
                      re.finditer(rb"materials/[^\x00-\x1f]{6,}?\.vtex", blob)))
    pats, aux = [], []
    for t in texs:
        low = t.lower()
        if "paints/" in low and "vmats/" not in low and not any(a.decode() in low for a in AUX):
            pats.append(t)
        else:
            aux.append(t)
    return pats, aux, blob


def grade(vmat_key):
    """评级: full(完整) / rough(勉强) / broken(残缺) + 说明"""
    pats, aux, blob = split_layers(vmat_key)
    if not pats:
        return "none", "无主图案 (纯色/特殊皮肤)", None, aux
    src = pats[0]
    kind = "tga" if "_tga_" in src else ("psd" if "_psd_" in src else "其他")
    e = tree_entry(src)
    size = e[5] if e else 0
    has_mask = b"paintmask" in blob
    if kind == "tga" and size > 500_000:
        return "full", f"tga 满铺成品图 ({size // 1024}KB)", src, aux
    if kind == "tga":
        return "rough", f"tga 但偏小 ({size // 1024}KB), 可能是局部图集", src, aux
    if kind == "psd":
        return "broken", f"psd 元素层 ({size // 1024}KB), 底色与蒙版靠引擎合成补齐", src, aux
    return "rough", f"未知格式 ({size // 1024}KB)", src, aux


def cmd_one(w, kit):
    vmat = wmap[w][kit]
    g, why, src, aux = grade(vmat)
    print(f"===== {w} / {kit} =====")
    print(f"皮肤材质: {vmat}  ({tree[vmat][5]}B)")
    print(f"评级    : {g.upper()}  —  {why}")
    if src:
        e = tree_entry(src)
        print(f"工具会指向: {src}")
        print(f"            (vtex 条目 {e[5] if e else '?'}B)")
    print("\n官方皮肤的完整层结构 (引擎合成管线输入):")
    for t in [src] + [a for a in aux if ".vtex" in a]:
        if not t:
            continue
        mark = " <== 唯一被接管的一层" if t == src else ""
        print(f"  [{role_of(t):<6}] {t.split('/')[-1]}{mark}")
    print("\n未接管的层 = 视觉上丢失的质感:")
    print("  底色层 default_weapon_color  -> 图案透明处没有底色兜底, 露黑/露默认涂装")
    print("  蒙版层 default_paintmask     -> 无分色控制, 图案平铺整把枪")
    print("  磨损层 paint_wear / 污渍层 gun_grunge -> 无磨损过渡, 边缘生硬")
    print("  法线/粗糙/AO                 -> 仍是默认涂装的手感")
    print("\n结论: 缺的不是某一层, 是整条合成管线。")


def cmd_weapon(w):
    if w not in wmap:
        print(f"[!] 无皮肤数据: {w}; 可用: {', '.join(sorted(wmap))}")
        return
    buckets = collections.defaultdict(list)
    for kit in sorted(wmap[w]):
        g, why, src, _ = grade(wmap[w][kit])
        buckets[g].append((kit, why))
    label = {"full": "✓ 完整 (tga 满铺成品图)", "rough": "~ 勉强 (tga 小图/未知)",
             "broken": "✗ 残缺 (psd 元素层)", "none": "— 无主图案"}
    print(f"{w}: {len(wmap[w])} 个皮肤")
    for g in ("full", "rough", "broken", "none"):
        if g not in buckets:
            continue
        print(f"\n  {label[g]}  {len(buckets[g])} 个")
        for kit, why in buckets[g][:40]:
            print(f"    {kit:<34} {why}")


def cmd_weapons():
    print(f"{'武器':<16}{'完整':>6}{'勉强':>6}{'残缺':>6}{'无图案':>7}")
    tot = collections.Counter()
    for w in sorted(wmap):
        c = collections.Counter(grade(v)[0] for v in wmap[w].values())
        tot.update(c)
        print(f"{w:<16}{c['full']:>6}{c['rough']:>6}{c['broken']:>6}{c['none']:>7}")
    print(f"{'合计':<16}{tot['full']:>6}{tot['rough']:>6}{tot['broken']:>6}{tot['none']:>7}")


if __name__ == "__main__":
    km.require_paths()
    tree = km.load_ref_tree()
    sm.tree_cache = tree
    wmap = sm.build_map(tree)
    a = sys.argv[1:]
    if not a or "--weapons" in a:
        cmd_weapons()
    elif len(a) == 1:
        cmd_weapon(a[0])
    else:
        if a[0] not in wmap or a[1] not in wmap[a[0]]:
            print(f"[!] 未知组合 {a[0]} {a[1]}; 用 --weapons 或 <武器> 查看可选")
            sys.exit(1)
        cmd_one(a[0], a[1])
