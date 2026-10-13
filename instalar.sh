#!/bin/sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
APPS="$HOME/.local/share/applications"
mkdir -p "$APPS" "$HOME/.local/bin"
ln -sf "$DIR/dualsense-painel" "$HOME/.local/bin/dualsense-painel"
cat > "$APPS/com.ayrames.DualSensePainel.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Painel do DualSense
Comment=Cor da luz, gatilhos adaptativos e modo carregar do controle do PS5
Exec=$DIR/dualsense-painel
Icon=$HOME/.local/share/icons/hicolor/scalable/apps/com.ayrames.DualSensePainel.svg
StartupWMClass=com.ayrames.DualSensePainel
Terminal=false
Categories=Settings;HardwareSettings;
Keywords=ps5;dualsense;controle;gatilho;
StartupNotify=true
DESKTOP
update-desktop-database "$APPS" 2>/dev/null || true
ICONS="$HOME/.local/share/icons/hicolor"
install -Dm644 "$DIR/dados/com.ayrames.DualSensePainel.svg" "$ICONS/scalable/apps/com.ayrames.DualSensePainel.svg"
install -Dm644 "$DIR/dados/com.ayrames.DualSensePainel-symbolic.svg" "$ICONS/symbolic/apps/com.ayrames.DualSensePainel-symbolic.svg"
gtk-update-icon-cache -q -t -f "$ICONS" 2>/dev/null || true
gio set "$DIR/dualsense-painel" metadata::custom-icon "file://$ICONS/scalable/apps/com.ayrames.DualSensePainel.svg" 2>/dev/null || true

if ! cmp -s "$DIR/dados/70-dualsense-painel.rules" /etc/udev/rules.d/70-dualsense-painel.rules; then
  pkexec sh -c 'install -m 0644 "$0" /etc/udev/rules.d/70-dualsense-painel.rules && udevadm control --reload && udevadm trigger --action=change --subsystem-match=input --subsystem-match=hidraw --subsystem-match=usb' "$DIR/dados/70-dualsense-painel.rules"
fi
echo "Pronto. Procure por \"Painel do DualSense\" no menu."
