"""Cut a 9:16 reel to the Day 7 recording, picture changing with the voice."""

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

ROOT = Path(__file__).resolve().parent
STORY = ROOT / "story"
BUILD = ROOT / "recording"
BUILD.mkdir(parents=True, exist_ok=True)
TALL = STORY / "tall.png"
OGG = Path("/Users/zigcode/Downloads/Day 7.ogg")
OUT = ROOT.parent / "OpsPilot-day7-reel.mp4"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
PORT = 9355
AUDIO_END = 127.706

SHELL = """<!doctype html>
<html><head><meta charset="utf-8"><style>
  * { box-sizing: border-box; }
  html, body { margin: 0; width: 1440px; height: 2560px; overflow: hidden; }
  body {
    color: #f4f1ea;
    font-family: "Avenir Next", "Helvetica Neue", sans-serif;
    background:
      radial-gradient(1000px 700px at 15% 0%, rgba(232,163,23,.18), transparent 55%),
      #090b0e;
  }
  body.shot {
    background: #090b0e center top / 1440px 2560px no-repeat;
  }
  body.shot:before {
    content: "";
    position: absolute; inset: 0;
    background: linear-gradient(180deg, rgba(9,11,14,.25) 0%, rgba(9,11,14,.55) 42%, rgba(9,11,14,.92) 100%);
  }
  .grid {
    position: absolute; inset: 0; pointer-events: none;
    background-image:
      linear-gradient(rgba(255,244,214,.04) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,244,214,.04) 1px, transparent 1px);
    background-size: 72px 72px;
  }
  .stage {
    position: relative; z-index: 1; height: 2560px;
    padding: 220px 100px 320px;
    display: flex; flex-direction: column; justify-content: center;
  }
  body.shot .stage { justify-content: flex-end; padding-bottom: 420px; }
  .kicker { margin: 0 0 18px; letter-spacing: .28em; font-size: 28px; font-weight: 700; color: #e8a317; }
  .kicker.red { color: #ff5a45; }
  h1 { margin: 0; font-size: 108px; line-height: .96; letter-spacing: -.04em; font-weight: 650; }
  h1.mega { font-size: 188px; }
  .lede { margin: 28px 0 0; font-size: 52px; line-height: 1.2; color: #d5ddd4; max-width: 1100px; }
  .rows { margin-top: 36px; display: flex; flex-direction: column; gap: 18px; }
  .row {
    display: flex; gap: 22px; align-items: baseline;
    background: rgba(16,19,24,.9); border: 1px solid rgba(232,220,188,.16);
    border-radius: 22px; padding: 26px 28px;
  }
  .n { color: #e8a317; font-size: 42px; font-weight: 700; width: 48px; }
  .row b { font-size: 44px; font-weight: 620; }
  .quote { margin-top: 12px; font-size: 78px; line-height: 1.08; letter-spacing: -.035em; font-weight: 650; }
  .fine { margin-top: 28px; font-size: 40px; color: #ffb2a8; }
  .term {
    background: #07080a; border-radius: 28px; border: 1px solid rgba(232,220,188,.18); overflow: hidden;
  }
  .term .top { padding: 22px 28px; background: #14181d; color: #8d978e; letter-spacing: .14em; font-size: 26px; }
  .term pre {
    margin: 0; padding: 36px 34px 42px;
    font-family: "IBM Plex Mono", "SF Mono", ui-monospace, monospace;
    font-size: 40px; line-height: 1.4; white-space: pre-wrap; color: #ffb2a8;
  }
  .code {
    margin-top: 28px; align-self: flex-start;
    font-family: "IBM Plex Mono", "SF Mono", ui-monospace, monospace;
    font-size: 64px; color: #3dcb9a;
    background: rgba(61,203,154,.1); border: 1px solid rgba(61,203,154,.4);
    border-radius: 18px; padding: 22px 28px;
  }
  .mark { margin-top: 36px; letter-spacing: .28em; font-size: 24px; color: #8d978e; }
</style></head>
<body class="__CLASS__" style="__STYLE__">
  <div class="grid"></div>
  <div class="stage">__BODY__<div class="mark">OPSPILOT</div></div>
</body></html>
"""


def page(body: str, klass: str = "", style: str = "") -> str:
    return (
        SHELL.replace("__CLASS__", klass)
        .replace("__STYLE__", style)
        .replace("__BODY__", body)
    )


SCENES = {
    "open": page(
        """
        <p class="kicker">AMAZON APP DEV HACKATHON</p>
        <h1 class="mega">Day 7</h1>
        <p class="lede">Building in public.</p>
        """,
        "shot",
        "background-image: linear-gradient(180deg, rgba(9,11,14,.2), rgba(9,11,14,.88)), url('app-top.png')",
    ),
    "three": page(
        """
        <p class="kicker">THE SETUP</p>
        <h1>Three roadblocks.</h1>
        <div class="rows">
          <div class="row"><span class="n">1</span><b>Model access is gone</b></div>
          <div class="row"><span class="n">2</span><b>The old Claude model is gone</b></div>
          <div class="row"><span class="n">3</span><b>The account rejected the request</b></div>
        </div>
        """
    ),
    "access": page(
        """
        <p class="kicker">BEDROCK · US-EAST-1</p>
        <h1>Model access has been retired.</h1>
        <p class="lede">There is no switch left. New accounts send a use case before the first call.</p>
        """
    ),
    "catalog": page(
        """
        <p class="kicker">MODEL CATALOG</p>
        <h1>Claude 3.5 Sonnet is not in the catalog.</h1>
        <p class="lede">The model configuration had to change.</p>
        """
    ),
    "rejected": page(
        """
        <p class="kicker red">THE BIG ONE</p>
        <p class="quote">“Your account is not authorized to perform this action.”</p>
        <p class="fine">Create a support case.</p>
        """,
    ),
    "shell": page(
        """
        <p class="kicker">CLOUDSHELL</p>
        <div class="term">
          <div class="top">N. VIRGINIA</div>
          <pre>Unable to create the environment.
Your account verification is still in progress.
This may take up to two days for new accounts.</pre>
        </div>
        """
    ),
    "clear": page(
        """
        <p class="kicker">WHAT IT ACTUALLY WAS</p>
        <div class="rows">
          <div class="row"><span class="n">—</span><b>Not a code problem</b></div>
          <div class="row"><span class="n">—</span><b>Not an IAM problem</b></div>
          <div class="row"><span class="n">—</span><b>An account verification problem</b></div>
        </div>
        """
    ),
    "source": page(
        """
        <p class="kicker">ONCE IT CLEARS</p>
        <h1>One real incident.</h1>
        <p class="lede">Analyzed through Bedrock. The result has to say</p>
        <div class="code">source: bedrock</div>
        """,
        "shot",
        "background-image: linear-gradient(180deg, rgba(9,11,14,.35), rgba(9,11,14,.9)), url('app-low.png')",
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
            raise RuntimeError("websocket failed")
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
                raise EOFError("closed")
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
        data = self.call("Page.captureScreenshot", {"format": "png"})["data"]
        path = BUILD / name
        path.write_bytes(base64.b64decode(data))
        print("frame", name, path.stat().st_size, flush=True)


def crop_boards() -> None:
    for name, y in (("app-top.png", 0), ("app-low.png", 400)):
        dest = BUILD / name
        subprocess.check_call(
            [
                "ffmpeg", "-y", "-i", str(TALL),
                "-vf", f"crop=1800:3200:0:{y},scale=1440:2560:flags=lanczos",
                str(dest),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("board", name, flush=True)


def render_graphics() -> None:
    html = BUILD / "html"
    html.mkdir(parents=True, exist_ok=True)
    for name in ("app-top.png", "app-low.png"):
        (html / name).write_bytes((BUILD / name).read_bytes())
    for name, markup in SCENES.items():
        (html / f"{name}.html").write_text(markup)
    proc = subprocess.Popen(
        [
            CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--no-first-run", "--window-size=1440,2560",
            f"--remote-debugging-port={PORT}",
            "--user-data-dir=/tmp/chrome-day7-recording",
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
            cdp.call("Page.navigate", {"url": (html / f"{name}.html").as_uri()})
            time.sleep(0.45)
            cdp.shot(f"{name}.png")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def still(image: Path, duration: float, dest: Path, fade_out: bool = False) -> None:
    fade = f",fade=t=out:st={max(0, duration - 0.35):.3f}:d=0.35" if fade_out else ""
    subprocess.check_call(
        [
            "ffmpeg", "-y", "-loop", "1", "-framerate", "30",
            "-t", f"{duration:.3f}", "-i", str(image),
            "-vf", f"scale=1440:2560:flags=lanczos,fps=30,format=yuv420p{fade}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
            "-pix_fmt", "yuv420p", "-an",
            str(dest),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def scroll(duration: float, dest: Path) -> None:
    y_expr = f"trunc((400*t/{duration:.3f})/2)*2"
    script = BUILD / "scroll.filter"
    script.write_text(
        f"[0:v]crop=1800:3200:0:'{y_expr}',scale=1440:2560:flags=lanczos,fps=30,format=yuv420p[v]\n"
    )
    subprocess.check_call(
        [
            "ffmpeg", "-y", "-loop", "1", "-framerate", "30",
            "-t", f"{duration:.3f}", "-i", str(TALL),
            "-filter_complex_script", str(script),
            "-map", "[v]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
            "-pix_fmt", "yuv420p", "-an",
            str(dest),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    crop_boards()
    render_graphics()
    clips = BUILD / "clips"
    clips.mkdir(parents=True, exist_ok=True)
    # Times follow the recording.
    timeline = [
        ("open", "open.png", 6.600, False),
        ("goal", "app-low.png", 6.280, False),
        ("fine", "app-top.png", 7.160, False),
        ("three", "three.png", 5.680, False),
        ("access", "access.png", 11.920, False),
        ("catalog", "catalog.png", 6.200, False),
        ("rejected", "rejected.png", 14.700, False),
        ("shell", "shell.png", 14.140, False),
        ("clear", "clear.png", 7.320, False),
        ("running", "app-top.png", 6.000, False),
        ("scroll", None, 10.000, False),
        ("fallback", "app-low.png", 22.000, False),
        ("source", "source.png", AUDIO_END - 118.000, True),
    ]
    listing = []
    cursor = 0.0
    for name, image, duration, fade_out in timeline:
        dest = clips / f"{name}.mp4"
        if name == "scroll":
            scroll(duration, dest)
        else:
            still(BUILD / image, duration, dest, fade_out=fade_out)
        listing.append(f"file '{dest.as_posix()}'")
        cursor += duration
        print(f"{name:10} {duration:6.2f}s  at {cursor:6.2f}", flush=True)
    (clips / "list.txt").write_text("\n".join(listing) + "\n")
    silent = BUILD / "silent.mp4"
    subprocess.check_call(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(clips / "list.txt"),
            "-c", "copy", str(silent),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.check_call(
        [
            "ffmpeg", "-y", "-i", str(silent), "-i", str(OGG),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy",
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-t", f"{AUDIO_END:.3f}",
            "-movflags", "+faststart",
            str(OUT),
        ]
    )
    print("WROTE", OUT, flush=True)


if __name__ == "__main__":
    main()
