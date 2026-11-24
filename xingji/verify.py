"""核验：模型写的文案里，地名和数字都要对得上本地事实。

模型最爱干两件事：顺手编一个「附近的茶馆」（清单里没有），
把门票说成 30 元（清单里写 50）。两件都能查。
"""

from __future__ import annotations

import re

# 认得出是「地方」的后缀。只收两字以上的：单字后缀（山、湖、寺、街、里、馆）
# 会在一堆普通词组里误命中——「注意周一闭馆」里的「馆」、「行程里」里的「里」，
# 第一次跑就抓了四条这种假地名，比真警告还吵。宁可漏抓，不能误抓。
SUFFIX = ("博物馆", "博物院", "美术馆", "纪念馆", "公园", "湿地", "古镇", "古街", "老街",
          "寺院", "遗址", "景区", "基地", "园区", "广场", "步行街", "小吃街", "商业街",
          "大道", "古镇区", "文化街", "巷子", "胡同")

NAME_RE = re.compile(
    "([\u4e00-\u9fff]{2,6}(?:" + "|".join(sorted(SUFFIX, key=len, reverse=True)) + "))")

NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(分钟|小时|个小时|元|块|公里|千米|km|KM)")

# 候选里出现这些字，说明它是半句话而不是地名
STOP_CHARS = ("的了着是在有就也还很要会把被给让从对和与或但而每这那个次元点上下前后中内外旁边"
              "去来走逛看吃住玩转进出过")
STOP_WORDS = ("注意", "记得", "建议", "可以", "推荐", "附近", "周边", "整个", "一家",
              "当地", "街上", "小巷", "夜市", "公园里", "中心城区", "别忘")

SUF_RE = re.compile("|".join(sorted(SUFFIX, key=len, reverse=True)))
CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")


def _mask(text: str, pois: list[dict]) -> str:
    """把清单里的地名替换成占位符。

    这一步是必须的：先摘掉已经认得的地方，剩下的才是「模型自己冒出来的」。
    不然「上午去武侯祠」这种正常句子会被后缀规则从中间切开。
    """
    out = text or ""
    for p in sorted(pois, key=lambda x: -len(x["name"])):
        out = out.replace(p["name"], "◎")
    return out


def places_in(text: str, pois: list[dict] | None = None) -> list[str]:
    """文本里像地名、但不在清单里的片段。

    不从左往右抓整段，而是从后缀往前一个字一个字地扩，碰到虚词就停。
    「顺路去锦里古街」这样抓出来是「锦里古街」，不是「顺路去锦里古街」。
    """
    out: list[str] = []
    masked = _mask(text, pois or [])
    for m in SUF_RE.finditer(masked):
        best = ""
        for n in range(2, 5):
            s = m.start() - n
            if s < 0:
                break
            # 往前扩的这段必须整段都是中文字。不加这一条，标点会被无视，直接跨过去
            # 把上一句的尾巴粘上来：「红墙竹影+博物馆」抓成了「墙竹影+博物馆」。
            seg = masked[s:m.start()]
            if not all(CJK_CHAR.match(ch) for ch in seg):
                break
            cand = masked[s:m.end()]
            if any(c in cand for c in STOP_CHARS) or any(w in cand for w in STOP_WORDS):
                break
            best = cand
        if len(best) >= 4 and best not in out:
            out.append(best)
    return out


def _matches(name: str, pois: list[dict]) -> bool:
    """这个名字能不能对上清单里的某一处。

    宽松到「互相包含」和「去后缀后的核心词在清单名里」为止：
    模型写「熊猫基地」，清单写「大熊猫繁育研究基地」，这是同一处，不该报。
    """
    for p in pois:
        pn = p["name"]
        if name == pn or name in pn or pn in name:
            return True
        core = name
        for suf in sorted(SUFFIX, key=len, reverse=True):
            if name.endswith(suf) and len(name) > len(suf):
                core = name[: -len(suf)]
                break
        if len(core) >= 2 and core in pn:
            return True
    return False


def foreign_places(text: str, pois: list[dict]) -> list[str]:
    """清单外的地名。

    先把清单里的名字摘掉，再把剩下像地名的片段按「核心词」回查一次：
    「熊猫基地」对上清单的「大熊猫繁育研究基地」算通过，「锦里古街」对不上就报。
    """
    return [n for n in places_in(text, pois) if not _matches(n, pois)]


def allowed_numbers(plan: dict) -> set[float]:
    """行程里真实出现过的数字。模型说的数字要落在这个集合里。"""
    allowed: set[float] = set()
    cap = plan.get("minutes_per_day") or 0
    allowed.update({float(cap), float(plan.get("travel") or 0)})
    allowed.update(float(d) for d in range(1, 13))  # 第 1 天到第 12 天
    for d in plan.get("days") or []:
        allowed.add(float(d["day"]))
        allowed.add(float(d["minutes"]))
        allowed.add(float(d["price"]))  # 每天的门票合计，模型会写「今天门票 105 元」
        for p in d["pois"]:
            allowed.add(float(p["minutes"]))
            allowed.add(float(p["price"]))
    if plan.get("budget") is not None:
        allowed.add(float(plan["budget"]))
    allowed.add(float(plan.get("total_price") or 0))
    return allowed


def number_claims(text: str) -> list[tuple[float, str]]:
    return [(float(m.group(1)), m.group(2)) for m in NUM_RE.finditer(text or "")]


def check_numbers(text: str, plan: dict) -> list[str]:
    """带单位的数字必须对得上。只查元、分钟、小时；距离在清单里没有数据，一律提醒。"""
    allowed = allowed_numbers(plan)
    bad: list[str] = []
    for value, unit in number_claims(text):
        if unit in ("公里", "千米", "km", "KM"):
            bad.append(f"{value:g} {unit} —— 清单里没有距离数据，别写死")
            continue
        if unit in ("小时", "个小时"):
            if not (1 <= value <= 12):
                bad.append(f"{value:g} 小时 —— 一天排不了这么久")
            continue
        if value not in allowed:
            bad.append(f"{value:g} {unit} —— 行程里没有这个数")
    return bad


def check_text(text: str, pois: list[dict], plan: dict) -> dict:
    return {
        "foreign": foreign_places(text, pois),
        "numbers": check_numbers(text, plan),
    }


def merge_checks(parts: list[dict]) -> dict:
    """把每天的结果合成一份，去重。"""
    foreign: list[str] = []
    numbers: list[str] = []
    for p in parts:
        for n in p.get("foreign") or []:
            if n not in foreign:
                foreign.append(n)
        for n in p.get("numbers") or []:
            if n not in numbers:
                numbers.append(n)
    return {"foreign": foreign, "numbers": numbers}


