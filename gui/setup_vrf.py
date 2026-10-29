"""下载并展开 Source2Viewer-CLI (VRF), 缩略图导出用。

GUI 首次跑如果提示"未找到 Source2Viewer-CLI", 执行一次即可:

    python gui/setup_vrf.py

产物: .cache/vrf/Source2Viewer-CLI.exe (约 53MB 下载, 已 gitignore)
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, ".cache", "vrf")
API = "https://api.github.com/repos/ValveResourceFormat/ValveResourceFormat/releases/latest"
WANT = "cli-windows-x64.zip"


def main() -> int:
    sys.path.insert(0, os.path.join(ROOT, "gui"))
    import thumbs  # noqa: E402

    if thumbs.vrf_exe():
        print(f"[+] 已存在: {thumbs.vrf_exe()}")
        return 0

    print("[*] 查询最新发布…")
    with urllib.request.urlopen(API, timeout=30) as r:
        rel = json.load(r)
    asset = next((a for a in rel["assets"] if a["name"] == WANT), None)
    if not asset:
        print(f"[!] 发布 {rel['tag_name']} 里没有 {WANT}")
        return 1
    print(f"[*] {rel['tag_name']} / {WANT}  {asset['size'] / 1e6:.1f}MB")

    os.makedirs(OUT, exist_ok=True)
    zpath = os.path.join(OUT, WANT)
    with urllib.request.urlopen(asset["browser_download_url"], timeout=600) as r, \
            open(zpath, "wb") as f:
        total = int(r.headers.get("content-length") or 0)
        got = 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            got += len(chunk)
            if total:
                print(f"\r    下载 {got / 1e6:.1f}/{total / 1e6:.1f}MB", end="")
    print()

    print("[*] 解压…")
    with zipfile.ZipFile(zpath) as z:
        z.extractall(OUT)
    os.remove(zpath)

    exe = thumbs.vrf_exe()
    if exe:
        print(f"[+] 就绪: {exe}")
        return 0
    found = shutil.which("Source2Viewer-CLI")
    print(f"[!] 解压完成但没找到 Source2Viewer-CLI.exe, 请检查 {OUT}")
    return 1 if not found else 0


if __name__ == "__main__":
    raise SystemExit(main())
