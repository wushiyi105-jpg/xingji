import unittest

from xingji import verify

POIS = [
    {"name": "武侯祠", "area": "武侯区"},
    {"name": "大熊猫繁育研究基地", "area": "成华区"},
    {"name": "四川博物院", "area": "青羊区"},
]

PLAN = {
    "days": [{"day": 1, "weekday": "周一", "minutes": 540, "price": 105.0,
              "areas": ["成华区"],
              "pois": [{"name": "大熊猫繁育研究基地", "minutes": 210, "price": 55.0,
                        "start": "09:00", "end": "12:30", "must": True, "note": ""},
                       {"name": "杜甫草堂", "minutes": 100, "price": 50.0,
                        "start": "14:10", "end": "15:50", "must": False, "note": ""}]}],
    "unscheduled": [], "total_price": 105.0, "minutes_per_day": 540, "travel": 40, "budget": 900,
}


class PlacesTest(unittest.TestCase):
    def test_known_name_is_masked_out(self):
        # 清单里的名字先从文本里摘掉，剩下的才算「模型自己冒出来的」
        self.assertEqual(verify.places_in("上午去武侯祠看红墙", POIS), [])
        self.assertNotIn("武侯祠", verify._mask("上午去武侯祠", POIS))

    def test_half_sentence_not_place(self):
        # 「注意周一闭馆」里的「馆」曾被抓成地名
        self.assertEqual(verify.places_in("注意周一闭馆别白跑", POIS), [])

    def test_de_clause_not_place(self):
        self.assertEqual(verify.places_in("闹市里的寺院很安静", POIS), [])

    def test_route_phrase_not_place(self):
        self.assertEqual(verify.places_in("时长都按行程里来", POIS), [])

    def test_verb_prefix_cut_off(self):
        # 从后缀往前扩，碰到「去」就停，不要把半句话当地名
        self.assertEqual(verify.places_in("顺路去锦里古街", POIS), ["锦里古街"])

    def test_dedup(self):
        self.assertEqual(verify.places_in("锦里古街和锦里古街", POIS), ["锦里古街"])

    def test_empty(self):
        self.assertEqual(verify.places_in("", POIS), [])


class ForeignTest(unittest.TestCase):
    def test_known_place_passes(self):
        self.assertEqual(verify.foreign_places("武侯祠值得去", POIS), [])

    def test_alias_via_core_word(self):
        # 模型写「熊猫基地」，清单写「大熊猫繁育研究基地」，应视为同一处
        self.assertEqual(verify.foreign_places("熊猫基地要早去", POIS), [])

    def test_invented_place_flagged(self):
        self.assertEqual(verify.foreign_places("顺路去锦里古街", POIS), ["锦里古街"])

    def test_flagged_in_order(self):
        text = "先去锦里古街，再去宽窄巷子"
        out = verify.foreign_places(text, POIS)
        self.assertEqual(out, ["锦里古街", "宽窄巷子"])


class NumberTest(unittest.TestCase):
    def test_allowed_price(self):
        self.assertEqual(verify.check_numbers("门票 55 元", PLAN), [])
        self.assertEqual(verify.check_numbers("今天门票 105 元", PLAN), [])

    def test_unknown_price(self):
        out = verify.check_numbers("门票 30 元", PLAN)
        self.assertEqual(len(out), 1)
        self.assertIn("30", out[0])

    def test_minutes_allowed(self):
        self.assertEqual(verify.check_numbers("看 210 分钟", PLAN), [])

    def test_minutes_unknown(self):
        self.assertTrue(verify.check_numbers("逛 45 分钟", PLAN))

    def test_day_number_allowed(self):
        self.assertEqual(verify.check_numbers("第 1 天先去这里", PLAN), [])

    def test_distance_always_flagged(self):
        out = verify.check_numbers("走过去 1.5 公里", PLAN)
        self.assertIn("距离", out[0])

    def test_hours_range(self):
        self.assertEqual(verify.check_numbers("一共 3 小时", PLAN), [])
        self.assertTrue(verify.check_numbers("要 20 小时", PLAN))

    def test_plain_number_ignored(self):
        self.assertEqual(verify.check_numbers("2026 年的行程", PLAN), [])

    def test_claims_pairs(self):
        self.assertEqual(verify.number_claims("55 元 210 分钟"), [(55.0, "元"), (210.0, "分钟")])


class MergeTest(unittest.TestCase):
    def test_merge_dedup(self):
        a = {"foreign": ["锦里古街"], "numbers": ["30 元 —— 行程里没有这个数"]}
        b = {"foreign": ["锦里古街", "宽窄巷子"], "numbers": []}
        m = verify.merge_checks([a, b])
        self.assertEqual(m["foreign"], ["锦里古街", "宽窄巷子"])
        self.assertEqual(len(m["numbers"]), 1)

    def test_check_text(self):
        out = verify.check_text("逛完武侯祠门票 30 元", POIS, PLAN)
        self.assertEqual(out["foreign"], [])
        self.assertTrue(out["numbers"])

    def test_merge_empty(self):
        self.assertEqual(verify.merge_checks([]), {"foreign": [], "numbers": []})


if __name__ == "__main__":
    unittest.main()

