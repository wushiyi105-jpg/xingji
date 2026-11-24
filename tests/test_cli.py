import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from xingji import cli, llm, store

LIST = "\n".join([
    "武侯祠 | 武侯区 | 120 | 50 | 全周 | 上午 | 1 | 红墙竹影",
    "四川博物院 | 青羊区 | 180 | 免费 | 周一休 | 上午 | 0 | 周一闭馆",
    "锦里 | 武侯区 | 90 | 免费 | 全周 | 下午 | 0 | 灯好看",
])


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "t.db")
        self.list_path = os.path.join(self.tmp, "清单.txt")
        with open(self.list_path, "w", encoding="utf-8") as f:
            f.write(LIST)

    def run_cli(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["--db", self.db] + argv)
        return code, buf.getvalue()

    def import_list(self):
        return self.run_cli(["import", self.list_path, "--destination", "成都"])

    def test_import(self):
        code, out = self.import_list()
        self.assertEqual(code, 0)
        self.assertIn("导入 3 个点", out)
        self.assertIn("武侯祠", out)

    def test_import_bad_file(self):
        bad = os.path.join(self.tmp, "bad.txt")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("只有名字")
        code, out = self.run_cli(["import", bad, "--destination", "成都"])
        self.assertEqual(code, 1)
        self.assertIn("清单是空的", out)

    def test_plan_without_list(self):
        code, out = self.run_cli(["plan", "--destination", "西安"])
        self.assertEqual(code, 1)
        self.assertIn("还没有景点清单", out)

    def test_plan(self):
        self.import_list()
        code, out = self.run_cli(["plan", "--destination", "成都", "--days", "1",
                                  "--minutes", "540", "--must", "武侯祠"])
        self.assertEqual(code, 0)
        self.assertIn("第 1 天", out)
        self.assertIn("存为行程", out)

    def test_plan_json(self):
        self.import_list()
        code, out = self.run_cli(["plan", "--destination", "成都", "--days", "1", "--json"])
        self.assertIn('"days"', out)

    def test_plan_out_file(self):
        self.import_list()
        target = os.path.join(self.tmp, "报告.md")
        code, out = self.run_cli(["plan", "--destination", "成都", "--days", "1", "--out", target])
        self.assertTrue(os.path.isfile(target))

    def test_plan_closed_day(self):
        self.import_list()
        code, out = self.run_cli(["plan", "--destination", "成都", "--days", "1",
                                  "--weekday", "1", "--must", "四川博物院"])
        self.assertEqual(code, 0)
        self.assertNotIn("09:00  四川博物院", out)

    def test_story_model_down(self):
        self.import_list()
        self.run_cli(["plan", "--destination", "成都", "--days", "1"])
        with patch.object(llm, "chat", side_effect=llm.LLMError("429")):
            code, out = self.run_cli(["story", "1"])
        self.assertEqual(code, 0)
        self.assertIn("模型没回", out)

    def test_story_flags_foreign(self):
        self.import_list()
        self.run_cli(["plan", "--destination", "成都", "--days", "1"])
        payload = json.dumps({"days": [{"day": 1, "title": "第一天",
                                       "text": "先去武侯祠，再去宽窄巷子"}],
                              "tips": ["带伞"]}, ensure_ascii=False)
        with patch.object(llm, "chat", return_value=payload):
            code, out = self.run_cli(["story", "1"])
        self.assertIn("清单里没有这些地方", out)
        self.assertIn("宽窄巷子", out)

    def test_story_retry_on_broken_json(self):
        self.import_list()
        self.run_cli(["plan", "--destination", "成都", "--days", "1"])
        good = json.dumps({"days": [], "tips": ["带伞"]}, ensure_ascii=False)
        with patch.object(llm, "chat", side_effect=['{"days": [', good]) as m:
            self.run_cli(["story", "1"])
        self.assertEqual(m.call_count, 2)

    def test_story_missing_trip(self):
        code, out = self.run_cli(["story", "99"])
        self.assertEqual(code, 1)
        self.assertIn("没有行程", out)

    def test_list_empty(self):
        code, out = self.run_cli(["list"])
        self.assertIn("还没有行程", out)

    def test_show_and_rm(self):
        self.import_list()
        self.run_cli(["plan", "--destination", "成都", "--days", "1"])
        code, out = self.run_cli(["show", "1"])
        self.assertIn("第 1 天", out)
        code, out = self.run_cli(["rm", "1"])
        self.assertIn("删掉了", out)

    def test_stats(self):
        self.import_list()
        self.run_cli(["plan", "--destination", "成都", "--days", "1"])
        code, out = self.run_cli(["stats"])
        self.assertIn("行程 1 份", out)

    def test_subcommands(self):
        p = cli.build_parser()
        names = p._subparsers._group_actions[0].choices
        for sub in ("import", "plan", "story", "list", "show", "rm", "stats", "serve"):
            self.assertIn(sub, names)


if __name__ == "__main__":
    unittest.main()


