# Setup — from bare Pi Zero 2 W to phone dashboard

You need: Pi Zero 2 W, microSD (8 GB+), a 5 V micro-USB supply, your Mac,
one ~17 cm piece of plain wire (solid-core is easiest), and a soldering iron (or a
single header pin / Dupont jumper).

## 1. Flash the SD card (Raspberry Pi Imager)

1. Install **Raspberry Pi Imager** on the Mac (raspberrypi.com/software) and insert the card.
2. **Device:** Raspberry Pi Zero 2 W.
   **OS:** *Raspberry Pi OS (other) → Raspberry Pi OS Lite (32-bit)*.
   rpitx is a 32-bit-era project, so the 32-bit image is the safest bet. Try 64-bit only
   if 32-bit gives trouble.
3. **Storage:** your SD card → **Next → Edit settings** (OS customisation):
   - **General:** hostname `ulight`; username + password (your choice, typed by you);
     **Configure wireless LAN:** *your* home SSID and password, typed by you.
     Set the Wi-Fi country (e.g. NL).
   - **Services:** ✅ Enable SSH → *Use password authentication* (or paste your public key).
   - Save → Yes → write.

   This is much easier than hand-editing `wpa_supplicant.conf`/`userconf` on the boot
   partition, and nothing secret ever touches this repo.

   *Fallback only:* if Wi-Fi refuses to join, you can set up **USB-gadget (Ethernet over USB)**
   mode and SSH in over the data micro-USB port. We'll do that together if needed.

4. Put the card in the Pi and power it from the port marked **PWR**. The first boot takes 2–5 min.

## 2. SSH in

```bash
ssh <your-username>@ulight.local
```

If `ulight.local` isn't found, look up the Pi's IP in your router and `ssh you@192.168.x.y`.

## 3. Install everything

On the Pi:

```bash
sudo apt-get update && sudo apt-get install -y git
```

```bash
git clone https://github.com/semluvsfood/ss-u-light.git ~/SS-U-Light
```

```bash
cd ~/SS-U-Light && ./setup/install.sh
```

`install.sh`:
1. installs `python3-flask`
2. clones and builds **rpitx** into `~/rpitx` (10–20 min; answer **y** when it asks to edit `config.txt`)
3. adds `/etc/sudoers.d/u-light`, which lets your user run **only** `sendook` and `tune` as root
4. installs and starts the `u-light` systemd service (auto-starts on boot)

Then reboot once so the `gpu_freq=250` change takes effect:

```bash
sudo reboot
```

## 4. Attach the antenna (do it NOW, after install and before the first transmit)

Power the Pi **off** first (`sudo poweroff`, then unplug).

- **Physical pin 7 = GPIO 4.** Hold the board component-side up, SD card on the left, with the
  40-hole header along the top edge. Pin 1 has the **square** pad, at the SD-card end.
  Even pins (2, 4, 6…) run along the outer board edge. Odd pins (1, 3, 5, 7…) are the
  **inner row**. **Pin 7 is the 4th hole on the inner row**, counting from the SD-card end.
  Compare with the diagram at pinout.xyz before soldering.
- Solder one end of the ~17 cm wire into that hole (or a single header pin plus a Dupont jumper).
  Leave the other end free, and keep it straight-ish and away from the GND/5 V pins.
- Double-check that it isn't touching pins 5, 6, 8 or 9 before powering back on.

## 5. Smoke test: does rpitx work on the Zero 2 W?

On the Pi:

```bash
cd ~/SS-U-Light && python3 -m tx.cli tone --seconds 1
```

You should see `OK` with tune's output, and **no** `sudo:` error. To actually *verify* RF,
use something that can listen: an RTL-SDR, a Flipper (Sub-GHz → Frequency Analyzer), or a
cheap 433 MHz receiver module. Look for a blip at ~433.92 MHz. (A plain FM radio won't help.)

Then a real OOK burst:

```bash
python3 -m tx.cli ev1527 0x12345 1
```

If that errors or a receiver shows garbage, try the fallback mode:

```bash
ULIGHT_SEND_MODE=string python3 -m tx.cli ev1527 0x12345 1
```

Tell Claude the exact output either way. **Don't trust anything that hasn't come off real hardware.**

## 6. Open the dashboard on your phone

Same Wi-Fi as the Pi → **http://ulight.local:8080** → Share → *Add to Home Screen*.
The pill in the corner should say **LIVE 433.92**.

No home Wi-Fi? Turn on the Pi's own hotspot. It prompts you for a password and stores nothing in git:

```bash
./setup/hotspot.sh on
```

Then join **U-Light** on your phone and open http://10.42.0.1:8080. Turn it off again with:

```bash
./setup/hotspot.sh off
```

## Handy commands

| What | Command |
|---|---|
| Logs | `journalctl -u u-light -f` |
| Restart after `git pull` | `sudo systemctl restart u-light` |
| Stop transmitting everything | `sudo systemctl stop u-light` |
| Save discovered codes to GitHub | `git add codes.json && git commit -m "codes: …" && git push` |
