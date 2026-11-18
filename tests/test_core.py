import json
import unittest

from notifier.district import BlockedError, Show, format_groups, parse_next_data, parse_shows
from notifier.monitor import State, detect, matches, priority_of

CFG = {
    "dates": ["2026-12-17", "2026-12-18"],
    "format_regex": "3D|INFINITY|IMAX|4DX",
    "morning_before_hour": 12,
    "min_seats": 1,
    "seats_back_cooldown_minutes": 30,
    "priority_theatres": [{"label": "Rakki", "match": "rakki"}, {"label": "BigPix", "match": "big ?pix"}],
}


def session(sid, time, avail, fmt="MS INFINITY VISION 3D"):
    return {"sid": sid, "showTime": time, "avail": avail, "total": 200, "scrnFmt": fmt,
            "mcd": "abc", "encSessionId": f"enc-{sid}"}


def page(cinemas):
    state = {
        "movieContents": {"176735": {"languageFormatGroups": [
            {"language": "English", "fmtGrpId": "Mm5dpqTqJz"}, {"language": "Tamil", "fmtGrpId": "x"}]}},
        "movieSessions": {"mm5dpqtqjz": {
            "data": {"sessionDates": ["2026-12-17", "2026-12-18"]},
            "arrangedSessions": [{"entityCode": cid, "entityName": name, "sessions": ss}
                                 for cid, name, ss in cinemas]}},
    }
    blob = json.dumps({"props": {"pageProps": {"data": {"serverState": state}}}})
    return f'<html><script id="__NEXT_DATA__" type="application/json">{blob}</script></html>'


def show(cid, name, sid, time, avail, fmt="MS INFINITY VISION 3D"):
    return Show(str(cid), name, str(sid), time, fmt, "English", avail, 200, "u")


class ParseTests(unittest.TestCase):
    def test_parses_sessions_and_groups(self):
        st = parse_next_data(page([(1, "PVR VR Mall", [session(10, "2026-12-17T07:35", 8)])]))
        groups, dates = format_groups(st)
        self.assertEqual([g["language"] for g in groups], ["English", "Tamil"])
        self.assertEqual(dates, ["2026-12-17", "2026-12-18"])
        (s,) = parse_shows(st, "English", "176735")
        self.assertEqual((s.cinema_name, s.avail, s.hour, s.date), ("PVR VR Mall", 8, 7, "2026-12-17"))
        self.assertIn("encsessionid=enc-10", s.booking_url)

    def test_challenge_page_raises(self):
        with self.assertRaises(BlockedError):
            parse_next_data("<title>Just a moment...</title>")


class FilterTests(unittest.TestCase):
    def test_matches(self):
        self.assertTrue(matches(show(1, "X", 1, "2026-12-17T07:30", 5), CFG))
        self.assertFalse(matches(show(1, "X", 1, "2026-12-17T13:00", 5), CFG))  # afternoon
        self.assertFalse(matches(show(1, "X", 1, "2026-12-17T07:30", 5, "2D"), CFG))  # 2D
        self.assertFalse(matches(show(1, "X", 1, "2026-12-25T07:30", 5), CFG))  # date
        self.assertTrue(matches(show(1, "X", 1, "2026-12-17T07:30", 5, "MS INFINITY VISION"), CFG))

    def test_priority(self):
        self.assertEqual(priority_of(show(1, "INOX Big Pix, Chennai", 1, "2026-12-17T07:30", 1), CFG), "BigPix")
        self.assertIsNone(priority_of(show(1, "PVR Palazzo", 1, "2026-12-17T07:30", 1), CFG))


class DetectTests(unittest.TestCase):
    def test_lifecycle(self):
        st = State()
        a = show(1, "PVR VR Mall", 1, "2026-12-17T07:35", 0)
        self.assertEqual(detect([a], st, CFG, now=0), [])  # sold out: no alert, but remembered

        # Rakki opens -> theatre_opened, priority
        r = show(2, "Rakki RGB Laser", 5, "2026-12-17T09:00", 50)
        ev = detect([a, r], st, CFG, now=60)
        self.assertEqual([(e.kind, e.priority) for e in ev], [("theatre_opened", "Rakki")])

        # Rakki adds another show -> new_show; VR seats free up -> seats_back
        r2 = show(2, "Rakki RGB Laser", 6, "2026-12-17T11:00", 20)
        a2 = show(1, "PVR VR Mall", 1, "2026-12-17T07:35", 3)
        ev = detect([a2, r, r2], st, CFG, now=120)
        self.assertEqual(sorted(e.kind for e in ev), ["new_show", "seats_back"])

        # Seats flicker 0 -> 2 inside cooldown -> no repeat alert
        detect([show(1, "PVR VR Mall", 1, "2026-12-17T07:35", 0)], st, CFG, now=180)
        ev = detect([show(1, "PVR VR Mall", 1, "2026-12-17T07:35", 2)], st, CFG, now=240)
        self.assertEqual(ev, [])

    def test_state_roundtrip(self):
        import os
        import tempfile
        st = State(seen_shows={"1:1": 3}, baseline_done=True)
        p = os.path.join(tempfile.mkdtemp(), "s.json")
        st.save(p)
        self.assertEqual(State.load(p).seen_shows, {"1:1": 3})


if __name__ == "__main__":
    unittest.main()
