"""Перевірка нових версій Limber на GitHub Releases."""
import json
import re
import ssl
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


def fetch_latest(timeout=15):
    """(версія, адреса сторінки релізу) або None, якщо перевірити не вдалося."""
    request = urllib.request.Request(LATEST_API, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "Limber-update-check",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
            data = json.load(response)
    except (OSError, ValueError):
        return None
    tag = data.get("tag_name")
    if not tag:
        return None
    return tag.lstrip("v"), data.get("html_url") or LATEST_PAGE
