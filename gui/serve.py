"""本地 Web 界面的服务端 (只用标准库, 零依赖)。

为什么不只用 PySide6: 这套逻辑本来就要能被任意前端复用。这里用
http.server 把 service.py 包成 JSON 接口, 浏览器直接当客户端。
好处是 ① 装不出 GUI 框架也能跑 ② 以后套 Tauri/Electron 时这层直接就是后端。

启动: python gui/serve.py [--port 8765] [--no-browser]
"""
from __future__ import annotations

import json
import mimetypes
import os

import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import service  # noqa: E402
import thumbs   # noqa: E402

WEB = os.path.join(HERE, "web")
LOG: list[str] = []


def _dir_vpk() -> str:
    return service.km.DIR_PATH


def _weapon_kits_payload(weapon: str) -> dict:
    kits = service.kits(weapon)
    for k in kits:
        rel = service.icon_rel(weapon, k["kit"])
        done = bool(rel) and os.path.exists(thumbs.png_path(rel))
        k["icon"] = f"/thumbs/{rel}.png" if done else None
    return {"weapon": weapon, "kits": kits}


class Handler(BaseHTTPRequestHandler):
    server_version = "cs2skin/0.1"

    # ------------------------------------------------------------ 路由
    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/":
                return self._file(os.path.join(WEB, "index.html"))
            if u.path.startswith("/thumbs/"):
                rel = unquote(u.path[len("/thumbs/"):])
                return self._file(os.path.join(thumbs.CACHE, rel.replace("/", os.sep)))
            if u.path == "/api/bootstrap":
                return self._json({
                    "state": service.state(),
                    "weapons": service.weapons(),
                    "knives": service.knives(),
                    "patches": service.patches(),
                    "vrf": bool(thumbs.vrf_exe()),
                })
            if u.path == "/api/kits":
                return self._json(_weapon_kits_payload(q.get("w", "")))
            if u.path == "/api/kit":
                return self._json(service.kit_detail(q.get("k", "")))
            if u.path == "/api/audit":
                return self._json(service.audit())
            if u.path == "/api/log":
                return self._json({"log": "\n".join(LOG)})
            return self._json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self):  # noqa: N802
        u = urlparse(self.path)
        try:
            body = self._body()
            if u.path == "/api/export_icons":
                ok, msg = thumbs.ensure_icons(service.icon_prefixes(body["weapon"]), _dir_vpk())
                return self._json({"ok": ok, "msg": msg, **_weapon_kits_payload(body["weapon"])})
            if u.path == "/api/export_tex":
                tex = body["path"]
                ok, msg = thumbs.ensure_texture(tex, _dir_vpk())
                f = thumbs.png_path(tex)
                rel = os.path.relpath(f, thumbs.CACHE).replace(os.sep, "/")
                return self._json({"ok": ok and os.path.exists(f),
                                   "url": f"/thumbs/{rel}" if os.path.exists(f) else None,
                                   "msg": msg})
            if u.path == "/api/swap":
                res = service.apply_swap(body["weapon"], body["owned"],
                                         body["want"], bool(body.get("force")))
                _push(res)
                return self._json({**res, "patches": service.patches()})
            if u.path == "/api/knife":
                res = service.apply_knife(body["id"], bool(body.get("no_inspect")),
                                          bool(body.get("no_main")))
                _push(res)
                return self._json({**res, "patches": service.patches()})
            if u.path == "/api/revert":
                res = service.revert()
                _push(res)
                return self._json({**res, "patches": service.patches()})
            if u.path == "/api/drop_patch":
                res = service.remove_patch(int(body["index"]))
                _push(res)
                return self._json({**res, "patches": service.patches()})
            return self._json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            return self._json({"ok": False, "log": f"{type(e).__name__}: {e}"}, 500)

    # ------------------------------------------------------------ 工具
    def _body(self) -> dict:
        n = int(self.headers.get("content-length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def _json(self, obj, code: int = 200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path: str):
        if not os.path.isfile(path):
            return self._json({"error": "missing", "path": path}, 404)
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(data)))
        self.send_header("cache-control", "max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):  # 静音默认访问日志
        pass


def _push(res: dict):
    text = res.get("log") or ""
    for line in str(text).rstrip().splitlines():
        LOG.append(line)
    del LOG[:-400]


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    port = 8765
    argv = sys.argv[1:]
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    service.bootstrap()
    httpd = Server(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"[+] CS2 皮肤控制台: {url}")
    print(f"    VRF: {thumbs.vrf_exe() or '未安装 (缩略图降级为色块)'}")
    if "--no-browser" not in argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] 已停止")


if __name__ == "__main__":
    main()
