"""Cut the Day 12 reel from frames and the cloned-voice lines."""

import subprocess
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VOICE = ROOT / "voice"
FRAMES = ROOT / "frames"
CLIPS = ROOT / "clips"
CLIPS.mkdir(parents=True, exist_ok=True)
OUT = ROOT.parent / "OpsPilot-day12-reel.mp4"
COUNT = 11

MINIMUM = {
    1: 4.2,
    2: 5.2,
    3: 5.4,
    4: 4.6,
    5: 6.2,
    6: 7.2,
    7: 4.4,
    8: 7.6,
    9: 7.4,
    10: 8.0,
    11: 6.4,
}


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as handle:
        return handle.getnframes() / float(handle.getframerate())


def main() -> None:
    durations = []
    for index in range(1, COUNT + 1):
        audio = wav_seconds(VOICE / f"{index:02d}.wav")
        duration = max(MINIMUM[index], audio + 0.55)
        durations.append(duration)
        clip = CLIPS / f"{index:02d}.mp4"
        fade_out = max(0.2, duration - 0.16)
        video_filter = "scale=1440:2560:flags=lanczos,format=yuv420p,fps=30"
        if index == 1:
            video_filter += ",fade=t=in:st=0:d=0.25"
        if index == COUNT:
            video_filter += f",fade=t=out:st={duration - 0.45:.3f}:d=0.45"
        subprocess.check_call(
            [
                "ffmpeg", "-y",
                "-loop", "1", "-framerate", "30", "-t", f"{duration:.3f}",
                "-i", str(FRAMES / f"{index:02d}.png"),
                "-i", str(VOICE / f"{index:02d}.wav"),
                "-vf", video_filter,
                "-af",
                (
                    "adelay=120:all=1,"
                    f"apad=whole_dur={duration:.3f},"
                    "afade=t=in:st=0:d=0.05,"
                    f"afade=t=out:st={fade_out:.3f}:d=0.12"
                ),
                "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                "-pix_fmt", "yuv420p", "-r", "30",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                "-t", f"{duration:.3f}",
                "-movflags", "+faststart",
                str(clip),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"clip {index:02d} {duration:.2f}s audio {audio:.2f}s", flush=True)

    listing = CLIPS / "list.txt"
    listing.write_text("".join(f"file '{(CLIPS / f'{i:02d}.mp4').as_posix()}'\n" for i in range(1, COUNT + 1)))
    subprocess.check_call(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
            "-c:v", "copy",
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart",
            str(OUT),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print("reel", OUT, f"{sum(durations):.1f}s", flush=True)


if __name__ == "__main__":
    main()
