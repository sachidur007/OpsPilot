"""Render the Day 12 reel frames in the same 9:16 system as Day 7."""

import importlib.util
import json
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRAMES = ROOT / "frames"
HTML = FRAMES / "html"
HTML.mkdir(parents=True, exist_ok=True)
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9336

spec = importlib.util.spec_from_file_location(
    "day7_frames",
    ROOT.parent / "day7-reel" / "render_frames.py",
)
day7 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(day7)
day7.FRAMES = FRAMES

SCENES = {
    "01": day7.page(
        "",
        """
        <p class="kicker">AMAZON APP DEV HACKATHON</p>
        <div class="dayline"><h1 class="mega">DAY 12</h1></div>
        <p class="lede">I made a classic developer mistake.</p>
        """,
    ),
    "02": day7.page(
        "cold",
        """
        <p class="kicker red">THE MISTAKE</p>
        <h1 class="mid">Building features.</h1>
        <p class="caption red">I should have been preparing the demo.</p>
        """,
    ),
    "03": day7.page(
        "mint",
        """
        <p class="kicker">WHAT IS RUNNING</p>
        <div class="check">
          <div><i class="box"></i>Command center</div>
          <div><i class="box"></i>Simulated incidents</div>
          <div><i class="box"></i>Recovery workflow</div>
        </div>
        <p class="caption mint">The product is real.</p>
        """,
    ),
    "04": day7.page(
        "",
        """
        <p class="kicker">THEN I LOOKED</p>
        <p class="quote">What I actually have to submit.</p>
        """,
    ),
    "05": day7.page(
        "cold",
        """
        <p class="kicker red">STILL OPEN</p>
        <div class="card">
          <div class="bar"><span class="dots"><i></i><i></i><i></i></span> THE ENTRY</div>
          <div class="row"><span>Alexa+ skill</span><b>Not built</b></div>
          <div class="row"><span>Latest code</span><b>Not committed</b></div>
        </div>
        <p class="caption red">Two holes.</p>
        """,
    ),
    "06": day7.page(
        "",
        """
        <p class="kicker">THE SUBMISSION</p>
        <div class="card">
          <div class="bar"><span class="dots"><i></i><i></i><i></i></span> NOT IN YET</div>
          <div class="row"><span>README</span><b>Needs work</b></div>
          <div class="row"><span>Demo video</span><b>Not public</b></div>
          <div class="row"><span>Devpost</span><b>Not submitted</b></div>
        </div>
        <p class="caption">A judge cannot see it.</p>
        """,
    ),
    "07": day7.page(
        "cold",
        """
        <p class="kicker red">AMAZON BEDROCK</p>
        <p class="quote">Still blocked.</p>
        <p class="fine">Error 002. The account is still not authorized.<br>Account details stay off this reel.</p>
        """,
    ),
    "08": day7.page(
        "",
        """
        <p class="kicker">THE REALISATION</p>
        <p class="quote">Building a product, and getting it ready for someone else to judge, are two different jobs.</p>
        """,
    ),
    "09": day7.page(
        "mint",
        """
        <p class="kicker">THE NEW ORDER</p>
        <div class="check">
          <div><i class="box"></i>Secure the code</div>
          <div><i class="box"></i>Make the demo repeatable</div>
          <div><i class="box"></i>Finish Alexa+</div>
          <div><i class="box"></i>Submit</div>
        </div>
        <p class="caption mint">No more features just because I can.</p>
        """,
    ),
    "10": day7.page(
        "",
        """
        <p class="kicker">11 DAYS LEFT</p>
        <h1 class="mid">Can I get it ready in time?</h1>
        <p class="fine">The question is no longer whether I can build FleetOps.</p>
        """,
    ),
    "11": day7.page(
        "mint",
        """
        <p class="kicker ice">YOUR TURN</p>
        <p class="quote">What is the one thing you wish you had done earlier?</p>
        <p class="fine">If you have done a hackathon, tell me.</p>
        """,
    ),
}


def main() -> None:
    for name, markup in SCENES.items():
        (HTML / f"{name}.html").write_text(markup)
    proc = subprocess.Popen(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            "--window-size=1440,2560",
            f"--remote-debugging-port={PORT}",
            "--user-data-dir=/tmp/chrome-opspilot-day12",
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
        cdp = day7.Cdp(page_tab["webSocketDebuggerUrl"])
        cdp.call("Page.enable")
        cdp.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1440, "height": 2560, "deviceScaleFactor": 1, "mobile": False},
        )
        for name in SCENES:
            cdp.call("Page.navigate", {"url": (HTML / f"{name}.html").as_uri()})
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
