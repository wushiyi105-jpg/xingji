"""网页端：左边选清单、给参数，右边出排程；再点「写解说」让模型讲一遍。"""

from __future__ import annotations

import json
import threading
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import plan as PL, poi as P, store, story as ST

MAX_BODY = 400_000

PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>行迹 · 行程规划</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--text:#c9d1d9;--dim:#8b949e;
--ok:#7ee787;--warn:#e3b341;--bad:#ff7b72;--blue:#79c0ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.75 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:22px;margin:0 0 6px}
.sub{color:var(--dim);font-size:13px;margin-bottom:20px}
.panel{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:16px}
.panel h2{font-size:14px;color:var(--dim);font-weight:400;margin:0 0 12px;letter-spacing:.5px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
label{font-size:13px;color:var(--dim)}
input,textarea,select{background:#0b0f14;color:var(--text);border:1px solid var(--line);border-radius:6px;
padding:7px 10px;font:14px ui-monospace,Consolas,monospace}
input[type=number]{width:88px}
textarea{width:100%;min-height:130px;margin-top:8px;font-size:13px}
button{background:#1f6feb;color:#fff;border:0;border-radius:7px;padding:9px 16px;font-size:14px;cursor:pointer}
button.ghost{background:#21262d;color:var(--text);border:1px solid var(--line)}
button:disabled{opacity:.45;cursor:not-allowed}
.day{background:#0b0f14;border-left:3px solid #1f6feb;border-radius:0 8px 8px 0;padding:12px 14px;margin:12px 0}
.day .head{font-size:14px;color:var(--blue);margin-bottom:6px}
.slot{display:flex;gap:10px;padding:5px 0;border-bottom:1px dashed #21262d;font-size:14px;align-items:baseline}
.time{color:var(--dim);font-family:ui-monospace,Consolas,monospace;white-space:nowrap}
.pname{flex:1}
.star{color:var(--ok)}
.meta{color:var(--dim);font-size:13px;margin-top:8px}
.warnbox{background:#3d2b00;border:1px solid #6b4a00;border-radius:8px;padding:10px 12px;margin:12px 0;font-size:13px;color:#f0d58c}
.tips{margin-top:12px}
.tips li{margin:4px 0}
.err{color:var(--bad);font-size:13px}
.spin{color:var(--dim);font-size:13px}
</style></head><body><div class="wrap">
<h1>行迹 <span style="color:var(--dim);font-size:13px;font-weight:400">本地排程 · 模型只讲不编</span></h1>
<div class="sub">塞不下的点会明确告诉你为什么没排进去，而不是被模型悄悄挪到别的天。</div>

<div class="panel">
  <h2>景点清单</h2>
  <div class="row">
    <label>目的地</label><input id="dest" value="成都" size="10">
    <label>天数</label><input id="days" type="number" value="3" min="1" max="30">
    <label>每天分钟</label><input id="minutes" type="number" value="540" step="30">
    <label>预算</label><input id="budget" type="number" value="900" step="50">
    <label>第1天是</label>
    <select id="wd"><option value="1">周一</option><option value="2">周二</option>
    <option value="3">周三</option><option value="4">周四</option><option value="5">周五</option>
    <option value="6">周六</option><option value="0">周日</option></select>
  </div>
  <div class="row" style="margin-top:10px">
    <label>必去（逗号分隔）</label><input id="must" value="大熊猫繁育研究基地,武侯祠" size="34">
  </div>
  <div class="row" style="margin-top:12px">
    <button id="go">排 一 下</button>
    <button id="story" class="ghost" disabled>写 解 说</button>
    <span class="meta" id="hint"></span>
  </div>
  <div style="margin-top:8px"><label>清单（每行：名称|区域|分钟|门票|开放日|时段|必去|备注）</label>
  <textarea id="list" placeholder="武侯祠 | 武侯区 | 120 | 50 | 全周 | 上午 | 0 | 红墙竹影"></textarea></div>
  <div class="row" style="margin-top:8px"><button id="imp" class="ghost">导入这份清单</button>
  <span class="meta" id="impmsg"></span></div>
</div>

<div class="panel">
  <h2>行程</h2>
  <div id="plan"><div class="spin">导入清单后点「排一下」。</div></div>
  <div id="narr"></div>
</div>

<div class="panel">
  <h2>历史</h2>
  <div id="hist" class="meta">…</div>
</div>

<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s==null?'':s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
let tripId=null;

async function jpost(path,body){
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  return [r.status, await r.json().catch(()=>({}))];
}
async function jget(path){
  const r=await fetch(path); return await r.json();
}

function renderPlan(p,dest){
  let h=`<div class="meta">${esc(dest)} · ${p.days.length} 天 · 门票合计 ${p.total_price} 元</div>`;
  p.days.forEach(d=>{
    if(!d.pois.length){h+=`<div class="day"><div class="head">第 ${d.day} 天（${d.weekday}）</div>
      <div class="err">这天空着</div></div>`;return}
    h+=`<div class="day"><div class="head">第 ${d.day} 天（${d.weekday}）
      · ${d.areas.join(' / ')} · ${d.minutes} 分钟 · ${d.price} 元</div>`;
    d.pois.forEach(x=>{
      h+=`<div class="slot"><span class="time">${x.start}-${x.end}</span>
      <span class="pname">${x.must?'<span class="star">★</span> ':''}${esc(x.name)}</span>
      <span class="time">${x.minutes} 分钟</span><span class="time">${x.price?x.price+' 元':'免费'}</span></div>`;
    });
    h+=`</div>`;
  });
  if(p.unscheduled.length){
    h+=`<div class="warnbox">没排进去：<br>`+
      p.unscheduled.map(u=>`· ${esc(u.name)} —— ${esc(u.why)}`).join('<br>')+`</div>`;
  }
  return h;
}

$('imp').onclick=async()=>{
  const dest=$('dest').value.trim();
  if(!dest) return;
  const [st,d]=await jpost('/api/import',{destination:dest,text:$('list').value});
  $('impmsg').textContent = st===200? `导入 ${d.count} 个点` : (d.error||'导入失败');
  $('hint').textContent = st===200? '清单已就位，可以排了。' : '';
  loadHist();
};

$('go').onclick=async()=>{
  const body={destination:$('dest').value.trim(),days:+$('days').value,
    minutes:+$('minutes').value,budget:+$('budget').value||null,
    weekday:+$('wd').value,must:$('must').value};
  const [st,d]=await jpost('/api/plan',body);
  if(st!==200){$('plan').innerHTML=`<div class="err">${esc(d.error||'没排出来')}</div>`;return}
  tripId=d.trip_id;
  $('plan').innerHTML=renderPlan(d.plan,d.destination);
  $('narr').innerHTML='';
  $('story').disabled=false;
  $('hint').textContent=`行程 #${tripId} 已存`;
  loadHist();
};

$('story').onclick=async()=>{
  if(!tripId) return;
  const b=$('story'); b.disabled=true; b.textContent='模型在写…';
  $('narr').innerHTML='<div class="spin">十几秒…</div>';
  try{
    const [st,d]=await jpost('/api/story',{id:tripId});
    if(st!==200){$('narr').innerHTML=`<div class="err">${esc(d.error||'没写出来')}</div>`;return}
    let h='';
    d.story.days.forEach(x=>{
      h+=`<div class="day"><div class="head">第 ${x.day} 天 · ${esc(x.title)}</div>
      <div>${esc(x.text)}</div></div>`;
    });
    if(d.story.tips.length) h+=`<div class="tips">提醒：<ul>`+
      d.story.tips.map(t=>`<li>${esc(t)}</li>`).join('')+'</ul></div>';
    if(d.story.foreign.length) h+=`<div class="warnbox">清单里没有这些地方：${esc(d.story.foreign.join('、'))}</div>`;
    if(d.story.numbers.length) h+=`<div class="warnbox">数字对不上：<br>${
      d.story.numbers.map(esc).join('<br>')}</div>`;
    $('narr').innerHTML=h;
  }finally{ b.disabled=false; b.textContent='写 解 说'; }
};

async function loadHist(){
  const d=await jget('/api/list');
  let h=d.trips.length? d.trips.slice(0,6).map(t=>
    `#${t.id} ${esc(t.destination)} ${t.days} 天 · ${t.created}`).join('<br>') : '还没有行程。';
  if(d.destinations.length) h+=`<br><br>已有清单：${d.destinations.map(x=>
    esc(x.destination)+'('+x.n+' 个点)').join('、')}`;
  $('hist').innerHTML=h;
}
loadHist();
</script></div></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "xingji/1.0"

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text):
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._html(PAGE)
            return
        if path == "/api/list":
            conn = self.server.conn
            with self.server.lock:
                self._json({"trips": store.list_trips(conn), "destinations": store.destinations(conn)})
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path not in ("/api/import", "/api/plan", "/api/story"):
            self._json({"error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._json({"error": "内容太长"}, 413)
            return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json({"error": "body 不是 JSON"}, 400)
            return

        if path == "/api/import":
            self._import(payload)
        elif path == "/api/plan":
            self._plan(payload)
        else:
            self._story(payload)

    def _import(self, payload):
        dest = (payload.get("destination") or "").strip()
        text = payload.get("text") or ""
        if not dest or not text.strip():
            self._json({"error": "要有目的地和清单内容"}, 400)
            return
        try:
            pois = P.read_list(text)
        except P.PoiError as e:
            self._json({"error": str(e)}, 400)
            return
        with self.server.lock:
            n = store.import_pois(self.server.conn, dest, pois)
        self._json({"count": n})

    def _plan(self, payload):
        dest = (payload.get("destination") or "").strip()
        if not dest:
            self._json({"error": "没有目的地"}, 400)
            return
        conn = self.server.conn
        with self.server.lock:
            pois = store.pois_of(conn, dest)
        if not pois:
            self._json({"error": f"「{dest}」还没有清单，先贴一份导入"}, 400)
            return
        try:
            days = max(1, min(30, int(payload.get("days") or 3)))
            minutes = max(120, min(900, int(payload.get("minutes") or 540)))
        except (TypeError, ValueError):
            self._json({"error": "天数和分钟要填数字"}, 400)
            return
        budget = payload.get("budget")
        try:
            budget = float(budget) if budget not in (None, "", "null") else None
        except (TypeError, ValueError):
            budget = None
        must = [m.strip() for m in str(payload.get("must") or "").split(",") if m.strip()]
        weekday = int(payload.get("weekday", 1)) % 7

        result = PL.schedule(pois, days, minutes, weekday, must, budget)
        with self.server.lock:
            trip_id = store.save_trip(conn, dest, days, minutes, budget,
                                      str(payload.get("prefs") or ""), result,
                                      created=datetime.now().strftime("%Y-%m-%d %H:%M"))
        self._json({"trip_id": trip_id, "destination": dest, "plan": result})

    def _story(self, payload):
        conn = self.server.conn
        try:
            tid = int(payload.get("id"))
        except (TypeError, ValueError):
            self._json({"error": "没有行程 id"}, 400)
            return
        with self.server.lock:
            trip = store.get_trip(conn, tid)
            pois = store.pois_of(conn, trip["destination"]) if trip else []
        if not trip:
            self._json({"error": f"没有行程 [{tid}]"}, 404)
            return
        if not pois:
            self._json({"error": "这份清单没了，重新导入一次"}, 400)
            return
        s = ST.write(trip["plan"], pois, trip["destination"], trip["prefs"])
        if s["error"]:
            self._json({"error": s["error"], "story": s}, 502)
            return
        with self.server.lock:
            store.save_story(conn, tid, s)
        self._json({"story": s})


def make_server(conn, port: int = 0, db: str = "") -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.conn = conn
    srv.db = db
    srv.lock = threading.Lock()
    return srv

