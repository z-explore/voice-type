"""Cloud hook is off by default; when enabled it posts multipart wav to an OpenAI-compatible URL."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np

from voice_type.asr import CloudWhisper
from voice_type.config import load_config


def test_cloud_disabled_by_default(tmp_path):
    cfg = load_config(tmp_path / "missing.toml")
    assert cfg["cloud"]["enabled"] is False and cfg["asr"]["engine"] == "local"


def test_cloud_request_format(monkeypatch):
    seen = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            seen.update(path=self.path, auth=self.headers["Authorization"], body=body)
            out = json.dumps({"text": "你好"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    monkeypatch.setenv("VT_TEST_KEY", "sk-test")
    c = CloudWhisper(f"http://127.0.0.1:{srv.server_port}/v1", "whisper-x", "VT_TEST_KEY", "zh", 5)
    assert c.transcribe(np.zeros(1600, np.float32), 16000) == "你好"
    assert seen["path"] == "/v1/audio/transcriptions"
    assert seen["auth"] == "Bearer sk-test"
    assert b'name="model"\r\n\r\nwhisper-x' in seen["body"] and b"RIFF" in seen["body"]
