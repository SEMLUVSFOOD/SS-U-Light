#!/usr/bin/env bash
# U-Light bridge installer — run ON THE PI, from the repo folder, as your normal user:
#     cd ~/SS-U-Light && ./setup/install.sh
# Safe to re-run. Never asks for or stores any Wi-Fi password.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
ME="$(id -un)"
RPITX_DIR="${RPITX_DIR:-$HOME/rpitx}"

say() { printf '\n\033[1;35m==> %s\033[0m\n' "$*"; }

if [ "$ME" = "root" ]; then echo "Run as your normal user (not sudo); it will ask for sudo when needed."; exit 1; fi

say "1/5  System packages (git, Flask)"
sudo apt-get update
sudo apt-get install -y git python3-flask

say "2/5  rpitx (builds from source — takes ~30-60 min on a Zero W)"
if command -v sendook >/dev/null && command -v tune >/dev/null; then
  echo "rpitx already installed: $(command -v sendook)"
else
  [ -d "$RPITX_DIR" ] || git clone https://github.com/F5OEO/rpitx.git "$RPITX_DIR"
  echo "rpitx's own installer will ask to edit config.txt (gpu_freq=250). Answer 'y'."
  (cd "$RPITX_DIR" && ./install.sh)
fi
# rpitx's own installer keeps going after a failed compile — check for real.
hash -r
if ! command -v sendook >/dev/null || ! command -v tune >/dev/null; then
  echo
  echo "!! rpitx did NOT build: sendook/tune are missing."
  echo "   Re-run its build with a log and look at the first error:"
  echo "     cd $RPITX_DIR && ./install.sh 2>&1 | tee ~/rpitx-build.log | grep -iE 'error|fatal|unable to locate'"
  echo "   The dashboard still works, but stays in MOCK mode until this is fixed."
  exit 1
fi
SENDOOK="$(command -v sendook)"
TUNE="$(command -v tune)"

say "3/5  Let the dashboard run ONLY sendook + tune as root (nothing else)"
TMP="$(mktemp)"
cat > "$TMP" <<SUDO
# U-Light bridge: rpitx needs root for DMA. Limited to these two binaries.
$ME ALL=(root) NOPASSWD: $SENDOOK, $TUNE
SUDO
sudo visudo -cf "$TMP"                       # refuse to install a broken sudoers file
sudo install -m 0440 -o root -g root "$TMP" /etc/sudoers.d/u-light
rm -f "$TMP"

say "4/5  systemd service (auto-start on boot)"
sed -e "s|@USER@|$ME|g" -e "s|@REPO@|$REPO|g" "$REPO/setup/u-light.service" \
  | sudo tee /etc/systemd/system/u-light.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now u-light.service

say "5/5  Done"
systemctl --no-pager --lines=5 status u-light.service || true
echo
echo "Open on your phone (same Wi-Fi):  http://$(hostname).local:8080"
echo "Logs:   journalctl -u u-light -f"
echo "If rpitx edited config.txt just now, reboot once:  sudo reboot"
