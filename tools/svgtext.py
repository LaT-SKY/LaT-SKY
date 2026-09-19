#!/usr/bin/env python3
"""把文字转成 SVG 路径。

GitHub 的 SVG 是在**访客的浏览器**里渲染的：Windows 用户没有思源宋体，
macOS 用户没有 Bebas Neue。只要用 font-family 写文字，主视觉就一定会掉字体。
所以标题必须转成 path —— 这样在任何设备上都是同一张图。
"""
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.misc.transform import Transform

_CACHE = {}


def load(path, index=0):
    key = (path, index)
    if key not in _CACHE:
        _CACHE[key] = TTFont(path, fontNumber=index, lazy=True)
    return _CACHE[key]


def measure(font, text, size, tracking=0.0):
    """返回文本宽度（px）。"""
    upem = font["head"].unitsPerEm
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    scale = size / upem
    x = 0.0
    for ch in text:
        gn = cmap.get(ord(ch))
        x += (hmtx[gn][0] * scale if gn else size * 0.5) + tracking
    return x - (tracking if text else 0.0)


def text_path(font, text, size, x=0.0, y=0.0, tracking=0.0):
    """返回 (path_d, width)。y 是基线位置。"""
    upem = font["head"].unitsPerEm
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    gs = font.getGlyphSet()
    scale = size / upem
    parts, cursor = [], x
    for ch in text:
        gn = cmap.get(ord(ch))
        if gn is None:
            cursor += size * 0.5 + tracking
            continue
        pen = SVGPathPen(gs, ntos=lambda v: f"{v:.2f}")
        gs[gn].draw(TransformPen(pen, Transform(scale, 0, 0, -scale, cursor, y)))
        d = pen.getCommands()
        if d:
            parts.append(d)
        cursor += hmtx[gn][0] * scale + tracking
    return " ".join(parts), cursor - x - (tracking if text else 0.0)
