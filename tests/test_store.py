import os
import tempfile
import unittest

from xingji import store

POI = {"name": "武侯祠", "area": "武侯区", "minutes": 120, "price": 50.0,
       "open_days": None, "open_spec": "全周", "best_time": "上午", "must": True, "note": "红墙"}
POI2 = {"name": "四川博物院", "area": "青羊区", "minutes": 180, "price": 0.0,
        "open_days": [0, 2, 3, 4, 5, 6], "open_spec": "周一休", "best_time": "上午",
        "must": False, "note": ""}


class PoiStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conn = store.connect(os.path.join(self.tmp, "t.db"))

    def tearDown(self):
        self.conn.close()

    def test_import_and_read(self):
        n = store.import_pois(self.conn, "成都", [POI, POI2])
        self.assertEqual(n, 2)
        ps = store.pois_of(self.conn, "成都")
        self.assertEqual(len(ps), 2)
        self.assertTrue(any(p["must"] for p in ps))

    def test_open_days_roundtrip(self):
        store.import_pois(self.conn, "成都", [POI2])
        p = store.pois_of(self.conn, "成都")[0]
        self.assertEqual(p["open_days"], [0, 2, 3, 4, 5, 6])

    def test_none_open_days(self):
        store.import_pois(self.conn, "成都", [POI])
        self.assertIsNone(store.pois_of(self.conn, "成都")[0]["open_days"])

    def test_replace_clears_old(self):
        store.import_pois(self.conn, "成都", [POI, POI2])
        store.import_pois(self.conn, "成都", [POI])
        self.assertEqual(len(store.pois_of(self.conn, "成都")), 1)

    def test_keep_without_replace(self):
        store.import_pois(self.conn, "成都", [POI])
        store.import_pois(self.conn, "成都", [POI2], replace=False)
        self.assertEqual(len(store.pois_of(self.conn, "成都")), 2)

    def test_destinations(self):
        store.import_pois(self.conn, "成都", [POI])
        store.import_pois(self.conn, "重庆", [POI])
        ds = store.destinations(self.conn)
        self.assertEqual({d["destination"] for d in ds}, {"成都", "重庆"})

    def test_pois_of_unknown(self):
        self.assertEqual(store.pois_of(self.conn, "西安"), [])


class TripTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conn = store.connect(os.path.join(self.tmp, "t.db"))
        self.plan = {"days": [{"day": 1, "pois": []}], "unscheduled": [{"name": "甲", "why": "x"}],
                     "total_price": 10.0}

    def tearDown(self):
        self.conn.close()

    def test_save_and_get(self):
        tid = store.save_trip(self.conn, "成都", 3, 540, 900, "带老人", self.plan, created="x")
        t = store.get_trip(self.conn, tid)
        self.assertEqual(t["destination"], "成都")
        self.assertEqual(t["plan"]["total_price"], 10.0)
        self.assertEqual(t["budget"], 900)

    def test_story_saved_separately(self):
        tid = store.save_trip(self.conn, "成都", 3, 540, None, "", self.plan, created="x")
        self.assertTrue(store.save_story(self.conn, tid, {"days": [], "tips": ["带伞"]}))
        self.assertEqual(store.get_trip(self.conn, tid)["story"]["tips"], ["带伞"])

    def test_story_missing_trip(self):
        self.assertFalse(store.save_story(self.conn, 999, {}))

    def test_get_missing(self):
        self.assertIsNone(store.get_trip(self.conn, 42))

    def test_list(self):
        store.save_trip(self.conn, "成都", 3, 540, None, "", self.plan, created="x")
        store.save_trip(self.conn, "重庆", 2, 480, None, "", self.plan, created="x")
        self.assertEqual([t["destination"] for t in store.list_trips(self.conn)], ["重庆", "成都"])

    def test_delete(self):
        tid = store.save_trip(self.conn, "成都", 3, 540, None, "", self.plan, created="x")
        self.assertTrue(store.delete_trip(self.conn, tid))
        self.assertFalse(store.delete_trip(self.conn, tid))

    def test_bad_json_tolerated(self):
        tid = store.save_trip(self.conn, "成都", 3, 540, None, "", self.plan, created="x")
        self.conn.execute("UPDATE trips SET plan='坏的' WHERE id=?", (tid,))
        self.conn.commit()
        self.assertEqual(store.get_trip(self.conn, tid)["plan"], {})

    def test_stats(self):
        store.save_trip(self.conn, "成都", 3, 540, None, "", self.plan, created="x")
        store.import_pois(self.conn, "成都", [POI])
        s = store.stats(self.conn)
        self.assertEqual(s["trips"], 1)
        self.assertEqual(s["pois"], 1)
        self.assertEqual(s["unscheduled"], 1)


if __name__ == "__main__":
    unittest.main()
