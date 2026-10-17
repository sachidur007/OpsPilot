"""Cut the Day 7 reel from frames and the cloned-voice lines."""

import subprocess
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VOICE = ROOT / "voice"
FRAMES = ROOT / "frames"
CLIPS = ROOT / "clips"
CLIPS.mkdir(parents=True, exist_ok=True)
OUT = ROOT.parent / "OpsPilot-day7-reel.mp4"

# Hold a frame long enough to read when the line is short.
MINIMUM = {
    1: 4.0,
    2: 3.2,
    3: 3.2,
    4: 3.6,
    5: 3.6,
    6: 3.8,
    7: 7.0,
    8: 6.5,
    9: 9.4,
    10: 11.2,
}


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as handle:
        return handle.getnframes() / float(handle.getframerate())


def main() -> None:
    durations = []
    for index in range(1, 11):
        audio = wav_seconds(VOICE / f"{index:02d}.wav")
        duration = max(MINIMUM[index], audio + 0.45)
        durations.append(duration)
        clip = CLIPS / f"{index:02d}.mp4"
        fade_out = max(0.2, duration - 0.12)
        video_filter = "scale=1440:2560:flags=lanczos,format=yuv420p,fps=30"
        if index == 1:
            video_filter += ",fade=t=in:st=0:d=0.25"
        if index == 10:
            video_filter += f",fade=t=out:st={duration - 0.4:.3f}:d=0.4"
        subprocess.check_call(
            [
                "ffmpeg", "-y",
                "-loop", "1", "-framerate", "30", "-t", f"{duration:.3f}",
                "-i", str(FRAMES / f"{index:02d}.png"),
                "-i", str(VOICE / f"{index:02d}.wav"),
                "-vf", video_filter,
                "-af",
                (
                    "adelay=80:all=1,"
                    f"apad=whole_dur={duration:.3f},"
                    "afade=t=in:st=0:d=0.04,"
                    f"afade=t=out:st={fade_out:.3f}:d=0.1"
                ),
                "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                "-pix_fmt", "yuv420p", "-r", "30",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                "-t", f"{duration:.3f}",
                "-movflags", "+faststart",
                str(clip),
            ]
        )
        print(f"clip {index:02d} {duration:.2f}s audio {audio:.2f}s", flush=True)

    listing = CLIPS / "list.txt"
    listing.write_text("".join(f"file '{(CLIPS / f'{i:02d}.mp4').as_posix()}'\n" for i in range(1, 11)))
    subprocess.check_call(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
            "-c:v", "copy",
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart",
            str(OUT),
        ]
    )
    print("TOTAL", round(sum(durations), 2), OUT, flush=True)


if __name__ == "__main__":
    main()
