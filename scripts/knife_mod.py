"""
CS2 通用刀型替换工具 (可分发版)
================================================
把默认刀 (T/CT) 本地替换为任意 CS2 原生刀型 (原色模型)。
通过 VPK 目录树条目重指向实现: 不碰 pak 数据包、不碰哈希数组、
树大小不变、哈希自洽、可一键回滚。纯本地视觉, 无网络行为。

首次使用 (新机器):
  python knife_mod.py --init          # 自动探测游戏路径 + 建原始备份 + 依赖检查
  python knife_mod.py --init --csgo "D:\\Steam\\steamapps\\common\\Counter-Strike Global Offensive\\game\\csgo"

日常使用:
  python knife_mod.py --list          # 列出可用刀型
  python knife_mod.py --knife karambit    # 换成爪子刀 (自动审计)
  python knife_mod.py --knife butterfly   # 换回蝴蝶刀
  python knife_mod.py --revert        # 还原默认刀
  python knife_mod.py --audit         # 审计当前状态
  python knife_mod.py --audit butterfly   # 审计 + 源数据包全窗口校验

警告: 修改后的文件不要带入 VAC 官方对局, 进官方局前先 --revert。
"""
import struct, hashlib, sys, os, json, shutil, re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(SCRIPT_DIR, "csgo_config.json")
SNAP = os.path.join(SCRIPT_DIR, "knife_mod_snapshot.json")
SIG_BLOCK = 1082
GAME_REL = ("Counter-Strike Global Offensive", "game", "csgo")
MODEL_T = "vmdl_c:weapons/models/knife/knife_default_t/weapon_knife_default_t"
MODEL_CT = "vmdl_c:weapons/models/knife/knife_default_ct/weapon_knife_default_ct"
GRAPH_T = "vnmgraph_c:animation/graphs/viewmodel/viewmodel_inspects.vnmgraph+knife_default_t"
GRAPH_CT = "vnmgraph_c:animation/graphs/viewmodel/viewmodel_inspects.vnmgraph+knife_default_ct"
# 主图槽: 顶层 viewmodel(20.8KB) 按 variationID 选子图, 槽位名固定是刀型的变体名。
# 换模型指针不会改 variationID, 所以 idle/draw/attack/手模 全由这里决定 —— 不改就还是匕首。
MAIN_T = "vnmgraph_c:animation/graphs/viewmodel/viewmodel_knife.vnmgraph+default_t"
MAIN_CT = "vnmgraph_c:animation/graphs/viewmodel/viewmodel_knife.vnmgraph+default_ct"
VMDOM = "vnmgraph_c:animation/graphs/viewmodel/"
KNOWN = {  # 展示名 -> 树内刀名 (weapons/models/knife/<名>/)
    "bayonet": "刺刀", "bowie": "鲍伊", "butterfly": "蝴蝶", "canis": "Canis",
    "cord": "皮带", "css": "经典(复刻)", "falchion": "弯刀", "flip": "折叠",
    "gut": "屠夫", "karambit": "爪子刀", "kukri": "弯镰", "m9": "M9刺刀",
    "navajo": "短剑", "outdoor": "求生", "push": "暗影双匕", "skeleton": "骷髅",
    "stiletto": "细刺", "tactical": "猎杀", "talon": "爪刃", "ursus": "熊刀",
}

CSGO = DIR_PATH = BAK_DIR = None


def set_paths(csgo):
    global CSGO, DIR_PATH, BAK_DIR
    CSGO = os.path.normpath(csgo)
    DIR_PATH = os.path.join(CSGO, "pak01_dir.vpk")
    BAK_DIR = DIR_PATH + ".bak_v6"


def load_config():
    if os.path.exists(CONFIG):
        try:
            with open(CONFIG, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def find_csgo(override=None):
    """按优先级探测 csgo 目录: 参数 > 环境变量 > 配置 > 注册表+库清单 > 常见路径"""
    cands = []
    if override:
        cands.append(override)
    if os.environ.get("CSGO_DIR"):
        cands.append(os.environ["CSGO_DIR"])
    cfg = load_config().get("csgo")
    if cfg:
        cands.append(cfg)
    try:  # 注册表找 Steam, 再解析全部库目录
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        steam, _ = winreg.QueryValueEx(k, "SteamPath")
        libs = [steam]
        vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
        if os.path.exists(vdf):
            with open(vdf, encoding="utf-8", errors="replace") as f:
                libs += re.findall(r'"path"\s+"([^"]+)"', f.read())
        for lib in libs:
            cands.append(os.path.join(lib.replace("\\\\", "\\"), "steamapps", "common", *GAME_REL))
    except Exception:
        pass
    for drv in "CDEF":  # 常见安装位置兜底
        cands += [rf"{drv}:\Program Files (x86)\Steam\steamapps\common\{os.path.join(*GAME_REL)}",
                  rf"{drv}:\Steam\steamapps\common\{os.path.join(*GAME_REL)}",
                  rf"{drv}:\Program Files\Steam\steamapps\common\{os.path.join(*GAME_REL)}"]
    for c in cands:
        if c and os.path.exists(os.path.join(c, "pak01_dir.vpk")):
            return c
    return None


def require_paths():
    csgo = find_csgo()
    if not csgo:
        print("[!] 未找到 CS2 csgo 目录; 请先运行 --init, 或用 --csgo 指定路径")
        sys.exit(1)
    set_paths(csgo)


def cmd_init(override=None):
    global CSGO
    csgo = find_csgo(override)
    if not csgo:
        print("[!] 未能自动找到 CS2 csgo 目录。请用 --csgo 手动指定, 例如:")
        print('    python knife_mod.py --init --csgo "D:\\Steam\\steamapps\\common\\Counter-Strike Global Offensive\\game\\csgo"')
        return False
    set_paths(csgo)
    print(f"[+] 游戏目录: {CSGO}")
    if os.path.exists(BAK_DIR):
        print(f"[+] 原始备份已存在: {BAK_DIR}")
    else:
        shutil.copy2(DIR_PATH, BAK_DIR)
        print(f"[+] 已创建原始备份: {BAK_DIR}")
        print("    注意: 备份必须是未打补丁的原始文件。若当前 pak01_dir.vpk 已被")
        print("    其他补丁修改过, 请先跑 Steam「验证完整性」还原后再重新 --init")
    try:
        import blake3  # noqa: F401
        print("[+] blake3 依赖 OK")
    except ImportError:
        print("[!] 缺少 blake3: pip install blake3 (否则审计将跳过数据包窗口校验)")
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump({"csgo": CSGO}, f, ensure_ascii=False, indent=2)
    print(f"[+] 配置已保存: {CONFIG}")
    cmd_audit()  # 信息性审计: 全新状态应全绿
    return True


def parse_tree(data):
    pos = 28
    def cstr(p):
        e = data.index(b"\x00", p)
        return data[p:e].decode("utf-8", "replace"), e + 1
    out = {}
    while True:
        ext, pos = cstr(pos)
        if not ext: break
        while True:
            path, pos = cstr(pos)
            if not path: break
            while True:
                name, pos = cstr(pos)
                if not name: break
                foff = pos
                crc, preload, arch, off, ln, term = struct.unpack_from("<IHHIIH", data, pos)
                assert term == 0xFFFF, f"bad terminator {term:#x} at {foff:#x}"
                pos += 18 + preload
                out[f"{ext}:{path}/{name}"] = (foff, crc, preload, arch, off, ln)
    return out


def compute_other_md5(data):
    sig, ver, tree_size = struct.unpack_from("<III", data, 0)
    _, hsz_bytes, osz, ssz = struct.unpack_from("<IIII", data, 12)
    tree = data[28:28 + tree_size]
    harr = data[28 + tree_size: 28 + tree_size + hsz_bytes]
    return hashlib.md5(tree).digest() + hashlib.md5(harr).digest()


def read_dir():
    with open(DIR_PATH, "rb") as f:
        return f.read()


def load_ref_tree():
    """只读操作用: 优先原始备份, 无备份时退回当前目录文件"""
    src = BAK_DIR if os.path.exists(BAK_DIR) else DIR_PATH
    return parse_tree(open(src, "rb").read())


def load_orig_tree():
    if not os.path.exists(BAK_DIR):
        print(f"[!] 无原始备份 {BAK_DIR}; 请先运行 --init 创建")
        sys.exit(1)
    return parse_tree(open(BAK_DIR, "rb").read())


def main_var_for(tree, k):
    """主图槽该指向哪张图 -> (条目, 类型)

    19 把中小刀型走变体体系: viewmodel_knife.vnmgraph+<刀名> (约 8KB 完整子图)
    3 把独立刀型 (butterfly/karambit/talon) 没有变体, 只有独立完整图
    viewmodel_knife_<刀名> —— 它同时被顶层 viewmodel 直接引用, 是自包含状态机,
    自带 INSPECT_LOOP, 正好该待在主图槽里。
    """
    var = f"{VMDOM}viewmodel_knife.vnmgraph+{k}"
    if var in tree:
        return var, "变体"
    full = f"{VMDOM}viewmodel_knife_{k}"
    if full in tree:
        return full, "完整图"
    return None, None


def discover_knives(tree):
    """从树发现全部刀型: 模型条目 + 检视槽用图 + 主图槽用图

    检视槽里塞的必须是「inspects 变体」(约 4.9KB, 只有一条 lookat clip,
    97.7% 同构), 不能是「专属完整图」(约 8.3KB, 自带 INSPECT_LOOP 循环
    状态且没有 INSPECTCANCEL 退出路径)。把完整图塞进检视槽会让检视播完
    不停止、连续重复触发。变体缺失时才退回完整图, 并用 heavy 标记提示。

    主图槽才是 idle/draw/attack/手模 的归属, 必须单独换, 见 main_var_for。
    """
    knives = {}
    for k, disp in KNOWN.items():
        model = f"vmdl_c:weapons/models/knife/knife_{k}/weapon_knife_{k}"
        if model not in tree:
            continue
        dedicated = f"{VMDOM}viewmodel_knife_{k}"
        variant = f"{VMDOM}viewmodel_inspects.vnmgraph+knife_{k}"
        graph = variant if variant in tree else (dedicated if dedicated in tree else None)
        if graph:
            knives[k] = (model, graph, disp)
    return knives


def build_targets(orig_tree, knife, force_inspect=False, no_main=False):
    """要重指向的条目 -> (pack, offset, len, crc)

    三条槽位, 各管一件事, 缺一条就出对应症状:
      模型槽  MODEL_*  外观几何 (换了它 = 看见另一把刀)
      主图槽  MAIN_*   idle/draw/attack + 手模 (不换 = 拔刀动作和手臂还是匕首的)
      检视槽  GRAPH_*  按 F 的检视玩法 (不换 = 播默认刀的检视)

    主图槽默认跟模型一起换; 若新图在游戏里表现异常, 加 --no-main 只换模型和检视。
    检视槽只在「有 inspects 变体」或显式 force_inspect 时才写 —— 没有变体的刀
    (butterfly) 把 8.3KB 完整图塞进 4.9KB 变体槽会进 INSPECT_LOOP 且无退出路径。
    """
    knives = discover_knives(orig_tree)
    if knife not in knives:
        print(f"[!] 未知刀型: {knife}\n可用: {', '.join(sorted(knives))}"); sys.exit(1)
    model, graph, _ = knives[knife]
    m = orig_tree[model]
    out = {MODEL_T: (m[3], m[4], m[5], m[1]),
           MODEL_CT: (m[3], m[4], m[5], m[1])}
    if not no_main:
        mv, _kind = main_var_for(orig_tree, knife)
        if mv:
            e = orig_tree[mv]
            out[MAIN_T] = (e[3], e[4], e[5], e[1])
            out[MAIN_CT] = (e[3], e[4], e[5], e[1])
    if "inspects" in graph or force_inspect:
        g = orig_tree[graph]
        out[GRAPH_T] = (g[3], g[4], g[5], g[1])
        out[GRAPH_CT] = (g[3], g[4], g[5], g[1])
    return out


def cmd_list():
    tree = load_ref_tree()
    knives = discover_knives(tree)
    print(f"可用刀型 ({len(knives)}):")
    for k in sorted(knives):
        model, graph, disp = knives[k]
        _mv, mkind = main_var_for(tree, k)
        if "inspects" in graph:
            gtype = "检视变体 OK"
        else:
            gtype = "[!] 无检视变体 (检视沿用默认刀)"
        print(f"  --knife {k:<10} {disp:<8} 主图槽={mkind or '缺失':<6} {gtype}")


def cmd_apply(knife, force_inspect=False, no_main=False):
    orig = open(BAK_DIR, "rb").read()
    orig_tree = parse_tree(orig)
    targets = build_targets(orig_tree, knife, force_inspect, no_main)
    cur = bytearray(orig)
    for t, (a, o, l, c) in targets.items():
        foff = orig_tree[t][0]
        struct.pack_into("<IHHII", cur, foff, c, 0, a, o, l)
    data = bytes(cur)
    om_off = len(data) - SIG_BLOCK - 48
    data = data[:om_off] + compute_other_md5(data) + data[om_off + 32:]
    with open(DIR_PATH, "r+b") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    mv, mkind = main_var_for(orig_tree, knife)
    parts = []
    parts.append(f"主图槽→{mkind}" if MAIN_T in targets else "主图槽未动")
    parts.append("检视槽→" + ("变体" if GRAPH_T in targets else "未动"))
    print(f"[+] 已替换为 {knife} ({len(targets)} 个条目指针 + other_md5 重算)  " + ", ".join(parts))
    if mv:
        print(f"    主图: {mv.split('/')[-1]}  {orig_tree[mv][5]}B")


def cmd_revert():
    if not os.path.exists(BAK_DIR):
        print(f"[!] 无原始备份 {BAK_DIR}; 请先运行 --init")
        sys.exit(1)
    shutil.copy2(BAK_DIR, DIR_PATH)
    print("[+] 已还原默认刀")


def audit_pack(path, pack_id, harr):
    try:
        import blake3
        has_b3 = True
    except ImportError:
        has_b3 = False
        print(f"  [!] pak01_{pack_id:03d}.vpk: 未安装 blake3, BLAKE3 窗口跳过 (pip install blake3)")
    by_pack = {}
    for i in range(len(harr) // 28):
        p, ty, off, sz, h = struct.unpack_from("<HHII16s", harr, i * 28)
        if p == pack_id:
            by_pack[off] = (sz, h, ty)
    ok, checked, skipped = True, 0, 0
    with open(path, "rb") as f:
        for off in sorted(by_pack):
            sz, h, ty = by_pack[off]
            if ty == 1 and not has_b3:
                skipped += 1
                continue
            f.seek(off)
            blob = f.read(sz)
            if len(blob) != sz or (blake3.blake3(blob) if ty == 1 else hashlib.md5(blob)).digest()[:16] != h:
                print(f"  [!] pack{pack_id} 窗口@{off} 校验失败"); ok = False
            checked += 1
    note = f" (跳过 {skipped})" if skipped else ""
    print(f"{'[+]' if ok else '[!]'} pak01_{pack_id:03d}.vpk {checked}/{len(by_pack)} 窗口{note}" + (" ✓" if ok else " ✗"))
    return ok


def cmd_audit(knife=None, force_inspect=False, no_main=False):
    print("========== 审计 ==========")
    ok = True
    cur = read_dir()
    orig = open(BAK_DIR, "rb").read()
    orig_tree = parse_tree(orig)
    tree = parse_tree(cur)
    good = len(cur) == len(orig)
    if not good:
        print(f"[!] 文件大小与原始基准不同: 当前 {len(cur)} vs 原始 {len(orig)}")
        print("    (磁盘可能是其他补丁状态; 执行 --knife <名> 或 --revert 后再审计)")
    else:
        print(f"[+] 文件大小不变: {len(cur)}")
    ok &= good
    diffs = [i for i in range(min(len(orig), len(cur))) if orig[i] != cur[i]]
    tree_size = struct.unpack_from("<I", cur, 8)[0]
    h0 = 28 + tree_size
    om0 = len(orig) - SIG_BLOCK - 48       # other_md5 区起点, 重指向后必须随之更新
    in_tree = all(d < h0 or d >= om0 for d in diffs)
    in_entry = True
    extra = ""
    if knife:
        targets = build_targets(orig_tree, knife, force_inspect, no_main)
        expect = set()
        for t in targets:
            foff = orig_tree[t][0]
            expect.update(range(foff, foff + 16))
        expect.update(range(len(orig) - SIG_BLOCK - 48, len(orig) - SIG_BLOCK))  # other_md5
        if set(diffs) <= expect:
            in_entry = True
        elif in_tree:
            # 盘上还叠着别的补丁（如 skin_mod 的换肤），条目级严格比对不再适用:
            # 差异确实全在树区, 只是不止换刀这几条。降级为区域校验并说明。
            extra = f"  (叠加了其他补丁: 多出 {len(set(diffs) - expect)}B 落在其他树条目内)"
            in_entry = True
        else:
            in_entry = False
    print(f"{'[+]' if in_tree and in_entry else '[!]'} 差异 {len(diffs)}B 全部位于允许区域: {in_tree and in_entry}{extra}")
    ok &= in_tree and in_entry
    # 大小相同则直接切片比较哈希数组+签名块
    if len(orig) == len(cur):
        om0 = len(orig) - SIG_BLOCK - 48
        good = orig[h0:om0] == cur[h0:om0]
        print(f"{'[+]' if good else '[!]'} 哈希数组区未变: {good}")
        ok &= good
    om_off = len(cur) - SIG_BLOCK - 48
    good = cur[om_off:om_off + 32] == compute_other_md5(cur)
    print(f"{'[+]' if good else '[!]'} other_md5 自洽: {good}")
    ok &= good
    # 涉及的 pack 全窗口审计
    packs = set()
    src = build_targets(orig_tree, knife, force_inspect, no_main) if knife else {}
    for t in (src or {}).values():
        packs.add(t[0])
    if packs:
        hsz = struct.unpack_from("<I", cur, 16)[0]
        harr = cur[h0:h0 + hsz]
        for p in sorted(packs):
            path = os.path.join(CSGO, f"pak01_{p:03d}.vpk")
            if os.path.exists(path):
                ok &= audit_pack(path, p, harr)
    snap = {"time": __import__("datetime").datetime.now().isoformat(),
            "knife": knife, "audit_ok": ok, "diff_bytes": len(diffs)}
    with open(SNAP, "w") as f:
        json.dump(snap, f, indent=2)
    print("==========", "审计通过" if ok else "审计失败!", "==========")
    return ok


if __name__ == "__main__":
    args = sys.argv[1:]
    csgo_arg = None
    if "--csgo" in args and len(args) > args.index("--csgo") + 1:
        csgo_arg = args[args.index("--csgo") + 1]
    if "--init" in args:
        cmd_init(csgo_arg)
        sys.exit(0 if CSGO else 1)
    require_paths()
    if "--list" in args:
        cmd_list()
    elif "--revert" in args:
        cmd_revert()
        sys.exit(0 if cmd_audit() else 1)
    elif "--audit" in args:
        k = args[args.index("--audit") + 1] if len(args) > args.index("--audit") + 1 and not args[args.index("--audit") + 1].startswith("--") else None
        sys.exit(0 if cmd_audit(k, "--force-inspect" in args, "--no-main" in args) else 1)
    elif "--knife" in args:
        i = args.index("--knife")
        if len(args) <= i + 1 or args[i + 1].startswith("--"):
            print("[!] --knife 需要刀型名, 见 --list"); sys.exit(1)
        fi = "--force-inspect" in args
        nm = "--no-main" in args
        cmd_apply(args[i + 1], fi, nm)
        sys.exit(0 if cmd_audit(args[i + 1], fi, nm) else 1)
    else:
        print(__doc__)
