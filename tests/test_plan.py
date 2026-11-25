import unittest

from xingji import plan


def mk(name, area="A", minutes=60, price=0.0, open_days=None, best="全天", must=False):
    return {"name": name, "area": area, "minutes": minutes, "price": price,
            "open_days": open_days, "open_spec": "全周", "best_time": best,
            "must": must, "note": ""}


class ScheduleTest(unittest.TestCase):
    def test_everything_fits(self):
        pois = [mk("甲", minutes=30), mk("乙", minutes=30)]
        r = plan.schedule(pois, 1, 480)
        self.assertEqual(len(r["days"][0]["pois"]), 2)
        self.assertEqual(r["unscheduled"], [])

    def test_time_overflow_goes_to_next_day(self):
        pois = [mk("甲", minutes=400), mk("乙", minutes=400)]
        r = plan.schedule(pois, 2, 480)
        self.assertEqual(len(r["days"][0]["pois"]), 1)
        self.assertEqual(len(r["days"][1]["pois"]), 1)

    def test_overflow_reported_when_no_room(self):
        pois = [mk(f"点{i}", minutes=200) for i in range(5)]
        r = plan.schedule(pois, 2, 480)
        self.assertGreaterEqual(len(r["unscheduled"]), 1)
        self.assertIn("时间", r["unscheduled"][0]["why"])

    def test_closed_day_skipped(self):
        pois = [mk("周一闭的馆", open_days=[0, 2, 3, 4, 5, 6]), mk("周一开的", minutes=30)]
        r = plan.schedule(pois, 1, 480, weekday_start=1)
        names = [p["name"] for p in r["days"][0]["pois"]]
        self.assertIn("周一开的", names)
        self.assertNotIn("周一闭的馆", names)

    def test_closed_all_days_reason(self):
        pois = [mk("只周二开", open_days=[2])]
        r = plan.schedule(pois, 2, 480, weekday_start=3)  # 只有周三周四，周二开的馆排不进
        self.assertIn("闭馆", r["unscheduled"][0]["why"])

    def test_budget_capped(self):
        pois = [mk("贵", price=500.0), mk("便宜", price=10.0)]
        r = plan.schedule(pois, 1, 480, budget=100)
        self.assertEqual([p["name"] for p in r["days"][0]["pois"]], ["便宜"])
        self.assertLessEqual(r["total_price"], 100)

    def test_must_is_scheduled_first(self):
        pois = [mk("普通甲", minutes=200, area="A"), mk("必去", minutes=200, area="B", must=True)]
        r = plan.schedule(pois, 1, 480, must=["必去"])
        self.assertEqual(r["days"][0]["pois"][0]["name"], "必去")

    def test_unknown_must(self):
        r = plan.schedule([mk("甲")], 1, 480, must=["不存在"])
        self.assertIn("不存在", r["unknown_must"])

    def test_area_travel_charged(self):
        pois = [mk("甲", area="A", minutes=100), mk("乙", area="B", minutes=100)]
        r = plan.schedule(pois, 1, 480, travel=40)
        self.assertEqual(r["days"][0]["minutes"], 300)  # 100 + 100 + 40 通勤 + 60 午饭

    def test_same_area_no_travel(self):
        pois = [mk("甲", area="A", minutes=100), mk("乙", area="A", minutes=100)]
        self.assertEqual(plan.schedule(pois, 1, 480)["days"][0]["minutes"], 200)

    def test_morning_before_afternoon(self):
        pois = [mk("下午的", minutes=100, best="下午"), mk("上午的", minutes=100, best="上午")]
        r = plan.schedule(pois, 1, 480)
        self.assertEqual(r["days"][0]["pois"][0]["name"], "上午的")

    def test_lunch_inserted(self):
        # 第一项到 12:30，第二项前插入一小时午饭
        pois = [mk("甲", minutes=210, best="上午"), mk("乙", area="B", minutes=60, best="下午")]
        r = plan.schedule(pois, 1, 480, travel=40)
        second = r["days"][0]["pois"][1]
        self.assertEqual(second["start"], "14:10")
        self.assertEqual(r["days"][0]["minutes"], 210 + 40 + 60 + 60)

    def test_times_are_strings(self):
        r = plan.schedule([mk("甲", minutes=60)], 1, 480)
        self.assertEqual(r["days"][0]["pois"][0]["start"], "09:00")
        self.assertEqual(r["days"][0]["pois"][0]["end"], "10:00")

    def test_weekday_labels(self):
        r = plan.schedule([mk("甲")], 3, 480, weekday_start=5)
        self.assertEqual([d["weekday"] for d in r["days"]], ["周五", "周六", "周日"])

    def test_zero_items(self):
        r = plan.schedule([], 2, 480)
        self.assertEqual(len(r["days"]), 2)
        self.assertEqual(r["days"][0]["pois"], [])


class BusyTest(unittest.TestCase):
    def test_ratio(self):
        r = plan.schedule([mk("甲", minutes=100)], 1, 200)
        self.assertAlmostEqual(plan.busy_ratio(r), 0.5)

    def test_empty(self):
        self.assertEqual(plan.busy_ratio({"days": []}), 0.0)


class CheckTest(unittest.TestCase):
    def test_empty_day_warning(self):
        notes = plan.check({"days": [{"day": 1, "weekday": "周一", "pois": [], "minutes": 0,
                                     "price": 0, "areas": []}], "minutes_per_day": 480})
        self.assertTrue(any("空" in n for n in notes))

    def test_overpacked(self):
        notes = plan.check({"days": [{"day": 1, "weekday": "周一", "pois": [], "minutes": 470,
                                     "price": 0, "areas": []}], "minutes_per_day": 480})
        self.assertTrue(any("赶" in n for n in notes))

    def test_loose(self):
        notes = plan.check({"days": [{"day": 1, "weekday": "周一", "pois": [], "minutes": 100,
                                     "price": 0, "areas": []}], "minutes_per_day": 480})
        self.assertTrue(any("再塞" in n for n in notes))

    def test_budget_over(self):
        notes = plan.check({"days": [], "budget": 100, "total_price": 300, "minutes_per_day": 480})
        self.assertTrue(any("超过预算" in n for n in notes))


class RenderTest(unittest.TestCase):
    def test_renders_names_and_times(self):
        r = plan.schedule([mk("甲", minutes=60, price=30.0), mk("乙", minutes=30, must=True)],
                          1, 480)
        text = plan.render(r, "成都")
        self.assertIn("成都", text)
        self.assertIn("甲", text)
        self.assertIn("09:00", text)
        self.assertIn("★ 09:00", text)

    def test_unscheduled_listed(self):
        r = plan.schedule([mk(f"点{i}", minutes=300) for i in range(3)], 1, 480)
        self.assertIn("没排进去", plan.render(r))

    def test_empty_day(self):
        r = plan.schedule([], 1, 480)
        self.assertIn("空", plan.render(r))


if __name__ == "__main__":
    unittest.main()




