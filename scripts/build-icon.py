"""Render ui/forge.ico from the desk SVG palette (W12 icon slice)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "ui" / "forge.ico"
SIZES = (256, 128, 64, 48, 32, 16)


def _draw(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(2, size // 16)
    radius = max(4, size // 5)
    draw.rounded_rectangle(
        (pad, pad, size - pad - 1, size - pad - 1),
        radius=radius,
        fill=(22, 17, 12, 255),
    )
    cx = size // 2
    stem_top = pad * 2
    stem_bottom = size * 11 // 32
    stem_w = max(2, size // 20)
    draw.line((cx, stem_top, cx, stem_bottom), fill=(255, 211, 154, 255), width=stem_w)
    dot_r = max(2, size // 12)
    dot_y = size * 7 // 16
    draw.ellipse((cx - dot_r, dot_y - dot_r, cx + dot_r, dot_y + dot_r), fill=(255, 177, 90, 255))
    arc_w = max(2, size // 16)
    draw.arc(
        (size // 5, size * 9 // 20, size * 4 // 5, size * 17 // 20),
        start=15,
        end=165,
        fill=(196, 92, 32, 255),
        width=arc_w,
    )
    return img


def main() -> None:
    frames = [_draw(s) for s in SIZES]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
