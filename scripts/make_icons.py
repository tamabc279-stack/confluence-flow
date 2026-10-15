r"""Vẽ PNG icon "Ba dòng chảy hợp lại" theo toạ độ web/icons/logo.svg (khung 120×120) — không cần cairosvg.

Chạy trên máy dev (cần Pillow):  "c:\Claude code\candle-radar\venv\Scripts\python" scripts\make_icons.py
Khuôn: candle-radar/scripts/make_icons.py (vẽ 4× rồi thu nhỏ; maskable phủ nền, hình thu vào vùng an toàn 80 %).
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

BG = (0x0F, 0x1A, 0x2E)
BLUE, PURPLE, GOLD, CREAM = (0x5A, 0xA2, 0xFF), (0xB0, 0x8C, 0xFF), (0xF2, 0xC2, 0x30), (0xFF, 0xF6, 0xD6)
OUT = Path(__file__).resolve().parent.parent / "web" / "icons"


def bezier(p0, p1, p2, p3, n=64):
    pts = []
    for i in range(n + 1):
        t = i / n
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
        pts.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return pts


def draw(size: int, maskable: bool) -> Image.Image:
    S = size * 4
    img = Image.new("RGBA", (S, S), BG + (255,) if maskable else (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if not maskable:
        d.rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 28 / 120), fill=BG)
    k = (S * 0.8 / 120) if maskable else (S / 120)
    off = (S - 120 * k) / 2

    def P(x, y):
        return (off + x * k, off + y * k)

    def stroke(pts, col, w):
        # đóng dấu hình tròn dọc đường (bước ≤ 1/4 bề dày) → nét mịn, đầu tròn; d.line nét dày bị răng cưa ở chỗ nối
        r = w * k / 2
        q = [P(x, y) for x, y in pts]
        for (x0, y0), (x1, y1) in zip(q, q[1:]):
            n = max(1, int(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 / (r / 4)))
            for i in range(n + 1):
                cx, cy = x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n
                d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)

    stroke([(16, 60), (84, 60)], PURPLE, 9)
    stroke(bezier((16, 31), (48, 31), (54, 60), (84, 60)), BLUE, 9)
    stroke(bezier((16, 89), (48, 89), (54, 60), (84, 60)), GOLD, 9)
    # quầng sáng quanh điểm hợp lưu
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    cx, cy = P(90, 60)
    r = 21 * k
    g.ellipse((cx - r, cy - r, cx + r, cy + r), fill=CREAM + (60,))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(5 * k)))
    d = ImageDraw.Draw(img)
    r = 12 * k
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=CREAM)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    draw(192, False).save(OUT / "icon-192.png")
    draw(512, False).save(OUT / "icon-512.png")
    draw(512, True).convert("RGB").save(OUT / "icon-maskable.png")
    print("ghi icon-192.png, icon-512.png, icon-maskable.png ->", OUT)


if __name__ == "__main__":
    main()
