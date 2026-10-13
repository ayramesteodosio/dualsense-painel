#!/bin/sh
set -e
VERSAO="${1:-0.0.0}"
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
PKG="$TMP/pkg"
APP="$PKG/usr/share/dualsense-painel"
ICONES="$PKG/usr/share/icons/hicolor"
mkdir -p "$PKG/DEBIAN" "$APP" "$PKG/usr/bin" "$PKG/usr/share/applications" "$PKG/usr/lib/udev/rules.d" \
  "$ICONES/scalable/apps" "$ICONES/symbolic/apps" "$RAIZ/dist"
cp -r "$RAIZ/dualsense_painel" "$APP/"
find "$APP" -name __pycache__ -prune -exec rm -rf {} +
printf 'VERSAO = "%s"\n' "$VERSAO" > "$APP/dualsense_painel/versao.py"
rm -rf "$APP/dualsense_painel/qt"

cat > "$PKG/usr/bin/dualsense-painel" <<'SH'
#!/bin/sh
cd /usr/share/dualsense-painel && exec python3 -m dualsense_painel "$@"
SH
chmod 755 "$PKG/usr/bin/dualsense-painel"

cat > "$PKG/usr/share/applications/com.ayrames.DualSensePainel.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=DualSense Panel
Name[pt_BR]=Painel do DualSense
Comment=Light bar color, adaptive triggers and charging mode for the PS5 controller
Comment[pt_BR]=Cor da luz, gatilhos adaptativos e modo carregar do controle do PS5
Exec=dualsense-painel
Icon=com.ayrames.DualSensePainel
StartupWMClass=com.ayrames.DualSensePainel
Terminal=false
Categories=Settings;HardwareSettings;
Keywords=ps5;dualsense;controle;gatilho;
StartupNotify=true
DESKTOP

install -m644 "$RAIZ/dados/com.ayrames.DualSensePainel.svg" "$ICONES/scalable/apps/"
install -m644 "$RAIZ/dados/com.ayrames.DualSensePainel-symbolic.svg" "$ICONES/symbolic/apps/"
install -m644 "$RAIZ/dados/70-dualsense-painel.rules" "$PKG/usr/lib/udev/rules.d/"

cat > "$PKG/DEBIAN/control" <<CONTROL
Package: dualsense-painel
Version: $VERSAO
Section: utils
Priority: optional
Architecture: all
Maintainer: ayramesteodosio <ayrames.teodosio@gmail.com>
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1
Recommends: pulseaudio-utils
Homepage: https://github.com/ayramesteodosio/dualsense-painel
Description: Painel para o controle DualSense do PS5
 Modo carregar que esconde o controle dos jogos enquanto carrega, luz da
 barra, LEDs, gatilhos adaptativos, teste do controle e informações de fábrica.
CONTROL

cat > "$PKG/DEBIAN/postinst" <<'SH'
#!/bin/sh
set -e
if [ "$1" = configure ] && command -v udevadm >/dev/null; then
  udevadm control --reload || true
  udevadm trigger --action=change --subsystem-match=input --subsystem-match=hidraw --subsystem-match=usb || true
fi
SH
chmod 755 "$PKG/DEBIAN/postinst"

dpkg-deb --root-owner-group --build "$PKG" "$RAIZ/dist/dualsense-painel_${VERSAO}_all.deb"
rm -rf "$TMP"
