#!/usr/bin/env python3
"""生成 assets/galgame-{dark,light}.svg。

三张小卡片横向排列：封面 / 游戏名 / 时长 / 成就。
时长和成就来自 Steam Web API，封面来自 VNDB 对应 Steam 版本的条目。

Steam key 只从环境变量读，绝不写进仓库：

    STEAM_API_KEY=... python3 tools/update_galgame.py

本地调试可以用已经保存下来的响应，避免反复请求 Steam：

    STEAM_GAMES_JSON=/path/to/steam.json \
    STEAM_ACHIEVEMENTS_JSON=/path/to/achievements.json \
    python3 tools/update_galgame.py

封面用 VNDB 的 256px 缩略图，再用 ImageMagick 压到 240x360 后内联成
base64；README 里的 SVG 是被 <img> 加载的，不能引用外部图片。
没有 ImageMagick 时会退回原图，功能不受影响。
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

STEAM_ID = "76561199114045991"
STEAM_OWNED = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
STEAM_ACH = "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/"
VNDB_RELEASE = "https://api.vndb.org/kana/release"
UA = "LaT-SKY-profile/1.0 (+https://github.com/LaT-SKY)"

GAMES = [
    {"appid": 324160, "title": "CLANNAD"},
    {"appid": 3418570, "title": "Summer Pockets REFLECTION BLUE"},
    {"appid": 635940, "title": "Little Busters!"},
]

W = 1000
H = 530
PAD = 28
INNER = W - 2 * PAD
CARD_W = 282
CARD_H = 430
CARD_TOP = 72
GAP = (INNER - 3 * CARD_W) / 2
COVER_W, COVER_H = 180, 270
CARD_PAD = 16

MONO = ('ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,'
        '"Liberation Mono",monospace')

THEMES = {
    "dark": {
        "panel": "#0D1224", "card": "#111A31", "border": "#1E2540",
        "title": "#8892B4", "num": "#C8CFE2", "accent": "#F5A9C8",
        "gold": "#EFC77E", "rule": "#222B45", "track": "#171E33",
        "edge": "#2A3350",
    },
    "light": {
        "panel": "#F6F8FA", "card": "#FFFFFF", "border": "#E3E6EC",
        "title": "#6B7280", "num": "#3A4256", "accent": "#C43E63",
        "gold": "#D9A441", "rule": "#E3E6EC", "track": "#EBEDF0",
        "edge": "#DDE1E8",
    },
}


# ---------------------------------------------------------------- 抓取

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def steam_data():
    key = os.environ.get("STEAM_API_KEY")
    games_file = os.environ.get("STEAM_GAMES_JSON")
    ach_file = os.environ.get("STEAM_ACHIEVEMENTS_JSON")

    if games_file:
        data = json.loads(Path(games_file).read_text("utf-8"))
    else:
        if not key:
            sys.exit("未设置 STEAM_API_KEY；本地调试可设 STEAM_GAMES_JSON")
        query = urllib.parse.urlencode({
            "key": key, "steamid": STEAM_ID,
            "include_appinfo": 1, "include_played_free_games": 1,
        })
        try:
            data = get_json(f"{STEAM_OWNED}?{query}")
        except Exception as e:  # noqa: BLE001 - 不打印带 key 的 URL
            sys.exit(f"Steam 库请求失败（{type(e).__name__}）："
                     "检查 key、SteamID 和隐私设置")

    games = (data.get("response") or {}).get("games")
    if games is None:
        sys.exit("Steam 没有返回游戏列表：检查 key、SteamID，"
                 "以及「游戏详情」是否公开")
    games = {g["appid"]: g for g in games}

    if ach_file:
        ach = json.loads(Path(ach_file).read_text("utf-8"))
    else:
        if not key:
            sys.exit("未设置 STEAM_API_KEY；本地调试可设 STEAM_ACHIEVEMENTS_JSON")
        ach = {}
        for g in GAMES:
            appid = g["appid"]
            query = urllib.parse.urlencode({
                "key": key, "steamid": STEAM_ID,
                "appid": appid, "l": "english",
            })
            try:
                ach[str(appid)] = get_json(f"{STEAM_ACH}?{query}")
            except Exception:  # noqa: BLE001 - 单个游戏失败就留空
                ach[str(appid)] = None
    return games, ach


def achievement_counts(raw):
    ps = (raw or {}).get("playerstats") or {}
    items = ps.get("achievements")
    if not ps.get("success") or items is None:
        return None, None
    got = sum(1 for x in items if int(x.get("achieved") or 0) == 1)
    return got, len(items)


def vndb_releases():
    filters = ["or"] + [["extlink", "=", ["steam", g["appid"]]] for g in GAMES]
    fields = "id,title,released,images{url,thumbnail,type},extlinks{id,name}"
    body = json.dumps({"filters": filters, "fields": fields,
                       "results": 10}).encode()
    req = urllib.request.Request(
        VNDB_RELEASE, data=body,
        headers={"User-Agent": UA, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"VNDB release API 请求失败：{e}")
    return data.get("results") or []


def release_covers(releases):
    """Steam appid -> 对应版本的数字封面（优先 dig）。"""
    out = {}
    for rel in releases:
        imgs = rel.get("images") or []
        dig = next((i for i in imgs if i.get("type") == "dig"), None)
        image = dig or (imgs[0] if imgs else None)
        for link in rel.get("extlinks") or []:
            if link.get("name") != "steam":
                continue
            try:
                appid = int(link.get("id"))
            except (TypeError, ValueError):
                continue
            out[appid] = image
    return out


def image_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        ctype = r.headers.get_content_type()
        raw = r.read()
    if not ctype.startswith("image/"):
        raise RuntimeError(f"不是图片：{ctype}")
    return raw, ctype


def shrink_jpeg(raw):
    """压到 240x360；没有 ImageMagick 就返回 None。"""
    tool = shutil.which("magick") or shutil.which("convert")
    if not tool:
        return None
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "in"
        dst = Path(td) / "out.jpg"
        src.write_bytes(raw)
        cmd = [tool, str(src), "-resize", "240x360^", "-gravity", "center",
               "-extent", "240x360", "-quality", "82", "-strip", str(dst)]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=20)
            return dst.read_bytes()
        except Exception:  # noqa: BLE001 - 压缩是优化，不是必需
            return None


def cover_uri(image):
    image = image or {}
    url = image.get("thumbnail") or image.get("url")
    if not url:
        return None
    raw, ctype = image_bytes(url)
    small = shrink_jpeg(raw)
    if small:
        return "data:image/jpeg;base64," + base64.b64encode(small).decode()
    return f"data:{ctype};base64," + base64.b64encode(raw).decode()


def load_rows():
    steam, ach = steam_data()
    covers = release_covers(vndb_releases())
    rows = []
    for cfg in GAMES:
        g = steam.get(cfg["appid"]) or {}
        got, total = achievement_counts(ach.get(str(cfg["appid"])))
        rows.append({
            "title": cfg["title"],
            "cover": cover_uri(covers.get(cfg["appid"])),
            "play": g.get("playtime_forever"),
            "got": got,
            "total": total,
        })
    return rows


# ---------------------------------------------------------------- 排版

def text_width(s, size):
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


def wrap_title(s, size, max_w):
    """最多两行；优先在空格处断开。"""
    if text_width(s, size) <= max_w:
        return [s]
    words = s.split()
    best = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        wa, wb = text_width(a, size), text_width(b, size)
        if wa <= max_w and wb <= max_w:
            score = max(wa, wb)
            if best is None or score < best[0]:
                best = (score, a, b)
    if best:
        return [best[1], best[2]]
    return [clip(s, size, max_w)]


def txt(x, y, s, fill, size=15, anchor="start", weight=400):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return (f'<text x="{x:.0f}" y="{y}" fill="{fill}" font-size="{size}" '
            f'font-weight="{weight}" font-family=\'{MONO}\'{a} '
            f'xml:space="preserve">{escape(str(s))}</text>')


def rich(x, y, parts, size=15, anchor="start", weight=400):
    spans = []
    for part in parts:
        s, c = part[0], part[1]
        sz = part[2] if len(part) > 2 else None
        attr = f' font-size="{sz}"' if sz else ""
        spans.append(f'<tspan fill="{c}"{attr}>{escape(str(s))}</tspan>')
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return (f'<text x="{x:.0f}" y="{y}" font-size="{size}" font-weight="{weight}" '
            f'font-family=\'{MONO}\'{a} xml:space="preserve">{"".join(spans)}</text>')


def card(rows, index, t):
    r = rows[index]
    x = PAD + index * (CARD_W + GAP)
    y = CARD_TOP
    cx = x + CARD_W / 2
    out = []

    out.append(f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{CARD_H}" '
               f'rx="14" fill="{t["card"]}" stroke="{t["border"]}"/>')

    cover_x = x + (CARD_W - COVER_W) / 2
    cover_y = y + CARD_PAD
    if r["cover"]:
        out.append(f'<g transform="translate({cover_x:.0f},{cover_y})" '
                   f'clip-path="url(#cover)"><image width="{COVER_W}" '
                   f'height="{COVER_H}" preserveAspectRatio="xMidYMid slice" '
                   f'href="{r["cover"]}"/></g>')
    else:
        out.append(f'<rect x="{cover_x:.0f}" y="{cover_y}" width="{COVER_W}" '
                   f'height="{COVER_H}" rx="8" fill="{t["track"]}"/>')
    out.append(f'<rect x="{cover_x:.0f}" y="{cover_y}" width="{COVER_W}" '
               f'height="{COVER_H}" rx="8" fill="none" stroke="{t["edge"]}"/>')

    lines = wrap_title(r["title"], 20, 242)
    for i, line in enumerate(lines[:2]):
        out.append(txt(cx, 384 + i * 24, line, t["num"], 20, "middle", 500))

    play = r["play"]
    if play is None:
        out.append(txt(cx, 446, "未入库", t["title"], 20, "middle"))
    else:
        play_s = f"{play / 60:.1f}"
        play_w = (text_width(play_s, 24) + text_width("h", 14) + 2)
        start = cx - play_w / 2
        out.append(rich(start, 446, [(play_s, t["num"]),
                                     ("h", t["accent"], 14)], 24, weight=500))

    if r["got"] is not None and r["total"]:
        out.append(rich(cx, 478, [("成就 ", t["title"]),
                                  (str(r["got"]), t["accent"]),
                                  (" / ", t["title"]),
                                  (str(r["total"]), t["num"])], 15, "middle"))
    else:
        out.append(txt(cx, 478, "成就 — / —", t["title"], 15, "middle"))

    return "\n".join(out)


def render(rows, theme):
    t = THEMES[theme]
    out = []
    out.append(txt(PAD, 30, "GALGAME", t["title"], 22, weight=500))
    out.append(f'<rect x="{PAD}" y="46" width="{INNER}" height="1" fill="{t["rule"]}"/>')

    for i in range(len(rows)):
        out.append(card(rows, i, t))

    defs = (f'<defs><clipPath id="cover" clipPathUnits="userSpaceOnUse">'
            f'<rect width="{COVER_W}" height="{COVER_H}" rx="8"/></clipPath></defs>')
    panel = (f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="16" '
             f'fill="{t["panel"]}" stroke="{t["border"]}"/>')
    label = "Steam Galgame 记录：" + "、".join(r["title"] for r in rows)

    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}" role="img" aria-label="{escape(label)}">\n'
            + defs + "\n" + panel + "\n" + "\n".join(out) + "\n</svg>")


if __name__ == "__main__":
    rows = load_rows()
    OUT = Path(__file__).resolve().parent.parent / "assets"
    OUT.mkdir(exist_ok=True)
    for th in ("dark", "light"):
        (OUT / f"galgame-{th}.svg").write_text(render(rows, th), "utf-8")
    total = sum((r["play"] or 0) for r in rows) / 60
    print(f"assets/galgame-{{dark,light}}.svg · {len(rows)} 部 · {total:.1f} 小时")
