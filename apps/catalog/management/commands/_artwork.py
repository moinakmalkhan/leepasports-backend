"""
Generated placeholder artwork for the demo catalog (Pillow only, no external assets).

Every product colour gets a studio-style shot: the garment silhouette in that colour,
soft shadow, directional light, on a tinted backdrop. Banners and category tiles use
the same drawing primitives so the storefront looks complete straight after seeding.
Real photography uploaded in the admin replaces these at any time.
"""

from __future__ import annotations

import io

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

SS = 2  # supersampling factor for smooth edges
ROSE = (225, 29, 72)
INK = (28, 25, 23)
PAPER = (245, 241, 237)


def _rgb(hex_: str) -> tuple[int, int, int]:
    hex_ = hex_.lstrip("#")
    return tuple(int(hex_[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _mix(a, b, t: float):
    return tuple(round(a[i] * (1 - t) + b[i] * t) for i in range(3))


def _lum(c) -> float:
    return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover - very old Pillow
        return ImageFont.load_default()


# --- silhouettes: polygons in a 0..1 box --------------------------------------------------


def _p(points, w, h, box=(0, 0, 1, 1)):
    x0, y0, x1, y1 = box
    return [((x0 + x * (x1 - x0)) * w, (y0 + y * (y1 - y0)) * h) for x, y in points]


TEE = [
    (0.38, 0.17),
    (0.44, 0.16),
    (0.47, 0.2),
    (0.5, 0.21),
    (0.53, 0.2),
    (0.56, 0.16),
    (0.62, 0.17),
    (0.82, 0.28),
    (0.75, 0.42),
    (0.67, 0.37),
    (0.68, 0.84),
    (0.32, 0.84),
    (0.33, 0.37),
    (0.25, 0.42),
    (0.18, 0.28),
]
LONG = [
    (0.38, 0.17),
    (0.44, 0.16),
    (0.47, 0.2),
    (0.5, 0.21),
    (0.53, 0.2),
    (0.56, 0.16),
    (0.62, 0.17),
    (0.78, 0.26),
    (0.86, 0.74),
    (0.78, 0.76),
    (0.69, 0.4),
    (0.69, 0.84),
    (0.31, 0.84),
    (0.31, 0.4),
    (0.22, 0.76),
    (0.14, 0.74),
    (0.22, 0.26),
]
HOODIE = [
    (0.36, 0.22),
    (0.64, 0.22),
    (0.8, 0.3),
    (0.87, 0.76),
    (0.78, 0.78),
    (0.71, 0.44),
    (0.71, 0.86),
    (0.29, 0.86),
    (0.29, 0.44),
    (0.22, 0.78),
    (0.13, 0.76),
    (0.2, 0.3),
]
JOGGER = [
    (0.33, 0.14),
    (0.67, 0.14),
    (0.7, 0.84),
    (0.66, 0.9),
    (0.54, 0.9),
    (0.51, 0.36),
    (0.49, 0.36),
    (0.46, 0.9),
    (0.34, 0.9),
    (0.3, 0.84),
]
LEGGING = [
    (0.36, 0.12),
    (0.64, 0.12),
    (0.63, 0.5),
    (0.58, 0.92),
    (0.52, 0.92),
    (0.5, 0.36),
    (0.48, 0.92),
    (0.42, 0.92),
    (0.37, 0.5),
]
SHORTS = [(0.3, 0.3), (0.7, 0.3), (0.75, 0.66), (0.53, 0.69), (0.5, 0.48), (0.47, 0.69), (0.25, 0.66)]
BRA = [
    (0.3, 0.3),
    (0.37, 0.24),
    (0.42, 0.38),
    (0.5, 0.42),
    (0.58, 0.38),
    (0.63, 0.24),
    (0.7, 0.3),
    (0.72, 0.56),
    (0.66, 0.66),
    (0.34, 0.66),
    (0.28, 0.56),
]


def _garment(kind: str, w: int, h: int, color, draw_shape):
    """Return (mask, details) for a garment kind drawn into a w×h canvas."""
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    details: list = []
    dark = _mix(color, (0, 0, 0), 0.25) if _lum(color) > 0.25 else _mix(color, (255, 255, 255), 0.18)

    def poly(points, box=(0, 0, 1, 1)):
        md.polygon(_p(points, w, h, box), fill=255)

    if kind in ("tee", "polo", "compression", "longsleeve"):
        poly(LONG if kind in ("compression", "longsleeve") else TEE)
        cx = w * 0.5
        details.append(("arc", [cx - w * 0.07, h * 0.13, cx + w * 0.07, h * 0.25], 15, 165, dark, int(w * 0.012)))
        if kind == "polo":
            details.append(
                ("poly", _p([(0.44, 0.16), (0.5, 0.26), (0.56, 0.16), (0.53, 0.15), (0.5, 0.21), (0.47, 0.15)], w, h), dark)
            )
            details.append(("line", [(cx, h * 0.21), (cx, h * 0.33)], dark, int(w * 0.008)))
    elif kind in ("hoodie", "jacket", "tracksuit"):
        if kind == "hoodie":
            md.ellipse([w * 0.37, h * 0.08, w * 0.63, h * 0.32], fill=255)
        poly(HOODIE)
        if kind == "hoodie":
            details.append(("rrect", [w * 0.36, h * 0.6, w * 0.64, h * 0.76], int(w * 0.03), dark))
            details.append(("line", [(w * 0.46, h * 0.27), (w * 0.45, h * 0.42)], dark, int(w * 0.007)))
            details.append(("line", [(w * 0.54, h * 0.27), (w * 0.55, h * 0.42)], dark, int(w * 0.007)))
            details.append(("arc", [w * 0.41, h * 0.12, w * 0.59, h * 0.3], 0, 180, dark, int(w * 0.012)))
        else:
            details.append(("line", [(w * 0.5, h * 0.22), (w * 0.5, h * 0.86)], dark, int(w * 0.01)))
            details.append(("poly", _p([(0.4, 0.2), (0.5, 0.3), (0.6, 0.2), (0.58, 0.16), (0.42, 0.16)], w, h), dark))
            if kind == "tracksuit":
                details.append(("line", [(w * 0.205, h * 0.31), (w * 0.14, h * 0.75)], (245, 245, 245), int(w * 0.012)))
                details.append(("line", [(w * 0.795, h * 0.31), (w * 0.86, h * 0.75)], (245, 245, 245), int(w * 0.012)))
    elif kind in ("jogger", "trackpant"):
        poly(JOGGER)
        details.append(("rect", [w * 0.33, h * 0.14, w * 0.67, h * 0.2], dark))
        details.append(("rect", [w * 0.34, h * 0.86, w * 0.46, h * 0.9], dark))
        details.append(("rect", [w * 0.54, h * 0.86, w * 0.66, h * 0.9], dark))
        details.append(("line", [(w * 0.47, h * 0.2), (w * 0.46, h * 0.3)], (240, 240, 240), int(w * 0.006)))
        details.append(("line", [(w * 0.53, h * 0.2), (w * 0.54, h * 0.3)], (240, 240, 240), int(w * 0.006)))
    elif kind == "legging":
        poly(LEGGING)
        details.append(("rect", [w * 0.36, h * 0.12, w * 0.64, h * 0.17], dark))
    elif kind == "shorts":
        poly(SHORTS)
        details.append(("rect", [w * 0.3, h * 0.3, w * 0.7, h * 0.36], dark))
    elif kind == "bra":
        poly(BRA)
        details.append(("rect", [w * 0.335, h * 0.58, w * 0.665, h * 0.66], dark))
    elif kind == "set":
        poly(LEGGING, (0.18, 0.3, 0.82, 1.0))
        poly(BRA, (0.1, -0.1, 0.9, 0.62))
    elif kind == "cap":
        md.pieslice([w * 0.24, h * 0.3, w * 0.76, h * 0.78], 180, 360, fill=255)
        md.rectangle([w * 0.24, h * 0.53, w * 0.76, h * 0.56], fill=255)
        md.ellipse([w * 0.52, h * 0.5, w * 0.9, h * 0.62], fill=255)
        details.append(("ellipse", [w * 0.48, h * 0.29, w * 0.52, h * 0.32], dark))
        details.append(("line", [(w * 0.5, h * 0.31), (w * 0.5, h * 0.54)], dark, int(w * 0.006)))
    elif kind == "beanie":
        md.pieslice([w * 0.26, h * 0.26, w * 0.74, h * 0.82], 180, 360, fill=255)
        md.rectangle([w * 0.26, h * 0.54, w * 0.74, h * 0.68], fill=255)
        md.ellipse([w * 0.44, h * 0.18, w * 0.56, h * 0.3], fill=255)
        details.append(("rect", [w * 0.26, h * 0.56, w * 0.74, h * 0.68], dark))
    elif kind == "socks":
        for off in (-0.13, 0.11):
            pts = [(0.36, 0.18), (0.5, 0.18), (0.5, 0.6), (0.66, 0.72), (0.64, 0.84), (0.44, 0.84), (0.36, 0.72)]
            md.polygon([(x + off * w, y) for x, y in _p(pts, w, h)], fill=255)
            details.append(("rect", [(0.36 + off) * w, h * 0.18, (0.5 + off) * w, h * 0.24], dark))
    elif kind == "bag":
        md.rounded_rectangle([w * 0.16, h * 0.38, w * 0.84, h * 0.78], radius=int(w * 0.12), fill=255)
        md.arc([w * 0.33, h * 0.22, w * 0.67, h * 0.52], 180, 360, fill=255, width=int(w * 0.035))
        details.append(("line", [(w * 0.22, h * 0.45), (w * 0.78, h * 0.45)], dark, int(w * 0.01)))
    elif kind == "bottle":
        md.rounded_rectangle([w * 0.38, h * 0.26, w * 0.62, h * 0.86], radius=int(w * 0.06), fill=255)
        md.rounded_rectangle([w * 0.42, h * 0.16, w * 0.58, h * 0.28], radius=int(w * 0.02), fill=255)
        details.append(("rect", [w * 0.42, h * 0.16, w * 0.58, h * 0.24], dark))
    elif kind == "towel":
        md.rounded_rectangle([w * 0.2, h * 0.3, w * 0.8, h * 0.74], radius=int(w * 0.03), fill=255)
        details.append(("rect", [w * 0.2, h * 0.64, w * 0.8, h * 0.68], dark))
    else:
        poly(TEE)
    return mask, details


def _draw_details(draw: ImageDraw.ImageDraw, details):
    for d in details:
        kind = d[0]
        if kind == "arc":
            draw.arc(d[1], d[2], d[3], fill=d[4], width=d[5])
        elif kind == "line":
            draw.line(d[1], fill=d[2], width=d[3])
        elif kind == "poly":
            draw.polygon(d[1], fill=d[2])
        elif kind == "rect":
            draw.rectangle(d[1], fill=d[2])
        elif kind == "rrect":
            draw.rounded_rectangle(d[1], radius=d[2], fill=d[3])
        elif kind == "ellipse":
            draw.ellipse(d[1], fill=d[2])


def kind_for(tags: list[str], category_slug: str) -> str:
    text = " ".join(tags + [category_slug])
    for needle, kind in (
        ("tracksuit", "tracksuit"),
        ("sports-bra", "bra"),
        ("bra", "bra"),
        ("set", "set"),
        ("legging", "legging"),
        ("hoodie", "hoodie"),
        ("sweatshirt", "hoodie"),
        ("jacket", "jacket"),
        ("windbreaker", "jacket"),
        ("jogger", "jogger"),
        ("track-pant", "jogger"),
        ("trouser", "jogger"),
        ("short", "shorts"),
        ("polo", "polo"),
        ("compression", "compression"),
        ("long-sleeve", "longsleeve"),
        ("beanie", "beanie"),
        ("cap", "cap"),
        ("sock", "socks"),
        ("bag", "bag"),
        ("duffel", "bag"),
        ("bottle", "bottle"),
        ("towel", "towel"),
    ):
        if needle in text:
            return kind
    return "tee"


def _backdrop(w: int, h: int, top, bottom) -> Image.Image:
    grad = Image.linear_gradient("L").resize((w, h))
    return Image.composite(Image.new("RGB", (w, h), bottom), Image.new("RGB", (w, h), top), grad)


def _render_garment(canvas: Image.Image, kind: str, color, box, *, logo=True):
    """Paint a shaded garment with a soft floor shadow into `box` (x0, y0, x1, y1) of `canvas`."""
    x0, y0, x1, y1 = (int(v) for v in box)
    w, h = x1 - x0, y1 - y0
    mask, details = _garment(kind, w, h, color, None)
    # shadow
    shadow = Image.new("L", canvas.size, 0)
    shadow.paste(mask, (x0 + int(w * 0.025), y0 + int(h * 0.03)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(6, w // 40)))
    canvas.paste(Image.new("RGB", canvas.size, (0, 0, 0)), (0, 0), shadow.point(lambda v: int(v * 0.28)))
    # garment body with directional light (top-left highlight → bottom-right shade)
    body = Image.new("RGB", (w, h), color)
    light = Image.linear_gradient("L").rotate(45, expand=False).resize((w, h))
    highlight = _mix(color, (255, 255, 255), 0.16)
    shade = _mix(color, (0, 0, 0), 0.22)
    shaded = Image.composite(Image.new("RGB", (w, h), shade), Image.new("RGB", (w, h), highlight), light)
    body = Image.blend(body, shaded, 0.55)
    d = ImageDraw.Draw(body)
    _draw_details(d, details)
    if logo and kind not in ("socks", "bottle", "towel", "legging"):
        mark = (255, 255, 255) if _lum(color) < 0.55 else INK
        size = max(10, int(w * 0.035))
        pos = {
            "jogger": (0.4, 0.27),
            "trackpant": (0.4, 0.27),
            "shorts": (0.4, 0.45),
            "cap": (0.5, 0.45),
            "beanie": (0.5, 0.45),
            "bag": (0.5, 0.6),
            "bra": (0.5, 0.5),
            "set": (0.5, 0.3),
        }.get(kind, (0.5, 0.36))
        d.text((w * pos[0], h * pos[1]), "CHOBBAR", fill=mark, font=_font(size), anchor="mm")
    # subtle fabric edge
    edge = mask.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(3))
    body.paste(_mix(color, (0, 0, 0), 0.35), (0, 0), edge.point(lambda v: int(v * 0.5)))
    canvas.paste(body, (x0, y0), mask)


def product_image(kind: str, hex_: str, *, variant: int = 0, size=(800, 1000)) -> bytes:
    """variant 0: studio front shot; 1: close crop on a deeper backdrop (used as the hover image)."""
    w, h = size[0] * SS, size[1] * SS
    color = _rgb(hex_)
    base = (231, 225, 218) if _lum(color) > 0.72 else PAPER
    if variant == 0:
        top, bottom = _mix(base, color, 0.08), _mix(base, color, 0.18)
        canvas = _backdrop(w, h, top, bottom)
        _render_garment(canvas, kind, color, (w * 0.06, h * 0.08, w * 0.94, h * 0.92))
    else:
        deep = _mix(color, INK, 0.55) if _lum(color) > 0.3 else _mix(color, (120, 113, 108), 0.35)
        canvas = _backdrop(w, h, _mix(deep, (255, 255, 255), 0.12), deep)
        _render_garment(canvas, kind, color, (-w * 0.12, h * 0.02, w * 1.12, h * 1.12))
    d = ImageDraw.Draw(canvas)
    tag = (255, 255, 255) if variant else _mix(base, INK, 0.45)
    d.text((w * 0.05, h * 0.955), "CHOBBAR", fill=tag, font=_font(int(w * 0.024)), anchor="ls")
    return _jpeg(canvas.resize(size, Image.LANCZOS))


def tile_image(kind: str, hex_: str, accent=ROSE, size=(600, 600)) -> bytes:
    """Square category / collection tile."""
    w, h = size[0] * SS, size[1] * SS
    color = _rgb(hex_)
    canvas = _backdrop(w, h, _mix(PAPER, accent, 0.06), _mix(PAPER, accent, 0.16))
    d = ImageDraw.Draw(canvas)
    d.ellipse([w * 0.18, h * 0.14, w * 0.82, h * 0.78], fill=_mix(PAPER, accent, 0.22))
    _render_garment(canvas, kind, color, (w * 0.1, h * 0.06, w * 0.9, h * 0.94))
    return _jpeg(canvas.resize(size, Image.LANCZOS))


def banner_image(kinds: list[tuple[str, str]], *, size=(1920, 820), tone=INK, accent=ROSE) -> bytes:
    """Wide hero: dark backdrop, rose glow, diagonal stripes and a row of garments on the right (text sits left)."""
    w, h = size[0] * SS, size[1] * SS
    canvas = _backdrop(w, h, _mix(tone, (255, 255, 255), 0.06), tone)
    glow = Image.new("L", (w, h), 0)
    gd = ImageDraw.Draw(glow)
    portrait = h > w
    cx, cy = (w * 0.5, h * 0.68) if portrait else (w * 0.7, h * 0.5)
    r = (w * 0.55) if portrait else (h * 0.75)
    gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(int(r * 0.45)))
    canvas.paste(Image.new("RGB", (w, h), accent), (0, 0), glow.point(lambda v: int(v * 0.55)))
    stripes = Image.new("L", (w, h), 0)
    sd = ImageDraw.Draw(stripes)
    step = int(min(w, h) * 0.06)
    for i in range(-h, w, step):
        sd.line([(i, h), (i + h, 0)], fill=255, width=max(2, step // 7))
    canvas.paste(Image.new("RGB", (w, h), (255, 255, 255)), (0, 0), stripes.point(lambda v: int(v * 0.035)))
    n = len(kinds)
    aspect = 0.8  # garment boxes keep the product-shot proportions

    def fitted(cx_, top, bottom):
        gh = bottom - top
        gw = gh * aspect
        return (cx_ - gw / 2, top, cx_ + gw / 2, bottom)

    if portrait:
        slot_w = w * 0.96 / n
        gh = min(h * 0.5, slot_w * 1.15 / aspect)
        for i, (kind, hex_) in enumerate(kinds):
            cx_ = w * 0.02 + slot_w * (i + 0.5)
            _render_garment(canvas, kind, _rgb(hex_), fitted(cx_, h * 0.97 - gh, h * 0.97), logo=False)
        shade = Image.linear_gradient("L").resize((w, h))  # dark at the top where the copy sits
    else:
        slot_w = w * 0.52 / n
        gh = min(h * 0.86, slot_w * 1.25 / aspect)
        for i, (kind, hex_) in enumerate(kinds):
            cx_ = w * 0.46 + slot_w * (i + 0.5)
            lift = h * (0.035 if i % 2 else 0.0)
            top = (h - gh) / 2 + lift
            _render_garment(canvas, kind, _rgb(hex_), fitted(cx_, top, top + gh), logo=False)
        shade = Image.linear_gradient("L").rotate(90).resize((w, h))  # rotate(90): dark on the left where the copy sits
        shade = ImageChops.invert(shade) if shade.getpixel((0, h // 2)) > 128 else shade
    canvas = Image.composite(canvas, Image.new("RGB", (w, h), tone), shade.point(lambda v: min(255, int(70 + v * 1.4))))
    return _jpeg(canvas.resize(size, Image.LANCZOS), quality=84)


def _jpeg(img: Image.Image, quality: int = 82) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()
