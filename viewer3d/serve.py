#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K3B 机械臂 · 三维图本地预览服务

作用：
  1. 把 D:\\BaiduNetdiskDownload\\最新三维图 里的 .stp 文件通过 HTTP 暴露出来
     （浏览器不允许 file:// 页面 fetch 本地文件，必须走 HTTP）
  2. 提供一个 /api/list 接口，自动扫描目录生成清单
  3. 启动后自动打开浏览器

用法：
  python serve.py
  或双击 启动预览.bat

换目录：
  set ARM3D_DIR=D:\\别的\\目录  &&  python serve.py
换端口：
  set ARM3D_PORT=9000  &&  python serve.py
"""

import json
import os
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.environ.get("ARM3D_DIR") or r"D:\BaiduNetdiskDownload\最新三维图"
PORT = int(os.environ.get("ARM3D_PORT", "8777"))
EXTS = (".stp", ".step", ".igs", ".iges", ".brep")

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".wasm": "application/wasm",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".md": "text/markdown; charset=utf-8",
}


def scan_models(root):
    """递归扫描 STEP 文件，返回清单"""
    items = []
    if not os.path.isdir(root):
        return items
    for cur, dirs, files in os.walk(root):
        dirs.sort()
        for fn in sorted(files):
            if not fn.lower().endswith(EXTS):
                continue
            full = os.path.join(cur, fn)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            rel = os.path.relpath(full, root).replace("\\", "/")
            parent = os.path.dirname(rel)
            items.append({
                "path": rel,
                "name": os.path.splitext(fn)[0],
                "ext": os.path.splitext(fn)[1].lower(),
                "folder": parent.replace("/", " / ") if parent else "",
                "size": size,
            })
    # 根目录文件排前面
    items.sort(key=lambda x: (x["folder"] != "", x["folder"], x["name"]))
    return items


class Handler(BaseHTTPRequestHandler):
    server_version = "K3BArm3D/1.0"
    protocol_version = "HTTP/1.1"

    # ---------- 工具 ----------

    def _send_bytes(self, data, mime, cache="no-store", code=200):
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_json(self, obj):
        self._send_bytes(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                         "application/json; charset=utf-8")

    def _safe(self, base, rel):
        """防目录穿越"""
        rel = rel.replace("\\", "/").lstrip("/")
        full = os.path.normpath(os.path.join(base, rel))
        base_n = os.path.normpath(base)
        if not (full == base_n or full.startswith(base_n + os.sep)):
            return None
        return full

    def _send_file(self, full, mime):
        try:
            size = os.path.getsize(full)
            f = open(full, "rb")
        except OSError:
            self._send_bytes(b"404 Not Found", "text/plain; charset=utf-8", code=404)
            return
        with f:
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                while True:
                    chunk = f.read(1024 * 256)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    # ---------- 路由 ----------

    def do_GET(self):
        path = unquote(urlparse(self.path).path)

        if path in ("/", "/index.html"):
            return self._send_file(os.path.join(HERE, "index.html"), MIME[".html"])

        if path == "/api/list":
            ok = os.path.isdir(MODEL_DIR)
            return self._send_json({
                "ok": ok,
                "dir": MODEL_DIR,
                "count": len(scan_models(MODEL_DIR)) if ok else 0,
                "items": scan_models(MODEL_DIR) if ok else [],
            })

        if path.startswith("/files/"):
            full = self._safe(MODEL_DIR, path[len("/files/"):])
            if not full:
                return self._send_bytes(b"403", "text/plain; charset=utf-8", code=403)
            ext = os.path.splitext(full)[1].lower()
            return self._send_file(full, MIME.get(ext, "application/octet-stream"))

        # URDF 包目录（preview.html 与 meshes/ 都从这里取）
        if path.startswith("/k3b_arm_urdf/"):
            urdf_dir = os.path.join(os.path.dirname(HERE), "k3b_arm_urdf")
            full = self._safe(urdf_dir, path[len("/k3b_arm_urdf/"):])
            if not full or not os.path.isfile(full):
                return self._send_bytes(b"404 Not Found", "text/plain; charset=utf-8", code=404)
            ext = os.path.splitext(full)[1].lower()
            return self._send_file(full, MIME.get(ext, "application/octet-stream"))

        # /viewer3d/ 前缀等价于根目录（preview.html 用绝对路径引 three）
        if path.startswith("/viewer3d/"):
            full = self._safe(HERE, path[len("/viewer3d/"):])
            if not full or not os.path.isfile(full):
                return self._send_bytes(b"404 Not Found", "text/plain; charset=utf-8", code=404)
            ext = os.path.splitext(full)[1].lower()
            return self._send_file(full, MIME.get(ext, "application/octet-stream"))

        # 其它静态资源（app.js / vendor/**）
        full = self._safe(HERE, path)
        if not full or not os.path.isfile(full):
            return self._send_bytes(b"404 Not Found", "text/plain; charset=utf-8", code=404)
        ext = os.path.splitext(full)[1].lower()
        return self._send_file(full, MIME.get(ext, "application/octet-stream"))

    def do_HEAD(self):
        """某些预览容器会先发 HEAD 探活"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, fmt, *args):
        # 只报 4xx/5xx，避免刷屏
        try:
            code = int(args[1]) if len(args) > 1 else 200
        except Exception:
            code = 200
        if code >= 400:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def handle_one_request(self):
        # 浏览器关页面时会直接断 TCP，别让它刷一屏 traceback
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            self.close_connection = True

    def log_error(self, fmt, *args):
        pass


def main():
    if not os.path.isdir(MODEL_DIR):
        print("[!] 模型目录不存在：%s" % MODEL_DIR)
        print("    可以用 ARM3D_DIR 环境变量指定其它目录")
        try:
            input("按回车退出…")
        except Exception:
            pass
        return

    count = len(scan_models(MODEL_DIR))
    url = "http://127.0.0.1:%d/" % PORT

    print("=" * 56)
    print(" K3B 机械臂 · 三维图预览")
    print(" 模型目录 : %s" % MODEL_DIR)
    print(" 文件数量 : %d 个 STEP" % count)
    print(" 访问地址 : %s" % url)
    print(" 关闭窗口或 Ctrl+C 结束")
    print("=" * 56)

    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        print("[!] 端口 %d 被占用：%s" % (PORT, e))
        print("    试试：set ARM3D_PORT=9000")
        try:
            input("按回车退出…")
        except Exception:
            pass
        return

    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
