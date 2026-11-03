import os
import struct

os.environ["ULIGHT_MOCK"] = "1"

from tx import capture_import, discovery, encoders, pulses, rpitx  # noqa: E402

HERE = os.path.dirname(__file__)


def test_ev1527_shape():
    tr = encoders.ev1527(0, 0b0001, t_us=300)
    assert tr[0] == (1, 300) and tr[1] == (0, 31 * 300)          # sync
    # 24 bits -> 48 pulses after sync; last bit is '1' = long high, short low
    assert len(tr) == 2 + 48
    assert tr[-2:] == [(1, 900), (0, 300)]
    assert tr[2:4] == [(1, 300), (0, 900)]                        # first bit '0'


def test_pt2262_float_and_sync():
    tr = encoders.pt2262("F", t_us=100)
    assert tr == [(1, 100), (0, 300), (1, 300), (0, 100), (1, 100), (0, 3100)]


def test_sendook_file_format():
    blob = pulses.to_sendook_file([(1, 350), (0, 1050)])
    assert len(blob) == 32
    active, ns, pad = struct.unpack("<dII", blob[:16])
    assert active == 1.0 and ns == 350_000 and pad == 0


def test_chip_string():
    assert pulses.to_chip_string([(1, 300), (0, 900)], 300) == "1000"


def test_mock_send_and_limits():
    res = rpitx.send_pulses(encoders.ev1527(1, 1), repeats=3, label="t")
    assert res.ok and res.mock and "-i" in res.command
    try:
        rpitx.send_pulses([(1, 100)], freq_hz=868_000_000)
        assert False, "should refuse out-of-band"
    except ValueError:
        pass
    try:
        rpitx.send_pulses([(1, 400_000)], repeats=10)
        assert False, "should refuse long burst"
    except ValueError:
        pass


def test_plans_build_and_ids_unique():
    for name in discovery.PLANS:
        cands = discovery.build_plan(name, {"my_address": 0x5A5A5})
        assert cands
        assert len({c["id"] for c in cands}) == len(cands), name
        for c in cands[:3]:
            assert discovery.candidate_to_train(c)


def test_every_candidate_fits_air_limit():
    for name in discovery.PLANS:
        for c in discovery.build_plan(name, {"my_address": 0x5A5A5}):
            tr = discovery.candidate_to_train(c)
            assert pulses.total_us(tr) * c["repeats"] / 1000 < rpitx.MAX_AIR_MS


def test_import_flipper_princeton():
    c, = capture_import.import_file(os.path.join(HERE, "..", "captures", "example-princeton.sub"))
    assert c["params"] == {"address": 0x12345, "data": 1, "t_us": 350}


def test_import_flipper_raw_roundtrip():
    cands = capture_import.import_file(os.path.join(HERE, "..", "captures", "example-raw.sub"))
    assert len(cands) == 3
    tr = discovery.candidate_to_train(cands[0])
    assert tr[0] == (1, 960)          # first bit of 0xABCDE is '1' -> 3T high


def test_import_rtl433_ook():
    text = ";pulse data\n;freq1 433920000\n" + "\n".join(["350 1050"] * 12) + "\n350 10850\n;end\n"
    c, = capture_import.parse_rtl433_ook(text, "t")
    assert c["proto"] == "raw" and c["freq_hz"] == 433_920_000
