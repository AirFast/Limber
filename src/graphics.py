"""Палітра й малювання через Pillow: іконки, кільце прогресу, склянки, тарілки, кружечки.
Tk не згладжує фігури, тож усе малюємо у збільшеному масштабі й зменшуємо (smooth_image)."""

import math
import os

from PIL import Image, ImageDraw, ImageTk

from core import DATA_DIR, ICON_PATH


C = {
    # Весняна зелень під іконку-листок; темне тло — з легким зеленим відтінком, вода — синя
    "bg": "#14261c",
    "card": "#1a3124",
    "panel": "#1f3a2b",
    "panel_hover": "#2a4d39",
    "track": "#2c4d38",
    "grid": "#1f3a2b",
    "accent": "#8fd477",
    "accent_dark": "#4fae5f",
    "on_accent": "#10301a",
    "text": "#eef7ec",
    "muted": "#a6c4a8",
    "dim": "#5f7b65",
    "water": "#4aa3df",
    "on_water": "#0b2233",
    "meal": "#f2a65a",       # їжа — теплий бурштиновий, щоб не плутати з водою й перервами
    "on_meal": "#2e1803",
}


SUPERSAMPLE = 4


def rgba(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5)) + (255,)


def smooth_image(width, height, paint, bg=None):
    """Малює у збільшеному масштабі й зменшує — Tk сам згладжування не вміє."""
    s = SUPERSAMPLE
    img = Image.new("RGBA", (width * s, height * s), rgba(bg) if bg else (0, 0, 0, 0))
    paint(ImageDraw.Draw(img), s)
    return img.resize((width, height), Image.LANCZOS)


def draw_progress_ring(d, s, size, pad, thickness, fraction, track, color):
    """Кільце прогресу із заокругленими кінцями дуги (координати — у масштабі s)."""
    box = (pad * s, pad * s, (size - pad) * s, (size - pad) * s)
    d.ellipse(box, outline=track, width=thickness * s)
    fraction = min(max(fraction, 0), 1)
    if fraction <= 0.002:
        return
    end = -90 + 360 * fraction
    d.arc(box, start=-90, end=end, fill=color, width=thickness * s)
    center = size * s / 2
    radius = (size / 2 - pad - thickness / 2) * s
    cap = thickness * s / 2
    for angle in (-90, end):
        x = center + radius * math.cos(math.radians(angle))
        y = center + radius * math.sin(math.radians(angle))
        d.ellipse((x - cap, y - cap, x + cap, y + cap), fill=color)


def make_icon(progress, paused):
    """Кільце, що заповнюється в міру наближення перерви."""
    color = rgba(C["dim"]) if paused else rgba(C["accent"])

    def paint(d, s):
        draw_progress_ring(d, s, 64, 4, 9, 0 if paused else progress, rgba(C["track"]), color)
        if paused:
            d.rounded_rectangle((21 * s, 20 * s, 28 * s, 44 * s), radius=2 * s, fill=color)
            d.rounded_rectangle((36 * s, 20 * s, 43 * s, 44 * s), radius=2 * s, fill=color)
        else:
            d.ellipse((24 * s, 24 * s, 40 * s, 40 * s), fill=color)

    return smooth_image(64, 64, paint)


def _vertical_gradient(width, height, top, bottom):
    image = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        frac = y / max(height - 1, 1)
        draw.line([(0, y), (width, y)], fill=tuple(int(a + (b - a) * frac) for a, b in zip(top, bottom)) + (255,))
    return image


class _Leaf:
    """Геометрія листка вздовж осі base→tip: контур, хвиляста центральна жилка, точки на ній."""

    def __init__(self, base, tip, width):
        self.base, self.tip, self.width = base, tip, width
        dx, dy = tip[0] - base[0], tip[1] - base[1]
        self.length = math.hypot(dx, dy)
        self.ux, self.uy = dx / self.length, dy / self.length
        self.nx, self.ny = -self.uy, self.ux

    def half_width(self, t):
        return self.width * (math.sin(math.pi * t) ** 0.95) * (1 - 0.12 * t)

    def at(self, t, offset=0.0):
        return (self.base[0] + self.ux * self.length * t + self.nx * offset,
                self.base[1] + self.uy * self.length * t + self.ny * offset)

    def outline(self, steps=90):
        upper = [self.at(i / steps, self.half_width(i / steps)) for i in range(steps + 1)]
        lower = [self.at(i / steps, -self.half_width(i / steps)) for i in range(steps + 1)]
        return upper + lower[::-1]

    def wave(self, t, amplitude, start=0.06, end=0.86, waves=1.6):
        s = (t - start) / (end - start)
        return amplitude * math.sin(2 * math.pi * waves * s) * math.sin(math.pi * s)

    def vein(self, amplitude, start=0.06, end=0.86, steps=60):
        return [self.at(t, self.wave(t, amplitude, start, end))
                for t in (start + (end - start) * i / steps for i in range(steps + 1))]


def make_app_icon(size=256):
    """Іконка Rhythmos: листок (здоров'я) з хвилястою жилкою (ритм) на весняному градієнті.
    Дрібні деталі — бокові жилки, тінь, відблиск — лише у великих розмірах: у 16–32 px вони б розмилися."""
    from PIL import ImageFilter
    detailed = size >= 48
    big = size * SUPERSAMPLE
    u = big / 256

    background = _vertical_gradient(big, big, (0xb6, 0xec, 0x88), (0x3a, 0xa8, 0x64))
    if detailed:  # м'який відблиск угорі ліворуч
        glow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse((-60 * u, -90 * u, 150 * u, 90 * u), fill=(255, 255, 255, 42))
        background.alpha_composite(glow.filter(ImageFilter.GaussianBlur(28 * u)))
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((10 * u, 10 * u, big - 10 * u, big - 10 * u), radius=58 * u, fill=255)
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    img.paste(background, (0, 0), mask)

    leaf = _Leaf((76 * u, 184 * u), (198 * u, 62 * u), 58 * u)
    outline = leaf.outline()
    if detailed:  # тінь під листком
        shadow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).polygon([(x + 5 * u, y + 9 * u) for x, y in outline], fill=(18, 88, 48, 120))
        img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(9 * u)))

    leaf_mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(leaf_mask).polygon(outline, fill=255)
    img.paste(_vertical_gradient(big, big, (0xff, 0xff, 0xff), (0xdf, 0xf4, 0xd2)), (0, 0), leaf_mask)

    d = ImageDraw.Draw(img)
    white = (255, 255, 255, 255)
    # черешок — плавно вигнутий
    stem = [leaf.at(0.02), (leaf.base[0] - 10 * u, leaf.base[1] + 14 * u), (leaf.base[0] - 22 * u, leaf.base[1] + 22 * u)]
    stem_width = 10 * u if detailed else 13 * u
    d.line(stem, fill=white, width=int(stem_width), joint="curve")
    r = stem_width / 2
    d.ellipse((stem[-1][0] - r, stem[-1][1] - r, stem[-1][0] + r, stem[-1][1] + r), fill=white)

    vein_color = (0x5f, 0xbd, 0x67, 255)
    amplitude = 9 * u
    if detailed:  # бокові жилки від хвилястої центральної до країв, трохи вигнуті до кінчика
        side = (0xb0, 0xe0, 0x9f, 255)
        for pos in (0.26, 0.46, 0.64):
            start = leaf.at(pos, leaf.wave(pos, amplitude))
            for sign in (1, -1):
                reach = leaf.half_width(pos + 0.15) * 0.68
                points = [start, leaf.at(pos + 0.05, sign * reach * 0.42), leaf.at(pos + 0.11, sign * reach * 0.78),
                          leaf.at(pos + 0.16, sign * reach)]
                d.line(points, fill=side, width=int(2.6 * u), joint="curve")
    d.line(leaf.vein(amplitude), fill=vein_color, width=int((7 if detailed else 11) * u), joint="curve")
    return img.resize((size, size), Image.LANCZOS)


def ensure_icon_file():
    """.ico для панелі завдань і ярликів."""
    if not os.path.exists(ICON_PATH):
        os.makedirs(DATA_DIR, exist_ok=True)
        make_app_icon(256).save(ICON_PATH, sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40),
                                                  (48, 48), (64, 64), (128, 128), (256, 256)])
    return ICON_PATH


_glass_cache = {}
MAX_GLASSES_SHOWN = 24    # більше склянок не малюємо (три ряди)
GLASSES_PER_ROW = 8       # далі склянки переносяться в наступний ряд


def blend(color, other, amount):
    """Змішування двох кольорів #rrggbb: amount = 0 → color, 1 → other."""
    a = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def glass_picture(width, height, filled, bg):
    """Абстрактна склянка з рідиною: хвиляста поверхня й відблиск на гребені.
    filled: True — випита (синя вода й синій контур), False — ще ні (сіра рідина й контур);
    при наведенні — що зробить клік: "add" — додасться (синій контур, бліда вода),
    "remove" — зніметься (сірий контур, ледь помітна вода)."""
    if filled == "add":
        edge, liquid, shine = lighten(C["water"], 0.35), blend(C["water"], bg, 0.6), blend(C["water"], bg, 0.3)
    elif filled == "remove":
        edge, liquid, shine = C["dim"], blend(C["water"], bg, 0.7), blend(C["water"], bg, 0.5)
    elif filled:
        edge, liquid, shine = lighten(C["water"], 0.35), C["water"], lighten(C["water"], 0.6)
    else:
        edge, liquid, shine = C["dim"], blend(C["dim"], bg, 0.55), blend(C["dim"], bg, 0.15)

    def paint(d, s):
        w, h = width * s, height * s
        stroke = max(1.5, width * 0.09) * s
        top, bottom = 0.1 * h, h - stroke / 2 - 0.5 * s
        left_top, right_top = stroke / 2 + 0.5 * s, w - stroke / 2 - 0.5 * s
        left_bottom, right_bottom = 0.2 * w, 0.8 * w

        def wall(y, x_top, x_bottom):
            return x_top + (x_bottom - x_top) * (y - top) / (bottom - top)

        # Поверхня рідини — синусоїда трохи більш ніж на півтора періоди
        level = top + (bottom - top) * 0.3
        amplitude = h * 0.045
        inset = stroke * 0.55
        x0, x1 = wall(level, left_top, left_bottom) + inset, wall(level, right_top, right_bottom) - inset
        steps = 28
        surface = [(x0 + (x1 - x0) * i / steps,
                    level + amplitude * math.sin(2 * math.pi * 1.6 * i / steps + 0.4)) for i in range(steps + 1)]
        d.polygon(surface + [(right_bottom - inset, bottom - inset), (left_bottom + inset, bottom - inset)],
                  fill=rgba(liquid))
        d.line(surface, fill=rgba(shine), width=max(1, int(stroke * 0.7)), joint="curve")

        d.line([(left_top, top), (left_bottom, bottom), (right_bottom, bottom), (right_top, top)],
               fill=rgba(edge), width=int(stroke), joint="curve")
        r = stroke / 2
        for x in (left_top, right_top):  # заокруглені верхні краї
            d.ellipse((x - r, top - r, x + r, top + r), fill=rgba(edge))

    return smooth_image(width, height, paint, bg)


_dot_cache = {}
_plate_cache = {}

# Стан їжі (Scheduler.meal_state) → як малювати тарілку у віконці їжі
PLATE_STATES = {"eat": "done", "skip": "skip", "missed": "skip", "upcoming": "later", "snoozed": "later",
                "eating": "now", "open": "now", "due": "now"}


def plate_picture(size, state, bg):
    """Тарілка згори (два кола). "done" — з'їдено (заповнена), "now" — час їсти (яскравий контур),
    "later" — ще буде (сірий контур), "skip" — пропущено (сірий контур, перекреслено);
    при наведенні на «Стані»: "add" — клік позначить з'їденою (бліда заливка), "remove" — зніме позначку."""
    meal = C["meal"]

    def paint(d, s):
        w = size * s
        stroke = max(1.5, size * 0.07) * s
        pad = stroke / 2 + 0.5 * s
        outer = (pad, pad, w - pad, w - pad)
        inset = size * 0.24 * s
        inner = (inset, inset, w - inset, w - inset)
        if state == "done":
            d.ellipse(outer, fill=rgba(meal))
            d.ellipse(inner, outline=rgba(lighten(meal, 0.45)), width=int(stroke))
        elif state == "add":
            d.ellipse(outer, fill=rgba(blend(meal, bg, 0.55)), outline=rgba(lighten(meal, 0.3)), width=int(stroke))
            d.ellipse(inner, outline=rgba(blend(meal, bg, 0.2)), width=int(stroke * 0.8))
        elif state == "remove":
            d.ellipse(outer, fill=rgba(blend(meal, bg, 0.75)), outline=rgba(C["dim"]), width=int(stroke))
            d.ellipse(inner, outline=rgba(blend(meal, bg, 0.5)), width=int(stroke * 0.8))
        elif state == "now":
            d.ellipse(outer, fill=rgba(blend(meal, bg, 0.78)), outline=rgba(meal), width=int(stroke))
            d.ellipse(inner, outline=rgba(blend(meal, bg, 0.4)), width=int(stroke * 0.8))
        else:
            d.ellipse(outer, outline=rgba(C["dim"]), width=int(stroke))
            d.ellipse(inner, outline=rgba(blend(C["dim"], bg, 0.5)), width=int(stroke * 0.8))
            if state == "skip":
                d.line((w * 0.24, w * 0.76, w * 0.76, w * 0.24), fill=rgba(C["dim"]), width=int(stroke))

    return smooth_image(size, size, paint, bg)


def plate_image(size, state, bg):
    key = (size, state, bg)
    if key not in _plate_cache:
        _plate_cache[key] = ImageTk.PhotoImage(plate_picture(size, state, bg))
    return _plate_cache[key]


def dot_image(size, color, filled, bg):
    """Згладжений кружечок для canvas (create_oval у Tk — з «драбинкою» по краю):
    заповнений або кільце завтовшки ~1,6 px."""
    key = (size, color, filled, bg)
    if key not in _dot_cache:
        def paint(d, s):
            d.ellipse((0.5 * s, 0.5 * s, (size - 0.5) * s, (size - 0.5) * s), fill=rgba(color))
            if not filled:
                ring = 1.6 * s
                d.ellipse((0.5 * s + ring, 0.5 * s + ring, (size - 0.5) * s - ring, (size - 0.5) * s - ring),
                          fill=rgba(bg))

        _dot_cache[key] = ImageTk.PhotoImage(smooth_image(size, size, paint, bg))
    return _dot_cache[key]


def glass_image(width, height, filled, bg):
    key = (width, height, filled, bg)
    if key not in _glass_cache:
        _glass_cache[key] = ImageTk.PhotoImage(glass_picture(width, height, filled, bg))
    return _glass_cache[key]


def check_mark(size, color):
    """Згладжена галочка на прозорому тлі."""
    def paint(d, s):
        width = max(2.0, size * 0.15) * s
        points = [(0.16 * size * s, 0.54 * size * s), (0.40 * size * s, 0.76 * size * s),
                  (0.84 * size * s, 0.26 * size * s)]
        d.line(points, fill=rgba(color), width=int(width), joint="curve")
        r = width / 2
        for x, y in (points[0], points[-1]):
            d.ellipse((x - r, y - r, x + r, y + r), fill=rgba(color))

    return ImageTk.PhotoImage(smooth_image(size, size, paint))


def lighten(color, amount=0.14):
    """Колір, світліший на amount — для стану наведення будь-якої кнопки.
    (Раніше всім кнопкам задавався той самий темний колір наведення, і на бірюзовій
    «Перерва зараз» темний текст ставав нерозбірливим.)"""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(round(c + (255 - c) * amount) for c in (r, g, b))
