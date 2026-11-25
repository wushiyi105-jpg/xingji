"""景点清单：读文件、认字段、算开放日。

用竖线分隔的文本，一行一个点：
    名称 | 区域 | 建议时长(分钟) | 门票(元) | 开放日 | 最佳时段 | 必去 | 备注

开放日写法：全周 / 周一 / 周一休 / 周二至周日 / 1,2（数字是 weekday，周一是 1）
"""

from __future__ import annotations

import re

FIELDS = ("name", "area", "minutes", "price", "open_days", "best_time", "must", "note")

WEEK = {"周一": 1, "星期二": 2, "周二": 2, "周三": 3, "星期四": 4, "周四": 4,
        "周五": 5, "星期六": 6, "周六": 6, "周日": 0, "周天": 0, "星期日": 0, "星期天": 0,
        "星期一": 1}

TIME_DEFAULT = "全天"


class PoiError(ValueError):
    pass


def weekday_of(label: str) -> int | None:
    for k, v in WEEK.items():
        if k == label:
            return v
    return None


def _day_num(text: str) -> int | None:
    t = (text or "").strip()
    if not t:
        return None
    wd = weekday_of(t)
    if wd is not None:
        return wd
    m = re.search(r"\d", t)
    return int(m.group(0)) % 7 if m else None


def parse_open(spec: str) -> list[int] | None:
    """把开放日写法转成允许的 weekday 集合。None 表示全周开放。

    这一步是行程最容易翻车的地方：周一去博物馆，到了才看见闭馆通知。
    """
    s = (spec or "").strip()
    if not s or s in ("全周", "每天", "无休", "all", "7", "不限"):
        return None
    s = (s.replace("至", "到").replace("－", "-").replace("—", "-")
         .replace("星期", "周").replace("礼拜", "周"))

    closed = bool(re.search(r"(闭馆|休息|检修|休)$", s)) or s.startswith("逢")
    s = re.sub(r"(闭馆|休息|检修|逢|休)", "", s).strip()

    if "到" in s or "-" in s:
        sep = "到" if "到" in s else "-"
        a_s, b_s = s.split(sep, 1)
        a, b = _day_num(a_s), _day_num(b_s)
        if a is None or b is None:
            raise PoiError(f"看不懂的开放日：{spec}")
        days = list(range(a, b + 1)) if a <= b else list(range(a, 7)) + list(range(b + 1))
    else:
        days = [d for d in (_day_num(t) for t in re.split(r"[,、/\s]+", s)) if d is not None]

    if not days:
        raise PoiError(f"看不懂的开放日：{spec}")

    if closed:
        return [d for d in range(7) if d not in days]
    return sorted(set(days))


def is_open(open_days: list[int] | None, weekday: int) -> bool:
    return True if open_days is None else weekday in open_days


def parse_price(text: str) -> float:
    s = (text or "").strip()
    if not s or s in ("免费", "0", "无"):
        return 0.0
    m = re.search(r"\d+(?:\.\d+)?", s)
    if not m:
        raise PoiError(f"看不懂的门票：{text}")
    return float(m.group(0))


def to_int(text: str, default: int = 90) -> int:
    m = re.search(r"\d+", (text or ""))
    return int(m.group(0)) if m else default


def parse_line(line: str, line_no: int = 0) -> dict:
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 4:
        raise PoiError(f"第 {line_no} 行字段不够（至少要 名称|区域|时长|门票）：{line}")
    name, area, minutes, price = parts[:4]
    rest = parts[4:] + [""] * 4
    open_spec, best, must_raw, note = rest[:4]
    if not name:
        raise PoiError(f"第 {line_no} 行没有名称")

    try:
        open_days = parse_open(open_spec)
        price_v = parse_price(price)
    except PoiError as e:
        raise PoiError(f"第 {line_no} 行：{e}") from e

    return {
        "name": name,
        "area": area or "市区",
        "minutes": max(15, to_int(minutes)),
        "price": price_v,
        "open_days": open_days,
        "open_spec": open_spec or "全周",
        "best_time": (best or TIME_DEFAULT).strip() or TIME_DEFAULT,
        "must": (must_raw or "").strip() in ("1", "是", "必去", "yes", "Y", "y"),
        "note": (note or "").strip(),
    }


def read_list(text: str) -> list[dict]:
    out: list[dict] = []
    for i, line in enumerate((text or "").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if i == 1 and "|" not in line:
            continue  # 第一行是标题，不是数据
        out.append(parse_line(line, i))
    if not out:
        raise PoiError("清单是空的")
    return out


def find(pois: list[dict], name: str) -> dict | None:
    """按名称找，支持包含匹配（「武侯祠」能找到「武侯祠博物馆」）。"""
    key = (name or "").strip()
    if not key:
        return None
    for p in pois:
        if p["name"] == key:
            return p
    for p in pois:
        if key in p["name"] or p["name"] in key:
            return p
    return None


def names(pois: list[dict]) -> list[str]:
    return [p["name"] for p in pois]
