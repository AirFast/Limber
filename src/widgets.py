"""Власні віджети Tk у стилі Rhythmos: кнопка, картка, повзунок, перемикач, прокрутка сторінки,
позначка «ДЕМО». Звичайні tk.Button на macOS ігнорують кольори, тож усе — з Label і Canvas."""

import tkinter as tk

from PIL import ImageTk

from graphics import C, lighten, rgba, smooth_image
from i18n import t
from system import font


def flat_button(parent, text, command, bg=None, fg=None, size=13, hover=None, image=None):
    bg = bg or C["panel"]
    hover = hover or lighten(bg)
    fg = fg or C["text"]
    if image:
        # У Tk padx — це ще й проміжок між текстом і картинкою, тому збираємо кнопку з двох Label
        btn = tk.Frame(parent, bg=bg, padx=22, pady=10, cursor="hand2")
        parts = [tk.Label(btn, text=text, bg=bg, fg=fg, font=font(size), cursor="hand2"),
                 tk.Label(btn, image=image, bg=bg, cursor="hand2")]
        parts[0].pack(side="left")
        parts[1].pack(side="left", padx=(7, 0))
        btn.image = image

        def paint(color):
            for widget in (btn, *parts):
                widget.configure(bg=color)

        for widget in (btn, *parts):
            widget.bind("<Button-1>", lambda e: command())
            widget.bind("<Enter>", lambda e: paint(hover))
            widget.bind("<Leave>", lambda e: paint(bg))
        return btn
    # Label, а не tk.Button: на macOS кнопка Tk завжди системна біла й ігнорує кольори
    btn = tk.Label(parent, text=text, bg=bg, fg=fg, disabledforeground=C["dim"],
                   padx=22, pady=10, font=font(size), cursor="hand2")
    btn.bind("<Button-1>", lambda e: command() if btn["state"] == "normal" else None)
    btn.bind("<Enter>", lambda e: btn.configure(bg=hover) if btn["state"] == "normal" else None)
    btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
    return btn


def demo_badge(parent):
    """Однакова позначка «ДЕМО» для всіх демо-вікон: перерва, тренування, вода, їжа, кінець дня."""
    return tk.Label(parent, text=t("demo_tag").upper(), bg=C["dim"], fg=C["bg"], font=font(8, "semibold"),
                    padx=7, pady=1)


def wrap_to_width(label):
    """Перенос рядка за фактичною шириною мітки (pack з fill="x"): довгий текст не розпирає картку."""
    label.bind("<Configure>", lambda e: label.configure(wraplength=max(e.width, 1)))
    return label


def card(parent, title=None, action=None):
    """Картка з заголовком; action = (текст, команда) — мала кнопка праворуч від заголовка
    (у налаштуваннях — «Спробувати»: перегляд поруч із тим, що він показує)."""
    frame = tk.Frame(parent, bg=C["card"], padx=18, pady=14)
    if title:
        head = tk.Frame(frame, bg=C["card"])
        head.pack(fill="x", pady=(0, 8))
        tk.Label(head, text=title.upper(), bg=C["card"], fg=C["accent"],
                 font=font(9, "semibold")).pack(side="left")
        if action:
            btn = flat_button(head, action[0], action[1], size=9)
            btn.configure(padx=10, pady=1)
            btn.pack(side="right")
    return frame


class Slider(tk.Frame):
    """Повзунок: перетягування, клік по доріжці, коліщатко миші."""
    PAD = 11

    def __init__(self, parent, label, lo, hi, step, value, fmt, on_change):
        bg = parent["bg"]
        super().__init__(parent, bg=bg)
        self.lo, self.hi, self.step, self.fmt, self.on_change = lo, hi, step, fmt, on_change
        self.value = self.snap(value)
        self.enabled = True
        # Рядок над доріжкою: підпис і значення; сюди ж можна поставити перемикач (див. «Їжа»)
        self.head = head = tk.Frame(self, bg=bg)
        head.pack(fill="x")
        self.label = tk.Label(head, text=label, bg=bg, fg=C["muted"], font=font(10))
        self.label.pack(side="left")
        self.value_label = tk.Label(head, text=fmt(self.value), bg=bg, fg=C["text"],
                                    font=font(11, "semibold"))
        self.value_label.pack(side="right")
        # Явна мала ширина: інакше Canvas просить типові ~380 px і роздуває колонки налаштувань
        self.canvas = tk.Canvas(self, width=160, height=26, bg=bg, highlightthickness=0, cursor="hand2")
        self.canvas.pack(fill="x", pady=(2, 0))
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.canvas.bind("<Button-1>", self.drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: self.on_change(self.value) if self.enabled else None)
        self.canvas.bind("<MouseWheel>", self.wheel)

    def snap(self, v):
        v = self.lo + round((v - self.lo) / self.step) * self.step
        return min(max(v, self.lo), self.hi)

    def drag(self, event):
        if not self.enabled:
            return
        width = max(self.canvas.winfo_width() - 2 * self.PAD, 1)
        self.set(self.snap(self.lo + (event.x - self.PAD) / width * (self.hi - self.lo)))

    # Чи прокручується зараз сторінка з повзунком — тоді коліщатко гортає її, а не змінює значення
    # (інакше на малому екрані, гортаючи налаштування, легко випадково посунути повзунок)
    page_scrolls = staticmethod(lambda: False)

    def wheel(self, event):
        if not self.enabled or self.page_scrolls():
            return None  # подію обробить вікно — прокрутка сторінки
        self.set(self.snap(self.value + (self.step if event.delta > 0 else -self.step)))
        self.on_change(self.value)
        return "break"

    def set_enabled(self, enabled):
        """Заблокований повзунок лише показує значення (наприклад, розраховане за профілем води)."""
        if enabled != self.enabled:
            self.enabled = enabled
            self.canvas.configure(cursor="hand2" if enabled else "arrow")
            self.value_label.configure(fg=C["text"] if enabled else C["muted"])
            self.draw()

    def set(self, value):
        if value != self.value:
            self.value = value
            self.value_label.configure(text=self.fmt(value))
            self.draw()

    def draw(self):
        width = self.canvas.winfo_width()
        if width < 2 * self.PAD:
            return
        x0, x1 = self.PAD, width - self.PAD
        xv = x0 + (x1 - x0) * (self.value - self.lo) / (self.hi - self.lo)
        fill = rgba(C["accent"] if self.enabled else C["dim"])
        knob = rgba(C["text"] if self.enabled else C["muted"])

        def paint(d, s):
            y, r = 13 * s, 3 * s
            d.rounded_rectangle((x0 * s - r, y - r, x1 * s + r, y + r), radius=r, fill=rgba(C["track"]))
            d.rounded_rectangle((x0 * s - r, y - r, xv * s + r, y + r), radius=r, fill=fill)
            d.ellipse(((xv - 10) * s, y - 10 * s, (xv + 10) * s, y + 10 * s), fill=fill)
            d.ellipse(((xv - 7) * s, y - 7 * s, (xv + 7) * s, y + 7 * s), fill=knob)

        self.photo = ImageTk.PhotoImage(smooth_image(width, 26, paint, self["bg"]))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)


class ScrollArea(tk.Frame):
    """Сторінка головного вікна з вертикальною прокруткою: якщо вміст вищий за вікно (малий екран),
    його гортають коліщатком або тонкою смугою праворуч; якщо нижчий — він розтягується на всю висоту."""
    BAR = 6

    def __init__(self, parent):
        bg = parent["bg"]
        super().__init__(parent, bg=bg)
        self.bar = tk.Canvas(self, width=self.BAR, bg=bg, highlightthickness=0)
        self.bar.pack(side="right", fill="y", padx=(8, 0))
        # width/height = 1: розмір полотна задає вікно, а не вміст
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, width=1, height=1, yscrollincrement=24)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.item = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.relayout())
        self.bar.bind("<Button-1>", self.drag)
        self.bar.bind("<B1-Motion>", self.drag)
        self._key = None

    def scrollable(self):
        return self.inner.winfo_reqheight() > self.canvas.winfo_height() + 1

    def relayout(self):
        """Ширина вмісту — як у полотна, висота — не менша за полотно; викликається й щосекунди,
        бо вміст може вирости (рядки розкладу, склянки)."""
        cw, ch, rh = self.canvas.winfo_width(), self.canvas.winfo_height(), self.inner.winfo_reqheight()
        if (cw, ch, rh) != self._key:
            self._key = (cw, ch, rh)
            self.canvas.itemconfigure(self.item, width=cw, height=max(ch, rh))
            self.canvas.configure(scrollregion=(0, 0, cw, max(ch, rh)))
        self.draw_bar()

    def draw_bar(self):
        self.bar.delete("all")
        if not self.scrollable():
            return
        top, bottom = self.canvas.yview()
        h = self.bar.winfo_height()
        self.bar.create_rectangle(0, 0, self.BAR, h, fill=C["card"], outline="")
        self.bar.create_rectangle(0, top * h, self.BAR, max(bottom * h, top * h + 24), fill=C["dim"], outline="")

    def scroll(self, units):
        if self.scrollable():
            self.canvas.yview_scroll(units, "units")
            self.draw_bar()

    def drag(self, event):
        if self.scrollable():
            top, bottom = self.canvas.yview()
            self.canvas.yview_moveto(event.y / max(self.bar.winfo_height(), 1) - (bottom - top) / 2)
            self.draw_bar()


class Toggle(tk.Frame):
    """Перемикач із підписом ліворуч; text=None — сам перемикач (підписом слугує сусідній текст)."""

    def __init__(self, parent, text, value, on_change):
        bg = parent["bg"]
        super().__init__(parent, bg=bg, cursor="hand2")
        self.value, self.on_change = value, on_change
        # Перемикач — праворуч першим, підпис забирає решту й переноситься: у вузькій колонці
        # довгий підпис інакше виштовхував перемикач за край картки
        self.canvas = tk.Canvas(self, width=46, height=24, bg=bg, highlightthickness=0, cursor="hand2")
        self.canvas.pack(side="right", padx=(8, 0) if text is not None else 0)
        widgets = [self, self.canvas]
        if text is not None:
            label = wrap_to_width(tk.Label(self, text=text, bg=bg, fg=C["text"], font=font(11), cursor="hand2",
                                           anchor="w", justify="left", wraplength=180))
            label.pack(side="left", fill="x", expand=True)
            widgets.append(label)
        for widget in widgets:
            widget.bind("<Button-1>", self.toggle)
        self.draw()

    def draw(self):
        color = rgba(C["accent"] if self.value else C["track"])
        knob = rgba("#ffffff" if self.value else C["muted"])
        x = 34 if self.value else 12

        def paint(d, s):
            d.rounded_rectangle((1 * s, 1 * s, 45 * s, 23 * s), radius=11 * s, fill=color)
            d.ellipse(((x - 8) * s, 4 * s, (x + 8) * s, 20 * s), fill=knob)

        self.photo = ImageTk.PhotoImage(smooth_image(46, 24, paint, self["bg"]))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)

    def toggle(self, _event=None):
        self.value = not self.value
        self.draw()
        self.on_change(self.value)
