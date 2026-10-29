"""
打包分发包 cs2-local-skin-changer.zip
=================================
把脚本与文档按固定清单打成一个 zip, 避免手工重打包造成"分发包与源码不一致"
(仓库里同时存在源码与 zip 时, 手工维护必然出现第二个真相来源)。

用法:
  python scripts/pack_release.py            # 重新生成 zip
  python scripts/pack_release.py --check    # 只比对 zip 与磁盘是否一致, 不写文件

清单外的文件不会进包; 新增脚本请同步改 MEMBERS。
"""
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP_NAME = "cs2-local-skin-changer.zip"
MEMBERS = [
    "scripts/knife_mod.py",
    "scripts/skin_mod.py",
    "scripts/diagnose_skin.py",
    "scripts/batch_random.py",
    "scripts/scan_workshop.py",
    "references/vpk-technique.md",
    "SKILL.md",
]


def build(check_only=False):
    zip_path = os.path.join(ROOT, ZIP_NAME)
    if check_only:
        if not os.path.exists(zip_path):
            print(f"[!] 分发包不存在: {ZIP_NAME}")
            return False
        ok = True
        with zipfile.ZipFile(zip_path) as z:
            names = {n.replace("\\", "/") for n in z.namelist()}
            for m in MEMBERS:
                if m not in names:
                    print(f"  缺: {m}")
                    ok = False
                    continue
                disk = open(os.path.join(ROOT, m), "rb").read()
                if z.read(m) != disk:
                    print(f"  陈旧: {m} (zip {len(z.read(m))}B / 磁盘 {len(disk)}B)")
                    ok = False
            extra = names - set(MEMBERS)
            for e in sorted(extra):
                print(f"  多余: {e}")
                ok = False
        print("分发包与源码一致" if ok else "分发包需要重新生成: python scripts/pack_release.py")
        return ok

    missing = [m for m in MEMBERS if not os.path.exists(os.path.join(ROOT, m))]
    if missing:
        print("[!] 缺少源文件:", ", ".join(missing))
        return False
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for m in MEMBERS:
            z.write(os.path.join(ROOT, m), m)  # 统一用正斜杠, 跨平台解压不乱
    size = os.path.getsize(zip_path)
    print(f"[+] 已生成 {ZIP_NAME}  ({len(MEMBERS)} 个文件, {size:,}B)")
    for m in MEMBERS:
        print(f"    {os.path.getsize(os.path.join(ROOT, m)):>7,}B  {m}")
    return True


if __name__ == "__main__":
    sys.exit(0 if build(check_only="--check" in sys.argv) else 1)
