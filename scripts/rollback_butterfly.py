# -*- coding: utf-8 -*-
"""回滚蝴蝶刀覆盖: 还原 gameinfo.gi + 删除覆盖 VPK。
pak01 从未被本方案修改, 无需任何其他操作。"""
import os
import shutil

GAME = r"c:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game"
GI = os.path.join(GAME, "csgo", "gameinfo.gi")
GI_BAK = GI + ".bak_butterfly"
VPK = os.path.join(GAME, "csgo", "custom", "butterfly_knife.vpk")


def main():
    if os.path.exists(GI_BAK):
        shutil.copy2(GI_BAK, GI)
        print("[1] gameinfo.gi 已还原自备份")
    else:
        raw = open(GI, "rb").read().decode("utf-8")
        if "butterfly_knife.vpk" in raw:
            lines = [l for l in raw.split("\n") if "butterfly_knife.vpk" not in l]
            open(GI, "wb").write("\n".join(lines).encode("utf-8"))
            print("[1] 备份不存在, 已按行移除挂载行")
        else:
            print("[1] gameinfo.gi 无挂载行, 无需还原")

    if os.path.exists(VPK):
        os.remove(VPK)
        print(f"[2] 已删除 {VPK}")
    else:
        print("[2] 覆盖 VPK 不存在")

    print("[完成] CS2 已恢复原状 (pak01 未被修改过)")


if __name__ == "__main__":
    main()
