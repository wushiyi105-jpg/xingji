import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from xingji import llm, store, web

LIST = "\n".join([
    "武侯祠 | 武侯区 | 120 | 50 | 全周 | 上午 | 1 | 红墙竹影",
    "锦里 | 武侯区 | 90 | 免费 | 全周 | 下午 | 0 | 灯好看",
])


class WebTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conn = store.connect(os.path.join(self.tmp, "t.db"))
        self.srv = web.make_server(self.conn, port=0)
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.t.join(timeout=3)
        self.conn.close()

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as r:
            return r.status, r.read().decode("utf-8")

    def post(self, path, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

    def test_index(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("行迹", body)
        self.assertIn("/api/plan", body)

    def test_list(self):
        d = json.loads(self.get("/api/list")[1])
        self.assertEqual(d["trips"], [])
        self.assertEqual(d["destinations"], [])

    def test_import(self):
        status, body = self.post("/api/import", {"destination": "成都", "text": LIST})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["count"], 2)

    def test_import_bad(self):
        status, body = self.post("/api/import", {"destination": "成都", "text": "坏"})
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(body))

    def test_import_missing_fields(self):
        status, _ = self.post("/api/import", {"destination": "", "text": LIST})
        self.assertEqual(status, 400)

    def test_plan_needs_list(self):
        status, body = self.post("/api/plan", {"destination": "西安"})
        self.assertEqual(status, 400)
        self.assertIn("清单", json.loads(body)["error"])

    def test_plan(self):
        self.post("/api/import", {"destination": "成都", "text": LIST})
        status, body = self.post("/api/plan", {"destination": "成都", "days": 1,
                                               "minutes": 540, "must": "武侯祠", "budget": 100})
        self.assertEqual(status, 200)
        d = json.loads(body)
        self.assertEqual(len(d["plan"]["days"]), 1)
        self.assertIn("trip_id", d)

    def test_plan_clamps_days(self):
        self.post("/api/import", {"destination": "成都", "text": LIST})
        status, body = self.post("/api/plan", {"destination": "成都", "days": 99})
        self.assertEqual(json.loads(body)["plan"]["days"][-1]["day"], 30)

    def test_plan_bad_days(self):
        self.post("/api/import", {"destination": "成都", "text": LIST})
        status, _ = self.post("/api/plan", {"destination": "成都", "days": "三天"})
        self.assertEqual(status, 400)

    def test_story(self):
        self.post("/api/import", {"destination": "成都", "text": LIST})
        tid = json.loads(self.post("/api/plan", {"destination": "成都", "days": 1})[1])["trip_id"]
        payload = json.dumps({"days": [{"day": 1, "title": "开局", "text": "先去武侯祠"}],
                              "tips": ["带伞"]}, ensure_ascii=False)
        with patch.object(llm, "chat", return_value=payload):
            status, body = self.post("/api/story", {"id": tid})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["story"]["days"][0]["title"], "开局")

    def test_story_model_down(self):
        self.post("/api/import", {"destination": "成都", "text": LIST})
        tid = json.loads(self.post("/api/plan", {"destination": "成都", "days": 1})[1])["trip_id"]
        with patch.object(llm, "chat", side_effect=llm.LLMError("429")):
            status, body = self.post("/api/story", {"id": tid})
        self.assertEqual(status, 502)

    def test_story_missing_trip(self):
        status, _ = self.post("/api/story", {"id": 999})
        self.assertEqual(status, 404)

    def test_unknown_paths(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get("/api/nope")
        self.assertEqual(cm.exception.code, 404)
        self.assertEqual(self.post("/api/nope", {})[0], 404)

    def test_bad_json(self):
        req = urllib.request.Request(self.base + "/api/plan", data=b"not json",
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)


if __name__ == "__main__":
    unittest.main()
