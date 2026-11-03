# PROGRESS — living checklist

_Last updated: 2026-11-03 · Pi status: **arrived — it's a Pi Zero W (original), not a 2 W**; Raspbian 13 (trixie) armv6l, SSH works, dashboard reachable; rpitx build failed on trixie → fixed with `setup/build-rpitx.sh`, waiting to run on the Pi_

## Phase 0 — everything possible without the Pi
- [x] Repo scaffold: `tx/`, `web/`, `setup/`, `captures/`, `tests/`, docs, `codes.json`
- [x] Verified rpitx OOK tool against source (F5OEO/rpitx @ ee7ff57): **`sendook`**,
      file mode `-i` with 16-byte `{double active; u32 ns; u32 pad}` records; `tune -f` for the tone
- [x] One isolated radio function `tx/rpitx.py:send_pulses()` (+ `string` fallback mode)
- [x] Safety limits: ISM-band lock, ≤1.5 s/burst, ≥120 ms gap, ≤20 repeats
- [x] Encoders: EV1527, PT2262/PT2260, HS2303-style, generic PWM 1:2, tone
- [x] Discovery plans: timing scan, EV1527 defaults, PT2262, HS2303, learn mode
- [x] "That did something!" → logs current + previous candidate to `codes.json`
- [x] Capture import: Flipper `.sub` (Princeton + RAW) and rtl_433 `.ook`, with sample files
- [x] Flask dashboard: Control / Discover / Codes tabs, mock radio, phone-first, dark mode,
      safe areas, focus rings, reduced motion
- [x] Screenshot → critique → iterate (fixed tab hiding, wordmark contrast, swatch clutter,
      live card ordering, background banding)
- [x] `setup/install.sh` (rpitx build, narrow sudoers, systemd), `u-light.service`, `hotspot.sh`
- [x] Tests (`python3 -m pytest -q`): encoders, file format, limits, plans, importers, web flow
- [x] Commit + push

## Phase 1 — Pi connected  ⏸ waiting for hardware
- [x] Flash Raspberry Pi OS Lite (32-bit) with Imager; hostname `ulight`, SSH on, home Wi-Fi typed by me
- [x] SSH in (`ulight.local` didn't resolve; found it by IP scan)
- [x] `git clone` + `./setup/install.sh`: service + sudoers OK, config.txt edited
- [x] Diagnosed rpitx build failure on trixie: no `libraspberrypi-dev` → apt line aborts (no fftw) and
      librpitx can't link `-lbcm_host`. librpitx has its own bcm_host functions in `rpi.c`, so we link without it.
- [ ] Run `setup/build-rpitx.sh` on the Pi → `sendook` + `tune` in /usr/local/bin (fallback: Legacy/Bookworm 32-bit image)
- [ ] Power off → solder the 17 cm wire to **pin 7 (GPIO 4)** → power on
- [ ] Smoke test: `python3 -m tx.cli tone` runs without errors
- [ ] Confirm RF with a receiver (SDR / Flipper / 433 module), if I can borrow one
- [ ] `python3 -m tx.cli ev1527 0x12345 1` works (else try `ULIGHT_SEND_MODE=string`)
- [ ] Dashboard reachable at http://ulight.local:8080, pill says LIVE

## Phase 2 — discovery
- [ ] Timing scan with the stick next to the Pi
- [ ] Learn mode (stick off → Start → stick on)
- [ ] EV1527 defaults / PT2262 / HS2303 sweeps
- [ ] ≥1 hit logged, bracketed with ◀︎ ▶︎, mapped to a colour
- [ ] **One confirmed real colour change** 🎉
- [ ] If nothing: borrow a Flipper/SDR, capture a real controller, import it in the Codes tab

## Phase 3 — polish
- [ ] Map all colours + off (+ native effects if the stick has them)
- [ ] Tune software effects (strobe / rainbow / pulse) and speed to the stick's real response time
- [ ] Custom presets saved on the Pi
- [ ] Final design pass on real phone (home-screen icon, haptics)

## Notes / decisions
- No secrets in git. Wi-Fi goes in Imager; the hotspot password is prompted at runtime.
- Mock mode turns on automatically when `sendook` isn't installed (`ULIGHT_MOCK=1/0` forces it).
  Mock hits from `run_mock.sh` go to `/tmp/ulight-mock-codes.json`, not the real `codes.json`.
- Hardware is a **Pi Zero W** (BCM2835, single core, 32-bit only). It is on rpitx's official
  supported list, so the Zero 2 W uncertainty no longer applies. Expect slower boots and builds.
- Software "pulse" is on/off breathing, not a real fade: the stick only knows the codes we find.
