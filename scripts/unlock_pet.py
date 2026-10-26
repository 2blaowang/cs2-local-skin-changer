# -*- coding: utf-8 -*-
"""解锁 CS2 的 Particle Editor 与 AnimGraph Editor:
1. sdkenginetools.txt: 注释掉 pet / animgraph_editor 的 m_ExcludeFromMods 块
2. assettypes_common.txt: 注释掉 particle_asset 的 m_HideForRetailMods 块
幂等, 修改前自动备份。
"""
import io
import os
import re
import shutil

BIN = r"c:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\bin"
F1 = os.path.join(BIN, "sdkenginetools.txt")
F2 = os.path.join(BIN, "assettypes_common.txt")


def comment_match(text, pat):
    """把 pat 匹配到的块按行加 // 前缀"""
    n = len(re.findall(pat, text))
    if n == 0:
        return text, 0
    assert n == 1, f"模式匹配 {n} 处(应 1): {pat}"
    m = re.search(pat, text)
    commented = "\r\n".join("//" + x for x in m.group(0).split("\r\n"))
    return text[:m.start()] + commented + text[m.end():], 1


def main():
    # --- 文件1: pet + animgraph_editor 的排除块 ---
    raw = io.open(F1, encoding="utf-8", newline="").read()
    if not os.path.exists(F1 + ".bak_pet"):
        shutil.copy2(F1, F1 + ".bak_pet")
        print("[备份] sdkenginetools.txt.bak_pet")
    changed = 0
    if "m_ExcludeFromMods" in raw:
        pat_pet = (r'm_ExcludeFromMods = \s*[\r\n]+\s*\[\s*[\r\n]+\s*"csgo",\s*[\r\n]+\s*\]')
        raw, n1 = comment_match(raw, pat_pet)
        changed += n1
        print(f"[1a] pet 排除块: 注释 {n1} 处")
        pat_ag = (r'm_ExcludeFromMods = \s*[\r\n]+\s*\[\s*[\r\n]+\s*"dota",\s*[\r\n]+'
                  r'\s*"csgo",\s*[\r\n]+\s*\]')
        raw, n2 = comment_match(raw, pat_ag)
        changed += n2
        print(f"[1b] animgraph_editor 排除块: 注释 {n2} 处")
        io.open(F1, "w", encoding="utf-8", newline="").write(raw)
        print(f"[1] sdkenginetools.txt 保存 (共 {changed} 处)")
    else:
        print("[1] sdkenginetools.txt 无排除块, 跳过")

    # --- 文件2: particle_asset 的隐藏块 ---
    raw2 = io.open(F2, encoding="utf-8", newline="").read()
    if not os.path.exists(F2 + ".bak_pet"):
        shutil.copy2(F2, F2 + ".bak_pet")
        print("[备份] assettypes_common.txt.bak_pet")
    m = re.search(r'particle_asset\s*=\s*\{', raw2)
    assert m, "找不到 particle_asset 块"
    seg_start = m.start()
    nxt = re.search(r'[\r\n]+\s*\w+_asset\s*=\s*\{', raw2[seg_start + 10:])
    seg_end = seg_start + 10 + (nxt.start() if nxt else 4000)
    seg = raw2[seg_start:seg_end]
    pat_hide = r'm_HideForRetailMods = \s*[\r\n]+\s*\[\s*[\r\n]+\s*"csgo",\s*[\r\n]+\s*\]'
    if pat_hide in seg or re.search(pat_hide, seg):
        seg2, n3 = comment_match(seg, pat_hide)
        raw2 = raw2[:seg_start] + seg2 + raw2[seg_end:]
        io.open(F2, "w", encoding="utf-8", newline="").write(raw2)
        print(f"[2] assettypes_common.txt: particle_asset 已解锁 (注释 {n3} 处)")
    else:
        print("[2] particle_asset 无隐藏块, 跳过")

    # --- 验证输出 ---
    print()
    print("=== 验证: pet 块现状 ===")
    v = io.open(F1, encoding="utf-8", newline="").read()
    mm = re.search(r'm_Name = "pet".{0,600}', v, re.S)
    print(mm.group(0)[:600] if mm else "未找到")
    print()
    print("=== 验证: particle_asset 块现状 ===")
    mm2 = re.search(r'particle_asset\s*=\s*\{.{0,700}', v := io.open(F2, encoding="utf-8", newline="").read(), re.S)
    print(mm2.group(0)[:700] if mm2 else "未找到")


if __name__ == "__main__":
    main()
