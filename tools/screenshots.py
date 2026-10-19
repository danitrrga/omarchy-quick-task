#!/usr/bin/env python3
"""Regenerate docs/screenshots/*.png from made-up data, on workspace 5.

  python3 tools/screenshots.py            # needs the plugin deployed and enabled

The README images must never show a real account, so for the duration of the run the cached account
(~/.cache/quick-task/account.json) is swapped for an invented one and restored byte for byte at the end,
even if a shot fails. The overlay is driven through its IPC target, the same functions a key press calls.
It is photographed over workspace 5 (empty, so the wallpaper is the background), then the workspace you
were on is restored. The card is found by its background colour: the overlay dims the whole screen, so
"what changed" is everything.

Needs: grim, hyprctl, omarchy-shell on PATH with OMARCHY_PATH set, python3 with Pillow.
"""
import json
import os
import subprocess
import sys
import time
import tempfile
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "helper"))
from quick_task.account import cache_path  # noqa: E402

PLUGIN = "io.github.danitrrga.quick-task"
WORKSPACE = "5"
OUT = ROOT / "docs" / "screenshots"
PAD = 70  # logical pixels of wallpaper kept around the card

DEMO = {
    "premium": False,
    "projects": [
        {"id": "p1", "name": "Inbox", "shared": False, "inbox": True},
        {"id": "p2", "name": "Home", "shared": False, "inbox": False},
        {"id": "p3", "name": "Work", "shared": False, "inbox": False},
        {"id": "p4", "name": "Reading", "shared": False, "inbox": False},
        {"id": "p5", "name": "Side project", "shared": False, "inbox": False},
    ],
    "sections": [
        {"id": "s1", "project_id": "p2", "name": "Errands"},
        {"id": "s2", "project_id": "p2", "name": "Chores"},
        {"id": "s3", "project_id": "p3", "name": "Planning"},
        {"id": "s4", "project_id": "p3", "name": "Admin"},
        {"id": "s5", "project_id": "p4", "name": "Queue"},
    ],
    "labels": [{"name": "email"}, {"name": "waiting"}, {"name": "deep-work"}],
    "collaborators": {},
}

# (file, what is typed, key presses after it)
SHOTS = [
    ("empty", "", []),
    ("picker", "Buy paint saturday #", ["down"]),
    ("ready", "Call Marta tomorrow 9am #Work /Planning @waiting p2", []),
    ("spanish", "Entregar propuesta el lunes a las 9 #Work /Admin p1", []),
]


def sh(*cmd, check=True):
    done = subprocess.run(cmd, capture_output=True, text=True)
    if check and done.returncode != 0:
        sys.exit(f"{cmd[0]} failed: {(done.stderr or done.stdout).strip()}")
    return done.stdout.strip()


def ipc(*words):
    return sh("omarchy-shell", PLUGIN, *words, check=False)


def workspace(name):
    sh("hyprctl", "dispatch", f'hl.dsp.focus({{ workspace = "{name}" }})')
    time.sleep(1.0)


def card_box(image, background, tolerance=6):
    """Bounding box of the largest block of pixels equal to the card's background colour."""
    r, g, b = background
    mask = Image.merge("RGB", image.split()).point(lambda v: v)  # copy
    channels = [ch.point(lambda v, c=c: 255 if abs(v - c) <= tolerance else 0) for ch, c in zip(image.split(), (r, g, b))]
    mask = ImageChops.multiply(ImageChops.multiply(channels[0], channels[1]), channels[2])
    cell = 8
    small = mask.resize((mask.width // cell, mask.height // cell), Image.BOX).point(lambda v: 255 if v > 200 else 0)
    w, h = small.size
    pixels = small.load()
    seen = [[False] * w for _ in range(h)]
    best = None
    for y0 in range(h):
        for x0 in range(w):
            if pixels[x0, y0] == 0 or seen[y0][x0]:
                continue
            stack, xs, ys = [(x0, y0)], [], []
            seen[y0][x0] = True
            while stack:
                x, y = stack.pop()
                xs.append(x), ys.append(y)
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny][nx] and pixels[nx, ny]:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if best is None or len(xs) > best[0]:
                best = (len(xs), min(xs) * cell, min(ys) * cell, (max(xs) + 1) * cell, (max(ys) + 1) * cell)
    return None if best is None else best[1:]


def theme_background():
    name = sh("omarchy", "theme", "current").strip().lower().replace(" ", "-")
    for base in (Path.home() / ".config/omarchy/themes", Path("/usr/share/omarchy/themes")):
        colors = base / name / "colors.toml"
        if colors.is_file():
            for line in colors.read_text().splitlines():
                if line.strip().startswith("background") and "=" in line and "_" not in line.split("=")[0]:
                    hexa = line.split("=")[1].strip().strip('"').lstrip("#")
                    return tuple(int(hexa[i:i + 2], 16) for i in (0, 2, 4))
    sys.exit("could not read the theme background")


def main():
    cache = cache_path()
    saved = cache.read_bytes() if cache.exists() else None
    original = json.loads(sh("hyprctl", "activeworkspace", "-j"))["id"]
    monitor = json.loads(sh("hyprctl", "monitors", "-j"))[0]
    scale = monitor.get("scale", 1) or 1
    background = theme_background()
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="quick-task-shots-"))
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        # fetched_at far in the future so the overlay never decides the demo is stale and re-syncs the real account
        cache.write_text(json.dumps({"fetched_at": time.time() + 3600, **DEMO}))
        workspace(WORKSPACE)
        for name, text, keys in SHOTS:
            ipc("close")
            time.sleep(0.5)
            ipc("open")
            time.sleep(1.6)
            if text:
                ipc("type", text)
            time.sleep(1.2)
            for key in keys:
                ipc("key", key)
                time.sleep(0.3)
            time.sleep(0.8)
            full = tmp / f"{name}.png"
            sh("grim", str(full))
            ipc("close")
            image = Image.open(full).convert("RGB")
            box = card_box(image, background)
            if not box:
                sys.exit(f"{name}: could not find the card (is the plugin enabled?)")
            pad = round(PAD * scale)
            box = (max(0, box[0] - pad), max(0, box[1] - pad), min(image.width, box[2] + pad), min(image.height, box[3] + pad))
            image.crop(box).save(OUT / f"{name}.png")
            print(f"{name}: {box[2] - box[0]}x{box[3] - box[1]} px -> docs/screenshots/{name}.png")
    finally:
        ipc("close")
        if saved is None:
            cache.unlink(missing_ok=True)
        else:
            cache.write_bytes(saved)
            os.chmod(cache, 0o600)
        workspace(str(original))


if __name__ == "__main__":
    main()
