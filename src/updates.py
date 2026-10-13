"""Перевірка нових версій Limber на GitHub Releases і автоматичне оновлення."""
import hashlib
import json
import os
import platform
import re
import ssl
import subprocess
import sys
import tempfile
import urllib.request

REPO = "AirFast/Limber"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
LATEST_PAGE = f"https://github.com/{REPO}/releases/latest"


def parse_version(text):
    """'v1.10.2' → (1, 10, 2). Порівнювати версії як рядки не можна: '1.10' < '1.9'."""
    parts = [int(n) for n in re.findall(r"\d+", text or "")[:3]]
    return tuple(parts + [0] * (3 - len(parts)))


def is_newer(candidate, current):
    return parse_version(candidate) > parse_version(current)


def _ssl_context():
    # Зібрана програма на macOS не бачить системних сертифікатів — беремо їх із certifi
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _open(url, timeout, accept="application/vnd.github+json"):
    headers = {"Accept": accept, "User-Agent": "Limber-updater"}
    # Лише для API й лише на сервері збирання (GitHub Actions): без токена спільні IP раннерів
    # швидко вичерпують ліміт запитів. У користувачів цієї змінної немає.
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(request, timeout=timeout, context=_ssl_context())


def fetch_latest(timeout=15):
    """(версія, адреса сторінки релізу, файли релізу) або None, якщо перевірити не вдалося.
    Файл релізу: {"name", "url", "size", "sha256"}."""
    try:
        with _open(LATEST_API, timeout) as response:
            data = json.load(response)
    except (OSError, ValueError):
        return None
    tag = data.get("tag_name")
    if not tag:
        return None
    assets = []
    for asset in data.get("assets", []):
        digest = asset.get("digest") or ""
        assets.append({
            "name": asset.get("name", ""),
            "url": asset.get("browser_download_url", ""),
            "size": asset.get("size", 0),
            "sha256": digest[7:] if digest.startswith("sha256:") else "",
        })
    return tag.lstrip("v"), data.get("html_url") or LATEST_PAGE, assets


def pick_asset(assets):
    """Файл оновлення для цієї системи: інсталятор Windows або dmg під архітектуру Mac."""
    for asset in assets:
        name = asset["name"]
        if sys.platform == "win32" and name.startswith("LimberSetup-") and name.endswith(".exe"):
            return asset
        if sys.platform == "darwin" and name.endswith(f"-macos-{platform.machine()}.dmg"):
            return asset
    return None


def can_self_update():
    """Оновлюється лише зібрана програма; запуск із коду оновлюють через git."""
    return getattr(sys, "frozen", False) and sys.platform in ("win32", "darwin")


def download(asset, progress=None, timeout=60):
    """Завантажує файл у тимчасову папку й перевіряє розмір та SHA-256. Повертає шлях.
    progress(відсоток) викликається з потоку завантаження."""
    folder = tempfile.mkdtemp(prefix="limber-update-")
    path = os.path.join(folder, asset["name"])
    digest = hashlib.sha256()
    received = 0
    with _open(asset["url"], timeout, accept="application/octet-stream") as response, open(path, "wb") as f:
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            digest.update(chunk)
            received += len(chunk)
            if progress and asset["size"]:
                progress(min(99, received * 100 // asset["size"]))
    if asset["size"] and received != asset["size"]:
        raise OSError(f"incomplete download: {received} of {asset['size']} bytes")
    if asset["sha256"] and digest.hexdigest() != asset["sha256"]:
        raise OSError("checksum mismatch")
    return path


def install(path):
    """Запускає встановлення окремим процесом. Після виклику програма має завершитися:
    на Windows інсталятор замінить файли й сам запустить нову версію,
    на macOS скрипт дочекається виходу, замінить Limber.app і відкриє його."""
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], creationflags=flags, close_fds=True)
    elif sys.platform == "darwin":
        _install_mac(path)


def _app_bundle():
    """…/Limber.app для зібраної програми (sys.executable = …/Limber.app/Contents/MacOS/Limber)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(sys.executable)))


_MAC_SCRIPT = r"""#!/bin/bash
# Оновлення Limber: чекаємо завершення старої версії, замінюємо Limber.app з dmg і відкриваємо.
PID="$1"; DMG="$2"; APP="$3"
while kill -0 "$PID" 2>/dev/null; do sleep 0.5; done
MNT="$(mktemp -d)"
hdiutil attach -nobrowse -quiet -mountpoint "$MNT" "$DMG" || exit 1
rm -rf "$APP.old"
if mv "$APP" "$APP.old" && ditto "$MNT/Limber.app" "$APP"; then
    rm -rf "$APP.old"
else
    rm -rf "$APP"; mv "$APP.old" "$APP"      # не вдалося — повертаємо стару версію
fi
hdiutil detach -quiet "$MNT"
rm -f "$DMG"
open "$APP"
"""


def _install_mac(dmg):
    script = os.path.join(os.path.dirname(dmg), "update.sh")
    with open(script, "w") as f:
        f.write(_MAC_SCRIPT)
    subprocess.Popen(["/bin/bash", script, str(os.getpid()), dmg, _app_bundle()],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
