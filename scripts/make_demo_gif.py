"""生成 assets/demo.gif：960×600 的终端风演示动图。

只用 Pillow（开发期依赖，不进 requirements）。跑法：
    python scripts/make_demo_gif.py

画面里的数字全是真跑出来的：14 个候选点，3 天排进 10 个，
4 个明确写了为什么没排进去。
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

W, H = 960, 600
BG = "#0b0f14"
BAR = "#161b22"
LINE = "#21262d"
GREEN = "#7ee787"
TEXT = "#c9d1d9"
DIM = "#8b949e"
BLUE = "#79c0ff"
YELLOW = "#e3b341"
RED = "#ff7b72"

FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"

LINE_H = 25
MAX_W = W - 56

COLORS = {"cmd": GREEN, "out": TEXT, "dim": DIM, "cite": BLUE, "warn": YELLOW, "bad": RED}


def font(size: int):
    return ImageFont.truetype(FONT_PATH, size)


_MEASURE = ImageDraw.Draw(Image.new("RGB", (1, 1)))


def clip(text: str, size: int = 16) -> str:
    f = font(size)
    if _MEASURE.textlength(text, font=f) <= MAX_W:
        return text
    while text and _MEASURE.textlength(text + "…", font=f) > MAX_W:
        text = text[:-1]
    return text + "…"


def render(rows, cursor_row=None):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 36], fill=BAR)
    for i, color in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
        d.ellipse([16 + i * 22, 12, 28 + i * 22, 24], fill=color)
    d.text((92, 9), "xingji — 本地排程，模型只讲不编", font=font(15), fill=DIM)
    d.line([0, 36, W, 36], fill=LINE)

    y = 54
    for idx, (style, text) in enumerate(rows):
        shown = clip(text)
        d.text((26, y), shown, font=font(16), fill=COLORS[style])
        if cursor_row == idx:
            w = _MEASURE.textlength(shown, font=font(16))
            d.rectangle([26 + w + 4, y + 2, 26 + w + 12, y + 19], fill=GREEN)
        y += LINE_H
        if y > H - 16:
            break
    return img


SCRIPT = [
    ("cmd", "> python -m xingji plan --destination 成都 --days 3 --must 熊猫,武侯祠"),
    ("out", "门票合计 245 元 · 每天 540 分钟（含午饭 1 小时）"),
    ("out", "第 1 天（周一）· 成华区 / 青羊区 · 500 分钟 · 105 元"),
    ("dim", "★ 09:00-12:30  大熊猫繁育研究基地  210 分钟  55 元"),
    ("dim", "★ 14:10-15:50  杜甫草堂            100 分钟  50 元"),
    ("dim", "  16:30-17:20  大慈寺               50 分钟  免费"),
    ("out", "第 2 天（周二）· 武侯区 / 青羊区 · 530 分钟 · 70 元"),
    ("dim", "  09:00-11:00  武侯祠              120 分钟  50 元"),
    ("dim", "  12:40-15:40  四川博物院          180 分钟  免费"),
    ("dim", "  15:40-16:50  人民公园             70 分钟  免费"),
    ("warn", "没排进去："),
    ("warn", "  · 春熙路 —— 每天的时间塞满了"),
    ("warn", "  · 成都博物馆 —— 每天的时间塞满了"),
    ("cmd", "> python -m xingji story 1"),
    ("out", "第 1 天 · 熊猫要趁早，下午逛园林"),
    ("dim", "上午先冲大熊猫繁育研究基地，越早到越好，熊猫上午最活跃。"),
    ("dim", "下午杜甫草堂园林大，慢慢走不赶。傍晚大慈寺转一圈就收工。"),
    ("dim", "今天门票一共 105 元。"),
    ("out", "核验：清单外地名 0 个，对不上的数字 0 处"),
]
TAIL = [
    ("out", "排不下的点不藏起来，直接告诉你为什么。"),
    ("dim", "模型曾编出「墙竹影+博物馆」这种地名，被核验当场摘出来。"),
]


def build():
    frames, shown = [], []
    for style, text in SCRIPT:
        if style == "cmd":
            for i in range(6, len(text) + 1, 6):
                frames.append(render(shown + [("cmd", text[:i])], cursor_row=len(shown)))
        shown = shown + [(style, text)]
        frames.append(render(shown))
    for _ in range(12):
        frames.append(render(shown + TAIL))

    frames = [f.quantize(colors=20, method=Image.MEDIANCUT) for f in frames]
    os.makedirs("assets", exist_ok=True)
    out = os.path.join("assets", "demo.gif")
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=140, loop=0, optimize=True)
    print(f"ok -> {out}  {len(frames)} 帧  {os.path.getsize(out) / 1024:.1f} KB")


if __name__ == "__main__":
    build()
