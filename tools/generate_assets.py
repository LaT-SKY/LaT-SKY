#!/usr/bin/env python3
"""生成 assets/banner.svg 和 assets/divider.svg。

文字全部转成 path 的原因：GitHub 的 SVG 是在**访客的浏览器**里渲染的，
Windows 用户没有思源宋体、macOS 用户没有 Bebas Neue，
只要用 font-family 写字，主视觉就一定会掉字体。

    python3 tools/generate_assets.py
"""
import random
import svgtext as st

W, H = 1200, 360
R = 16  # 圆角：README 里 <img> 无法加样式，只能画进 SVG

SKY_TOP = "#06080F"
SKY_MID = "#0C1226"
SKY_LOW = "#1B1B40"
TEXT    = "#EDEFF7"
MUTED   = "#8892B4"
SAKURA  = "#F5A9C8"
ROSE    = "#E8657F"
GOLD    = "#EFC77E"
GOLD_D  = "#D9A441"
MOON    = "#F0DCB4"

SERIF_L = st.load("/usr/share/fonts/noto-cjk/NotoSerifCJK-Light.ttc", 2)
SERIF_M = st.load("/usr/share/fonts/noto-cjk/NotoSerifCJK-Medium.ttc", 2)
BEBAS   = st.load("/usr/local/share/fonts/b/BebasNeue_Regular.ttf", 0)
MONO    = st.load("/usr/share/fonts/maple/MapleMono-NF-CN-Regular.ttf", 0)

rnd = random.Random(20240919)


def starfield():
    out = []
    for _ in range(380):
        x, y = rnd.uniform(0, W), rnd.uniform(0, H * 0.9)
        if rnd.random() > (1.0 - y / H) ** 0.40:
            continue
        r = round(rnd.choice([0.5, 0.6, 0.7, 0.9, 1.1, 1.4]) * rnd.uniform(0.85, 1.2), 2)
        o = round(rnd.uniform(0.10, 0.92) * (1 - (y / H) ** 1.5), 2)
        if o <= 0.05:
            continue
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="#fff" opacity="{o}"/>')
    return "".join(out)


def sparkle(cx, cy, s, fill, opacity=1.0):
    k = s * 0.22
    d = (f"M{cx} {cy-s}C{cx+k} {cy-k} {cx+k} {cy-k} {cx+s} {cy}"
         f"C{cx+k} {cy+k} {cx+k} {cy+k} {cx} {cy+s}"
         f"C{cx-k} {cy+k} {cx-k} {cy+k} {cx-s} {cy}"
         f"C{cx-k} {cy-k} {cx-k} {cy-k} {cx} {cy-s}Z")
    return f'<path d="{d}" fill="{fill}" opacity="{opacity}"/>'


def petal(cx, cy, s, rot, opacity):
    d = "M0 0C5.5 -3 6.2 -10.5 0 -13C-6.2 -10.5 -5.5 -3 0 0Z"
    return (f'<g transform="translate({cx:.1f} {cy:.1f}) rotate({rot:.0f}) scale({s/13:.2f})">'
            f'<path d="{d}" fill="{SAKURA}" opacity="{opacity}"/></g>')


def meteor_streak(x, y, length, opacity):
    """斜向流星：渐隐光尾 + 明亮头点。"""
    dx, dy = length * 0.86, length * 0.51
    return (f'<g opacity="{opacity}" transform="translate({x} {y})">'
            f'<path d="M0 0L{dx:.0f} {dy:.0f}" stroke="url(#meteor)" stroke-width="1.5" '
            f'stroke-linecap="round" fill="none"/>'
            f'<circle cx="{dx:.0f}" cy="{dy:.0f}" r="1.9" fill="#fff" opacity="0.95"/></g>')


def wisp(cx, cy, rx, ry, fill, opacity):
    return f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{fill}" opacity="{opacity}"/>'


# 天际线：近乎笔直，只在偏右处留一个很轻的脉动
HZ = 300
horizon = (f"M0 {HZ}L624 {HZ}"
           f"L656 {HZ-7}L682 {HZ+8}L712 {HZ-19}L744 {HZ+11}L772 {HZ-4}L800 {HZ}"
           f"L{W} {HZ}")

name_d, name_w = st.text_path(SERIF_L, "望向天脉", 78, x=84, y=154, tracking=7.5)
lat_d,  lat_w  = st.text_path(BEBAS,   "LAT-SKY",  44, x=88, y=212, tracking=17)
sub_d,  sub_w  = st.text_path(MONO,    "Miprota · Protakarose · umamusume", 19, x=90, y=258, tracking=0.8)
ghost_d, ghost_w = st.text_path(SERIF_M, "脈", 232, x=0, y=0, tracking=0)

BANNER = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="望向天脉 / LaT-SKY">
<defs>
  <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{SKY_TOP}"/>
    <stop offset="0.50" stop-color="{SKY_MID}"/>
    <stop offset="1" stop-color="{SKY_LOW}"/>
  </linearGradient>

  <!-- 地平线以下升起的暖光：全图唯一的光源方向 -->
  <radialGradient id="dawn" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="{SAKURA}" stop-opacity="0.78"/>
    <stop offset="0.40" stop-color="{ROSE}" stop-opacity="0.34"/>
    <stop offset="1" stop-color="{ROSE}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="dawnGold" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="{GOLD}" stop-opacity="0.42"/>
    <stop offset="1" stop-color="{GOLD}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="moonGlow" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="{MOON}" stop-opacity="0.30"/>
    <stop offset="0.55" stop-color="{MOON}" stop-opacity="0.07"/>
    <stop offset="1" stop-color="{MOON}" stop-opacity="0"/>
  </radialGradient>

  <!-- 月亮受光自左下（与地平线辉光同向） -->
  <linearGradient id="moonFill" x1="0.15" y1="1" x2="0.9" y2="0.05">
    <stop offset="0" stop-color="#FFF6E2"/>
    <stop offset="0.55" stop-color="{MOON}"/>
    <stop offset="1" stop-color="#C9A96E"/>
  </linearGradient>

  <linearGradient id="hz" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{ROSE}" stop-opacity="0.14"/>
    <stop offset="0.22" stop-color="{SAKURA}" stop-opacity="0.62"/>
    <stop offset="0.56" stop-color="{SAKURA}" stop-opacity="0.92"/>
    <stop offset="0.74" stop-color="{GOLD}" stop-opacity="1"/>
    <stop offset="0.92" stop-color="{SAKURA}" stop-opacity="0.40"/>
    <stop offset="1" stop-color="{ROSE}" stop-opacity="0"/>
  </linearGradient>

  <radialGradient id="vignette" cx="0.5" cy="0.46" r="0.78">
    <stop offset="0.55" stop-color="#000" stop-opacity="0"/>
    <stop offset="1" stop-color="#04060E" stop-opacity="0.42"/>
  </radialGradient>

  <mask id="crescent">
    <rect width="{W}" height="{H}" fill="#000"/>
    <circle cx="1022" cy="104" r="47" fill="#fff"/>
    <circle cx="1047" cy="89" r="43.5" fill="#000"/>
  </mask>

  <linearGradient id="meteor" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#fff" stop-opacity="0"/>
    <stop offset="0.72" stop-color="#fff" stop-opacity="0.55"/>
    <stop offset="1" stop-color="#fff" stop-opacity="0.95"/>
  </linearGradient>
  <clipPath id="card"><rect width="{W}" height="{H}" rx="{R}"/></clipPath>

  <filter id="soften" x="-40%" y="-400%" width="180%" height="900%">
    <feGaussianBlur stdDeviation="4.5"/>
  </filter>
  <filter id="haze" x="-60%" y="-300%" width="220%" height="700%">
    <feGaussianBlur stdDeviation="17"/>
  </filter>
  <filter id="petalBlur" x="-70%" y="-70%" width="240%" height="240%">
    <feGaussianBlur stdDeviation="0.9"/>
  </filter>
  <filter id="grain" x="0" y="0" width="100%" height="100%">
    <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="4" stitchTiles="stitch"/>
    <feColorMatrix type="saturate" values="0"/>
  </filter>
</defs>

<g clip-path="url(#card)">
<rect width="{W}" height="{H}" fill="url(#sky)"/>
{starfield()}

<ellipse cx="512" cy="474" rx="880" ry="245" fill="url(#dawn)"/>
<ellipse cx="948" cy="456" rx="470" ry="172" fill="url(#dawnGold)"/>

<!-- 低空薄云：给辉光一点层次 -->
<g filter="url(#haze)">
{wisp(430, 286, 300, 15, SAKURA, 0.20)}
{wisp(760, 296, 360, 13, GOLD, 0.17)}
{wisp(1010, 278, 250, 11, SAKURA, 0.16)}
{wisp(170, 262, 210, 9, ROSE, 0.14)}
</g>

<circle cx="1022" cy="104" r="162" fill="url(#moonGlow)"/>
<circle cx="1022" cy="104" r="47" fill="url(#moonFill)" opacity="0.95" mask="url(#crescent)"/>

{sparkle(1046, 246, 11, GOLD, 0.9)}
{sparkle(196, 66, 7, "#fff", 0.6)}
{sparkle(918, 186, 5, SAKURA, 0.72)}
{sparkle(642, 40, 4.5, "#fff", 0.5)}
{sparkle(1148, 60, 5.5, "#fff", 0.5)}

<g filter="url(#petalBlur)">
{meteor_streak(214, 34, 132, 0.55)}
{meteor_streak(1052, 288, 76, 0.30)}

{petal(1128, 152, 12, 26, 0.58)}
{petal(1168, 226, 9, -34, 0.42)}
{petal(806, 84, 10, 58, 0.36)}
{petal(468, 52, 8, -12, 0.30)}
{petal(1084, 302, 8, 74, 0.44)}
{petal(612, 118, 7, 40, 0.26)}
{petal(288, 122, 6.5, -22, 0.24)}
{petal(960, 320, 7, 16, 0.30)}
</g>

<rect width="{W}" height="{H}" fill="url(#vignette)"/>

<path d="{horizon}" fill="none" stroke="url(#hz)" stroke-width="9" stroke-linecap="round" filter="url(#soften)" opacity="0.45"/>
<path d="{horizon}" fill="none" stroke="url(#hz)" stroke-width="1.7" stroke-linecap="round"/>

<rect width="{W}" height="{H}" filter="url(#grain)" opacity="0.042"/>

<path d="{name_d}" fill="{TEXT}"/>
<path d="{lat_d}" fill="{SAKURA}"/>
<path d="{sub_d}" fill="{MUTED}"/>
</g>
</svg>'''



def divider():
    h, y = 26, 13
    # 中心两侧各一个极小的脉动，呼应 banner 的天际线
    line = (f"M0 {y}L470 {y}L492 {y-4}L512 {y+5}L534 {y-8}L556 {y+3}L574 {y}"
            f"L626 {y}L644 {y-3}L666 {y+8}L688 {y-5}L708 {y+4}L730 {y}L{W} {y}")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" role="img" aria-label="分隔线">
<defs>
  <linearGradient id="dl" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{ROSE}" stop-opacity="0"/>
    <stop offset="0.30" stop-color="{ROSE}" stop-opacity="0.34"/>
    <stop offset="0.46" stop-color="{ROSE}" stop-opacity="0.62"/>
    <stop offset="0.54" stop-color="{ROSE}" stop-opacity="0.62"/>
    <stop offset="0.70" stop-color="{ROSE}" stop-opacity="0.34"/>
    <stop offset="1" stop-color="{ROSE}" stop-opacity="0"/>
  </linearGradient>
</defs>
<path d="{line}" fill="none" stroke="url(#dl)" stroke-width="1.6" stroke-linecap="round"/>
{sparkle(600, y, 8, GOLD_D, 1.0)}
{sparkle(600, y, 3.6, "#FFFFFF", 0.95)}
</svg>'''


# ── 输出 ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import pathlib
    OUT = pathlib.Path(__file__).resolve().parent.parent / "assets"
    OUT.mkdir(exist_ok=True)
    (OUT / "banner.svg").write_text(BANNER)
    (OUT / "divider.svg").write_text(divider())
    print("assets/banner.svg, assets/divider.svg 已更新")
