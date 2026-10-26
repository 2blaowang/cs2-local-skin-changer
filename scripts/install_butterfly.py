# -*- coding: utf-8 -*-
"""安装蝴蝶刀覆盖: VPK 放入 game/csgo/custom/ + 备份并修改 gameinfo.gi (只加一行)"""
import os
import re
import shutil

GAME = r"c:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game"
VPK_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "butterfly_knife.vpk")
CUSTOM_DIR = os.path.join(GAME, "csgo", "custom")
VPK_DST = os.path.join(CUSTOM_DIR, "butterfly_knife.vpk")
GI = os.path.join(GAME, "csgo", "gameinfo.gi")
GI_BAK = GI + ".bak_butterfly"
MOUNT_LINE = "\t\t\tGame\tcsgo/custom/butterfly_knife.vpk // butterfly knife override"


def main():
    assert os.path.exists(VPK_SRC), "缺少 butterfly_knife.vpk, 先运行 build_butterfly_vpk.py"
    os.makedirs(CUSTOM_DIR, exist_ok=True)
    shutil.copy2(VPK_SRC, VPK_DST)
    print(f"[1] VPK 已就位: {VPK_DST} ({os.path.getsize(VPK_DST)} 字节)")

    if not os.path.exists(GI_BAK):
        shutil.copy2(GI, GI_BAK)
        print(f"[2] 已备份 gameinfo.gi -> {os.path.basename(GI_BAK)}")
    else:
        print(f"[2] 备份已存在, 保留最早的: {os.path.basename(GI_BAK)}")

    raw = open(GI, "rb").read().decode("utf-8")
    if "butterfly_knife.vpk" in raw:
        print("[3] 挂载行已存在, 跳过")
        return
    pat = re.compile(r"(\r?\n)(\t{3}Game\tcsgo)(\r?\n)")
    n = len(pat.findall(raw))
    assert n == 1, f"锚点 'Game csgo' 匹配 {n} 处 (应为 1), 中止"
    raw2 = pat.sub(lambda m: m.group(1) + MOUNT_LINE + m.group(1) + m.group(2) + m.group(3),
                   raw, count=1)
    open(GI, "wb").write(raw2.encode("utf-8"))
    i = raw2.index("SearchPaths")
    j = raw2.index("AddonRoot")
    print("[3] gameinfo.gi 已修改, SearchPaths 现为:")
    print(raw2[i:j].replace("\r\n", "\n").rstrip())


if __name__ == "__main__":
    main()
