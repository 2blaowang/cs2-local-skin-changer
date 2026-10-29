"""缩略图提供器: 把 VPK 里的 vtex_c 变成界面能显示的 PNG, 并缓存。

为什么不自己解码 vtex
---------------------
VTEX 是 DXT/BC 压缩 + 多层 mip + 平台数据块, Python 侧没有可靠实现。
直接用 ValveResourceFormat 的命令行工具 (Source2Viewer-CLI) 导出 PNG 是
唯一稳妥路线, 它是社区事实标准, MIT 协议, 支持直接读 pak01_dir.vpk。

两级缓存
--------
icons  : 武器 × kit 的检视图 (游戏里库存那张成品小图), 按武器整批导出
paint  : kit 的图案本体 (大图), 只在选中时导出

两级都很重, 所以只在真正要显示时才导出, 结果落在 .cache/thumbs/ 下,
文件名与 VPK 路径一一对应, 导出过的永远不再导出。
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "scripts"))

CACHE = os.path.join(ROOT, ".cache", "thumbs")
VRF_DIR = os.path.join(ROOT, ".cache", "vrf")
ICON_ROOT = "panorama/images/econ/default_generated/"


def vrf_exe() -> str | None:
    """找 Source2Viewer-CLI: 环境变量 > .cache/vrf 下任意位置 > PATH"""
    env = os.environ.get("VRF_CLI")
    if env and os.path.exists(env):
        return env
    if os.path.isdir(VRF_DIR):
        for base, _dirs, files in os.walk(VRF_DIR):
            for f in files:
                if f.lower() in ("source2viewer-cli.exe", "source2viewer-cli"):
                    return os.path.join(base, f)
    from shutil import which
    return which("Source2Viewer-CLI") or which("Source2Viewer-CLI.exe")


def png_path(vpk_path: str) -> str:
    """vtex 路径 -> 缓存里的 png 路径 (VRF 导出时保持目录结构, 扩展名换 .png)"""
    return os.path.join(CACHE, vpk_path.replace("/", os.sep) + ".png")


def has(vpk_path: str) -> bool:
    return os.path.exists(png_path(vpk_path))


def _export(prefix: str, vpk: str, timeout: int = 240) -> tuple[bool, str]:
    """按路径前缀批量导出 (一次进程调用能出几十上百张, 别一张一张调)"""
    exe = vrf_exe()
    if not exe:
        return False, "未找到 Source2Viewer-CLI (见 gui/README 的安装说明)"
    os.makedirs(CACHE, exist_ok=True)
    cmd = [exe, "-i", vpk, "-o", CACHE, "-d",
           "--vpk_extensions", "vtex_c", "--vpk_filepath", prefix]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return False, f"导出超时 ({timeout}s): {prefix}"
    except Exception as e:  # noqa: BLE001
        return False, f"导出失败: {e}"
    if p.returncode != 0:
        return False, (p.stderr or p.stdout or "VRF 返回非零").strip()[:400]
    return True, p.stdout.strip()[-400:]


# ------------------------------------------------------------------ 检视图

def ensure_icons(prefixes: list[str], vpk: str) -> tuple[bool, str]:
    """按 UI 名批量导出某武器的检视图

    传进来的是检视图里的 UI 名 (M4A4 是 m4a1), 由 service.icon_prefixes()
    反解得到 —— 不要自己拼武器目录名, 拼错会 0 命中。

    注意这里**不做整目录兜底**: default_generated 下有 6000+ 张、几百 MB,
    一次误触发就是几分钟白等。前缀没命中就如实返回失败。
    """
    if not prefixes:
        return False, "该武器没有检视图资源"
    ok, msgs = True, []
    for p in prefixes:
        o, m = _export(ICON_ROOT + f"weapon_{p}", vpk)
        ok = ok and o
        if m:
            msgs.append(m)
    return ok, "\n".join(msgs)[-600:]


# ------------------------------------------------------------------ 图案本体

def ensure_texture(vpk_path: str, vpk: str) -> tuple[bool, str]:
    """按需导出单张贴图 (kit 的图案本体)"""
    if has(vpk_path):
        return True, "缓存命中"
    folder = vpk_path.rsplit("/", 1)[0] if "/" in vpk_path else ""
    ok, msg = _export(vpk_path, vpk)
    if ok and has(vpk_path):
        return True, msg
    # 前缀不精确时退回整个目录
    if folder:
        ok2, msg2 = _export(folder + "/", vpk, timeout=600)
        if ok2:
            return True, msg + "\n" + msg2
    return False, msg


# ------------------------------------------------------------------ 占位图

def placeholder(text: str, size: int = 128) -> str | None:
    """没有 VRF / 未导出时的占位图: 按名字哈希取色 + 首字, 免得界面全是空白"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    os.makedirs(os.path.join(CACHE, "_ph"), exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in text)[:60]
    out = os.path.join(CACHE, "_ph", f"{safe}.png")
    if os.path.exists(out):
        return out
    h = abs(hash(text)) % 360
    rgb = _hsl(h, 0.45, 0.42)
    img = Image.new("RGB", (size, size), rgb)
    d = ImageDraw.Draw(img)
    d.rectangle([0, size - 28, size, size], fill=_hsl(h, 0.45, 0.30))
    d.text((8, size - 22), text[:14], fill=(235, 235, 235))
    cy = size // 2 - 16
    d.text((size // 2 - 8, cy), (text[:1] or "?").upper(), fill=(240, 240, 240))
    img.save(out)
    return out


def _hsl(h: int, s: float, light: float):
    import colorsys
    r, g, b = colorsys.hls_to_rgb(h / 360.0, light, s)
    return int(r * 255), int(g * 255), int(b * 255)


if __name__ == "__main__":  # 自检: python gui/thumbs.py
    import knife_mod as km
    km.set_paths(km.find_csgo())
    print("vrf:", vrf_exe())
    print("cache:", CACHE)
