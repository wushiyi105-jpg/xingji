"""存储：景点清单按目的地分，行程单独一张表。"""

from __future__ import annotations

import json
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS attractions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    destination TEXT NOT NULL,
    name TEXT NOT NULL,
    area TEXT NOT NULL DEFAULT '市区',
    minutes INTEGER NOT NULL DEFAULT 90,
    price REAL NOT NULL DEFAULT 0,
    open_spec TEXT NOT NULL DEFAULT '全周',
    open_days TEXT,
    best_time TEXT NOT NULL DEFAULT '全天',
    must INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    UNIQUE (destination, name)
);
CREATE TABLE IF NOT EXISTS trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    destination TEXT NOT NULL,
    days INTEGER NOT NULL,
    minutes_per_day INTEGER NOT NULL,
    budget REAL,
    prefs TEXT NOT NULL DEFAULT '',
    plan TEXT NOT NULL DEFAULT '{}',
    story TEXT NOT NULL DEFAULT '{}',
    created TEXT NOT NULL
);
"""


def connect(path: str = "data/xingji.db") -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def import_pois(conn, destination: str, pois: list[dict], replace: bool = True) -> int:
    """导入清单。默认整份替换：同一目的地改了清单就该是新的，不该留旧点。"""
    if replace:
        conn.execute("DELETE FROM attractions WHERE destination=?", (destination,))
    for p in pois:
        conn.execute(
            "INSERT OR REPLACE INTO attractions"
            " (destination, name, area, minutes, price, open_spec, open_days, best_time, must, note)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (destination, p["name"], p["area"], p["minutes"], p["price"], p["open_spec"],
             json.dumps(p["open_days"]) if p["open_days"] is not None else None,
             p["best_time"], 1 if p["must"] else 0, p["note"]),
        )
    conn.commit()
    return len(pois)


def _row_to_poi(row) -> dict:
    d = dict(row)
    raw = d.get("open_days")
    d["open_days"] = json.loads(raw) if raw else None
    d["must"] = bool(d["must"])
    return d


def pois_of(conn, destination: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM attractions WHERE destination=? ORDER BY area, name", (destination,)).fetchall()
    return [_row_to_poi(r) for r in rows]


def destinations(conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT destination, COUNT(*) AS n FROM attractions GROUP BY destination ORDER BY destination")]


def save_trip(conn, destination: str, days: int, minutes_per_day: int, budget,
              prefs: str, plan: dict, story: dict | None = None, created: str = "") -> int:
    cur = conn.execute(
        "INSERT INTO trips (destination, days, minutes_per_day, budget, prefs, plan, story, created)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (destination, days, minutes_per_day, budget, prefs,
         json.dumps(plan, ensure_ascii=False), json.dumps(story or {}, ensure_ascii=False), created),
    )
    conn.commit()
    return cur.lastrowid


def save_story(conn, trip_id: int, story: dict) -> bool:
    cur = conn.execute("UPDATE trips SET story=? WHERE id=?",
                       (json.dumps(story, ensure_ascii=False), trip_id))
    conn.commit()
    return cur.rowcount > 0


def get_trip(conn, trip_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    for k in ("plan", "story"):
        try:
            d[k] = json.loads(d.get(k) or "{}")
        except json.JSONDecodeError:
            d[k] = {}
    return d


def list_trips(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT id, destination, days, minutes_per_day, budget, created,"
        " length(plan) AS plan_len FROM trips ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def delete_trip(conn, trip_id: int) -> bool:
    cur = conn.execute("DELETE FROM trips WHERE id=?", (trip_id,))
    conn.commit()
    return cur.rowcount > 0


def stats(conn) -> dict:
    trips = conn.execute("SELECT COUNT(*) AS n FROM trips").fetchone()["n"]
    pois = conn.execute("SELECT COUNT(*) AS n FROM attractions").fetchone()["n"]
    dests = conn.execute("SELECT COUNT(DISTINCT destination) AS n FROM trips").fetchone()["n"]
    unscheduled = 0
    for row in conn.execute("SELECT plan FROM trips"):
        try:
            unscheduled += len(json.loads(row["plan"] or "{}").get("unscheduled") or [])
        except json.JSONDecodeError:
            pass
    return {"trips": trips, "pois": pois, "destinations": dests, "unscheduled": unscheduled}
