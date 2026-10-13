#!/usr/bin/env bash
# Збирає Limber.app і Limber-<версія>-macos.dmg (запускати на macOS).
# Використання:  ./build_mac.sh            — версія береться з src/limber.py
#                ./build_mac.sh 1.3.0
set -euo pipefail
cd "$(dirname "$0")"

VERSION="${1:-$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/limber.py)}"
ARCH="$(uname -m)"
echo "Limber $VERSION ($ARCH)"

python3 -m pip install --disable-pip-version-check -q -r requirements.txt -r requirements-build.txt
python3 tools/make_icon.py

python3 -m PyInstaller --noconfirm --clean --windowed \
    --name Limber \
    --icon "$PWD/assets/limber.icns" \
    --osx-bundle-identifier com.airfast.limber \
    --hidden-import pystray._darwin \
    --distpath dist --workpath build --specpath build \
    src/limber.py

APP="dist/Limber.app"
PLIST="$APP/Contents/Info.plist"
# Програма рядка меню: без іконки в Dock і без головного меню
plutil -replace LSUIElement -bool true "$PLIST"
plutil -replace CFBundleShortVersionString -string "$VERSION" "$PLIST"
plutil -replace CFBundleVersion -string "$VERSION" "$PLIST"
plutil -replace NSHighResolutionCapable -bool true "$PLIST"
# Після зміни Info.plist підпис треба оновити (ad-hoc: без акаунта Apple Developer)
codesign --force --deep --sign - "$APP"

DMG_DIR="build/dmg"
rm -rf "$DMG_DIR" && mkdir -p "$DMG_DIR"
cp -R "$APP" "$DMG_DIR/"
ln -s /Applications "$DMG_DIR/Applications"
DMG="dist/Limber-$VERSION-macos-$ARCH.dmg"
rm -f "$DMG"
hdiutil create -volname "Limber" -srcfolder "$DMG_DIR" -ov -format UDZO "$DMG"
echo "Готово: $DMG"
