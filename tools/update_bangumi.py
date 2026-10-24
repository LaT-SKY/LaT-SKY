#!/usr/bin/env python3
"""生成 Bangumi 卡片：历史评价 + 最近在看（浅色 / 深色两版）。

数据来自 Bangumi 公开 API（api.bgm.tv/v0），只需要用户名，不需要 token：
    GET /v0/users/{username}/collections?subject_type=2&type={1..5}

封面为什么内联成 base64：
  README 里的 SVG 是被 <img> 加载的，浏览器对「SVG 作为图片」有安全限制，
  不会去请求外部的 <image href="https://...">。封面必须写成 data URI，
  否则在 GitHub 上就是一排空框。

和 update_heatmap.py 一样，文字走系统字体栈而不是转 path：
  这张图每天要在 Action 里重跑，CI 上没有 Maple Mono / 思源字体，
  而且番剧标题每天在变，没法预先转曲。布局按估算宽度截断。

注意：API 只认 username，数字 uid 会 404；改名以后要同步改下面的 USER。

用法：
    python3 tools/update_bangumi.py
"""
import base64
import json
import sys
import urllib.request
from xml.sax.saxutils import escape

USER = "miprota"
API = "https://api.bgm.tv"
UA = "LaT-SKY-profile/1.0 (+https://github.com/LaT-SKY)"

RATED_ROWS = 5      # 历史评价展示几条
DOING_ROWS = 4      # 最近在看展示几条

W = 1000
PANEL_PAD = 28      # 卡片内边距
INNER = W - 2 * PANEL_PAD

HEAD_Y = 26
RULE_Y = 44

SEC1_LABEL_Y = 82
ROW_TOP0 = 98
ROW_PITCH = 96
COVER_W, COVER_H = 60, 86
ROW_X = 84          # 标题左缘（让开封面）
SEC_GAP = 48        # 上一段最后一张封面 -> 下一段小标题

MONO = ('ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,'
        '"Liberation Mono",monospace')

THEMES = {
    "dark": {
        "panel": "#0D1224", "border": "#1E2540",
        "title": "#8892B4", "num": "#C8CFE2", "tick": "#5F6A8C",
        "rule": "#222B45", "track": "#171E33", "accent": "#F5A9C8",
        "gold": "#EFC77E", "edge": "#2A3350",
    },
    "light": {
        "panel": "#F6F8FA", "border": "#E3E6EC",
        "title": "#6B7280", "num": "#3A4256", "tick": "#9AA1B5",
        "rule": "#E3E6EC", "track": "#EBEDF0", "accent": "#C43E63",
        "gold": "#D9A441", "edge": "#DDE1E8",
    },
}


# ---------------------------------------------------------------- 数据

def api(path):
    req = urllib.request.Request(API + path, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.load(r)
    except Exception as e:  # noqa: BLE001 - 直接给出可读的失败原因
        sys.exit(f"请求 {path} 失败：{e}")


def collections(status):
    out, offset = [], 0
    while True:
        d = api(f"/v0/users/{USER}/collections?subject_type=2&type={status}"
                f"&limit=50&offset={offset}")
        page = d.get("data") or []
        out += page
        if not page or len(out) >= (d.get("total") or 0):
            return out
        offset += 50


def row_of(c):
    s = c["subject"]
    return {
        "title": s.get("name_cn") or s.get("name") or "?",
        "year": (s.get("date") or "")[:4],
        "eps": s.get("eps") or 0,
        "rate": c.get("rate") or 0,
        "ep": c.get("ep_status") or 0,
        "images": s.get("images") or {},
    }


def fetch():
    done = collections(2)
    doing = sorted(collections(3), key=lambda c: c.get("updated_at") or "",
                   reverse=True)
    rated = sorted((c for c in done if c.get("rate")),
                   key=lambda c: (-c["rate"], c.get("updated_at") or ""))
    return {
        "rated_total": len(rated),
        "doing_total": len(doing),
        "rated": [row_of(c) for c in rated[:RATED_ROWS]],
        "doing": [row_of(c) for c in doing[:DOING_ROWS]],
    }


def cover_uri(row, cache):
    """取封面并转成 data URI；grid 挂了就退到 small / common。"""
    for key in ("grid", "small", "common"):
        url = row["images"].get(key)
        if not url:
            continue
        if url in cache:
            return cache[url]
        req = urllib.request.Request(
            url, headers={"User-Agent": UA, "Referer": "https://bgm.tv/"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                ctype = r.headers.get_content_type()
                raw = r.read()
        except Exception as e:  # noqa: BLE001
            print(f"封面 {url} 失败：{e}", file=sys.stderr)
            continue
        if not ctype.startswith("image/"):
            continue
        cache[url] = f"data:{ctype};base64,{base64.b64encode(raw).decode()}"
        return cache[url]
    return None


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


def txt(x, y, s, fill, size=15, anchor="start", weight=400):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return (f'<text x="{x:.0f}" y="{y}" fill="{fill}" font-size="{size}" '
            f'font-weight="{weight}" font-family=\'{MONO}\'{a} '
            f'xml:space="preserve">{escape(s)}</text>')


def rich(x, y, parts, size=13, anchor="start"):
    """同一行里混色的数字：parts = [(文字, 颜色), ...]。"""
    spans = "".join(f'<tspan fill="{c}">{escape(s)}</tspan>' for s, c in parts)
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return (f'<text x="{x:.0f}" y="{y}" font-size="{size}" font-weight="400" '
            f'font-family=\'{MONO}\'{a} xml:space="preserve">{spans}</text>')


def meta_of(row):
    bits = []
    if row["year"]:
        bits.append(row["year"])
    if row["eps"]:
        bits.append(f"{row['eps']} 集")
    return " · ".join(bits) or "—"


def section(y, label, count, suffix, t):
    return "\n".join([
        f'<rect x="0" y="{y - 18}" width="4" height="18" rx="2" '
        f'fill="{t["accent"]}"/>',
        txt(14, y, label, t["title"], 20, "start", 500),
        rich(INNER, y, [(str(count), t["num"]),
                        ("\u00a0" + suffix, t["title"])], 16, "end"),
    ])


def cover(row, top, t):
    if not row.get("uri"):
        return (f'<rect x="0" y="{top}" width="{COVER_W}" height="{COVER_H}" '
                f'rx="5" fill="{t["track"]}"/>')
    return (f'<g transform="translate(0,{top})" clip-path="url(#cover)">'
            f'<image width="{COVER_W}" height="{COVER_H}" '
            f'preserveAspectRatio="xMidYMid slice" href="{row["uri"]}"/>'
            f'</g>'
            f'<rect x="0" y="{top}" width="{COVER_W}" height="{COVER_H}" '
            f'rx="5" fill="none" stroke="{t["edge"]}"/>')


def render(d, theme):
    t = THEMES[theme]
    out = []

    score_x = INNER - 34        # 大号分数的右缘
    bar_w, ep_w = 140, 44
    bar_x = INNER - ep_w - 12 - bar_w   # 进度条左缘

    # 页眉
    out.append(txt(0, HEAD_Y, "BANGUMI", t["title"], 22))
    out.append(txt(INNER, HEAD_Y, "bgm.tv/user/" + USER, t["title"], 16,
                   "end"))
    out.append(f'<rect x="0" y="{RULE_Y}" width="{INNER}" height="1" '
               f'fill="{t["rule"]}"/>')

    # 历史评价：按分数从高到低
    out.append(section(SEC1_LABEL_Y, "历史评价", d["rated_total"],
                       "部已评分", t))
    for i, row in enumerate(d["rated"]):
        top = ROW_TOP0 + i * ROW_PITCH
        out.append(cover(row, top, t))
        out.append(txt(ROW_X, top + 32,
                       clip(row["title"], 23, score_x - ROW_X - 44),
                       t["num"], 23))
        out.append(txt(ROW_X, top + 57, meta_of(row), t["title"], 16))
        out.append(txt(score_x, top + 51, str(row["rate"]), t["accent"], 34,
                       "end", 500))
        out.append(txt(INNER, top + 51, "分", t["title"], 16, "end"))

    # 最近在看
    last1 = ROW_TOP0 + max(len(d["rated"]) - 1, 0) * ROW_PITCH + COVER_H
    sec2 = last1 + SEC_GAP
    out.append(section(sec2, "最近在看", d["doing_total"], "部在追", t))
    tops = sec2 + 16
    for i, row in enumerate(d["doing"]):
        top = tops + i * ROW_PITCH
        out.append(cover(row, top, t))
        out.append(txt(ROW_X, top + 32,
                       clip(row["title"], 23, bar_x - ROW_X - 16),
                       t["num"], 23))
        out.append(txt(ROW_X, top + 57, meta_of(row), t["title"], 16))

        p = (row["ep"] / row["eps"]) if row["eps"] else 0
        bar_y = top + 21
        out.append(f'<rect x="{bar_x}" y="{bar_y}" width="{bar_w}" '
                   f'height="8" rx="4" fill="{t["track"]}"/>')
        if p > 0:
            w = max(6, bar_w * min(p, 1))
            fill = t["gold"] if p >= 1 else t["accent"]
            out.append(f'<rect x="{bar_x}" y="{bar_y}" width="{w:.1f}" '
                       f'height="8" rx="4" fill="{fill}"/>')
        ep = f"{row['ep']}/{row['eps']}" if row["eps"] else str(row["ep"])
        out.append(txt(INNER, top + 33, ep, t["title"], 16, "end"))

    if not d["doing"]:
        out.append(txt(ROW_X, tops + 32, "最近没有在看的番", t["title"], 18))

    if d["doing"]:
        inner_h = tops + (len(d["doing"]) - 1) * ROW_PITCH + COVER_H + 26
    else:
        inner_h = tops + 64
    height = inner_h + 2 * PANEL_PAD

    defs = (f'<defs><clipPath id="cover" clipPathUnits="userSpaceOnUse">'
            f'<rect width="{COVER_W}" height="{COVER_H}" rx="5"/>'
            f'</clipPath></defs>')
    panel = (f'<rect x="0.5" y="0.5" width="{W - 1}" height="{height - 1}" '
             f'rx="16" fill="{t["panel"]}" stroke="{t["border"]}"/>')

    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" '
            f'height="{height}" viewBox="0 0 {W} {height}" role="img" '
            f'aria-label="Bangumi：历史评价与最近在看">\n'
            + defs + "\n" + panel + "\n"
            + f'<g transform="translate({PANEL_PAD},{PANEL_PAD})">' + "\n"
            + "\n".join(out) + "\n</g>\n</svg>")


if __name__ == "__main__":
    import pathlib

    data = fetch()
    cache = {}
    for row in data["rated"] + data["doing"]:
        row["uri"] = cover_uri(row, cache)
        if not row["uri"]:
            # 宁可让 Action 失败、保留上一版，也不提交一张缺封面的卡片
            sys.exit(f"封面获取失败：{row['title']}")

    OUT = pathlib.Path(__file__).resolve().parent.parent / "assets"
    OUT.mkdir(exist_ok=True)
    for th in ("dark", "light"):
        (OUT / f"bangumi-{th}.svg").write_text(render(data, th), "utf-8")
    print(f"assets/bangumi-{{dark,light}}.svg · 历史评价 {data['rated_total']} 部"
          f" · 在看 {data['doing_total']} 部")