"""Runs the smoke test from source next to the installed, running Rhythmos without touching it: a copy of
the real data in a temporary folder and an own single-instance lock.

    python tools/smoke_local.py [out dir]      # screenshots and info.txt go to out dir (default: ./smoke-local)

Windows: the data folder follows %APPDATA%; macOS: ~/Library/Application Support, so HOME is redirected.
"""

import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "smoke-local"))
# The out dir is emptied before the run, so it must be an earlier smoke output (info.txt, screenshots) or empty:
# a wrong argument once pointed it at the repository and wiped the working copy
if os.path.isdir(out) and any(not (name == "info.txt" or name.endswith(".png")) for name in os.listdir(out)):
    sys.exit(f"{out} is not a smoke test output (it has other files); refusing to empty it")
home = tempfile.mkdtemp(prefix="rhythmos-smoke-")

if sys.platform == "darwin":
    real = os.path.expanduser("~/Library/Application Support/Rhythmos")
    os.environ["HOME"] = home
    data = os.path.join(home, "Library", "Application Support", "Rhythmos")
else:
    real = os.path.join(os.environ["APPDATA"], "Rhythmos")
    os.environ["APPDATA"] = home
    data = os.path.join(home, "Rhythmos")

os.makedirs(data)
for name in ("config.json", "stats.json", "state.json"):
    if os.path.exists(os.path.join(real, name)):
        shutil.copy(os.path.join(real, name), data)
if os.path.isdir(os.path.join(real, "stats")):
    shutil.copytree(os.path.join(real, "stats"), os.path.join(data, "stats"))

sys.path.insert(0, os.path.join(ROOT, "src"))
import system  # noqa: E402

system.MUTEX_NAME += "Smoke"          # Windows; on macOS the lock file lives in the redirected data folder
system.SHOW_EVENT_NAME += "Smoke"
import rhythmos  # noqa: E402

print(f"data copy: {data}\nscreenshots: {out}")
shutil.rmtree(out, ignore_errors=True)
sys.argv = ["rhythmos.py", "--smoke-test", out]
rhythmos.main()
