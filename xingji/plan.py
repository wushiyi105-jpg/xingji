"""排程：本地把景点塞进有限的天数里。

模型不该干这件事。塞不下就是塞不下，让模型排，它会把第 4 天的景点搬到第 2 天，
然后你到了才发现，那天下午还有两个馆要看。
"""

from __future__ import annotations

from . import poi as P

WEEK_ZH = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]  # 与 poi 一致：0 是周日
TRAVEL_MIN = 40          # 跨区域换场，按 40 分钟算（本地实测地铁换乘一顿折腾）
DAY_START = 9 * 60       # 早上 9 点出发
LUNCH_MIN = 60           # 中午留一小时吃饭，算进当天的预算
NOON = 12 * 60
BEST_RANK = {"上午": 0, "全天": 1, "下午": 2}


def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _order(pois: list[dict]) -> list[dict]:
    """必去的先排，上午的先排，其余按区域聚在一起。

    一开始我只按区域排序，结果「上午最活跃」的大熊猫基地被排到了 11:40 —
    到那儿熊猫已经吃饱睡下了。best_time 必须参与排序。
    """
    return sorted(pois, key=lambda p: (
        0 if p["must"] else 1,
        BEST_RANK.get(p["best_time"], 1),
        p["area"],
        -p["minutes"],
        p["name"],
    ))


def schedule(pois: list[dict], days: int, minutes_per_day: int = 480,
             weekday_start: int = 0, must: list[str] | None = None,
             budget: float | None = None, travel: int = TRAVEL_MIN) -> dict:
    """把景点排进 days 天。返回每天的安排 + 排不进去的及其原因。"""
    must_names = [m for m in (must or []) if m]
    unknown_must = [m for m in must_names if not P.find(pois, m)]
    left = _order(list(pois))

    plan_days: list[dict] = []
    unscheduled: list[dict] = []

    for d in range(days):
        wd = (weekday_start + d) % 7
        day_pois: list[dict] = []
        used = 0
        price = 0.0
        area = ""
        clock = DAY_START
        lunched = False

        for p in list(left):
            if not P.is_open(p["open_days"], wd):
                continue
            move = travel if (area and p["area"] != area) else 0
            # 到点了就先把饭吃了，再进下一个点。别让午饭卡在景点中间。
            eat = (not lunched) and (clock + move >= NOON - LUNCH_MIN)
            cost = p["minutes"] + move + (LUNCH_MIN if eat else 0)
            if used + cost > minutes_per_day:
                continue
            if budget is not None and price + p["price"] > budget:
                continue

            clock += move
            if eat:
                clock += LUNCH_MIN
                lunched = True
            day_pois.append({
                "name": p["name"],
                "area": p["area"],
                "minutes": p["minutes"],
                "price": p["price"],
                "start": _fmt(clock),
                "end": _fmt(clock + p["minutes"]),
                "must": p["must"],
                "note": p["note"],
            })
            clock += p["minutes"]
            used += cost
            price += p["price"]
            area = p["area"]
            left.remove(p)

        plan_days.append({
            "day": d + 1,
            "weekday": WEEK_ZH[wd],
            "weekday_num": wd,
            "pois": day_pois,
            "minutes": used,
            "price": round(price, 2),
            "areas": sorted({p["area"] for p in day_pois}),
        })

    for p in left:
        reasons = []
        if not any(P.is_open(p["open_days"], (weekday_start + d) % 7) for d in range(days)):
            reasons.append("这几天都闭馆")
        if not reasons:
            reasons.append("每天的时间塞满了")
        if budget is not None and p["price"] > 0:
            reasons.append("预算不够")
        unscheduled.append({"name": p["name"], "why": reasons[0],
                            "minutes": p["minutes"], "price": p["price"]})

    total_price = sum(d["price"] for d in plan_days)
    total_min = sum(d["minutes"] for d in plan_days)
    return {
        "days": plan_days,
        "unscheduled": unscheduled,
        "unknown_must": unknown_must,
        "total_price": round(total_price, 2),
        "total_minutes": total_min,
        "budget": budget,
        "minutes_per_day": minutes_per_day,
        "travel": travel,
    }


def busy_ratio(plan: dict) -> float:
    """每天用了多少比例的时间。太低说明还能加，太高说明排太满。"""
    days = plan.get("days") or []
    if not days:
        return 0.0
    cap = plan.get("minutes_per_day") or 480
    return round(sum(d["minutes"] for d in days) / (cap * len(days)), 3)


def check(plan: dict) -> list[str]:
    """本地自查，给模型和人都看的几条硬事实。"""
    notes = []
    for d in plan.get("days") or []:
        if not d["pois"]:
            notes.append(f"第 {d['day']} 天（{d['weekday']}）还是空的，得补点或被闭馆卡住了")
    r = busy_ratio(plan)
    if r > 0.95:
        notes.append(f"每天用掉 {int(r * 100)}% 的时间，几乎没有余量，走起来会很赶")
    elif r and r < 0.45:
        notes.append(f"每天只用了 {int(r * 100)}% 的时间，可以再塞两个点")
    if plan.get("budget") is not None:
        if plan["total_price"] > plan["budget"]:
            notes.append(f"门票合计 {plan['total_price']:.0f} 元，超过预算 {plan['budget']:.0f} 元")
        elif plan["budget"] and plan["total_price"] < plan["budget"] * 0.6:
            notes.append("门票花得比预算少不少，预算可以留着吃饭和打车")
    return notes


def render(plan: dict, destination: str = "") -> str:
    lines = []
    if destination:
        lines.append(f"=== {destination} · {len(plan['days'])} 天 ===")
    lines.append(f"门票合计 {plan['total_price']:.0f} 元 · "
                 f"在路上的时间按每天 {plan['minutes_per_day']} 分钟算")
    for d in plan["days"]:
        if not d["pois"]:
            lines.append(f"\n第 {d['day']} 天（{d['weekday']}）—— 空")
            continue
        lines.append(f"\n第 {d['day']} 天（{d['weekday']}）· {' / '.join(d['areas'])}"
                     f" · {d['minutes']} 分钟 · {d['price']:.0f} 元")
        for p in d["pois"]:
            tag = "★ " if p["must"] else "  "
            note = f"  ({p['note']})" if p["note"] else ""
            lines.append(f"{tag}{p['start']}-{p['end']}  {p['name']}  {p['minutes']} 分钟"
                         f"  {'免费' if p['price'] == 0 else str(int(p['price'])) + ' 元'}{note}")
    if plan["unscheduled"]:
        lines.append("\n没排进去：")
        for u in plan["unscheduled"]:
            lines.append(f"  · {u['name']} —— {u['why']}")
    if plan["unknown_must"]:
        lines.append(f"\n! 清单里没有这些必去点：{'、'.join(plan['unknown_must'])}")
    for n in check(plan):
        lines.append(f"! {n}")
    return "\n".join(lines)
