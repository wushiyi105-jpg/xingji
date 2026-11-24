"""命令行入口。"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

from . import plan as PL, poi as P, store, story as ST

_OPENED: list = []


def _open(args):
    conn = store.connect(args.db)
    _OPENED.append(conn)
    return conn


def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def cmd_import(args) -> int:
    conn = _open(args)
    text = _read(args.file)
    try:
        pois = P.read_list(text)
    except P.PoiError as e:
        print(f"✗ {e}")
        return 1
    dest = args.destination or args.file.split(os.sep)[-1].split(".")[0]
    n = store.import_pois(conn, dest, pois)
    print(f"· {dest}：导入 {n} 个点")
    must = [p["name"] for p in pois if p["must"]]
    closed = [p["name"] for p in pois if p["open_days"] is not None]
    if must:
        print(f"  必去：{'、'.join(must)}")
    if closed:
        print(f"  有闭馆日：{'、'.join(closed)}")
    return 0


def cmd_plan(args) -> int:
    conn = _open(args)
    pois = store.pois_of(conn, args.destination)
    if not pois:
        print(f"✗ 「{args.destination}」还没有景点清单，先 import 一份")
        return 1

    must = [m.strip() for m in (args.must or "").split(",") if m.strip()]
    result = PL.schedule(pois, args.days, args.minutes, args.weekday,
                         must, args.budget, args.travel)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(PL.render(result, args.destination))

    trip_id = store.save_trip(conn, args.destination, args.days, args.minutes,
                              args.budget, args.prefs or "", result, created=_now())
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(PL.render(result, args.destination))
        print(f"\n· 写到了 {args.out}")
    print(f"· 存为行程 [{trip_id}]，想看解说跑 `story {trip_id}`")
    return 0


def cmd_story(args) -> int:
    conn = _open(args)
    trip = store.get_trip(conn, args.id)
    if not trip:
        print(f"✗ 没有行程 [{args.id}]")
        return 1
    pois = store.pois_of(conn, trip["destination"])
    if not pois:
        print(f"✗ 「{trip['destination']}」的景点清单没了，重新 import 一次")
        return 1

    print("等模型写一遍……")
    s = ST.write(trip["plan"], pois, trip["destination"], args.prefs or trip["prefs"])
    if s["error"]:
        print(f"✗ {s['error']}")
        return 0
    print(ST.render(s, trip["plan"]))
    flags = ST.flagged(s)
    print(f"\n· 核验：清单外地名 {len(s['foreign'])} 个，对不上的数字 {len(s['numbers'])} 处"
          + ("（都对得上）" if flags == 0 else ""))
    store.save_story(conn, trip["id"], s)
    return 0


def cmd_list(args) -> int:
    conn = _open(args)
    rows = store.list_trips(conn)
    if not rows:
        print("还没有行程。")
    else:
        print(f"{'ID':>3}  {'天':>2}  {'每天分钟':>6}  {'预算':>6}  目的地        时间")
        for r in rows:
            budget = "-" if r["budget"] is None else f"{r['budget']:.0f}"
            print(f"{r['id']:>3}  {r['days']:>2}  {r['minutes_per_day']:>6}  {budget:>6}"
                  f"  {r['destination']:<12} {r['created']}")
    dests = store.destinations(conn)
    if dests:
        print("\n已有清单：" + "、".join(f"{d['destination']}({d['n']} 个点)" for d in dests))
    return 0


def cmd_show(args) -> int:
    conn = _open(args)
    trip = store.get_trip(conn, args.id)
    if not trip:
        print(f"✗ 没有行程 [{args.id}]")
        return 1
    print(PL.render(trip["plan"], trip["destination"]))
    if trip["story"] and not trip["story"].get("error"):
        print("\n" + ST.render(trip["story"], trip["plan"]))
    return 0


def cmd_rm(args) -> int:
    conn = _open(args)
    print("· 删掉了" if store.delete_trip(conn, args.id) else "✗ 没有这个行程")
    return 0


def cmd_stats(args) -> int:
    conn = _open(args)
    s = store.stats(conn)
    print(f"行程 {s['trips']} 份 · 涉及 {s['destinations']} 个目的地 · 清单里 {s['pois']} 个点")
    if s["trips"]:
        print(f"合计 {s['unscheduled']} 个点没排进去（每次都会告诉你为什么）")
    return 0


def cmd_serve(args) -> int:
    from . import web
    conn = store.connect(args.db)
    srv = web.make_server(conn, port=args.port, db=args.db)
    host, port = srv.server_address
    print(f"行迹已起在 http://127.0.0.1:{port}")
    print("Ctrl+C 停止")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n停了")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="xingji", description="行程规划：本地排程，模型只讲不编")
    p.add_argument("--db", default="data/xingji.db")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("import", help="导入景点清单（竖线分隔的文本）")
    i.add_argument("file")
    i.add_argument("--destination", default="")
    i.set_defaults(func=cmd_import)

    pl = sub.add_parser("plan", help="排一份行程")
    pl.add_argument("--destination", required=True)
    pl.add_argument("--days", type=int, default=3)
    pl.add_argument("--minutes", type=int, default=540, help="每天可用分钟（含午饭）")
    pl.add_argument("--weekday", type=int, default=1, help="第 1 天是周几：周日=0，周一=1（默认周一）")
    pl.add_argument("--must", default="", help="必去点，逗号分隔")
    pl.add_argument("--budget", type=float, default=None, help="门票预算，元")
    pl.add_argument("--travel", type=int, default=PL.TRAVEL_MIN, help="跨区域通勤分钟")
    pl.add_argument("--prefs", default="")
    pl.add_argument("--json", action="store_true")
    pl.add_argument("--out", default="")
    pl.set_defaults(func=cmd_plan)

    st = sub.add_parser("story", help="让模型把行程写成一段话")
    st.add_argument("id", type=int)
    st.add_argument("--prefs", default="")
    st.set_defaults(func=cmd_story)

    sub.add_parser("list", help="所有行程").set_defaults(func=cmd_list)

    s = sub.add_parser("show", help="看某一份")
    s.add_argument("id", type=int)
    s.set_defaults(func=cmd_show)

    r = sub.add_parser("rm", help="删一份")
    r.add_argument("id", type=int)
    r.set_defaults(func=cmd_rm)

    sub.add_parser("stats", help="统计").set_defaults(func=cmd_stats)

    v = sub.add_parser("serve", help="起网页")
    v.add_argument("--port", type=int, default=8776)
    v.set_defaults(func=cmd_serve)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    finally:
        while _OPENED:
            try:
                _OPENED.pop().close()
            except Exception:  # noqa: BLE001
                pass


