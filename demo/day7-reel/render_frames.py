"""Render 9:16 reel frames at 1440x2560."""

import base64
import shutil
import hashlib
import json
import os
import socket
import struct
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHOTS = ROOT / "shots"
FRAMES = ROOT / "frames"
FRAMES.mkdir(parents=True, exist_ok=True)
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
PORT = 9334

BOARD = SHOTS / "board.png"
DOSSIER = SHOTS / "dossier.png"


def crop_dossier() -> None:
    box = json.loads((SHOTS / "dossier.json").read_text())
    scale = 2
    pad = int(18 * scale)
    left = max(0, int(box["x"] * scale) - pad)
    top = max(0, int(box["y"] * scale) - pad)
    width = int(box["width"] * scale) + pad * 2
    height = int(box["height"] * scale) + pad * 2
    width -= width % 2
    height -= height % 2
    subprocess.check_call(
        [
            "ffmpeg", "-y", "-i", str(BOARD),
            "-vf", f"crop={width}:{height}:{left}:{top}",
            str(DOSSIER),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print("dossier crop", DOSSIER.stat().st_size, flush=True)


SHELL = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { box-sizing: border-box; }
  html, body { margin: 0; width: 1440px; height: 2560px; overflow: hidden; background: #090b0e; }
  body {
    color: #f4f1ea;
    font-family: "Avenir Next", "Helvetica Neue", sans-serif;
    background:
      radial-gradient(980px 640px at 12% -8%, rgba(232,163,23,.20), transparent 58%),
      radial-gradient(820px 520px at 110% 8%, rgba(255,90,69,.10), transparent 52%),
      #090b0e;
  }
  body.cold {
    background:
      radial-gradient(900px 560px at 80% -10%, rgba(255,90,69,.20), transparent 55%),
      #090b0e;
  }
  body.mint {
    background:
      radial-gradient(900px 560px at 10% -8%, rgba(61,203,154,.16), transparent 55%),
      #090b0e;
  }
  .grid {
    position: absolute; inset: 0; pointer-events: none;
    background-image:
      linear-gradient(rgba(255,244,214,.045) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,244,214,.045) 1px, transparent 1px);
    background-size: 72px 72px;
    mask-image: linear-gradient(#000 0%, transparent 76%);
  }
  .stage { position: relative; z-index: 1; height: 2560px; padding: 168px 92px 460px; display: flex; flex-direction: column; }
  .kicker { margin: 0; letter-spacing: .34em; font-size: 28px; font-weight: 700; color: #e8a317; }
  .kicker.ice { color: #9fd4ff; }
  .kicker.red { color: #ff5a45; }
  h1 { margin: 18px 0 0; font-size: 132px; line-height: .9; letter-spacing: -.045em; font-weight: 650; }
  h1.mega { font-size: 210px; }
  h1.mid { font-size: 104px; line-height: .96; }
  .dayline { display: flex; align-items: flex-end; gap: 18px; margin-top: 28px; }
  .slash { font-size: 92px; color: #e8a317; font-weight: 700; letter-spacing: -.04em; line-height: .8; padding-bottom: 18px; }
  .lede { margin: 48px 0 0; font-size: 68px; line-height: 1.12; max-width: 1180px; font-weight: 560; }
  .screen {
    margin-top: 48px; border-radius: 36px; overflow: hidden;
    border: 1px solid rgba(232,220,188,.22);
    box-shadow: 0 30px 80px rgba(0,0,0,.45);
    background: #101318;
  }
  .screen img { display: block; width: 100%; height: auto; }
  .screen.dim img { filter: saturate(.35) brightness(.62); }
  .screen.dossier img { width: 100%; height: 980px; object-fit: cover; object-position: center top; }
  .wash { position: relative; }
  .wash:after { content: ""; position: absolute; inset: 0; background: linear-gradient(180deg, rgba(255,90,69,.08), rgba(255,90,69,.28)); }
  .caption { margin-top: 42px; font-size: 92px; line-height: .98; letter-spacing: -.04em; font-weight: 680; }
  .caption.red { color: #ff5a45; }
  .caption.mint { color: #3dcb9a; }
  .card {
    margin-top: 42px; border-radius: 32px; background: rgba(16,19,24,.92);
    border: 1px solid rgba(232,220,188,.16); padding: 42px 44px 48px;
  }
  .bar { display: flex; align-items: center; gap: 14px; color: #8d978e; font-size: 26px; letter-spacing: .08em; }
  .dots { display: flex; gap: 10px; }
  .dots i { width: 16px; height: 16px; border-radius: 50%; display: block; }
  .dots i:nth-child(1) { background: #ff5a45; }
  .dots i:nth-child(2) { background: #e8a317; }
  .dots i:nth-child(3) { background: #3dcb9a; }
  .card h2 { margin: 36px 0 0; font-size: 72px; line-height: 1.02; letter-spacing: -.03em; }
  .card p { margin: 22px 0 0; font-size: 40px; line-height: 1.35; color: #c9d0c6; }
  .search {
    margin-top: 36px; border: 1px solid rgba(232,220,188,.2); border-radius: 18px;
    padding: 28px 32px; font-size: 40px; color: #f4f1ea;
  }
  .empty { margin-top: 28px; padding: 36px; border-radius: 18px; background: rgba(255,90,69,.08); color: #ffb2a8; font-size: 40px; }
  .row { display: flex; justify-content: space-between; gap: 24px; padding: 26px 0; border-bottom: 1px solid rgba(232,220,188,.12); font-size: 36px; }
  .row b { font-weight: 600; }
  .row span { color: #8d978e; }
  .banner { margin-top: 28px; background: #ff5a45; color: #1a0907; font-weight: 750; font-size: 40px; border-radius: 16px; padding: 22px 26px; }
  .quote { margin-top: 80px; font-size: 92px; line-height: 1.05; letter-spacing: -.04em; font-weight: 680; }
  .fine { margin-top: 36px; font-size: 36px; color: #8d978e; line-height: 1.4; }
  .term { margin-top: 36px; background: #07080a; border-radius: 28px; border: 1px solid rgba(232,220,188,.16); overflow: hidden; }
  .term .top { padding: 22px 28px; background: #14181d; color: #8d978e; font-size: 26px; letter-spacing: .12em; }
  .term pre { margin: 0; padding: 36px 34px 48px; font-family: "IBM Plex Mono", "SF Mono", ui-monospace, monospace; font-size: 34px; line-height: 1.45; white-space: pre-wrap; color: #d7e0d4; }
  .term .prompt { color: #3dcb9a; }
  .term .err { color: #ffb2a8; }
  .steps { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 36px; }
  .steps span { border: 1px solid rgba(232,220,188,.2); border-radius: 999px; padding: 16px 26px; font-size: 32px; color: #f4f1ea; }
  .steps i { color: #e8a317; font-style: normal; align-self: center; font-size: 32px; }
  .pill { margin-top: 28px; align-self: flex-start; background: rgba(232,163,23,.14); color: #ffd27a; border: 1px solid rgba(232,163,23,.45); border-radius: 999px; padding: 18px 28px; font-size: 36px; font-weight: 700; }
  .check { margin-top: 28px; display: flex; flex-direction: column; gap: 22px; }
  .check div { display: flex; align-items: center; gap: 22px; font-size: 52px; letter-spacing: -.03em; }
  .box { width: 42px; height: 42px; border-radius: 10px; border: 3px solid #8d978e; flex: 0 0 auto; }
  .code { margin-top: 18px; font-family: "IBM Plex Mono", "SF Mono", ui-monospace, monospace; font-size: 64px; color: #3dcb9a; background: rgba(61,203,154,.08); border: 1px solid rgba(61,203,154,.35); border-radius: 20px; padding: 28px 32px; }
  .end { margin-top: 48px; font-size: 64px; color: #f4f1ea; }
  .mark { position: absolute; left: 92px; bottom: 250px; letter-spacing: .28em; font-size: 24px; color: #8d978e; }
</style>
</head>
<body class="__TONE__">
  <div class="grid"></div>
  <div class="stage">
    __BODY__
    <div class="mark">OPSPILOT</div>
  </div>
</body>
</html>
"""


def page(tone: str, body: str) -> str:
    return SHELL.replace("__TONE__", tone).replace("__BODY__", body)


SCENES = {
    "01": page(
        "",
        """
        <p class="kicker">AMAZON APP DEV HACKATHON</p>
        <div class="dayline"><h1 class="mega">DAY 7</h1><div class="slash">/20</div></div>
        <p class="lede">I tried to connect FleetOps to Claude.</p>
        """,
    ),
    "02": page(
        "mint",
        """
        <p class="kicker">THE BUILD</p>
        <div class="screen"><img src="board.png" alt=""></div>
        <p class="caption mint">The app works.</p>
        """,
    ),
    "03": page(
        "cold",
        """
        <p class="kicker red">THE ACCOUNT</p>
        <div class="screen dim wash"><img src="board.png" alt=""></div>
        <p class="caption red">AWS doesn't.</p>
        """,
    ),
    "04": page(
        "",
        """
        <p class="kicker">BEDROCK · US-EAST-1</p>
        <div class="card">
          <div class="bar"><span class="dots"><i></i><i></i><i></i></span> MODEL ACCESS</div>
          <h2>Model access page has been retired.</h2>
          <p>Serverless models turn on the first time the account calls them. There is no switch left to flip.</p>
        </div>
        <p class="caption">Model access changed.</p>
        """,
    ),
    "05": page(
        "",
        """
        <p class="kicker">MODEL CATALOG</p>
        <div class="card">
          <div class="bar"><span class="dots"><i></i><i></i><i></i></span> SEARCH</div>
          <div class="search">Claude 3.5 Sonnet</div>
          <div class="empty">No match in the catalog.</div>
          <p>The Sonnet model on the account now is Claude Sonnet 5.</p>
        </div>
        <p class="caption">Old Claude model unavailable.</p>
        """,
    ),
    "06": page(
        "cold",
        """
        <p class="kicker red">ANTHROPIC USE CASE</p>
        <div class="card">
          <div class="bar"><span class="dots"><i></i><i></i><i></i></span> FIRST-TIME FORM</div>
          <div class="row"><span>Company</span><b>Individual developer</b></div>
          <div class="row"><span>Website</span><b>GitHub profile</b></div>
          <div class="row"><span>Users</span><b>Internal demo</b></div>
          <div class="banner">Request rejected</div>
        </div>
        <p class="caption">Use-case request rejected.</p>
        """,
    ),
    "07": page(
        "cold",
        """
        <p class="kicker red">AMAZON BEDROCK</p>
        <p class="quote">“Your account is not authorized to perform this action.”</p>
        <p class="fine">Please create a support case.<br>Account details hidden.</p>
        """,
    ),
    "08": page(
        "",
        """
        <p class="kicker">CLOUDSHELL</p>
        <div class="term">
          <div class="top">CLOUD SHELL · N. VIRGINIA</div>
          <pre><span class="prompt">~ $</span>

<span class="err">Unable to create the environment.
Your account verification is in progress.
This may take up to two days for new accounts.</span></pre>
        </div>
        <p class="caption">Account verification pending.</p>
        """,
    ),
    "09": page(
        "",
        """
        <p class="kicker">COMMANDER</p>
        <div class="screen dossier"><img src="dossier.png" alt=""></div>
        <div class="steps"><span>Incident</span><i>→</i><span>Investigate</span><i>→</i><span>Evidence</span><i>→</i><span>Recommendation</span></div>
        <div class="pill">Current: scenario fallback</div>
        """,
    ),
    "10": page(
        "mint",
        """
        <p class="kicker ice">THE MILESTONE</p>
        <h1 class="mid">Next.</h1>
        <div class="check">
          <div><i class="box"></i>AWS verification</div>
          <div><i class="box"></i>Bedrock access</div>
          <div><i class="box"></i>Real Claude analysis</div>
        </div>
        <div class="code">source: bedrock</div>
        <p class="end">The build continues.</p>
        """,
    ),
}


class Cdp:
    def __init__(self, ws_url: str):
        host_path = ws_url.split("://", 1)[1]
        host, path = host_path.split("/", 1)
        hostname, port = host.split(":")
        self.sock = socket.create_connection((hostname, int(port)))
        key = base64.b64encode(os.urandom(16)).decode()
        handshake = (
            f"GET /{path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(handshake.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        if accept not in buf.decode(errors="ignore"):
            raise RuntimeError(buf.decode(errors="ignore")[:240])
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

    def shot(self, name: str) -> None:
        data = self.call("Page.captureScreenshot", {"format": "png"}, timeout=20)["data"]
        path = FRAMES / name
        path.write_bytes(base64.b64decode(data))
        print("frame", name, path.stat().st_size, flush=True)


def main() -> None:
    crop_dossier()
    html_dir = FRAMES / "html"
    html_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(BOARD, html_dir / "board.png")
    shutil.copy(DOSSIER, html_dir / "dossier.png")
    for name, markup in SCENES.items():
        (html_dir / f"{name}.html").write_text(markup)
    proc = subprocess.Popen(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            "--window-size=1440,2560",
            f"--remote-debugging-port={PORT}",
            "--user-data-dir=/tmp/chrome-opspilot-reel-frames",
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
            raise RuntimeError("chrome did not open")
        page_tab = next(tab for tab in tabs if tab.get("type") == "page")
        cdp = Cdp(page_tab["webSocketDebuggerUrl"])
        cdp.call("Page.enable")
        cdp.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1440, "height": 2560, "deviceScaleFactor": 1, "mobile": False},
        )
        for name in SCENES:
            url = (html_dir / f"{name}.html").as_uri()
            cdp.call("Page.navigate", {"url": url})
            time.sleep(0.45)
            cdp.shot(f"{name}.png")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
