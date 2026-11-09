#!/usr/bin/env python3
"""Generate the 4x3 Anti-Entropy Generator KAnim (world atlas + build menu icon).

The artwork is drawn procedurally at 3x resolution and downsampled, which keeps
the small details (bevels, brushed metal, engraved ticks) crisp in game.
"""
from __future__ import annotations

import math
import struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "anim" / "assets" / "anti_entropy_generator"

FRAME_W, FRAME_H = 512, 384
COLS, ROWS = 4, 2
COUNT = COLS * ROWS
UI_SIZE = 256
S = 3  # supersampling factor

# 4x3, OnFloor, non-rotatable vanilla reference: FabricatedWoodMaker
# (plantmatter_compressor_kanim).  Its idle bounds are approximately
# (30, -326, 843, 679); the UI symbol is about 270x230.
WORLD_BOUNDS = (30.0, -326.0, 843.0, 679.0)
UI_BOUNDS = (10.0, -120.0, 270.0, 230.0)

WORLD_NAME = "world"
WORKING_NAME = "working"
OFF_NAME = "off"
PLACE_NAME = "place"
UI_NAME = "ui"


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def sdbm_lower(text: str) -> int:
    h = 0
    for ch in text.lower():
        h = (ord(ch) + (h << 6) + (h << 16) - h) & 0xFFFFFFFF
    return (h ^ 0x80000000) - 0x80000000


def kstring(text: str) -> bytes:
    data = text.encode("utf-8")
    return struct.pack("<i", len(data)) + data


def sc(value: float) -> int:
    return int(round(value * S))


def vgrad(size, stops):
    """Vertical RGBA gradient.  stops = [(0..1, (r, g, b, a)), ...]."""
    w, h = size
    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
    ps = [s[0] for s in stops]
    arr = np.empty((h, 4), np.float32)
    for k in range(4):
        arr[:, k] = np.interp(ys, ps, [s[1][k] for s in stops])
    arr = np.repeat(arr[:, None, :], w, axis=1)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def hgrad(size, stops):
    """Horizontal RGBA gradient, used for cylindrical metal parts."""
    w, h = size
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
    arr = np.empty((h, w, 4), np.float32)
    for k in range(4):
        row = np.interp(xs, [s[0] for s in stops], [s[1][k] for s in stops])
        arr[:, :, k] = row[None, :]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def radial(size, center, radius, stops):
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt((xx - center[0]) ** 2 + (yy - center[1]) ** 2) / max(1.0, radius)
    d = np.clip(d, 0.0, 1.0)
    ps = [s[0] for s in stops]
    arr = np.empty((h, w, 4), np.float32)
    for k in range(4):
        arr[..., k] = np.interp(d, ps, [s[1][k] for s in stops])
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def fade(size, top: int, bottom: int):
    """Vertical alpha mask."""
    w, h = size
    arr = np.linspace(top, bottom, h).astype(np.uint8)[:, None]
    arr = np.repeat(arr, w, axis=1)
    return Image.fromarray(arr)


def mask_rrect(size, box, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle(box, radius=radius, fill=255)
    return m


def mask_ellipse(size, box):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).ellipse(box, fill=255)
    return m


def mask_polygon(size, points):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).polygon(points, fill=255)
    return m


def mul_alpha(layer, mask):
    r, g, b, a = layer.split()
    a = ImageChops.multiply(a, mask)
    return Image.merge("RGBA", (r, g, b, a))


def stroke(size, box, radius, colour, width):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(
        box, radius=radius, outline=colour, width=width
    )
    return layer


def add_scratches(img, mask, seed, count, alpha=38):
    """Sparse micro-scratches: light scuffs plus darker grime lines."""
    W, H = img.size
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rng = np.random.default_rng(seed)
    for _ in range(count):
        x = float(rng.uniform(0, W))
        y = float(rng.uniform(0, H))
        length = float(rng.uniform(10, 90)) * S * 0.6
        angle = float(rng.normal(-0.35, 0.5))
        dx = math.cos(angle) * length
        dy = math.sin(angle) * length
        a = int(rng.uniform(alpha * 0.25, alpha))
        width = max(1, int(rng.integers(1, 3)))
        if rng.random() < 0.62:
            colour = (215, 230, 245, a)
        else:
            colour = (10, 14, 20, int(a * 1.3))
        d.line([x, y, x + dx, y + dy], fill=colour, width=width)
    layer = layer.filter(ImageFilter.GaussianBlur(0.7 * S))
    layer = mul_alpha(layer, mask)
    img.alpha_composite(layer)
    return img


def apply_texture(img, mask, seed, brushed=0.09, grain=0.022, mottle=0.05,
                  scratches=0, vertical=False):
    """Brushed metal, fine grain and blotchy patina, restricted to a mask."""
    arr = np.asarray(img).astype(np.float32)
    h, w = arr.shape[:2]
    rng = np.random.default_rng(seed)

    # Low-frequency blotches: handling marks / patina.
    small = rng.normal(0.0, 1.0, (max(4, h // 44), max(4, w // 44))).astype(np.float32)
    m_img = Image.fromarray(np.clip(small * 54 + 128, 0, 255).astype(np.uint8)).resize(
        (w, h), Image.BICUBIC
    )
    mot = (np.asarray(m_img).astype(np.float32) - 128.0) / 128.0

    # Stretched low-res noise -> visible brushing after downsampling.
    if vertical:
        small = rng.normal(0.0, 1.0, (max(2, h // 110), max(2, w // 5))).astype(np.float32)
    else:
        small = rng.normal(0.0, 1.0, (max(2, h // 5), max(2, w // 110))).astype(np.float32)
    b_img = Image.fromarray(np.clip(small * 54 + 128, 0, 255).astype(np.uint8)).resize(
        (w, h), Image.BICUBIC
    )
    b = (np.asarray(b_img).astype(np.float32) - 128.0) / 128.0

    # Fine grain, generated at half resolution so it survives the 3x downsample.
    small = rng.normal(0.0, 1.0, (max(2, h // 2), max(2, w // 2))).astype(np.float32)
    g_img = Image.fromarray(np.clip(small * 50 + 128, 0, 255).astype(np.uint8)).resize(
        (w, h), Image.BICUBIC
    )
    g = (np.asarray(g_img).astype(np.float32) - 128.0) / 128.0

    factor = (1.0 + b * brushed + g * grain + mot * mottle)[..., None]
    m = (np.asarray(mask).astype(np.float32) / 255.0)[..., None]
    arr[..., :3] = arr[..., :3] * (1.0 - m) + arr[..., :3] * factor * m
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

    if scratches:
        img = add_scratches(img, mask, seed + 101, scratches)
    return img


def final_grain(img, seed=0, strength=0.022):
    """Per-pixel grain applied after downsampling, so it stays visible."""
    arr = np.asarray(img).astype(np.float32)
    h, w = arr.shape[:2]
    rng = np.random.default_rng(seed)
    n = (rng.normal(0.0, 1.0, (h, w)).astype(np.float32) * strength)[..., None]
    a = arr[..., 3:4] / 255.0
    arr[..., :3] = arr[..., :3] * (1.0 + n * a)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def add_glow(img, center, radius, colour, alpha, blur):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = center
    for k in range(6, 0, -1):
        r = radius * (0.55 + 0.14 * k)
        a = int(alpha * (7 - k) / 6.0)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*colour, a))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    img.alpha_composite(layer)


def hex_points(cx, cy, radius, rot=math.pi / 6):
    return [
        (cx + math.cos(rot + i * math.pi / 3) * radius,
         cy + math.sin(rot + i * math.pi / 3) * radius)
        for i in range(6)
    ]


# ---------------------------------------------------------------------------
# world frame
# ---------------------------------------------------------------------------

def gear_polygon(cx, cy, r_root, r_tip, teeth, angle):
    """Outline of a spur gear: alternating root and tooth-tip arcs."""
    pts = []
    step = 2 * math.pi / teeth
    for i in range(teeth):
        a0 = angle + i * step
        a1 = a0 + step
        pts.append((cx + math.cos(a0) * r_root, cy + math.sin(a0) * r_root))
        pts.append((cx + math.cos(a0 + step * 0.10) * r_tip,
                    cy + math.sin(a0 + step * 0.10) * r_tip))
        pts.append((cx + math.cos(a1 - step * 0.10) * r_tip,
                    cy + math.sin(a1 - step * 0.10) * r_tip))
        pts.append((cx + math.cos(a1) * r_root, cy + math.sin(a1) * r_root))
    return pts


def draw_frame(index: int, dim: bool = False, working: bool = True) -> Image.Image:
    W, H = FRAME_W * S, FRAME_H * S
    size = (W, H)
    img = Image.new("RGBA", size, (0, 0, 0, 0))

    phase = (index / COUNT) if working else 0.0
    angle = 2 * math.pi * phase
    pulse = 0.5 + 0.5 * math.sin(2 * math.pi * phase)

    # --- palette ---------------------------------------------------------
    shell_top = (54, 71, 90, 255)
    shell_mid = (33, 46, 61, 255)
    shell_bot = (15, 22, 30, 255)
    panel_top = (15, 23, 32, 255)
    panel_mid = (20, 30, 41, 255)
    panel_bot = (9, 14, 20, 255)
    brass_hi = (232, 201, 141, 255)
    brass_mid = (176, 137, 80, 255)
    brass_lo = (104, 76, 40, 255)
    cyan = (110, 245, 230, 255)

    # --- soft shadow -----------------------------------------------------
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [sc(28), sc(32), sc(486), sc(372)], radius=sc(30), fill=(0, 0, 0, 125)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(sc(11)))
    img.alpha_composite(shadow)

    # --- chassis ---------------------------------------------------------
    body_box = [sc(18), sc(18), sc(494), sc(366)]
    body_mask = mask_rrect(size, body_box, sc(28))
    body = vgrad(
        size,
        [(0.0, shell_top), (0.16, (42, 57, 73, 255)), (0.55, shell_mid), (1.0, shell_bot)],
    )
    img.paste(body, (0, 0), body_mask)

    # dark outer edge + top bevel + bottom occlusion
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(body_box, radius=sc(28), outline=(5, 8, 12, 255), width=sc(3))

    top_bevel = stroke(size, [sc(21), sc(21), sc(491), sc(363)], sc(26),
                       (186, 210, 232, 150), sc(2))
    top_bevel = mul_alpha(top_bevel, fade(size, 255, 20))
    img.alpha_composite(top_bevel)

    bottom_bevel = stroke(size, [sc(21), sc(21), sc(491), sc(363)], sc(26),
                          (0, 0, 0, 190), sc(5))
    bottom_bevel = mul_alpha(bottom_bevel, fade(size, 0, 230))
    img.alpha_composite(bottom_bevel)

    # left/right edge light for extra dimensionality
    edge_l = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(edge_l).line([sc(22), sc(30), sc(22), sc(354)],
                                fill=(196, 220, 244, 70), width=sc(1))
    img.alpha_composite(mul_alpha(edge_l, body_mask))
    edge_r = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(edge_r).line([sc(490), sc(30), sc(490), sc(354)],
                                fill=(0, 0, 0, 120), width=sc(2))
    img.alpha_composite(mul_alpha(edge_r, body_mask))

    # --- recessed front panel -------------------------------------------
    panel_box = [sc(40), sc(40), sc(472), sc(344)]
    panel_mask = mask_rrect(size, panel_box, sc(20))
    panel = vgrad(
        size,
        [(0.0, panel_top), (0.45, panel_mid), (1.0, panel_bot)],
    )
    img.paste(panel, (0, 0), panel_mask)

    # inner shadow along the top of the recess
    panel_shadow = stroke(size, [sc(42), sc(42), sc(470), sc(342)], sc(19),
                          (0, 0, 0, 210), sc(7))
    panel_shadow = panel_shadow.filter(ImageFilter.GaussianBlur(sc(2)))
    panel_shadow = mul_alpha(panel_shadow, ImageChops.multiply(fade(size, 255, 0), panel_mask))
    img.alpha_composite(panel_shadow)

    # thin brass inlay around the panel
    inlay = stroke(size, [sc(47), sc(47), sc(465), sc(337)], sc(15),
                   (214, 178, 112, 80), sc(1))
    inlay = mul_alpha(inlay, fade(size, 190, 90))
    img.alpha_composite(inlay)

    # glass sheen (soft diagonal band)
    sheen = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(sheen).polygon(
        [(sc(40), sc(170)), (sc(210), sc(40)), (sc(316), sc(40)), (sc(40), sc(250))],
        fill=(170, 225, 255, 16),
    )
    sheen = sheen.filter(ImageFilter.GaussianBlur(sc(20)))
    sheen = mul_alpha(sheen, panel_mask)
    img.alpha_composite(sheen)

    # panel vignette
    vig = radial(
        size, (sc(256), sc(192)), sc(300),
        [(0.0, (0, 0, 0, 0)), (0.62, (0, 0, 0, 0)), (1.0, (0, 0, 0, 105))],
    )
    img.alpha_composite(Image.composite(vig, Image.new("RGBA", size), panel_mask))

    # faint etched hex grid on the front panel
    grid = Image.new("RGBA", size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    hr = sc(13)
    hstep = hr * 1.5
    vstep = hr * math.sqrt(3)
    row = 0
    yy = -vstep
    while yy < H + vstep:
        xx = -hstep + (row % 2) * hstep
        while xx < W + hstep:
            gd.polygon(hex_points(xx, yy, hr), outline=(140, 190, 220, 11))
            xx += hstep * 2
        yy += vstep
        row += 1
    grid = mul_alpha(grid, panel_mask)
    img.alpha_composite(grid)

    # engraved guide lines
    d = ImageDraw.Draw(img)
    for y in (108, 282):
        d.line([sc(98), sc(y), sc(414), sc(y)], fill=(140, 180, 210, 16), width=sc(1))
    for x in (96, 416):
        d.line([sc(x), sc(114), sc(x), sc(280)], fill=(140, 180, 210, 12), width=sc(1))

    # --- top heat-sink fins ---------------------------------------------
    fin_slot = mask_rrect(size, [sc(106), sc(48), sc(406), sc(104)], sc(12))
    slot = vgrad(size, [(0.0, (5, 8, 12, 255)), (1.0, (18, 25, 34, 255))])
    img.paste(slot, (0, 0), fin_slot)
    slot_rim = stroke(size, [sc(106), sc(48), sc(406), sc(104)], sc(12),
                      (92, 116, 142, 90), sc(2))
    slot_rim = mul_alpha(slot_rim, fade(size, 200, 40))
    img.alpha_composite(slot_rim)

    # cast shadows on the slot floor
    for i in range(7):
        x = 126 + i * 40
        sh = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle(
            [sc(x + 4), sc(58), sc(x + 22), sc(101)], radius=sc(6),
            fill=(0, 0, 0, 130),
        )
        sh = sh.filter(ImageFilter.GaussianBlur(sc(3)))
        img.alpha_composite(mul_alpha(sh, fin_slot))

    for i in range(7):
        x = 126 + i * 40
        box = [sc(x), sc(53), sc(x + 18), sc(100)]
        fin_mask = mask_rrect(size, box, sc(6))
        fin = vgrad(
            size,
            [(0.0, (142, 168, 194, 255)), (0.16, (102, 124, 148, 255)),
             (0.62, (58, 74, 92, 255)), (1.0, (26, 36, 48, 255))],
        )
        img.paste(fin, (0, 0), fin_mask)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(box, radius=sc(6), outline=(9, 13, 19, 235), width=sc(2))
        # bright top edge, dark base
        d.line([sc(x + 3), sc(54), sc(x + 15), sc(54)],
               fill=(212, 234, 255, 150), width=sc(1))
        d.line([sc(x + 3), sc(99), sc(x + 15), sc(99)],
               fill=(0, 0, 0, 160), width=sc(1))
        d.line([sc(x + 2), sc(56), sc(x + 2), sc(96)],
               fill=(178, 206, 232, 75), width=sc(1))
        d.line([sc(x + 16), sc(56), sc(x + 16), sc(96)],
               fill=(0, 0, 0, 130), width=sc(1))

    # brass base rail under the fins
    rail_box = [sc(118), sc(98), sc(394), sc(106)]
    rail_mask = mask_rrect(size, rail_box, sc(4))
    rail = vgrad(size, [(0.0, brass_hi), (0.45, brass_mid), (1.0, brass_lo)])
    img.paste(rail, (0, 0), rail_mask)
    d = ImageDraw.Draw(img)
    d.line([sc(120), sc(99), sc(392), sc(99)], fill=(255, 238, 198, 170), width=sc(1))
    d.line([sc(120), sc(105), sc(392), sc(105)], fill=(52, 37, 20, 180), width=sc(1))
    for i in range(5):
        sx = 132 + i * 64
        d.ellipse([sc(sx - 2), sc(101), sc(sx + 2), sc(104)],
                  fill=(94, 70, 38, 255), outline=(244, 218, 164, 120), width=sc(1))

    # thin energised strip under the heat-sink rail
    d.rounded_rectangle([sc(124), sc(106), sc(388), sc(109)], radius=sc(1),
                        fill=(34, 118, 118, 150),
                        outline=(120, 240, 225, 80), width=sc(1))
    if not dim:
        add_glow(img, (sc(256), sc(108)), sc(64), (80, 235, 220), 26, sc(9))

    # --- vertical brass heat pipes --------------------------------------
    pipe_mask = Image.new("L", size, 0)
    for cx in (64, 448):
        # pipe shadow
        sh = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle(
            [sc(cx - 8), sc(114), sc(cx + 10), sc(290)], radius=sc(9),
            fill=(0, 0, 0, 120),
        )
        sh = sh.filter(ImageFilter.GaussianBlur(sc(5)))
        img.alpha_composite(sh)

        pipe_box = [sc(cx - 8), sc(112), sc(cx + 8), sc(290)]
        ImageDraw.Draw(pipe_mask).rounded_rectangle(pipe_box, radius=sc(8), fill=255)
        pipe = hgrad(
            size,
            [(0.0, (34, 20, 12, 255)), (0.09, (92, 54, 30, 255)),
             (0.18, (188, 118, 68, 255)), (0.24, (255, 214, 158, 255)),
             (0.32, (198, 128, 76, 255)), (0.58, (126, 76, 42, 255)),
             (0.84, (70, 42, 24, 255)), (1.0, (30, 19, 11, 255))],
        )
        img.paste(pipe, (0, 0), pipe_mask)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(pipe_box, radius=sc(8), outline=(42, 28, 15, 230), width=sc(2))
        d.line([sc(cx - 3), sc(116), sc(cx - 3), sc(286)],
               fill=(255, 232, 196, 85), width=sc(1))

        # pipe clamps (not at the ends, so the tube reads as continuous)
        for cy in (140, 262):
            cbox = [sc(cx - 11), sc(cy - 5), sc(cx + 11), sc(cy + 5)]
            cmask = mask_rrect(size, cbox, sc(2))
            ImageDraw.Draw(pipe_mask).rounded_rectangle(cbox, radius=sc(2), fill=255)
            collar = hgrad(
                size,
                [(0.0, (62, 43, 24, 255)), (0.14, (150, 110, 62, 255)),
                 (0.28, (226, 192, 134, 255)), (0.46, (158, 116, 64, 255)),
                 (0.80, (98, 69, 37, 255)), (1.0, (48, 33, 18, 255))],
            )
            img.paste(collar, (0, 0), cmask)
            d.rounded_rectangle(cbox, radius=sc(2), outline=(38, 26, 14, 240), width=sc(2))
            d.line([sc(cx - 8), sc(cy - 4), sc(cx + 8), sc(cy - 4)],
                   fill=(255, 232, 186, 80), width=sc(1))
            d.line([sc(cx - 8), sc(cy + 4), sc(cx + 8), sc(cy + 4)],
                   fill=(26, 18, 9, 190), width=sc(1))
            d.ellipse([sc(cx + 8), sc(cy - 2), sc(cx + 11), sc(cy + 1)],
                      fill=(34, 25, 13, 255), outline=(228, 198, 140, 140), width=sc(1))

        # dark end caps where the tube meets the frame
        for cy in (112, 288):
            cbox = [sc(cx - 8), sc(cy), sc(cx + 8), sc(cy + 4)]
            cmask = mask_rrect(size, cbox, sc(2))
            ImageDraw.Draw(pipe_mask).rounded_rectangle(cbox, radius=sc(2), fill=255)
            img.paste(vgrad(size, [(0.0, (70, 52, 30, 255)), (1.0, (26, 18, 10, 255))]),
                      (0, 0), cmask)
            d.rounded_rectangle(cbox, radius=sc(2), outline=(24, 16, 8, 230), width=sc(1))

        # tiny cyan tell-tale
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([sc(cx - 3), sc(196), sc(cx + 3), sc(206)],
                            radius=sc(2), fill=(28, 96, 96, 255),
                            outline=(120, 235, 220, 190), width=sc(1))

    # --- conduits linking pipes to the reactor --------------------------
    for x0, x1 in ((70, 170), (342, 442)):
        cbox = [sc(x0), sc(184), sc(x1), sc(200)]
        cmask = mask_rrect(size, cbox, sc(5))
        cond = vgrad(
            size,
            [(0.0, (96, 118, 142, 255)), (0.3, (62, 80, 100, 255)),
             (0.8, (33, 45, 59, 255)), (1.0, (18, 25, 34, 255))],
        )
        img.paste(cond, (0, 0), cmask)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(cbox, radius=sc(5), outline=(9, 13, 18, 230), width=sc(2))
        d.line([sc(x0 + 2), sc(186), sc(x1 - 2), sc(186)],
               fill=(178, 206, 230, 80), width=sc(1))
        # flange at the outer end
        d.rounded_rectangle([sc(x0 - 3), sc(180), sc(x0 + 5), sc(204)],
                            radius=sc(3), fill=(52, 66, 84, 255),
                            outline=(10, 14, 20, 230), width=sc(1))

    # --- reactor core ----------------------------------------------------
    cx, cy = sc(256), sc(192)
    plate_r = sc(90)

    # ambient bloom on the panel behind the reactor
    if not dim:
        amb = radial(
            size, (cx, cy), sc(190),
            [(0.0, (46, 168, 162, 46)), (0.55, (20, 90, 92, 20)), (1.0, (0, 0, 0, 0))],
        )
        img.alpha_composite(Image.composite(amb, Image.new("RGBA", size), panel_mask))

    # outer mounting plate
    plate_mask = mask_ellipse(size, [cx - plate_r, cy - plate_r, cx + plate_r, cy + plate_r])
    plate = vgrad(
        size,
        [(0.0, (76, 94, 114, 255)), (0.45, (46, 60, 76, 255)),
         (1.0, (18, 25, 34, 255))],
    )
    img.paste(plate, (0, 0), plate_mask)
    d = ImageDraw.Draw(img)
    d.ellipse([cx - plate_r, cy - plate_r, cx + plate_r, cy + plate_r],
              outline=(6, 9, 13, 255), width=sc(3))

    # machined outer ring (84 -> 72)
    ro, ri = sc(84), sc(72)
    outer = mask_ellipse(size, [cx - ro, cy - ro, cx + ro, cy + ro])
    inner = mask_ellipse(size, [cx - ri, cy - ri, cx + ri, cy + ri])
    ring_mask = ImageChops.subtract(outer, inner)
    ring = radial(
        size, (cx, cy), ro,
        [(0.0, (0, 0, 0, 0)), (0.80, (86, 105, 126, 255)),
         (0.88, (150, 174, 198, 255)), (1.0, (34, 45, 58, 255))],
    )
    img.paste(ring, (0, 0), ring_mask)

    # engraved ticks on the ring
    tick = Image.new("RGBA", size, (0, 0, 0, 0))
    td = ImageDraw.Draw(tick)
    for i in range(36):
        a = 2 * math.pi * i / 36
        r0, r1 = sc(74), sc(82) if i % 3 == 0 else sc(78)
        td.line(
            [cx + math.cos(a) * r0, cy + math.sin(a) * r0,
             cx + math.cos(a) * r1, cy + math.sin(a) * r1],
            fill=(0, 0, 0, 150) if i % 3 == 0 else (0, 0, 0, 90),
            width=sc(1) if i % 3 else sc(2),
        )
    tick = mul_alpha(tick, ring_mask)
    img.alpha_composite(tick)

    # brass trim on both edges of the ring
    d = ImageDraw.Draw(img)
    d.ellipse([cx - ro, cy - ro, cx + ro, cy + ro],
              outline=(206, 172, 110, 130), width=sc(2))
    d.ellipse([cx - ri, cy - ri, cx + ri, cy + ri],
              outline=(196, 162, 102, 100), width=sc(1))

    # dark well
    well_r = sc(70)
    well_mask = mask_ellipse(size, [cx - well_r, cy - well_r, cx + well_r, cy + well_r])
    well = radial(
        size, (cx, cy), well_r,
        [(0.0, (16, 36, 44, 255)), (0.62, (10, 21, 27, 255)), (1.0, (4, 8, 11, 255))],
    )
    img.paste(well, (0, 0), well_mask)

    # glass lens
    glass_r = sc(62)
    glass_mask = mask_ellipse(size, [cx - glass_r, cy - glass_r, cx + glass_r, cy + glass_r])
    if dim:
        glass = radial(
            size, (cx, cy), glass_r,
            [(0.0, (20, 74, 78, 255)), (0.55, (10, 34, 38, 255)), (1.0, (5, 13, 16, 255))],
        )
    else:
        glass = radial(
            size, (cx, cy), glass_r,
            [(0.0, (38, 182, 176, 255)), (0.28, (22, 122, 130, 255)),
             (0.60, (10, 54, 62, 255)), (1.0, (4, 11, 15, 255))],
        )
    img.paste(glass, (0, 0), glass_mask)

    # glass rim + inner occlusion
    d = ImageDraw.Draw(img)
    d.ellipse([cx - glass_r, cy - glass_r, cx + glass_r, cy + glass_r],
              outline=(8, 15, 18, 255), width=sc(4))
    rim_shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(rim_shadow).ellipse(
        [cx - glass_r + sc(4), cy - glass_r + sc(4),
         cx + glass_r - sc(4), cy + glass_r - sc(4)],
        outline=(0, 0, 0, 120), width=sc(5),
    )
    rim_shadow = rim_shadow.filter(ImageFilter.GaussianBlur(sc(3)))
    rim_shadow = mul_alpha(rim_shadow, glass_mask)
    img.alpha_composite(rim_shadow)
    d.ellipse([cx - glass_r + sc(2), cy - glass_r + sc(2),
               cx + glass_r - sc(2), cy + glass_r - sc(2)],
              outline=(190, 240, 236, 60) if not dim else (90, 120, 120, 35),
              width=sc(1))

    if not dim:
        # curved specular reflection on the glass dome
        spec = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(spec).arc(
            [cx - glass_r + sc(6), cy - glass_r + sc(6),
             cx + glass_r - sc(6), cy + glass_r - sc(6)],
            192, 278, fill=(235, 255, 255, 95), width=sc(3),
        )
        spec = spec.filter(ImageFilter.GaussianBlur(sc(3)))
        spec = mul_alpha(spec, glass_mask)
        img.alpha_composite(spec)

        # light pooling along the bottom of the lens
        pool = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(pool).arc(
            [cx - glass_r + sc(9), cy - glass_r + sc(9),
             cx + glass_r - sc(9), cy + glass_r - sc(9)],
            18, 162, fill=(120, 255, 240, 58), width=sc(7),
        )
        pool = pool.filter(ImageFilter.GaussianBlur(sc(5)))
        img.alpha_composite(mul_alpha(pool, glass_mask))

        # faint concentric energy rings
        for rr, aa in ((sc(50), 34), (sc(56), 22)):
            ring_l = Image.new("RGBA", size, (0, 0, 0, 0))
            ImageDraw.Draw(ring_l).ellipse(
                [cx - rr, cy - rr, cx + rr, cy + rr],
                outline=(150, 255, 242, aa), width=sc(1),
            )
            img.alpha_composite(mul_alpha(ring_l, glass_mask))

        add_glow(img, (cx, cy), sc(66), (70, 235, 220), int(70 + 50 * pulse), sc(10))

    # hex crystal
    hex_r = sc(42)
    hp = hex_points(cx, cy, hex_r)
    hex_mask = mask_polygon(size, hp)
    if dim:
        crystal = vgrad(size, [(0.0, (52, 104, 108, 255)), (1.0, (14, 44, 50, 255))])
    else:
        crystal = vgrad(
            size,
            [(0.0, (158, 244, 236, 255)), (0.32, (86, 214, 210, 255)),
             (0.72, (22, 128, 138, 255)), (1.0, (8, 66, 76, 255))],
        )
    img.paste(crystal, (0, 0), hex_mask)

    # faceted shading: lit upper facets, shaded lower facets
    facet_colours = [
        (12, 66, 78, 205),     # bottom-right
        (18, 84, 94, 200),     # bottom-left
        (96, 214, 208, 185),   # left
        (240, 255, 252, 190),  # top-left
        (188, 252, 246, 185),  # top-right
        (126, 236, 230, 185),  # right
    ]
    facet = Image.new("RGBA", size, (0, 0, 0, 0))
    fd = ImageDraw.Draw(facet)
    for i in range(6):
        p0, p1 = hp[i], hp[(i + 1) % 6]
        fd.polygon([(cx, cy), p0, p1], fill=facet_colours[i])
    for i, p in enumerate(hp):
        fd.line([cx, cy, p[0], p[1]], fill=(4, 34, 40, 110), width=sc(1))
    facet = mul_alpha(facet, hex_mask)
    img.alpha_composite(facet)
    # bright rim on the lit upper edges
    if not dim:
        for i in (2, 3, 4):
            p0, p1 = hp[i], hp[(i + 1) % 6]
            fd2 = ImageDraw.Draw(img)
            fd2.line([p0[0], p0[1], p1[0], p1[1]],
                     fill=(255, 255, 255, 170), width=sc(2))

    # refraction halo around the crystal
    if not dim:
        halo = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(halo).ellipse(
            [cx - hex_r - sc(5), cy - hex_r - sc(5),
             cx + hex_r + sc(5), cy + hex_r + sc(5)],
            outline=(140, 250, 238, 55), width=sc(2),
        )
        halo = halo.filter(ImageFilter.GaussianBlur(sc(2)))
        img.alpha_composite(mul_alpha(halo, glass_mask))

    d = ImageDraw.Draw(img)
    d.polygon(hp, outline=(232, 255, 252, 230) if not dim else (96, 128, 128, 150))

    inner_hex = hex_points(cx, cy, sc(18))
    inner_mask = mask_polygon(size, inner_hex)
    if dim:
        inner = vgrad(size, [(0.0, (52, 96, 100, 255)), (1.0, (24, 58, 62, 255))])
    else:
        inner = vgrad(
            size,
            [(0.0, (255, 255, 255, 255)), (0.42, (158, 255, 244, 255)),
             (1.0, (48, 196, 194, 255))],
        )
    img.paste(inner, (0, 0), inner_mask)
    d.polygon(inner_hex, outline=(248, 255, 253, 220) if not dim else (70, 104, 104, 140))
    ring_hex = hex_points(cx, cy, sc(29))
    d.polygon(ring_hex, outline=(210, 255, 248, 55) if not dim else (60, 96, 96, 60))
    # specular streak on the crystal
    if not dim:
        glint = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(glint).polygon(
            [(cx - sc(20), cy - sc(26)), (cx - sc(9), cy - sc(34)),
             (cx - sc(2), cy - sc(12)), (cx - sc(13), cy - sc(4))],
            fill=(255, 255, 255, 95),
        )
        glint = glint.filter(ImageFilter.GaussianBlur(sc(2)))
        img.alpha_composite(mul_alpha(glint, hex_mask))
    d.ellipse([cx - sc(7), cy - sc(7), cx + sc(7), cy + sc(7)],
              fill=(255, 255, 253, int(210 + 45 * pulse)) if not dim else (40, 78, 80, 255))

    if not dim:
        add_glow(img, (cx, cy), sc(17), (185, 255, 247), int(45 + 40 * pulse), sc(5))

    # orbiting satellites
    for i in range(8):
        a = 2 * math.pi * (i / 8.0 + phase * 0.3)
        px = cx + math.cos(a) * sc(78)
        py = cy + math.sin(a) * sc(78)
        if not dim:
            add_glow(img, (int(px), int(py)), sc(9), (120, 250, 235), 90, sc(4))
        d = ImageDraw.Draw(img)
        d.ellipse([px - sc(3), py - sc(3), px + sc(3), py + sc(3)],
                  fill=(230, 255, 250, 255) if not dim else (46, 70, 72, 255))

    # --- mechanical transmission: flywheel, pistons, gauges -------------
    d = ImageDraw.Draw(img)
    steel_dark = (22, 31, 42, 255)
    steel_mid = (64, 81, 100, 255)
    steel_hi = (166, 192, 216, 255)
    bronze_mid = (176, 132, 70, 255)
    bronze_hi = (255, 226, 166, 255)

    # moving coolant slugs in the vertical brass pipes
    if working and not dim:
        for px in (64, 448):
            for k in range(3):
                t = (phase + k / 3.0) % 1.0
                py = 120 + t * 160
                add_glow(img, (sc(px), sc(py)), sc(8), (90, 240, 225), 95, sc(5))
                d.rounded_rectangle([sc(px - 4), sc(py - 5), sc(px + 4), sc(py + 5)],
                                    radius=sc(2), fill=(214, 255, 248, 235))

    # small drive gears flanking the flywheel
    for gx, gy, gr, teeth, spin in (
        (cx - sc(96), cy + sc(64), sc(24), 12, -angle),
        (cx + sc(96), cy + sc(64), sc(24), 12, -angle),
    ):
        pts = gear_polygon(gx, gy, gr * 0.80, gr, teeth, spin)
        gmask = mask_polygon(size, [(int(round(x)), int(round(y))) for x, y in pts])
        img.paste(vgrad(size, [(0.0, steel_hi), (0.35, steel_mid), (1.0, steel_dark)]),
                  (0, 0), gmask)
        d = ImageDraw.Draw(img)
        d.polygon([(int(round(x)), int(round(y))) for x, y in pts],
                  outline=(8, 12, 18, 240))
        hub = sc(8)
        d.ellipse([gx - hub, gy - hub, gx + hub, gy + hub],
                  fill=(36, 48, 64, 255), outline=bronze_hi, width=sc(1))

    # flywheel: toothed outer ring
    fly_r_root = sc(68)
    fly_r_tip = sc(78)
    fly_pts = gear_polygon(cx, cy, fly_r_root, fly_r_tip, 24, angle)
    fly_mask = mask_polygon(size, [(int(round(x)), int(round(y))) for x, y in fly_pts])
    fly_inner = mask_ellipse(size, [cx - sc(58), cy - sc(58), cx + sc(58), cy + sc(58)])
    fly_ring = ImageChops.subtract(fly_mask, fly_inner)
    ring_fill = radial(
        size, (cx, cy), fly_r_tip,
        [(0.0, (0, 0, 0, 0)), (0.80, (54, 70, 88, 255)),
         (0.90, (154, 180, 206, 255)), (1.0, (18, 25, 34, 255))],
    )
    img.paste(ring_fill, (0, 0), fly_ring)
    d = ImageDraw.Draw(img)
    d.polygon([(int(round(x)), int(round(y))) for x, y in fly_pts],
              outline=(6, 9, 13, 255), width=sc(2))

    # six tapered spokes
    for i in range(6):
        a = angle + 2 * math.pi * i / 6
        nx, ny = math.cos(a), math.sin(a)
        px, py = -ny, nx
        w0, w1 = sc(7), sc(4)
        r0, r1 = sc(26), sc(64)
        pts = [
            (cx + nx * r0 + px * w0, cy + ny * r0 + py * w0),
            (cx + nx * r1 + px * w1, cy + ny * r1 + py * w1),
            (cx + nx * r1 - px * w1, cy + ny * r1 - py * w1),
            (cx + nx * r0 - px * w0, cy + ny * r0 - py * w0),
        ]
        smask = mask_polygon(size, [(int(round(x)), int(round(y))) for x, y in pts])
        img.paste(vgrad(size, [(0.0, (144, 168, 194, 255)), (0.45, (78, 96, 118, 255)),
                               (1.0, (24, 34, 46, 255))]), (0, 0), smask)
        d = ImageDraw.Draw(img)
        d.polygon([(int(round(x)), int(round(y))) for x, y in pts],
                  outline=(7, 10, 15, 220))

    # flywheel hub
    hub_r = sc(30)
    hub_mask = mask_ellipse(size, [cx - hub_r, cy - hub_r, cx + hub_r, cy + hub_r])
    img.paste(vgrad(size, [(0.0, (96, 116, 138, 255)), (0.45, (48, 62, 80, 255)),
                           (1.0, (18, 25, 34, 255))]), (0, 0), hub_mask)
    d = ImageDraw.Draw(img)
    d.ellipse([cx - hub_r, cy - hub_r, cx + hub_r, cy + hub_r],
              outline=(6, 9, 13, 255), width=sc(2))
    d.ellipse([cx - hub_r + sc(4), cy - hub_r + sc(4),
               cx + hub_r - sc(4), cy + hub_r - sc(4)],
              outline=(206, 172, 110, 130), width=sc(1))
    for i in range(6):
        a = angle + 2 * math.pi * i / 6
        bx = cx + math.cos(a) * sc(21)
        by = cy + math.sin(a) * sc(21)
        d.ellipse([bx - sc(3), by - sc(3), bx + sc(3), by + sc(3)],
                  fill=(30, 40, 54, 255), outline=(198, 216, 234, 110), width=sc(1))

    # small glowing anti-entropy core in the middle of the hub
    core_r = sc(12)
    core_mask = mask_ellipse(size, [cx - core_r, cy - core_r, cx + core_r, cy + core_r])
    img.paste(radial(size, (cx, cy), core_r,
                     [(0.0, (235, 255, 252, 255)), (0.45, (110, 236, 228, 255)),
                      (1.0, (12, 92, 102, 255))]), (0, 0), core_mask)
    if not dim:
        add_glow(img, (cx, cy), sc(20), (100, 245, 232), int(55 + 35 * pulse), sc(6))

    # crank pin and the two horizontal pistons
    pin_x = cx + math.cos(angle) * sc(43)
    pin_y = cy + math.sin(angle) * sc(43)
    left_cross = sc(158) + sc(14) * (0.5 + 0.5 * math.cos(angle))
    right_cross = sc(354) - sc(14) * (0.5 - 0.5 * math.cos(angle))

    for hx0, hx1 in ((sc(74), sc(154)), (sc(358), sc(438))):
        hbox = [hx0, cy - sc(25), hx1, cy + sc(25)]
        hmask = mask_rrect(size, hbox, sc(7))
        img.paste(vgrad(size, [(0.0, (150, 174, 198, 255)), (0.28, (88, 106, 128, 255)),
                               (0.75, (42, 56, 72, 255)), (1.0, (18, 25, 34, 255))]),
                  (0, 0), hmask)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(hbox, radius=sc(7), outline=(6, 9, 13, 255), width=sc(2))
        for ry in (cy - sc(14), cy, cy + sc(14)):
            d.line([hx0 + sc(4), ry, hx1 - sc(4), ry],
                   fill=(0, 0, 0, 80), width=sc(1))
            d.line([hx0 + sc(4), ry + sc(1), hx1 - sc(4), ry + sc(1)],
                   fill=(190, 214, 236, 35), width=sc(1))
        for bx in (hx0 + sc(7), hx1 - sc(7)):
            for by in (cy - sc(16), cy + sc(16)):
                d.ellipse([bx - sc(2), by - sc(2), bx + sc(2), by + sc(2)],
                          fill=(32, 44, 58, 255), outline=(190, 212, 232, 80), width=sc(1))

    # piston rods and crossheads
    d = ImageDraw.Draw(img)
    for cross_x, inner_x in ((left_cross, sc(154)), (right_cross, sc(358))):
        d.line([inner_x, cy, cross_x, cy], fill=(18, 26, 36, 255), width=sc(9))
        d.line([inner_x, cy - sc(1), cross_x, cy - sc(1)],
               fill=(190, 214, 236, 120), width=sc(2))
        cbox = [cross_x - sc(8), cy - sc(17), cross_x + sc(8), cy + sc(17)]
        cmask = mask_rrect(size, cbox, sc(3))
        img.paste(vgrad(size, [(0.0, (164, 188, 212, 255)), (1.0, (54, 70, 88, 255))]),
                  (0, 0), cmask)
        d.rounded_rectangle(cbox, radius=sc(3), outline=(6, 9, 13, 255), width=sc(2))

    # connecting rods are drawn last so they sit above the flywheel
    for cross_x in (left_cross, right_cross):
        d.line([cross_x, cy, pin_x, pin_y], fill=(16, 24, 34, 255), width=sc(13))
        d.line([cross_x, cy, pin_x, pin_y], fill=(92, 112, 136, 255), width=sc(8))
        d.line([cross_x, cy - sc(1), pin_x, pin_y - sc(1)],
               fill=(206, 228, 248, 90), width=sc(2))
        for bx, by in ((cross_x, cy), (pin_x, pin_y)):
            d.ellipse([bx - sc(7), by - sc(7), bx + sc(7), by + sc(7)],
                      fill=bronze_mid, outline=(34, 24, 12, 255), width=sc(2))
            d.ellipse([bx - sc(3), by - sc(3), bx + sc(3), by + sc(3)],
                      fill=(66, 46, 24, 255), outline=(255, 232, 188, 90), width=sc(1))

    # pressure gauges
    for gx, gy in ((sc(112), sc(266)), (sc(400), sc(266))):
        gauge_r = sc(18)
        d = ImageDraw.Draw(img)
        d.ellipse([gx - gauge_r - sc(3), gy - gauge_r - sc(3),
                   gx + gauge_r + sc(3), gy + gauge_r + sc(3)],
                  fill=(0, 0, 0, 80))
        d.ellipse([gx - gauge_r, gy - gauge_r, gx + gauge_r, gy + gauge_r],
                  fill=(44, 56, 72, 255), outline=(214, 178, 112, 200), width=sc(2))
        dial_r = sc(14)
        d.ellipse([gx - dial_r, gy - dial_r, gx + dial_r, gy + dial_r],
                  fill=(224, 218, 196, 255), outline=(8, 12, 18, 230), width=sc(1))
        for i in range(9):
            a = math.radians(210 + i * 30)
            d.line([gx + math.cos(a) * sc(14), gy + math.sin(a) * sc(14),
                    gx + math.cos(a) * sc(10), gy + math.sin(a) * sc(10)],
                   fill=(42, 36, 28, 220), width=sc(1))
        needle = math.radians(210 + 120 * (0.5 + 0.5 * math.sin(angle * 2)))
        d.line([gx, gy, gx + math.cos(needle) * sc(11), gy + math.sin(needle) * sc(11)],
               fill=(178, 34, 28, 255), width=sc(2))
        d.ellipse([gx - sc(3), gy - sc(3), gx + sc(3), gy + sc(3)],
                  fill=(38, 32, 24, 255), outline=(230, 206, 154, 160), width=sc(1))

    # exhaust steam above the heat-sink when working
    if working and not dim:
        for i in range(4):
            t = (phase + i * 0.25) % 1.0
            px = 256 + 24 * math.sin(2 * math.pi * (phase + i * 0.37))
            py = 116 - t * 62
            alpha = int(48 * (1.0 - t))
            if alpha > 0:
                puff = radial(
                    size, (sc(px), sc(py)), sc(15 + 9 * t),
                    [(0.0, (232, 248, 255, alpha)),
                     (0.55, (198, 226, 242, alpha // 2)),
                     (1.0, (0, 0, 0, 0))],
                )
                img.alpha_composite(puff)

    # --- bottom exhaust grille ------------------------------------------
    frame_box = [sc(86), sc(296), sc(426), sc(338)]
    frame_mask = mask_rrect(size, frame_box, sc(8))
    frame = vgrad(
        size,
        [(0.0, (78, 96, 118, 255)), (0.3, (48, 62, 79, 255)),
         (1.0, (18, 25, 34, 255))],
    )
    img.paste(frame, (0, 0), frame_mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(frame_box, radius=sc(8), outline=(6, 9, 13, 255), width=sc(2))
    fh = stroke(size, [frame_box[0] + sc(2), frame_box[1] + sc(2),
                       frame_box[2] - sc(2), frame_box[3] - sc(2)], sc(6),
                (176, 202, 226, 90), sc(1))
    fh = mul_alpha(fh, fade(size, 255, 20))
    img.alpha_composite(fh)

    # recessed cavity
    cav_box = [sc(92), sc(302), sc(420), sc(332)]
    cav_mask = mask_rrect(size, cav_box, sc(4))
    cav = vgrad(size, [(0.0, (2, 4, 7, 255)), (1.0, (9, 14, 20, 255))])
    img.paste(cav, (0, 0), cav_mask)
    cav_shadow = stroke(size, [cav_box[0] + sc(1), cav_box[1] + sc(1),
                               cav_box[2] - sc(1), cav_box[3] - sc(1)], sc(3),
                        (0, 0, 0, 200), sc(4))
    cav_shadow = cav_shadow.filter(ImageFilter.GaussianBlur(sc(2)))
    cav_shadow = mul_alpha(cav_shadow, ImageChops.multiply(fade(size, 255, 0), cav_mask))
    img.alpha_composite(cav_shadow)

    # fine vertical louvers
    for i in range(30):
        x = 96 + i * 11
        box = [sc(x), sc(303), sc(x + 5), sc(331)]
        slat_mask = mask_rrect(size, box, sc(2))
        slat = hgrad(
            size,
            [(0.0, (104, 124, 146, 255)), (0.28, (66, 83, 102, 255)),
             (0.7, (34, 46, 60, 255)), (1.0, (18, 25, 34, 255))],
        )
        img.paste(slat, (0, 0), slat_mask)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(box, radius=sc(2), outline=(7, 11, 16, 220), width=sc(1))
        d.line([sc(x + 1), sc(304), sc(x + 1), sc(329)],
               fill=(176, 202, 226, 45), width=sc(1))
        d.line([sc(x + 4), sc(304), sc(x + 4), sc(329)],
               fill=(0, 0, 0, 120), width=sc(1))

    # cross-braces
    for y in (311, 321):
        d.line([sc(94), sc(y), sc(418), sc(y)], fill=(8, 12, 17, 120), width=sc(1))
        d.line([sc(94), sc(y + 1), sc(418), sc(y + 1)], fill=(150, 176, 200, 26), width=sc(1))

    # frame screws
    for sx in (95, 417):
        for sy in (303, 331):
            d.ellipse([sc(sx - 2), sc(sy - 2), sc(sx + 2), sc(sy + 2)],
                      fill=(30, 40, 52, 255), outline=(150, 176, 200, 90), width=sc(1))

    # --- ports -----------------------------------------------------------
    def draw_port(box, top, bottom, edge, direction, glow_colour):
        x0, y0, x1, y1 = box
        housing = [sc(x0 - 4), sc(y0 - 4), sc(x1 + 4), sc(y1 + 4)]
        h_mask = mask_rrect(size, housing, sc(12))
        h_fill = vgrad(size, [(0.0, (62, 79, 98, 255)), (0.5, (34, 46, 61, 255)),
                              (1.0, (15, 22, 30, 255))])
        img.paste(h_fill, (0, 0), h_mask)
        hd = ImageDraw.Draw(img)
        hd.rounded_rectangle(housing, radius=sc(12), outline=(6, 9, 13, 255), width=sc(3))
        hb = stroke(size, [housing[0] + sc(2), housing[1] + sc(2),
                           housing[2] - sc(2), housing[3] - sc(2)], sc(10),
                    (184, 208, 230, 120), sc(2))
        hb = mul_alpha(hb, fade(size, 255, 20))
        img.alpha_composite(hb)

        slot_box = [sc(x0), sc(y0), sc(x1), sc(y1)]
        s_mask = mask_rrect(size, slot_box, sc(8))
        s_fill = vgrad(size, [(0.0, top), (0.45, bottom), (1.0, tuple(int(c * 0.6) for c in bottom[:3]) + (255,))])
        img.paste(s_fill, (0, 0), s_mask)
        sd = ImageDraw.Draw(img)
        sd.rounded_rectangle(slot_box, radius=sc(8), outline=edge, width=sc(2))
        # inner shadow at the top of the slot
        iss = stroke(size, [slot_box[0] + sc(1), slot_box[1] + sc(1),
                            slot_box[2] - sc(1), slot_box[3] - sc(1)], sc(7),
                     (0, 0, 0, 170), sc(3))
        iss = mul_alpha(iss, fade(size, 255, 0))
        img.alpha_composite(iss)

        # recessed circular bezel around the flow arrow
        gcx, gcy = sc((x0 + x1) / 2), sc((y0 + y1) / 2)
        d = ImageDraw.Draw(img)
        d.ellipse([gcx - sc(17), gcy - sc(17), gcx + sc(17), gcy + sc(17)],
                  outline=(0, 0, 0, 70), width=sc(2))
        d.arc([gcx - sc(16), gcy - sc(16), gcx + sc(16), gcy + sc(16)],
              190, 350, fill=(255, 255, 255, 45), width=sc(1))
        d.line([sc(x0 + 4), sc(y1 - 2), sc(x1 - 4), sc(y1 - 2)],
               fill=(255, 255, 255, 55), width=sc(1))

        if not dim:
            gx = (x0 + x1) / 2
            gy = (y0 + y1) / 2
            add_glow(img, (sc(gx), sc(gy)), sc(24), glow_colour, 70, sc(8))

        # flow arrow
        ax = sc((x0 + x1) / 2)
        ay = sc((y0 + y1) / 2)
        hw, hh = sc(9), sc(11)
        if direction > 0:
            pts = [(ax - hw, ay - hh), (ax + hw, ay), (ax - hw, ay + hh)]
        else:
            pts = [(ax + hw, ay - hh), (ax - hw, ay), (ax + hw, ay + hh)]
        ImageDraw.Draw(img).polygon(pts, fill=(240, 252, 255, 245))

    # Port graphics are centred on the connector cell centres. For a 4-wide building the
    # origin cell is the second column from the left, so the cells are at frame x = 64 and
    # x = 448. The liquid row centre is y = 320, the gas row centre is y = 64, and the
    # power socket is the centre of the bottom row (x = 192, y = 320).
    draw_port((40, 296, 88, 344), (78, 168, 232, 255), (28, 84, 140, 255),
              (150, 218, 255, 230), +1, (80, 170, 240))
    draw_port((424, 296, 472, 344), (78, 168, 232, 255), (28, 84, 140, 255),
              (150, 218, 255, 230), +1, (80, 170, 240))
    draw_port((40, 40, 88, 88), (78, 220, 196, 255), (24, 116, 106, 255),
              (150, 255, 236, 230), +1, (80, 235, 210))
    draw_port((424, 40, 472, 88), (78, 220, 196, 255), (24, 116, 106, 255),
              (150, 255, 236, 230), +1, (80, 235, 210))

    # power port (bottom-row centre)
    px0, py0, px1, py1 = 164, 292, 220, 348
    ph = [sc(px0 - 4), sc(py0 - 4), sc(px1 + 4), sc(py1 + 4)]
    ph_mask = mask_rrect(size, ph, sc(10))
    ph_fill = vgrad(size, [(0.0, (70, 58, 30, 255)), (0.5, (44, 35, 18, 255)),
                           (1.0, (18, 14, 8, 255))])
    img.paste(ph_fill, (0, 0), ph_mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(ph, radius=sc(10), outline=(6, 9, 13, 255), width=sc(3))
    ps = [sc(px0), sc(py0), sc(px1), sc(py1)]
    ps_mask = mask_rrect(size, ps, sc(6))
    ps_fill = vgrad(size, [(0.0, (255, 214, 108, 255)), (0.55, (176, 132, 40, 255)),
                           (1.0, (104, 76, 22, 255))])
    img.paste(ps_fill, (0, 0), ps_mask)
    d.rounded_rectangle(ps, radius=sc(6), outline=(255, 238, 170, 235), width=sc(2))
    if not dim:
        add_glow(img, (sc(192), sc(320)), sc(22), (255, 200, 80), 80, sc(8))
    bolt = [
        (sc(200), sc(298)), (sc(186), sc(314)), (sc(194), sc(314)),
        (sc(189), sc(328)), (sc(205), sc(309)), (sc(197), sc(309)),
    ]
    d.polygon(bolt, fill=(255, 244, 188, 255))

    # --- corner bolts ----------------------------------------------------
    for bx, by in ((46, 46), (466, 46), (46, 338), (466, 338)):
        d = ImageDraw.Draw(img)
        d.ellipse([sc(bx - 10), sc(by - 10), sc(bx + 10), sc(by + 10)],
                  fill=(0, 0, 0, 90))
        d.ellipse([sc(bx - 8), sc(by - 8), sc(bx + 8), sc(by + 8)],
                  fill=(74, 92, 112, 255), outline=(8, 12, 17, 255), width=sc(2))
        d.ellipse([sc(bx - 6), sc(by - 6), sc(bx + 6), sc(by + 6)],
                  fill=(48, 61, 77, 255), outline=(150, 176, 200, 90), width=sc(1))
        d.line([sc(bx - 4), sc(by), sc(bx + 4), sc(by)], fill=(12, 17, 23, 255), width=sc(2))
        d.line([sc(bx), sc(by - 4), sc(bx), sc(by + 4)], fill=(12, 17, 23, 255), width=sc(2))
        d.ellipse([sc(bx - 4), sc(by - 5), sc(bx - 1), sc(by - 2)],
                  fill=(190, 212, 232, 140))

    # --- front-panel screws ----------------------------------------------
    for bx, by in ((56, 56), (456, 56), (56, 328), (456, 328)):
        d = ImageDraw.Draw(img)
        d.ellipse([sc(bx - 6), sc(by - 6), sc(bx + 6), sc(by + 6)],
                  fill=(0, 0, 0, 80))
        d.ellipse([sc(bx - 5), sc(by - 5), sc(bx + 5), sc(by + 5)],
                  fill=(58, 72, 90, 255), outline=(6, 9, 13, 230), width=sc(1))
        d.ellipse([sc(bx - 4), sc(by - 4), sc(bx + 4), sc(by + 4)],
                  fill=(40, 51, 65, 255), outline=(156, 182, 206, 70), width=sc(1))
        d.line([sc(bx - 3), sc(by), sc(bx + 3), sc(by)],
               fill=(10, 14, 19, 255), width=sc(1))
        d.line([sc(bx), sc(by - 3), sc(bx), sc(by + 3)],
               fill=(10, 14, 19, 255), width=sc(1))
        d.ellipse([sc(bx - 3), sc(by - 4), sc(bx - 1), sc(by - 2)],
                  fill=(188, 210, 232, 120))

    # --- small maker's plate on the bottom rail --------------------------
    plate = [sc(290), sc(345), sc(374), sc(360)]
    plate_mask = mask_rrect(size, plate, sc(2))
    plate_fill = vgrad(size, [(0.0, (196, 162, 100, 255)), (0.45, (142, 108, 58, 255)),
                              (1.0, (86, 62, 32, 255))])
    img.paste(plate_fill, (0, 0), plate_mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(plate, radius=sc(2), outline=(44, 31, 16, 230), width=sc(1))
    d.line([sc(292), sc(346), sc(372), sc(346)],
           fill=(255, 234, 188, 120), width=sc(1))
    for i, ly in enumerate((350, 354, 358)):
        d.line([sc(306), sc(ly), sc(358) - sc(i * 10), sc(ly)],
               fill=(58, 41, 20, 130), width=sc(1))
    for sx in (296, 368):
        d.ellipse([sc(sx - 2), sc(351), sc(sx + 2), sc(355)],
                  fill=(72, 52, 26, 255), outline=(238, 210, 156, 100), width=sc(1))

    # --- frame rivets ----------------------------------------------------
    for rx, ry in ((108, 29), (256, 29), (404, 29),
                   (108, 355), (256, 355), (404, 355),
                   (28, 192), (484, 192)):
        d = ImageDraw.Draw(img)
        d.ellipse([sc(rx - 4), sc(ry - 4), sc(rx + 4), sc(ry + 4)],
                  fill=(0, 0, 0, 70))
        d.ellipse([sc(rx - 3), sc(ry - 3), sc(rx + 3), sc(ry + 3)],
                  fill=(64, 80, 99, 255), outline=(6, 9, 13, 255), width=sc(1))
        d.ellipse([sc(rx - 2), sc(ry - 2), sc(rx + 2), sc(ry + 2)],
                  fill=(44, 56, 71, 255), outline=(160, 186, 210, 70), width=sc(1))
        d.ellipse([sc(rx - 2), sc(ry - 2), sc(rx), sc(ry)],
                  fill=(186, 208, 230, 90))

    # --- key light / cool rim light --------------------------------------
    warm = radial(
        size, (sc(90), sc(26)), sc(440),
        [(0.0, (255, 216, 164, 22)), (0.55, (255, 216, 164, 7)), (1.0, (0, 0, 0, 0))],
    )
    img.alpha_composite(warm)
    cool = radial(
        size, (sc(478), sc(376)), sc(430),
        [(0.0, (36, 86, 128, 20)), (0.6, (36, 86, 128, 5)), (1.0, (0, 0, 0, 0))],
    )
    img.alpha_composite(cool)

    # --- surface texture -------------------------------------------------
    # Everything solid gets a unified material pass, except the reactor lens
    # (glass should stay clean) and the glowing core.
    opaque = img.split()[3].point(lambda v: 255 if v > 180 else 0)
    core_excl = mask_ellipse(
        size, [cx - sc(92), cy - sc(92), cx + sc(92), cy + sc(92)]
    )
    glass_keep = mask_ellipse(
        size, [cx - sc(65), cy - sc(65), cx + sc(65), cy + sc(65)]
    )
    metal_mask = ImageChops.subtract(ImageChops.subtract(opaque, core_excl), pipe_mask)
    img = apply_texture(
        img, metal_mask, seed=11,
        brushed=0.130, grain=0.045, mottle=0.090, scratches=190,
    )
    # vertical brushing on the cylindrical brass pipes
    img = apply_texture(
        img, pipe_mask, seed=53,
        brushed=0.055, grain=0.022, mottle=0.030, scratches=22, vertical=True,
    )
    # finer, softer grain on the glass panel
    panel_tex = ImageChops.subtract(panel_mask, core_excl)
    img = apply_texture(
        img, panel_tex, seed=23,
        brushed=0.022, grain=0.022, mottle=0.060, scratches=70,
    )
    # faint handling marks on the reactor housing (glass stays clean)
    img = apply_texture(
        img, ImageChops.subtract(core_excl, glass_keep), seed=37,
        brushed=0.045, grain=0.014, mottle=0.030, scratches=0,
    )

    # --- grime and edge darkening ---------------------------------------
    grime = vgrad(
        size,
        [(0.0, (0, 0, 0, 0)), (0.62, (0, 0, 0, 0)), (1.0, (0, 0, 0, 70))],
    )
    img.alpha_composite(Image.composite(grime, Image.new("RGBA", size), panel_mask))
    # dark contact shadow just inside the panel rim
    contact = stroke(size, [sc(42), sc(42), sc(470), sc(342)], sc(19),
                     (0, 0, 0, 150), sc(6))
    contact = contact.filter(ImageFilter.GaussianBlur(sc(4)))
    contact = mul_alpha(contact, panel_mask)
    img.alpha_composite(contact)

    # --- off state: desaturate and darken -------------------------------
    if dim:
        arr = np.asarray(img).astype(np.float32)
        lum = (arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114)[..., None]
        arr[..., :3] = arr[..., :3] * 0.38 + lum * 0.30
        arr[..., :3] *= 0.82
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

    # --- global vignette -------------------------------------------------
    v = radial(
        size, (sc(256), sc(192)), sc(330),
        [(0.0, (0, 0, 0, 0)), (0.68, (0, 0, 0, 0)), (1.0, (0, 0, 0, 55))],
    )
    img.alpha_composite(v)

    out = img.resize((FRAME_W, FRAME_H), Image.LANCZOS)
    return final_grain(out, seed=index + 5, strength=0.024)


# ---------------------------------------------------------------------------
# build menu icon
# ---------------------------------------------------------------------------

def draw_icon() -> Image.Image:
    W = UI_SIZE * S
    size = (W, W)
    img = Image.new("RGBA", size, (0, 0, 0, 0))

    # shadow
    sh = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        [sc(18), sc(20), sc(240), sc(244)], radius=sc(40), fill=(0, 0, 0, 130)
    )
    sh = sh.filter(ImageFilter.GaussianBlur(sc(9)))
    img.alpha_composite(sh)

    # tile
    tile_box = [sc(12), sc(12), sc(244), sc(244)]
    tile_mask = mask_rrect(size, tile_box, sc(40))
    tile = vgrad(
        size,
        [(0.0, (58, 76, 96, 255)), (0.16, (44, 60, 77, 255)),
         (0.6, (30, 42, 56, 255)), (1.0, (14, 21, 29, 255))],
    )
    img.paste(tile, (0, 0), tile_mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(tile_box, radius=sc(40), outline=(5, 8, 12, 255), width=sc(3))
    tb = stroke(size, [sc(15), sc(15), sc(241), sc(241)], sc(37),
                (190, 214, 236, 140), sc(2))
    tb = mul_alpha(tb, fade(size, 255, 20))
    img.alpha_composite(tb)

    # inner panel
    panel_box = [sc(30), sc(30), sc(226), sc(226)]
    panel_mask = mask_rrect(size, panel_box, sc(30))
    panel = vgrad(size, [(0.0, (14, 22, 31, 255)), (0.5, (19, 29, 40, 255)),
                         (1.0, (8, 13, 19, 255))])
    img.paste(panel, (0, 0), panel_mask)
    d.rounded_rectangle(panel_box, radius=sc(30), outline=(2, 5, 8, 200), width=sc(2))
    inlay = stroke(size, [sc(36), sc(36), sc(220), sc(220)], sc(25),
                   (218, 182, 116, 90), sc(1))
    inlay = mul_alpha(inlay, fade(size, 190, 90))
    img.alpha_composite(inlay)

    # soft diagonal sheen on the tile
    sheen = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(sheen).polygon(
        [(sc(20), sc(120)), (sc(140), sc(16)), (sc(206), sc(16)), (sc(20), sc(190))],
        fill=(180, 228, 255, 14),
    )
    sheen = sheen.filter(ImageFilter.GaussianBlur(sc(14)))
    img.alpha_composite(Image.composite(sheen, Image.new("RGBA", size), tile_mask))

    # key light
    warm = radial(
        size, (sc(36), sc(24)), sc(240),
        [(0.0, (255, 216, 164, 26)), (0.6, (255, 216, 164, 7)), (1.0, (0, 0, 0, 0))],
    )
    img.alpha_composite(warm)

    # core
    cx, cy = sc(128), sc(121)
    plate_r = sc(71)
    plate_mask = mask_ellipse(size, [cx - plate_r, cy - plate_r, cx + plate_r, cy + plate_r])
    plate = vgrad(size, [(0.0, (84, 102, 122, 255)), (0.5, (46, 60, 77, 255)),
                         (1.0, (17, 24, 33, 255))])
    img.paste(plate, (0, 0), plate_mask)
    d = ImageDraw.Draw(img)
    d.ellipse([cx - plate_r, cy - plate_r, cx + plate_r, cy + plate_r],
              outline=(5, 8, 12, 255), width=sc(2))

    ro, ri = sc(67), sc(56)
    outer = mask_ellipse(size, [cx - ro, cy - ro, cx + ro, cy + ro])
    inner = mask_ellipse(size, [cx - ri, cy - ri, cx + ri, cy + ri])
    ring_mask = ImageChops.subtract(outer, inner)
    ring = radial(size, (cx, cy), ro,
                  [(0.0, (0, 0, 0, 0)), (0.82, (96, 116, 138, 255)),
                   (0.90, (168, 192, 216, 255)), (1.0, (34, 45, 58, 255))])
    img.paste(ring, (0, 0), ring_mask)

    # engraved ticks
    tick = Image.new("RGBA", size, (0, 0, 0, 0))
    td = ImageDraw.Draw(tick)
    for i in range(24):
        a = 2 * math.pi * i / 24
        r0, r1 = sc(58), sc(65) if i % 2 == 0 else sc(62)
        td.line([cx + math.cos(a) * r0, cy + math.sin(a) * r0,
                 cx + math.cos(a) * r1, cy + math.sin(a) * r1],
                fill=(0, 0, 0, 140), width=sc(1) if i % 2 else sc(2))
    img.alpha_composite(mul_alpha(tick, ring_mask))

    d.ellipse([cx - ro, cy - ro, cx + ro, cy + ro],
              outline=(208, 174, 112, 150), width=sc(2))
    d.ellipse([cx - ri, cy - ri, cx + ri, cy + ri],
              outline=(196, 162, 102, 100), width=sc(1))

    glass_r = sc(48)
    glass_mask = mask_ellipse(size, [cx - glass_r, cy - glass_r,
                                     cx + glass_r, cy + glass_r])
    glass = radial(size, (cx, cy), glass_r,
                   [(0.0, (40, 186, 180, 255)), (0.30, (22, 122, 130, 255)),
                    (0.64, (10, 52, 60, 255)), (1.0, (4, 11, 15, 255))])
    img.paste(glass, (0, 0), glass_mask)
    d.ellipse([cx - glass_r, cy - glass_r, cx + glass_r, cy + glass_r],
              outline=(6, 12, 15, 255), width=sc(3))

    spec = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(spec).arc(
        [cx - glass_r + sc(5), cy - glass_r + sc(5),
         cx + glass_r - sc(5), cy + glass_r - sc(5)],
        192, 278, fill=(235, 255, 255, 100), width=sc(3),
    )
    spec = spec.filter(ImageFilter.GaussianBlur(sc(2)))
    img.alpha_composite(mul_alpha(spec, glass_mask))

    add_glow(img, (cx, cy), sc(50), (70, 235, 220), 80, sc(8))

    hp = hex_points(cx, cy, sc(32))
    hex_mask = mask_polygon(size, hp)
    crystal = vgrad(size, [(0.0, (166, 248, 240, 255)), (0.3, (94, 222, 216, 255)),
                           (0.72, (26, 136, 146, 255)), (1.0, (9, 72, 82, 255))])
    img.paste(crystal, (0, 0), hex_mask)
    facet_colours = [
        (12, 66, 78, 200), (18, 84, 94, 195),
        (96, 214, 208, 180), (240, 255, 252, 185),
        (188, 252, 246, 180), (126, 236, 230, 180),
    ]
    facet = Image.new("RGBA", size, (0, 0, 0, 0))
    fd = ImageDraw.Draw(facet)
    for i in range(6):
        p0, p1 = hp[i], hp[(i + 1) % 6]
        fd.polygon([(cx, cy), p0, p1], fill=facet_colours[i])
    for p in hp:
        fd.line([cx, cy, p[0], p[1]], fill=(4, 34, 40, 110), width=sc(1))
    img.alpha_composite(mul_alpha(facet, hex_mask))
    d.polygon(hp, outline=(236, 255, 252, 230))

    inner_hex = hex_points(cx, cy, sc(14))
    inner_mask = mask_polygon(size, inner_hex)
    inner_fill = vgrad(size, [(0.0, (255, 255, 255, 255)), (0.45, (168, 255, 246, 255)),
                              (1.0, (54, 200, 198, 255))])
    img.paste(inner_fill, (0, 0), inner_mask)
    d.polygon(inner_hex, outline=(250, 255, 254, 210))
    d.ellipse([cx - sc(5), cy - sc(5), cx + sc(5), cy + sc(5)],
              fill=(255, 255, 253, 255))
    add_glow(img, (cx, cy), sc(14), (185, 255, 247), 85, sc(4))

    # mechanical flywheel over the energy core
    gear_pts = gear_polygon(cx, cy, sc(52), sc(61), 16, 0.10)
    gear_mask = mask_polygon(size, [(int(round(x)), int(round(y))) for x, y in gear_pts])
    gear_inner = mask_ellipse(size, [cx - sc(44), cy - sc(44), cx + sc(44), cy + sc(44)])
    gear_ring = ImageChops.subtract(gear_mask, gear_inner)
    img.paste(radial(size, (cx, cy), sc(61),
                     [(0.0, (0, 0, 0, 0)), (0.78, (58, 74, 92, 255)),
                      (0.90, (160, 184, 208, 255)), (1.0, (18, 25, 34, 255))]),
              (0, 0), gear_ring)
    d = ImageDraw.Draw(img)
    d.polygon([(int(round(x)), int(round(y))) for x, y in gear_pts],
              outline=(6, 9, 13, 255), width=sc(1))
    for i in range(6):
        a = 0.10 + 2 * math.pi * i / 6
        nx, ny = math.cos(a), math.sin(a)
        px, py = -ny, nx
        w0, w1 = sc(3), sc(2)
        r0, r1 = sc(14), sc(46)
        pts = [
            (cx + nx * r0 + px * w0, cy + ny * r0 + py * w0),
            (cx + nx * r1 + px * w1, cy + ny * r1 + py * w1),
            (cx + nx * r1 - px * w1, cy + ny * r1 - py * w1),
            (cx + nx * r0 - px * w0, cy + ny * r0 - py * w0),
        ]
        smask = mask_polygon(size, [(int(round(x)), int(round(y))) for x, y in pts])
        img.paste(vgrad(size, [(0.0, (148, 172, 198, 255)), (1.0, (30, 42, 56, 255))]),
                  (0, 0), smask)
    hub_r = sc(17)
    hub_mask = mask_ellipse(size, [cx - hub_r, cy - hub_r, cx + hub_r, cy + hub_r])
    img.paste(vgrad(size, [(0.0, (104, 124, 146, 255)), (1.0, (24, 34, 46, 255))]),
              (0, 0), hub_mask)
    d.ellipse([cx - hub_r, cy - hub_r, cx + hub_r, cy + hub_r],
              outline=(214, 178, 112, 190), width=sc(1))
    core_r = sc(8)
    d.ellipse([cx - core_r, cy - core_r, cx + core_r, cy + core_r],
              fill=(168, 255, 246, 255), outline=(255, 255, 255, 220), width=sc(1))
    add_glow(img, (cx, cy), sc(18), (100, 245, 232), 70, sc(4))

    # orbiting satellites
    for i in range(6):
        a = 2 * math.pi * i / 6 + 0.35
        px = cx + math.cos(a) * sc(61)
        py = cy + math.sin(a) * sc(61)
        add_glow(img, (int(px), int(py)), sc(7), (120, 250, 235), 80, sc(3))
        d.ellipse([px - sc(2), py - sc(2), px + sc(2), py + sc(2)],
                  fill=(230, 255, 250, 255))

    # port indicators: gas top, liquid bottom
    for x0, x1, y0, y1, top, bottom, edge in (
        (36, 56, 52, 76, (78, 220, 196, 255), (24, 116, 106, 255), (150, 255, 236, 230)),
        (200, 220, 52, 76, (78, 220, 196, 255), (24, 116, 106, 255), (150, 255, 236, 230)),
        (36, 56, 172, 196, (78, 168, 232, 255), (28, 84, 140, 255), (150, 218, 255, 230)),
        (200, 220, 172, 196, (78, 168, 232, 255), (28, 84, 140, 255), (150, 218, 255, 230)),
    ):
        box = [sc(x0), sc(y0), sc(x1), sc(y1)]
        m = mask_rrect(size, box, sc(5))
        g = vgrad(size, [(0.0, top), (1.0, bottom)])
        img.paste(g, (0, 0), m)
        d.rounded_rectangle(box, radius=sc(5), outline=edge, width=sc(2))
        d.line([sc(x0 + 2), sc(y0 + 2), sc(x1 - 2), sc(y0 + 2)],
               fill=(255, 255, 255, 120), width=sc(1))
        ax = sc((x0 + x1) / 2)
        ay = sc((y0 + y1) / 2)
        d.polygon([(ax - sc(4), ay - sc(5)), (ax + sc(4), ay),
                   (ax - sc(4), ay + sc(5))], fill=(240, 252, 255, 240))

    # power bolt
    add_glow(img, (sc(128), sc(214)), sc(20), (255, 200, 80), 70, sc(6))
    hb = mask_ellipse(size, [sc(112), sc(198), sc(144), sc(230)])
    hb_fill = vgrad(size, [(0.0, (70, 56, 28, 255)), (0.55, (42, 33, 16, 255)),
                           (1.0, (18, 14, 8, 255))])
    img.paste(hb_fill, (0, 0), hb)
    d.ellipse([sc(112), sc(198), sc(144), sc(230)],
              outline=(255, 226, 150, 200), width=sc(2))
    d.ellipse([sc(116), sc(202), sc(140), sc(226)],
              outline=(10, 8, 4, 160), width=sc(1))
    bolt = [
        (sc(133), sc(201)), (sc(120), sc(215)), (sc(127), sc(215)),
        (sc(123), sc(229)), (sc(138), sc(211)), (sc(131), sc(211)),
    ]
    ImageDraw.Draw(img).polygon(bolt, fill=(255, 220, 96, 255),
                                outline=(255, 244, 184, 255))

    opaque = img.split()[3].point(lambda v: 255 if v > 180 else 0)
    core_excl = mask_ellipse(size, [cx - sc(64), cy - sc(64),
                                    cx + sc(64), cy + sc(64)])
    img = apply_texture(
        img, ImageChops.subtract(opaque, core_excl), seed=31,
        brushed=0.140, grain=0.038, mottle=0.080, scratches=110,
    )
    glass_keep = mask_ellipse(size, [cx - sc(49), cy - sc(49),
                                      cx + sc(49), cy + sc(49)])
    img = apply_texture(
        img, ImageChops.subtract(core_excl, glass_keep), seed=43,
        brushed=0.040, grain=0.012, mottle=0.024, scratches=0,
    )

    v = radial(size, (sc(128), sc(128)), sc(170),
               [(0.0, (0, 0, 0, 0)), (0.7, (0, 0, 0, 0)), (1.0, (0, 0, 0, 60))])
    img.alpha_composite(v)

    out = img.resize((UI_SIZE, UI_SIZE), Image.LANCZOS)
    return final_grain(out, seed=77, strength=0.020)


# ---------------------------------------------------------------------------
# KAnim byte writers
# ---------------------------------------------------------------------------

def build_bytes(world_uvs: list[tuple[float, float, float, float]], off_uv, ui_uv) -> bytes:
    world = sdbm_lower(WORLD_NAME)
    off = sdbm_lower(OFF_NAME)
    place = sdbm_lower(PLACE_NAME)
    ui = sdbm_lower(UI_NAME)

    out = bytearray()
    out += b"BILD"
    out += struct.pack("<i", 10)
    out += struct.pack("<i", 4)  # symbols
    out += struct.pack("<i", 0)
    out += kstring("anti_entropy_generator")

    def write_symbol(symbol_hash: int, frames) -> None:
        nonlocal out
        out += struct.pack("<i", symbol_hash)
        out += struct.pack("<i", symbol_hash)
        out += struct.pack("<i", 0)  # channels
        out += struct.pack("<i", 0)  # flags
        out += struct.pack("<i", len(frames))
        for seq, bounds, uv in frames:
            out += struct.pack("<i", seq)
            out += struct.pack("<i", 1)
            out += struct.pack("<i", 0)
            out += struct.pack("<4f", *bounds)
            out += struct.pack("<4f", *uv)

    write_symbol(world, [(i, WORLD_BOUNDS, uv) for i, uv in enumerate(world_uvs)])
    write_symbol(off, [(0, WORLD_BOUNDS, off_uv)])
    write_symbol(place, [(0, WORLD_BOUNDS, world_uvs[0])])
    write_symbol(ui, [(0, UI_BOUNDS, ui_uv)])

    strings = [(world, WORLD_NAME), (off, OFF_NAME), (place, PLACE_NAME), (ui, UI_NAME)]
    out += struct.pack("<i", len(strings))
    for symbol_hash, name in strings:
        out += struct.pack("<i", symbol_hash)
        out += kstring(name)

    return bytes(out)


def anim_bytes(world_uvs, off_uv, ui_uv) -> bytes:
    world = sdbm_lower(WORLD_NAME)
    off = sdbm_lower(OFF_NAME)
    place = sdbm_lower(PLACE_NAME)
    ui = sdbm_lower(UI_NAME)

    out = bytearray()
    out += b"ANIM"
    out += struct.pack("<i", 5)
    out += struct.pack("<i", 0)
    out += struct.pack("<i", 0)
    out += struct.pack("<i", 5)  # animations

    def element(symbol_hash: int, frame: int) -> bytes:
        b = bytearray()
        b += struct.pack("<i", symbol_hash)
        b += struct.pack("<i", frame)
        b += struct.pack("<i", symbol_hash)
        b += struct.pack("<i", 0)
        b += struct.pack("<4f", 1.0, 1.0, 1.0, 1.0)
        b += struct.pack("<6f", 1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        b += struct.pack("<f", 0.0)
        return bytes(b)

    def animation(name: str, symbol_hash: int, bounds, frame_count: int,
                  use_frames: bool, frame_rate: float) -> None:
        nonlocal out
        out += kstring(name)
        out += struct.pack("<i", symbol_hash)
        out += struct.pack("<f", frame_rate)
        out += struct.pack("<i", frame_count)
        for i in range(frame_count):
            out += struct.pack("<4f", *bounds)
            out += struct.pack("<i", 1)
            out += element(symbol_hash, i if use_frames else 0)

    # 8 mechanical frames at 10 fps: one flywheel revolution per loop.
    animation("working", world, WORLD_BOUNDS, COUNT, True, 10.0)
    animation("idle", world, WORLD_BOUNDS, 1, False, 6.0)
    animation("off", off, WORLD_BOUNDS, 1, False, 6.0)
    animation("place", place, WORLD_BOUNDS, 1, False, 6.0)
    animation("ui", ui, UI_BOUNDS, 1, False, 6.0)

    strings = [(world, WORLD_NAME), (off, OFF_NAME), (place, PLACE_NAME), (ui, UI_NAME)]
    out += struct.pack("<i", 0)
    out += struct.pack("<i", len(strings))
    for symbol_hash, name in strings:
        out += struct.pack("<i", symbol_hash)
        out += kstring(name)

    return bytes(out)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    world_w = FRAME_W * COLS
    world_h = FRAME_H * ROWS
    # Power-of-two atlas, like the vanilla/mod KAnim assets.
    atlas_w = 2048
    atlas_h = 2048

    atlas = Image.new("RGBA", (atlas_w, atlas_h), (0, 0, 0, 0))

    world_uvs: list[tuple[float, float, float, float]] = []
    for i in range(COUNT):
        col, row = i % COLS, i // COLS
        frame = draw_frame(i)
        atlas.paste(frame, (col * FRAME_W, row * FRAME_H))
        world_uvs.append(
            (
                col * FRAME_W / atlas_w,
                row * FRAME_H / atlas_h,
                (col + 1) * FRAME_W / atlas_w,
                (row + 1) * FRAME_H / atlas_h,
            )
        )

    off_image = draw_frame(0, dim=True, working=False)
    off_x = 0
    off_y = world_h
    atlas.paste(off_image, (off_x, off_y))
    off_uv = (
        off_x / atlas_w,
        off_y / atlas_h,
        (off_x + FRAME_W) / atlas_w,
        (off_y + FRAME_H) / atlas_h,
    )

    icon = draw_icon()
    ui_x = FRAME_W
    ui_y = world_h
    atlas.paste(icon, (ui_x, ui_y))
    ui_uv = (
        ui_x / atlas_w,
        ui_y / atlas_h,
        (ui_x + UI_SIZE) / atlas_w,
        (ui_y + UI_SIZE) / atlas_h,
    )

    atlas.save(OUT / "anti_entropy_generator_0.png", optimize=True, compress_level=9)
    (OUT / "anti_entropy_generator_build.bytes").write_bytes(
        build_bytes(world_uvs, off_uv, ui_uv)
    )
    (OUT / "anti_entropy_generator_anim.bytes").write_bytes(
        anim_bytes(world_uvs, off_uv, ui_uv)
    )

    preview = ROOT / "tools" / "anti_entropy_generator_preview.png"
    preview.parent.mkdir(parents=True, exist_ok=True)
    atlas.crop((0, 0, FRAME_W, FRAME_H)).save(preview, optimize=True)
    icon.save(ROOT / "tools" / "anti_entropy_generator_icon.png", optimize=True)

    print("wrote", OUT)
    print("wrote", preview)


if __name__ == "__main__":
    main()
