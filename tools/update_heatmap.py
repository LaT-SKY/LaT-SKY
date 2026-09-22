#!/usr/bin/env python3
"""生成贡献热力图（浅色 / 深色两版）。

为什么不用 ghchart：它的空格子写死 #EEEEEE，深色主题下会变成一片
刺眼的亮灰网格。自己生成才能两版都控色。

为什么用 <text> 而不是把文字转成 path：
  这张图要在 GitHub Actions 里每天自动重跑，而 CI 上没有 Maple Mono、
  也没有思源字体。改成系统字体栈交给访客的浏览器渲染，脚本就完全不依赖
  字体文件，Action 里零安装、零 pip 依赖。

用法：
    python3 tools/update_heatmap.py          # 需要已登录的 gh
    GH_TOKEN=xxx python3 tools/update_heatmap.py
"""
import datetime
import json
import subprocess
import sys
from xml.sax.saxutils import escape

W = 1200
CELL, GAP = 18, 4
PITCH = CELL + GAP
GRID_Y = 62

MONO = ('ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,'
        '"Liberation Mono",monospace')

THEMES = {
    "dark": {
        "ramp": ["#171E33", "#5C3A55", "#9E5B82", "#D4809F", "#F5A9C8"],
        "title": "#8892B4", "num": "#C8CFE2", "tick": "#5F6A8C",
    },
    "light": {
        "ramp": ["#EBEDF0", "#F7CFDE", "#F0A2BE", "#E36A8C", "#C43E63"],
        "title": "#6B7280", "num": "#3A4256", "tick": "#9AA1B5",
    },
}


def fetch(user="LaT-SKY"):
    q = ('{user(login:"%s"){contributionsCollection{contributionCalendar{'
         'totalContributions weeks{contributionDays{contributionCount date}}}}}}' % user)
    out = subprocess.run(["gh", "api", "graphql", "-f", f"query={q}"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"gh api 失败：{out.stderr[:300]}")
    cal = json.loads(out.stdout)["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    weeks = [[{"n": d["contributionCount"], "d": d["date"]} for d in w["contributionDays"]]
             for w in cal["weeks"]]
    flat = [d for w in weeks for d in w]
    return {"weeks": weeks, "start": flat[0]["d"], "end": flat[-1]["d"],
            "total": cal["totalContributions"]}


def level(n):
    return 0 if n == 0 else 1 if n <= 4 else 2 if n <= 11 else 3 if n <= 20 else 4


def txt(x, y, s, fill, size=17, anchor="start", weight=400):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return (f'<text x="{x:.0f}" y="{y}" fill="{fill}" font-size="{size}" '
            f'font-weight="{weight}" font-family=\'{MONO}\'{a}>{escape(s)}</text>')


def render(data, theme):
    t = THEMES[theme]
    weeks = data["weeks"]
    H = GRID_Y + 7 * PITCH - GAP + 6

    cells = []
    for ci, week in enumerate(weeks):
        for ri, day in enumerate(week):
            cells.append(f'<rect x="{ci*PITCH}" y="{GRID_Y+ri*PITCH}" width="{CELL}" '
                         f'height="{CELL}" rx="4.5" fill="{t["ramp"][level(day["n"])]}"/>')

    # 月份刻度：按每周中间那天判断是否翻月；末月靠右时改成右对齐，避免出画布
    ticks, prev_month, prev_x = [], None, -999
    for ci, week in enumerate(weeks):
        # 防护：如果是不完整的周（如第一周或最后一周），取最后一天作为判断基准
        mid_day = week[3] if len(week) > 3 else week[-1]
        mid = datetime.date.fromisoformat(mid_day["d"])
        
        x = ci * PITCH
        if mid.month != prev_month and x - prev_x >= 46:
            anchor = "end" if x > W - 44 else "start"
            ticks.append(txt(x, 48, f"{mid.month}月", t["tick"], size=15, anchor=anchor))
            prev_month, prev_x = mid.month, x

    head = (txt(0, 20, f"近一年贡献 · {data['start']} → {data['end']}", t["title"])
            + txt(W, 20, f"共 {data['total']:,} 次", t["num"], anchor="end", weight=500))

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="近一年贡献热力图">
{head}
{''.join(ticks)}
{''.join(cells)}
</svg>'''


if __name__ == "__main__":
    import pathlib

    data = fetch()
    OUT = pathlib.Path(__file__).resolve().parent.parent / "assets"
    OUT.mkdir(exist_ok=True)
    for th in ("dark", "light"):
        (OUT / f"heat-{th}.svg").write_text(render(data, th))
    print(f"assets/heat-{{dark,light}}.svg · {data['total']} 次 · {data['start']} → {data['end']}")