"""Scroll the live board in time with the story."""

import subprocess
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "story"
IMG = ROOT / "tall.png"
A1 = ROOT / "01.wav"
A2 = ROOT / "02.wav"
AUDIO = ROOT / "story.wav"
OUT = Path(__file__).resolve().parent.parent / "OpsPilot-day7-reel.mp4"
GAP = 0.45


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as handle:
        return handle.getnframes() / float(handle.getframerate())


def main() -> None:
    first = wav_seconds(A1)
    second = wav_seconds(A2)
    spoken = first + GAP + second
    total = spoken + 0.7
    arrive = first + GAP
    subprocess.check_call(
        [
            "ffmpeg", "-y",
            "-i", str(A1),
            "-f", "lavfi", "-t", f"{GAP}", "-i", "anullsrc=r=48000:cl=mono",
            "-i", str(A2),
            "-filter_complex",
            (
                "[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=mono[a0];"
                "[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=mono[g];"
                "[2:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=mono[a1];"
                "[a0][g][a1]concat=n=3:v=0:a=1,"
                "loudnorm=I=-14:TP=-1.5:LRA=11,"
                "afade=t=in:st=0:d=0.06,"
                f"afade=t=out:st={spoken - 0.2:.3f}:d=0.2,"
                "apad=whole_dur="
                f"{total:.3f}[a]"
            ),
            "-map", "[a]",
            str(AUDIO),
        ]
    )
    # Stay on the open incidents, then ease down onto the dossier
    # as the voice says this is the backup.
    travel_start = 7.4
    travel_end = arrive
    span = max(0.2, travel_end - travel_start)
    progress = f"((t-{travel_start})/{span:.3f})"
    y_expr = (
        f"if(lt(t,{travel_start}),0,"
        f"if(lt(t,{travel_end:.3f}),"
        f"trunc((400*pow({progress},2)*(3-2*{progress}))/2)*2,"
        "400))"
    )
    script = ROOT / "video.filter"
    script.write_text(
        "[0:v]"
        f"crop=1800:3200:0:'{y_expr}',"
        "scale=1440:2560:flags=lanczos,"
        "fps=30,format=yuv420p,"
        "fade=t=in:st=0:d=0.35,"
        f"fade=t=out:st={total - 0.45:.3f}:d=0.45[v]\n"
    )
    subprocess.check_call(
        [
            "ffmpeg", "-y",
            "-loop", "1", "-framerate", "30", "-i", str(IMG),
            "-i", str(AUDIO),
            "-filter_complex_script", str(script),
            "-map", "[v]", "-map", "1:a",
            "-t", f"{total:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "16",
            "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart",
            str(OUT),
        ]
    )
    print(f"first {first:.2f} arrive {arrive:.2f} total {total:.2f}", OUT, flush=True)


if __name__ == "__main__":
    main()
