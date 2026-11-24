"""模型层：把排好的行程写成有人味的一段话，并且不许编地名、不许编数字。

排程是本地定的，模型只负责「讲」。它讲得再好，只要出现清单外的地名，就标出来。
"""

from __future__ import annotations

import json
import re

from . import llm, poi as P, verify

SYSTEM = """你在帮朋友写一份旅行安排，语气像发给同行人的私聊，不是旅行网站。

规则：
1. 只提「行程」里列出的地方，名字照抄，一个字都不改。
2. 不许编造任何地点：不要写「顺路的小店」「附近的茶馆」「推荐一家面馆」这类清单外的具体场所。
3. 不许编数字：门票价格、游览时长、通勤时间只能照抄行程里给的，不要自己估。
4. 不要写距离和交通方式的具体耗时（清单里没有这些数据）。
5. 每天一段：一句标题 + 3 到 5 句正文，说清楚「为什么这么排」「看点在哪」「注意什么」。
   正文控制在 120 字以内，别写成攻略长文。
6. 最后给 3 条通用提醒。
7. 只输出 JSON，不要任何解释文字。

JSON：
{
  "days": [{"day": 1, "title": "…", "text": "…"}],
  "tips": ["…", "…", "…"]
}"""


def _as_text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for k in ("value", "text", "content"):
            if isinstance(value.get(k), str):
                return value[k].strip()
    if isinstance(value, list):
        return "\n".join(_as_text(v) for v in value if _as_text(v))
    return ""


def build_prompt(plan: dict, pois: list[dict], destination: str, prefs: str = "") -> str:
    lines = [f"目的地：{destination}", f"共 {len(plan['days'])} 天，"
             f"每天大致 {plan['minutes_per_day']} 分钟（含午饭 1 小时）"]
    if prefs:
        lines.append(f"同行人的偏好：{prefs}")
    lines.append("")
    for d in plan["days"]:
        if not d["pois"]:
            lines.append(f"第 {d['day']} 天（{d['weekday']}）：空着")
            continue
        lines.append(f"第 {d['day']} 天（{d['weekday']}），门票 {d['price']:.0f} 元：")
        for p in d["pois"]:
            note = f"，{p['note']}" if p["note"] else ""
            star = "（必去）" if p["must"] else ""
            lines.append(f"  {p['start']}-{p['end']} {p['name']}{star}，"
                         f"{p['minutes']} 分钟，{('免费' if p['price'] == 0 else str(int(p['price'])) + ' 元')}"
                         f"{note}")
    if plan["unscheduled"]:
        lines.append("")
        lines.append("这次没排进去的（可以解释一句为什么，但不要说成能去）：")
        for u in plan["unscheduled"]:
            lines.append(f"  {u['name']}（{u['why']}）")
    lines.append("")
    lines.append("按上面的安排写，只输出 JSON。")
    return "\n".join(lines)


def parse(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```$", "", text).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            pass
    return {}


def write(plan: dict, pois: list[dict], destination: str, prefs: str = "") -> dict:
    result = {"days": [], "tips": [], "error": "", "foreign": [], "numbers": []}
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": build_prompt(plan, pois, destination, prefs)}]

    # 第一版只给 2000 的预算，模型写到第 1 天就把 JSON 截断了（推理型模型先吃掉
    # 一大半预算写思考）。写满 8 天行程时更明显。所以：解析不出来就加倍再来一次。
    data: dict = {}
    raw = ""
    for budget in (3200, 6400):
        try:
            raw = llm.chat(msgs, max_tokens=budget)
        except llm.LLMError as e:
            result["error"] = f"模型没回：{e}"
            return result
        data = parse(raw)
        if data:
            break
    if not data:
        result["error"] = "模型输出不是 JSON，原文：" + (raw or "")[:80]
        return result

    checks = []
    for item in data.get("days") or []:
        if not isinstance(item, dict):
            continue
        text = _as_text(item.get("text"))
        day_no = item.get("day")
        try:
            day_no = int(day_no)
        except (TypeError, ValueError):
            day_no = len(result["days"]) + 1
        result["days"].append({"day": day_no, "title": _as_text(item.get("title")), "text": text})
        checks.append(verify.check_text(text + " " + _as_text(item.get("title")), pois, plan))

    tips = [_as_text(t) for t in (data.get("tips") or []) if _as_text(t)]
    result["tips"] = tips[:5]
    if tips:
        checks.append(verify.check_text(" ".join(tips), pois, plan))

    merged = verify.merge_checks(checks)
    result["foreign"] = merged["foreign"]
    result["numbers"] = merged["numbers"]
    return result


def render(story: dict, plan: dict) -> str:
    if story.get("error"):
        return story["error"]
    lines: list[str] = []
    for d in story.get("days") or []:
        lines.append(f"\n第 {d['day']} 天 · {d['title']}" if d["title"] else f"\n第 {d['day']} 天")
        if d["text"]:
            lines.append(d["text"])
    if story.get("tips"):
        lines.append("\n提醒：")
        for t in story["tips"]:
            lines.append(f"  · {t}")
    if story.get("foreign"):
        lines.append(f"\n! 清单里没有这些地方：{'、'.join(story['foreign'])}")
    if story.get("numbers"):
        lines.append("\n! 数字对不上：")
        for n in story["numbers"]:
            lines.append(f"  · {n}")
    return "\n".join(lines)


def flagged(story: dict) -> int:
    return len(story.get("foreign") or []) + len(story.get("numbers") or [])
