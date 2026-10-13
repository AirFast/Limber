"""Генерує assets/limber.ico з тієї ж функції, якою малює іконку сама програма."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from limber import make_app_icon  # noqa: E402

SIZES = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]

if __name__ == "__main__":
    out = os.path.join(ROOT, "assets", "limber.ico")
    make_app_icon(256).save(out, sizes=SIZES)
    make_app_icon(256).save(os.path.join(ROOT, "assets", "limber.png"))
    print(f"saved {out}")
