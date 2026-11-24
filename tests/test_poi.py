import unittest

from xingji import poi


class OpenTest(unittest.TestCase):
    def test_all_week(self):
        self.assertIsNone(poi.parse_open("全周"))
        self.assertIsNone(poi.parse_open(""))
        self.assertIsNone(poi.parse_open("无休"))

    def test_single_closed(self):
        days = poi.parse_open("周一休")
        self.assertNotIn(1, days)
        self.assertIn(0, days)
        self.assertEqual(len(days), 6)

    def test_range(self):
        days = poi.parse_open("周二至周日")
        self.assertEqual(sorted(days), [0, 2, 3, 4, 5, 6])

    def test_range_weekday(self):
        self.assertEqual(poi.parse_open("周一至周五"), [1, 2, 3, 4, 5])

    def test_list(self):
        self.assertEqual(poi.parse_open("周一,周三"), [1, 3])

    def test_digits(self):
        self.assertEqual(poi.parse_open("1,2"), [1, 2])

    def test_dash_range(self):
        self.assertEqual(poi.parse_open("1-5"), [1, 2, 3, 4, 5])

    def test_xingqiri(self):
        self.assertEqual(poi.parse_open("星期二"), [2])

    def test_bad(self):
        with self.assertRaises(poi.PoiError):
            poi.parse_open("看心情")

    def test_is_open(self):
        self.assertTrue(poi.is_open(None, 1))
        self.assertFalse(poi.is_open([2, 3], 1))


class PriceTest(unittest.TestCase):
    def test_free(self):
        self.assertEqual(poi.parse_price("免费"), 0.0)
        self.assertEqual(poi.parse_price(""), 0.0)

    def test_number(self):
        self.assertEqual(poi.parse_price("55"), 55.0)
        self.assertEqual(poi.parse_price("70元"), 70.0)

    def test_bad(self):
        with self.assertRaises(poi.PoiError):
            poi.parse_price("看情况")


class LineTest(unittest.TestCase):
    def test_full_line(self):
        p = poi.parse_line("武侯祠 | 武侯区 | 120 | 50 | 全周 | 上午 | 1 | 红墙竹影")
        self.assertEqual(p["name"], "武侯祠")
        self.assertEqual(p["minutes"], 120)
        self.assertEqual(p["price"], 50.0)
        self.assertIsNone(p["open_days"])
        self.assertEqual(p["best_time"], "上午")
        self.assertTrue(p["must"])
        self.assertEqual(p["note"], "红墙竹影")

    def test_minimal_line(self):
        p = poi.parse_line("锦里|武侯区|90|免费")
        self.assertEqual(p["best_time"], "全天")
        self.assertFalse(p["must"])

    def test_too_few_fields(self):
        with self.assertRaises(poi.PoiError):
            poi.parse_line("只有名字|区域")

    def test_min_minutes(self):
        p = poi.parse_line("小点|区|5|0")
        self.assertEqual(p["minutes"], 15)


class ReadListTest(unittest.TestCase):
    def test_header_skipped(self):
        text = "成都景点清单\n武侯祠 | 武侯区 | 120 | 50\n"
        ps = poi.read_list(text)
        self.assertEqual(len(ps), 1)

    def test_comments_skipped(self):
        ps = poi.read_list("# 注释\n武侯祠|武侯区|120|50\n")
        self.assertEqual(len(ps), 1)

    def test_empty(self):
        with self.assertRaises(poi.PoiError):
            poi.read_list("")

    def test_error_carries_line_no(self):
        with self.assertRaises(poi.PoiError) as cm:
            poi.read_list("武侯祠|武侯区|120|50\n坏行")
        self.assertIn("第 2 行", str(cm.exception))


class FindTest(unittest.TestCase):
    def setUp(self):
        self.pois = [
            {"name": "武侯祠", "area": "武侯区"},
            {"name": "大熊猫繁育研究基地", "area": "成华区"},
        ]

    def test_exact(self):
        self.assertEqual(poi.find(self.pois, "武侯祠")["area"], "武侯区")

    def test_contains(self):
        self.assertEqual(poi.find(self.pois, "熊猫")["name"], "大熊猫繁育研究基地")

    def test_missing(self):
        self.assertIsNone(poi.find(self.pois, "故宫"))

    def test_empty(self):
        self.assertIsNone(poi.find(self.pois, ""))

    def test_names(self):
        self.assertEqual(poi.names(self.pois), ["武侯祠", "大熊猫繁育研究基地"])


if __name__ == "__main__":
    unittest.main()
