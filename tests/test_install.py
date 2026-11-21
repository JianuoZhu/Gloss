"""模型下载器：用本地 HTTP 服务器测，不联网。"""

from __future__ import annotations

import hashlib
import io
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from gloss import local_mt
from gloss.local_mt import Asset

MODEL = b"fake model weights " * 5000
ZIP = io.BytesIO()
with zipfile.ZipFile(ZIP, "w") as z:
    z.writestr("llama-server.exe", b"MZ fake")
    z.writestr("ggml.dll", b"dll")
FILES = {"/model.bin": MODEL, "/runtime.zip": ZIP.getvalue()}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        data = FILES.get(self.path)
        if data is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def base():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_install_downloads_verifies_and_unzips(base, tmp_path, monkeypatch):
    assets = [
        Asset(f"{base}/runtime.zip", tmp_path / "dl" / "runtime.zip", len(FILES["/runtime.zip"]),
              hashlib.sha256(FILES["/runtime.zip"]).hexdigest(), tmp_path / "llama"),
        Asset(f"{base}/model.bin", tmp_path / "models" / "model.bin", len(MODEL), hashlib.sha256(MODEL).hexdigest()),
    ]
    monkeypatch.setitem(local_mt.ASSETS, "test", assets)
    seen = []
    local_mt.install("test", lambda p, name: seen.append((p, name)))
    assert (tmp_path / "models" / "model.bin").read_bytes() == MODEL
    assert (tmp_path / "llama" / "llama-server.exe").exists() and (tmp_path / "llama" / "ggml.dll").exists()
    assert seen[-1] == (1.0, "") and any(name == "model.bin" for _, name in seen)
    assert local_mt.download_size("test") == 0  # 都在了，不用再下

    seen.clear()
    local_mt.install("test", lambda p, name: seen.append((p, name)))  # 再装一次不会重复下载
    assert seen == [(1.0, "")]


def test_install_rejects_corrupt_download(base, tmp_path, monkeypatch):
    monkeypatch.setitem(local_mt.ASSETS, "test", [Asset(f"{base}/model.bin", tmp_path / "model.bin", len(MODEL), "0" * 64)])
    with pytest.raises(RuntimeError, match="校验失败"):
        local_mt.install("test")
    assert not (tmp_path / "model.bin").exists() and not (tmp_path / "model.bin.part").exists()


def test_install_reports_missing_file(base, tmp_path, monkeypatch):
    monkeypatch.setitem(local_mt.ASSETS, "test", [Asset(f"{base}/nope.bin", tmp_path / "nope.bin", 10)])
    with pytest.raises(RuntimeError, match="下载 nope.bin 失败"):
        local_mt.install("test")
