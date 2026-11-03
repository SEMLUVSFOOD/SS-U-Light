#!/usr/bin/env bash
# OPTIONAL: make the Pi its own Wi-Fi hotspot (for when there's no home Wi-Fi).
# Uses NetworkManager (default on Raspberry Pi OS Bookworm). While the hotspot
# is on, the Pi is NOT on your home Wi-Fi — keep SSH/USB access in mind.
#   ./setup/hotspot.sh on      # prompts for a hotspot password (not stored in git)
#   ./setup/hotspot.sh off     # back to home Wi-Fi
# Then join "U-Light" on your phone and open http://10.42.0.1:8080
set -euo pipefail
case "${1:-}" in
  on)
    read -rsp "New hotspot password (8+ chars, typed by you, not saved in the repo): " PW; echo
    [ "${#PW}" -ge 8 ] || { echo "Too short."; exit 1; }
    sudo nmcli device wifi hotspot ifname wlan0 con-name u-light-hotspot ssid "U-Light" password "$PW"
    echo "Hotspot up. Phone: join 'U-Light', open http://10.42.0.1:8080" ;;
  off)
    sudo nmcli connection down u-light-hotspot || true
    echo "Hotspot off. NetworkManager will reconnect to your home Wi-Fi." ;;
  *) echo "usage: $0 on|off"; exit 1 ;;
esac
