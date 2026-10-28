# 一次性批量实验: 其余武器每把随机换一个皮肤 (叠加到当前补丁之上)
import sys, struct, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import knife_mod as km, skin_mod as sm

km.require_paths()
tree = km.load_ref_tree()
sm.tree_cache = tree
wmap = sm.build_map(tree)
done = {"ak47", "m4a4", "m4a1_silencer"}

plan = {}
for w, kits in wmap.items():
    if w in done:
        continue
    # 只挑"满铺成品图"型皮肤: tga 单层源且贴图够大, 保证图案完整
    good = []
    for kit in sorted(kits):
        src_tex, tgts = sm.tex_targets(tree, wmap, w, kit)
        if tgts and src_tex and "_tga_" in src_tex and tree[src_tex][5] > 500_000:
            good.append((kit, src_tex, tgts))
    if not good:  # 该武器没有成品图型皮肤则跳过, 保留原版
        print(f"  {w:<14} -- 无满铺成品图皮肤, 跳过")
        continue
    kit, src_tex, tgts = random.choice(good)
    plan[w] = (kit, src_tex, tgts)

bak_len = os.path.getsize(km.BAK_DIR)
data = bytearray(km.read_dir())
assert len(data) == bak_len, "当前文件大小与备份不符, 拒绝批量叠加"
for w, (kit, src_tex, tgts) in sorted(plan.items()):
    se = tree[src_tex]
    print(f"  {w:<14} -> {kit}  ({len(tgts)} 贴图, 源 {se[5]}B)")
    for t in tgts:
        te = tree[t]
        struct.pack_into("<IHHII", data, te[0], se[1], 0, se[3], se[4], se[5])

data = bytes(data)
om = len(data) - km.SIG_BLOCK - 48
data = data[:om] + km.compute_other_md5(data) + data[om + 32:]
with open(km.DIR_PATH, "r+b") as f:
    f.write(data)
    f.truncate()
    f.flush()
    os.fsync(f.fileno())
print(f"[+] 已批量应用 {len(plan)} 把武器")
km.cmd_audit()
