#!/usr/bin/env python3
"""生成 assets/osu-{dark,light}.svg。

数据全部来自 osu! 的公开页面，不需要 API key：
  /users/<id>/<mode>            页面里的 data-initial-data 带统计和排名历史
  /users/<id>/scores/best?...   公开 JSON，取一张最佳成绩
  a.ppy.sh/<id>                 头像

为什么不用 osu! API v2：那要 client id/secret，而这里只需要公开成绩。
为什么头像/国旗内联成 base64：README 里的 SVG 是被 <img> 加载的，
浏览器不会为 SVG 图片请求外部资源。

    python3 tools/update_osu.py
"""

import base64
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

USER_ID = 39161898
MODE = "mania"
BASE = "https://osu.ppy.sh"
UA = "LaT-SKY-profile/1.0 (+https://github.com/LaT-SKY)"

W = 1000
H = 396
PAD = 28
INNER = W - 2 * PAD

MONO = ('ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,'
        '"Liberation Mono",monospace')

THEMES = {
    "dark": {
        "panel": "#0D1224", "border": "#1E2540", "title": "#8892B4",
        "num": "#C8CFE2", "accent": "#F5A9C8", "gold": "#EFC77E",
        "rule": "#222B45", "track": "#171E33", "edge": "#2A3350",
    },
    "light": {
        "panel": "#F6F8FA", "border": "#E3E6EC", "title": "#6B7280",
        "num": "#3A4256", "accent": "#C43E63", "gold": "#D9A441",
        "rule": "#E3E6EC", "track": "#EBEDF0", "edge": "#DDE1E8",
    },
}


# ---------------------------------------------------------------- 抓取

def fetch(url, accept=None, tries=2):
    headers = {"User-Agent": UA}
    if accept:
        headers["Accept"] = accept
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read(), r.headers.get_content_type()
        except Exception as e:  # noqa: BLE001 - 统一转成可读的失败信息
            last = e
            if attempt + 1 < tries:
                time.sleep(1.5)
    raise RuntimeError(f"{url}: {last}")


def load_user():
    raw, _ = fetch(f"{BASE}/users/{USER_ID}/{MODE}")
    page = raw.decode("utf-8", "replace")
    m = re.search(r'data-initial-data="([^"]*)"', page, re.S)
    if not m:
        sys.exit("找不到 data-initial-data，osu! 页面结构可能变了")
    data = json.loads(html.unescape(m.group(1)))
    user = data.get("user") or {}
    if not user.get("statistics"):
        sys.exit("页面里没有 statistics，可能被限流或账号不可见")
    return user


def load_best():
    try:
        raw, _ = fetch(
            f"{BASE}/users/{USER_ID}/scores/best?mode={MODE}&limit=1",
            accept="application/json",
        )
        scores = json.loads(raw)
        return scores[0] if scores else None
    except Exception as e:  # noqa: BLE001 - 最佳成绩是可选的
        print(f"最佳成绩获取失败：{e}", file=sys.stderr)
        return None


def data_uri(url):
    raw, ctype = fetch(url)
    if not ctype.startswith("image/"):
        raise RuntimeError(f"不是图片：{url} ({ctype})")
    return f"data:{ctype};base64,{base64.b64encode(raw).decode()}"


# ---------------------------------------------------------------- 整理

def fmt_int(n):
    return f"{round(n):,}" if isinstance(n, (int, float)) else "—"


def fmt_hours(sec):
    return f"{sec / 3600:.1f}" if isinstance(sec, (int, float)) else "—"


def fmt_acc(v):
    return f"{v:.2f}" if isinstance(v, (int, float)) else "—"


def clean_name(name):
    name = name or "—"
    return re.sub(r"[\u200e\u200f\u202a-\u202e]", "", name)


def play_info(score):
    if not score:
        return None
    bm = score.get("beatmap") or {}
    bs = score.get("beatmapset") or {}
    version = bm.get("version") or ""
    if version and not version.startswith("["):
        version = f"[{version}]"
    title = " ".join(x for x in (bs.get("title"), version) if x)
    mods = "".join(
        (m.get("acronym") or "") if isinstance(m, dict) else str(m)
        for m in (score.get("mods") or [])
    )
    pp = score.get("pp")
    acc = score.get("accuracy")
    return {
        "title": title or "—",
        "pp": f"{pp:.1f}pp" if pp is not None else "",
        "acc": f"{acc * 100:.2f}%" if acc is not None else "",
        "rank": score.get("rank") or "",
        "mods": mods,
    }


def normalize(user, best):
    s = user.get("statistics") or {}
    country = user.get("country") or {}
    code = user.get("country_code") or country.get("code") or "CN"
    name = "中国" if code == "CN" else (country.get("name") or code)
    level = (s.get("level") or {}).get("current")
    history = (user.get("rank_history") or user.get("rankHistory") or {}).get("data") or []
    history = [int(v) for v in history if isinstance(v, (int, float)) and v > 0]
    return {
        "name": clean_name(user.get("username")),
        "country": name,
        "country_code": code,
        "level": level,
        "join": (user.get("join_date") or "")[:7].replace("-", "."),
        "pp": s.get("pp"),
        "global_rank": s.get("global_rank"),
        "country_rank": s.get("country_rank"),
        "acc": s.get("hit_accuracy"),
        "plays": s.get("play_count"),
        "play_time": s.get("play_time"),
        "combo": s.get("maximum_combo"),
        "hits": s.get("total_hits"),
        "history": history,
        "best": play_info(best),
    }


# ---------------------------------------------------------------- 排版

def text_width(s, size):
    """粗略估算渲染宽度：CJK 记 1em，其余记 0.62em。"""
    return sum((1.0 if ord(ch) > 0x2E7F else 0.62) for ch in s) * size


def clip(s, size, max_w):
    if text_width(s, size) <= max_w:
        return s
    out = ""
    for ch in s:
        if text_width(out + ch + "…", size) > max_w:
            break
        out += ch
    return out + "…"


def txt(x, y, s, fill, size=15, anchor="start", weight=400, opacity=None):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    o = f' opacity="{opacity}"' if opacity is not None else ""
    return (f'<text x="{x:.0f}" y="{y}" fill="{fill}" font-size="{size}" '
            f'font-weight="{weight}" font-family=\'{MONO}\'{a}{o} '
            f'xml:space="preserve">{escape(str(s))}</text>')


def rich(x, y, parts, size=15, anchor="start", weight=400):
    """同一行里混字号/颜色：parts = [(文字, 颜色[, 字号]), ...]。"""
    spans = []
    for part in parts:
        s, c = part[0], part[1]
        sz = part[2] if len(part) > 2 else None
        attr = f' font-size="{sz}"' if sz else ""
        spans.append(f'<tspan fill="{c}"{attr}>{escape(str(s))}</tspan>')
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return (f'<text x="{x:.0f}" y="{y}" font-size="{size}" font-weight="{weight}" '
            f'font-family=\'{MONO}\'{a} xml:space="preserve">{"".join(spans)}</text>')


def sparkline(history, t):
    x0, x1, y0, y1 = 620, 972, 84, 148
    if len(history) < 2:
        return txt((x0 + x1) / 2, 118, "暂无排名历史", t["title"], 14, "middle")

    lo, hi = min(history), max(history)
    span = hi - lo or 1
    pts = []
    for i, v in enumerate(history):
        x = x0 + (x1 - x0) * i / (len(history) - 1)
        y = y0 + (v - lo) / span * (y1 - y0)
        pts.append((x, y))

    line = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    area = f"{line} L{x1} {y1} L{x0} {y1} Z"
    label = "近 90 天排名" if len(history) == 90 else "排名走势"

    return "\n".join([
        txt(x1, 72, label, t["title"], 14, "end"),
        f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="1" '
        f'fill="{t["rule"]}" opacity="0.55"/>',
        f'<rect x="{x0}" y="{(y0 + y1) / 2:.0f}" width="{x1 - x0}" height="1" '
        f'fill="{t["rule"]}" opacity="0.55"/>',
        f'<rect x="{x0}" y="{y1}" width="{x1 - x0}" height="1" '
        f'fill="{t["rule"]}" opacity="0.55"/>',
        f'<path d="{area}" fill="url(#rankFill)"/>',
        f'<path d="{line}" fill="none" stroke="{t["accent"]}" stroke-width="2.2" '
        f'stroke-linecap="round" stroke-linejoin="round"/>',
        f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="10" '
        f'fill="{t["gold"]}" opacity="0.12"/>',
        f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="3.6" '
        f'fill="{t["gold"]}"/>',
        txt(x0, 168, fmt_int(history[0]), t["title"], 13),
        txt(x1, 168, fmt_int(history[-1]), t["gold"], 13, "end"),
    ])


def render(me, theme, avatar_uri, flag_uri):
    t = THEMES[theme]
    out = []

    # 页眉
    out.append(txt(PAD, 30, "OSU! · MANIA", t["title"], 22, weight=500))
    out.append(txt(W - PAD, 30, f"osu.ppy.sh/users/{USER_ID}", t["title"], 16, "end"))
    out.append(f'<rect x="{PAD}" y="46" width="{INNER}" height="1" fill="{t["rule"]}"/>')

    # 头像与身份
    out.append(f'<g clip-path="url(#avatar)"><image x="38" y="64" width="88" '
               f'height="88" preserveAspectRatio="xMidYMid slice" href="{avatar_uri}"/></g>')
    out.append(f'<circle cx="82" cy="108" r="44" fill="none" stroke="{t["accent"]}" '
               f'stroke-width="1.5" stroke-opacity="0.6"/>')
    out.append(f'<circle cx="82" cy="108" r="48" fill="none" stroke="{t["accent"]}" '
               f'stroke-opacity="0.12"/>')
    out.append(txt(148, 102, clip(me["name"], 30, 360), t["num"], 30, weight=500))

    meta = [(me["country"], t["title"]), (" · ", t["title"]),
            ("osu!mania", t["accent"])]
    if me["level"]:
        meta.append((f" · Lv.{me['level']}", t["title"]))
    meta_x = 186 if flag_uri else 148
    if flag_uri:
        out.append(f'<image x="148" y="112" width="30" height="20" href="{flag_uri}"/>')
    out.append(rich(meta_x, 129, meta, 15))
    if me["join"]:
        out.append(txt(148, 153, f"{me['join']} 入坑", t["title"], 14))

    # 排名走势
    out.append(sparkline(me["history"], t))

    # 主数据
    out.append(rich(PAD, 222, [(fmt_int(me["pp"]), t["num"]),
                               (" pp", t["accent"], 18)], 44, weight=500))
    out.append(txt(PAD, 248, "表现分", t["title"], 14))

    out.append(rich(330, 222, [(fmt_acc(me["acc"]), t["num"]),
                               ("%", t["accent"], 26)], 44, weight=500))
    out.append(txt(330, 248, "准确率", t["title"], 14))

    out.append(rich(620, 222, [("#", t["title"], 26),
                               (fmt_int(me["global_rank"]), t["num"])], 44, weight=500))
    out.append(txt(620, 248, "全球排名", t["title"], 14))
    if me["country_rank"]:
        out.append(rich(620, 270, [(me["country"] + " ", t["title"]),
                                   ("#" + fmt_int(me["country_rank"]), t["num"])], 14))

    # 次级数据
    out.append(rich(PAD, 300, [
        (fmt_int(me["plays"]), t["num"]), (" 次游玩 · ", t["title"]),
        (fmt_hours(me["play_time"]), t["num"]), (" 小时 · 最高连击 ", t["title"]),
        (fmt_int(me["combo"]), t["num"]), (" · 总命中 ", t["title"]),
        (fmt_int(me["hits"]), t["num"]),
    ], 15))

    out.append(f'<rect x="{PAD}" y="318" width="{INNER}" height="1" fill="{t["rule"]}"/>')

    # 最佳成绩
    out.append(f'<rect x="{PAD}" y="330" width="4" height="18" rx="2" fill="{t["accent"]}"/>')
    out.append(txt(PAD + 12, 344, "BEST PLAY", t["title"], 13, weight=500))

    best = me["best"]
    if best:
        out.append(txt(PAD, 372, clip(best["title"], 18, 650), t["num"], 18))
        rank = best["rank"]
        if rank and best["mods"]:
            rank += " +" + best["mods"]
        right = " · ".join(x for x in (best["pp"], best["acc"], rank) if x)
        out.append(txt(W - PAD, 372, right, t["accent"], 17, "end"))
    else:
        out.append(txt(PAD, 372, "暂无最佳成绩", t["title"], 18))

    defs = (f'<defs><clipPath id="avatar"><circle cx="82" cy="108" r="44"/>'
            f'</clipPath><linearGradient id="rankFill" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{t["accent"]}" stop-opacity="0.22"/>'
            f'<stop offset="1" stop-color="{t["accent"]}" stop-opacity="0"/>'
            f'</linearGradient></defs>')
    panel = (f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="16" '
             f'fill="{t["panel"]}" stroke="{t["border"]}"/>')
    label = (f'osu!mania 成绩：{me["name"]}，全球排名 {fmt_int(me["global_rank"])}，'
             f'{fmt_int(me["pp"])}pp，准确率 {fmt_acc(me["acc"])}%')

    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}" role="img" aria-label="{escape(label)}">\n'
            + defs + "\n" + panel + "\n" + "\n".join(out) + "\n</svg>")


if __name__ == "__main__":
    user = load_user()
    best = load_best()
    me = normalize(user, best)

    try:
        avatar = data_uri(user.get("avatar_url") or f"https://a.ppy.sh/{USER_ID}")
    except Exception as e:  # noqa: BLE001 - 头像没有就失败，避免提交空卡片
        sys.exit(f"头像获取失败：{e}")

    flag = None
    try:
        flag = data_uri(f"{BASE}/images/flags/{me['country_code']}.png")
    except Exception as e:  # noqa: BLE001 - 国旗只是装饰
        print(f"国旗获取失败：{e}", file=sys.stderr)

    OUT = Path(__file__).resolve().parent.parent / "assets"
    OUT.mkdir(exist_ok=True)
    for th in ("dark", "light"):
        (OUT / f"osu-{th}.svg").write_text(render(me, th, avatar, flag), "utf-8")
    print(f"assets/osu-{{dark,light}}.svg · {me['name']} · {fmt_int(me['pp'])}pp · "
          f"全球 #{fmt_int(me['global_rank'])}")
