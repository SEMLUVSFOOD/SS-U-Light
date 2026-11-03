#!/usr/bin/env bash
# Build ONLY the two rpitx tools we use (sendook + tune) and install them to /usr/local/bin.
#
# Why not rpitx's own install.sh? On Raspberry Pi OS 13 (trixie) it fails:
#   * `libraspberrypi-dev` no longer exists, so its apt line aborts (taking fftw/imagemagick with it)
#   * librpitx links with -lbcm_host, which came from that package
# librpitx already ships its own bcm_host_get_peripheral_address()/..._sdram_address()
# in src/rpi.c, so we simply link WITHOUT -lbcm_host. We also skip csdr/ft8/sstv etc.
# Safe to re-run.
set -euo pipefail

RPITX_DIR="${RPITX_DIR:-$HOME/rpitx}"
say() { printf '\n\033[1;35m==> %s\033[0m\n' "$*"; }

say "Build tools"
sudo apt-get install -y build-essential git

say "Sources"
[ -d "$RPITX_DIR" ] || git clone https://github.com/F5OEO/rpitx.git "$RPITX_DIR"
[ -d "$RPITX_DIR/src/librpitx" ] || git clone https://github.com/F5OEO/librpitx.git "$RPITX_DIR/src/librpitx"

say "librpitx (static library, no bcm_host)"
cd "$RPITX_DIR/src/librpitx/src"
make clean >/dev/null || true
make librpitx.a LDFLAGS="-lm -lrt -lpthread -fPIC"
sudo make install PREFIX=/usr/local/

say "sendook + tune"
cd "$RPITX_DIR/src"
rm -f ../sendook ../tune
make ../sendook ../tune \
  CXXFLAGS="-std=c++11 -Wall -O2 -Wno-unused-variable -I/usr/local/include" \
  LDFLAGS="-L/usr/local/lib -lrpitx -lm -lrt -lpthread"
sudo install -m 0755 ../sendook ../tune /usr/local/bin/

say "config.txt (rpitx wants a fixed GPU clock)"
CFG=/boot/firmware/config.txt; [ -f "$CFG" ] || CFG=/boot/config.txt
for LINE in gpu_freq=250 force_turbo=1; do
  grep -qxF "$LINE" "$CFG" || echo "$LINE" | sudo tee -a "$CFG" >/dev/null
done

hash -r
echo
echo "Installed: $(command -v sendook)  $(command -v tune)"
