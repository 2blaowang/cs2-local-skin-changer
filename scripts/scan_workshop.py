# -*- coding: utf-8 -*-
"""泛武器词扫描 + 模型类型分布统计"""
import knife_mod, os, glob, re, collections

WS = r"C:\Program Files (x86)\Steam\steamapps\workshop\content\730"
PAT = re.compile(r"(gun|rifle|pistol|\bsmg\b|awp|\bak[-_ ]|\bm4|sword|katana|blade|saber|machete|\baxe\b|hammer|crowbar|\bbat\b|scythe|spear|dagger|revolver|deagle|crossbow|bow\b|viewmodel|v_model|arms)", re.I)

def main():
    dirs = sorted(glob.glob(os.path.join(WS, "*", "*_dir.vpk")))
    hits, bucket = [], collections.Counter()
    for d in dirs:
        wid = os.path.basename(os.path.dirname(d))
        try:
            tree = knife_mod.parse_tree(open(d, "rb").read())
        except Exception:
            continue
        for k in tree:
            if not k.startswith("vmdl_c:"):
                continue
            p = k.split(":", 1)[1]
            seg = p.split("/")
            bucket[seg[1] if len(seg) > 2 else seg[0]] += 1
            low = p.lower()
            if "worldnodes" in low or "window" in low:
                continue
            if PAT.search(low):
                hits.append((wid, p, tree[k][5]))
    print("[*] 模型路径第二段分布 top25:")
    for name, n in bucket.most_common(25):
        print(f"  {n:5d}  {name}")
    print(f"\n[*] 泛武器词命中 {len(hits)}:")
    for wid, p, ln in hits[:60]:
        print(f"  [{wid}] {p}  ({ln}B)")

if __name__ == "__main__":
    main()
