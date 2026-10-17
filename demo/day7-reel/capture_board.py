"""Capture the live command center with the fallback badge visible."""

import base64
import hashlib
import json
import os
import socket
import struct
import subprocess
import time
import urllib.request
from pathlib import Path

SHOTS = Path(__file__).resolve().parent / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
PORT = 9341


class Cdp:
    def __init__(self, ws_url: str):
        host_path = ws_url.split("://", 1)[1]
        host, path = host_path.split("/", 1)
        hostname, port = host.split(":")
        self.sock = socket.create_connection((hostname, int(port)))
        key = base64.b64encode(os.urandom(16)).decode()
        handshake = (
            f"GET /{path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(handshake.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        if accept not in buf.decode(errors="ignore"):
            raise RuntimeError(buf.decode(errors="ignore")[:300])
        self.msg_id = 0
        self.buf = b""

    def _readn(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _recv(self):
        while True:
            head = self._readn(2)
            opcode = head[0] & 0x0F
            length = head[1] & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._readn(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._readn(8))[0]
            payload = self._readn(length)
            if opcode == 0x8:
                raise EOFError("socket closed")
            if opcode == 0x9:
                continue
            if opcode == 0x1:
                return json.loads(payload.decode())

    def call(self, method, params=None, timeout=30):
        self.msg_id += 1
        ident = self.msg_id
        self.sock.settimeout(timeout)
        body = json.dumps({"id": ident, "method": method, "params": params or {}}).encode()
        mask = os.urandom(4)
        header = bytearray([0x81])
        n = len(body)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack(">H", n))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack(">Q", n))
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(body))
        self.sock.sendall(bytes(header) + mask + masked)
        while True:
            msg = self._recv()
            if msg.get("id") == ident:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def js(self, expression, timeout=30):
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
            timeout=timeout,
        )
        if result.get("exceptionDetails"):
            raise RuntimeError(result["exceptionDetails"])
        return result["result"].get("value")

    def shot(self, name):
        self.js(
            """document.querySelectorAll('nextjs-portal,.note').forEach(node => node.remove());
            document.querySelectorAll('p,div,span').forEach(node => {
              if ((node.childElementCount === 0) && (node.textContent || '').includes('Hear briefing if the voice')) node.remove();
            });"""
        )
        time.sleep(0.15)
        data = self.call("Page.captureScreenshot", {"format": "png"}, timeout=20)["data"]
        path = SHOTS / name
        path.write_bytes(base64.b64decode(data))
        print("shot", name, path.stat().st_size, flush=True)
        return path

    def wait_js(self, expression, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.js(expression):
                    return
            except Exception:
                pass
            time.sleep(0.25)
        raise TimeoutError(expression)


def main():
    proc = subprocess.Popen(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            f"--window-size=1440,900",
            f"--remote-debugging-port={PORT}",
            "--user-data-dir=/tmp/chrome-opspilot-reel-b",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        tabs = None
        for _ in range(40):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=1) as res:
                    tabs = json.load(res)
                    break
            except Exception:
                time.sleep(0.25)
        if not tabs:
            raise RuntimeError("chrome did not open a debug port")
        page = next(tab for tab in tabs if tab.get("type") == "page")
        cdp = Cdp(page["webSocketDebuggerUrl"])
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                const original = window.fetch.bind(window);
                window.fetch = (url, options) => {
                  if (String(url).includes('/agent/speak')) {
                    return Promise.resolve(new Response(new Uint8Array(), {status: 204}));
                  }
                  return original(url, options);
                };
                """
            },
        )
        cdp.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1440, "height": 900, "deviceScaleFactor": 2, "mobile": False},
        )
        cdp.call("Page.navigate", {"url": "http://localhost:3000/"})
        cdp.wait_js("document.body && document.body.innerText.includes('payment-service')", timeout=25)
        cdp.wait_js("document.body.innerText.includes('Scenario fallback')", timeout=40)
        time.sleep(0.6)
        cdp.shot("board.png")
        box = cdp.js(
            """(() => {
              const node = document.querySelector('.dossier');
              if (!node) return null;
              const rect = node.getBoundingClientRect();
              return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
            })()"""
        )
        print("dossier", box, flush=True)
        (SHOTS / "dossier.json").write_text(json.dumps(box))
        print("CAPTURED", flush=True)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
