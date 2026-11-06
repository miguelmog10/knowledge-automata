"""Record the guide's animation (docs/guide/animation.html) as MP4 videos.

The page draws any moment of the animation from the time alone. This script opens it in
headless Chromium at the exact video size, asks it for each frame in turn (30 per second),
takes a screenshot of each and pipes them to ffmpeg. Every frame is drawn on purpose, so the
video is smooth whatever the speed of the computer.

Needs ffmpeg on the PATH. Install the browser once, then record all four videos
(portrait and square, light and dark) into build/animation/, which git ignores:

    uv run --with playwright==1.63.0 playwright install chromium
    uv run --with playwright==1.63.0 python scripts/record_animation.py

Options: --format portrait|square|all, --theme light|dark|all, --fps, --out-dir.
The videos are release assets, not repository files (see docs/guide/README.md).
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "docs" / "guide" / "animation.html"
SIZES = {"portrait": (1080, 1350), "square": (1080, 1080)}
THEMES = ("light", "dark")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record the guide's animation as MP4 videos.")
    parser.add_argument("--format", choices=[*SIZES, "all"], default="all")
    parser.add_argument("--theme", choices=[*THEMES, "all"], default="all")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--out-dir", type=Path, default=REPO / "build" / "animation")
    return parser.parse_args()


def record(browser, fmt: str, theme: str, fps: int, out: Path) -> None:
    width, height = SIZES[fmt]
    page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
    page.goto(f"{PAGE.as_uri()}?record=1&t=0&theme={theme}&format={fmt}", wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    duration = page.evaluate("window.__duration")
    frames = round(duration * fps) + 1

    ffmpeg = subprocess.Popen(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "image2pipe", "-framerate", str(fps), "-i", "-",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(out),
        ],
        stdin=subprocess.PIPE,
    )  # fmt: skip
    try:
        for i in range(frames):
            page.evaluate(f"window.__seek({i / fps})")
            ffmpeg.stdin.write(page.screenshot(type="png"))
    finally:
        ffmpeg.stdin.close()
        ffmpeg.wait()
        page.close()
    if ffmpeg.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {out.name} (exit code {ffmpeg.returncode})")
    print(f"{out.relative_to(REPO) if out.is_relative_to(REPO) else out}: {frames} frames")


def main() -> int:
    args = parse_args()
    if shutil.which("ffmpeg") is None:
        print("ffmpeg is not on the PATH. Install it, then run this script again.")
        return 1
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError:
        print("Playwright is missing. Run the script with: uv run --with playwright==1.63.0 ...")
        return 1

    formats = list(SIZES) if args.format == "all" else [args.format]
    themes = list(THEMES) if args.theme == "all" else [args.theme]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Error:
            print("Chromium is not installed for Playwright. Run once:")
            print("  uv run --with playwright==1.63.0 playwright install chromium")
            return 1
        try:
            for fmt in formats:
                for theme in themes:
                    out = args.out_dir / f"knowledge-automata-loop-{fmt}-{theme}.mp4"
                    record(browser, fmt, theme, args.fps, out)
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
