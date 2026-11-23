#!/bin/zsh
# Gera o "Ripagem Maker.app" (app nativo do macOS) a partir de main.swift.
# Uso: ./build_app.sh            -> cria "Ripagem Maker.app" na pasta acima de APP_TRANSCRICAO_SPEAKERS
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"                       # APP_TRANSCRICAO_SPEAKERS
DEST="$(cd "$ROOT/.." && pwd)/Ripagem Maker.app"
PY="$(command -v python3)"
PY="$(python3 -c 'import sys;print(sys.executable)')"
BUILD="$HERE/.build"
rm -rf "$BUILD"; mkdir -p "$BUILD/AppIcon.iconset"

echo "1/4 ícone"
cp "$ROOT/design/logo/ripagem-maker-icone-1024.png" "$BUILD/icon_1024.png"
for s in 16 32 128 256 512; do
  sips -z $s $s "$BUILD/icon_1024.png" --out "$BUILD/AppIcon.iconset/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) "$BUILD/icon_1024.png" --out "$BUILD/AppIcon.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$BUILD/AppIcon.iconset" -o "$BUILD/AppIcon.icns"

echo "2/4 compilando (Swift)"
swiftc -O -swift-version 5 -target arm64-apple-macos13.0 "$HERE/main.swift" -o "$BUILD/DRStudio" -framework Cocoa -framework WebKit

echo "3/4 montando o pacote"
rm -rf "$DEST"
mkdir -p "$DEST/Contents/MacOS" "$DEST/Contents/Resources"
cp "$BUILD/DRStudio" "$DEST/Contents/MacOS/DRStudio"
cp "$BUILD/AppIcon.icns" "$DEST/Contents/Resources/AppIcon.icns"
cat > "$DEST/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Ripagem Maker</string>
  <key>CFBundleDisplayName</key><string>Ripagem Maker</string>
  <key>CFBundleIdentifier</key><string>local.drstudio.app</string>
  <key>CFBundleExecutable</key><string>DRStudio</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
  <key>DRStudioRoot</key><string>$ROOT</string>
  <key>DRStudioPython</key><string>$PY</string>
</dict></plist>
EOF

echo "4/4 assinatura local (ad-hoc)"
codesign --force --deep -s - "$DEST" >/dev/null
echo "Pronto: $DEST"
