"""Custom Tk widgets in the Rhythmos style: button, card, slider, toggle, page scrolling,
the DEMO badge. Plain tk.Button ignores colours on macOS, so everything is built from Label and Canvas."""

import tkinter as tk

from PIL import ImageTk

from graphics import C, lighten, rgba, smooth_image
from i18n import t
from system import HAND, font


def flat_button(parent, text, command, bg=None, fg=None, size=13, hover=None, image=None):
    bg = bg or C["panel"]
    hover = hover or lighten(bg)
    fg = fg or C["text"]
    if image:
        # In Tk padx is also the gap between text and image, so the button is built from two Labels
        btn = tk.Frame(parent, bg=bg, padx=22, pady=10, cursor=HAND)
        parts = [tk.Label(btn, text=text, bg=bg, fg=fg, font=font(size), cursor=HAND),
                 tk.Label(btn, image=image, bg=bg, cursor=HAND)]
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
    # A Label, not tk.Button: on macOS a Tk button is always system white and ignores colours
    btn = tk.Label(parent, text=text, bg=bg, fg=fg, disabledforeground=C["dim"],
                   padx=22, pady=10, font=font(size), cursor=HAND)
    btn.bind("<Button-1>", lambda e: command() if btn["state"] == "normal" else None)
    btn.bind("<Enter>", lambda e: btn.configure(bg=hover) if btn["state"] == "normal" else None)
    btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
    return btn


def demo_badge(parent):
    """The same DEMO badge for every demo window: break, workout, water, meal, day end."""
    return tk.Label(parent, text=t("demo_tag").upper(), bg=C["dim"], fg=C["bg"], font=font(8, "semibold"),
                    padx=7, pady=1)


def wrap_to_width(label):
    """Wraps text to the label's actual width (pack with fill="x"): long text doesn't widen the card."""
    label.bind("<Configure>", lambda e: label.configure(wraplength=max(e.width, 1)))
    return label


# Spacing scale for a steady vertical rhythm: every gap is a multiple of one 4 px unit.
# Proximity: a label sits close to its own control (TIGHT), settings are farther apart (ITEM),
# cards farther still (CARD). A card heading is closer to its content than to the card edge.
UNIT = 4
TIGHT = UNIT          # label and its control, a hint and what it explains
ITEM = 5 * UNIT       # between settings inside a card
CARD = 5 * UNIT       # between cards and columns
CARD_PAD = (6 * UNIT, 5 * UNIT)   # inside a card: horizontal, vertical
HEAD_GAP = 4 * UNIT   # card heading and its first item
EDGE = 5 * UNIT       # inside corner windows and toasts


def card(parent, title=None, action=None, pad=CARD_PAD, head_gap=HEAD_GAP):
    """A card with a heading; action = (text, command) adds a small button right of the heading
    (in settings, "Try it": the preview sits next to what it shows)."""
    frame = tk.Frame(parent, bg=C["card"], padx=pad[0], pady=pad[1])
    if title:
        head = tk.Frame(frame, bg=C["card"])
        head.pack(fill="x", pady=(0, head_gap))
        tk.Label(head, text=title.upper(), bg=C["card"], fg=C["accent"],
                 font=font(9, "semibold")).pack(side="left")
        if action:
            btn = flat_button(head, action[0], action[1], size=9)
            btn.configure(padx=10, pady=1)
            btn.pack(side="right")
    return frame


class Slider(tk.Frame):
    """A slider: drag, click on the track, mouse wheel."""
    PAD = 11

    def __init__(self, parent, label, lo, hi, step, value, fmt, on_change):
        bg = parent["bg"]
        super().__init__(parent, bg=bg)
        self.lo, self.hi, self.step, self.fmt, self.on_change = lo, hi, step, fmt, on_change
        self.value = self.snap(value)
        self.enabled = True
        # Row above the track: label and value; a toggle can go here too (see Meals)
        self.head = head = tk.Frame(self, bg=bg)
        head.pack(fill="x")
        self.label = tk.Label(head, text=label, bg=bg, fg=C["muted"], font=font(10))
        self.label.pack(side="left")
        self.value_label = tk.Label(head, text=fmt(self.value), bg=bg, fg=C["text"],
                                    font=font(11, "semibold"))
        self.value_label.pack(side="right")
        # Explicit small width: otherwise the Canvas asks for ~380 px and widens the settings columns
        self.canvas = tk.Canvas(self, width=160, height=26, bg=bg, highlightthickness=0, cursor=HAND)
        self.canvas.pack(fill="x", pady=(TIGHT, 0))
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

    # Whether the page with the slider scrolls right now: then the wheel scrolls it instead of changing the value
    # (otherwise, scrolling the settings on a small screen, it's easy to move a slider by accident)
    page_scrolls = staticmethod(lambda: False)

    def wheel(self, event):
        if not self.enabled or self.page_scrolls():
            return None  # the window handles the event: page scrolling
        self.set(self.snap(self.value + (self.step if event.delta > 0 else -self.step)))
        self.on_change(self.value)
        return "break"

    def set_enabled(self, enabled):
        """A locked slider only shows the value (for example, one computed from the water profile)."""
        if enabled != self.enabled:
            self.enabled = enabled
            self.canvas.configure(cursor=HAND if enabled else "arrow")
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
    """A main window page with vertical scrolling: if the content is taller than the window (a small screen),
    it scrolls with the wheel or a thin bar on the right; if shorter, it stretches to the full height."""
    BAR = 6

    def __init__(self, parent):
        bg = parent["bg"]
        super().__init__(parent, bg=bg)
        self.bar = tk.Canvas(self, width=self.BAR, bg=bg, highlightthickness=0)
        self.bar.pack(side="right", fill="y", padx=(8, 0))
        # width/height = 1: the window sets the canvas size, not the content
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
        """Content width matches the canvas, height is at least the canvas; also called every second,
        because the content can grow (schedule rows, glasses)."""
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
    """A toggle with a label on the left; text=None gives just the toggle (neighbouring text serves as the label)."""

    def __init__(self, parent, text, value, on_change):
        bg = parent["bg"]
        super().__init__(parent, bg=bg, cursor=HAND)
        self.value, self.on_change = value, on_change
        # The toggle is packed right first, the label takes the rest and wraps: in a narrow column
        # a long label would otherwise push the toggle past the card edge
        self.canvas = tk.Canvas(self, width=46, height=24, bg=bg, highlightthickness=0, cursor=HAND)
        self.canvas.pack(side="right", padx=(8, 0) if text is not None else 0)
        widgets = [self, self.canvas]
        if text is not None:
            label = wrap_to_width(tk.Label(self, text=text, bg=bg, fg=C["text"], font=font(11), cursor=HAND,
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
