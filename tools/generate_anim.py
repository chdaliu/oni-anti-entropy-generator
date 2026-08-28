#!/usr/bin/env python3
"""Generate the 4x3 Anti-Entropy Generator KAnim (world atlas + build menu icon)."""
from __future__ import annotations

import math
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "anim" / "assets" / "anti_entropy_generator"

FRAME_W, FRAME_H = 512, 384
COLS, ROWS = 4, 2
COUNT = COLS * ROWS
UI_SIZE = 256
S = 2  # supersampling factor

# 4x3, OnFloor, non-rotatable vanilla reference: FabricatedWoodMaker
# (plantmatter_compressor_kanim).  Its idle bounds are approximately
# (30, -326, 843, 679); the UI symbol is about 270x230.
WORLD_BOUNDS = (30.0, -326.0, 843.0, 679.0)
UI_BOUNDS = (10.0, -120.0, 270.0, 230.0)

WORLD_NAME = "world"
OFF_NAME = "off"
PLACE_NAME = "place"
UI_NAME = "ui"


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


def draw_arrow(d: ImageDraw.ImageDraw, x: int, y: int, direction: int, colour: tuple[int, int, int, int]) -> None:
    """Small triangular arrow; direction +1 points right, -1 points left."""
    if direction > 0:
        points = [(x - 10, y - 12), (x + 10, y), (x - 10, y + 12)]
    else:
        points = [(x + 10, y - 12), (x - 10, y), (x + 10, y + 12)]
    d.polygon(points, fill=colour)


def draw_frame(index: int, dim: bool = False) -> Image.Image:
    width, height = FRAME_W * S, FRAME_H * S
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    phase = index / COUNT
    pulse = 0.5 + 0.5 * math.sin(2 * math.pi * phase)

    body_fill = (24, 31, 42, 255)
    body_edge = (96, 126, 156, 255)
    panel_fill = (16, 22, 31, 255)
    panel_edge = (54, 72, 92, 255)
    rib_fill = (35, 47, 62, 255)
    fin_fill = (42, 57, 75, 255)

    # soft drop shadow
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle(
        [sc(24), sc(26), sc(488), sc(370)],
        radius=sc(32),
        fill=(0, 0, 0, 110),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(sc(14)))
    img = Image.alpha_composite(img, shadow)
    d = ImageDraw.Draw(img)

    # chassis
    d.rounded_rectangle(
        [sc(16), sc(18), sc(496), sc(366)],
        radius=sc(30),
        fill=body_fill,
        outline=body_edge,
        width=sc(5),
    )
    d.rounded_rectangle(
        [sc(30), sc(34), sc(482), sc(350)],
        radius=sc(22),
        fill=panel_fill,
        outline=panel_edge,
        width=sc(3),
    )

    # side ribs
    for x in (60, 452):
        d.rounded_rectangle(
            [sc(x - 9), sc(56), sc(x + 9), sc(328)],
            radius=sc(9),
            fill=rib_fill,
            outline=(70, 92, 116, 150),
            width=sc(2),
        )

    # top heat-sink fins
    for i in range(7):
        x = sc(122 + i * 40)
        d.rounded_rectangle(
            [x, sc(46), x + sc(18), sc(92)],
            radius=sc(6),
            fill=fin_fill,
            outline=(92, 122, 150, 190),
            width=sc(2),
        )

    # bottom vents
    for i in range(9):
        x = sc(92 + i * 38)
        d.rounded_rectangle(
            [x, sc(300), x + sc(22), sc(322)],
            radius=sc(4),
            fill=(38, 51, 67, 255),
            outline=(64, 82, 102, 130),
            width=sc(1),
        )

    # scanlines
    for y in range(112, 296, 12):
        d.line([sc(54), sc(y), sc(458), sc(y)], fill=(120, 160, 190, 14), width=1)

    # ---- core glow ----
    if not dim:
        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        cx, cy = sc(256), sc(190)
        radius = sc(56 + 18 * pulse)
        for k in range(6, 0, -1):
            r = int(radius * (1.0 + k * 0.20))
            alpha = int((10 + 16 * pulse) * (7 - k) / 6)
            gd.ellipse(
                [cx - r, cy - r, cx + r, cy + r],
                fill=(70, 235, 220, alpha),
            )
        glow = glow.filter(ImageFilter.GaussianBlur(sc(14)))
        img = Image.alpha_composite(img, glow)
        d = ImageDraw.Draw(img)

    # core ring
    cx, cy = sc(256), sc(190)
    ring_colour = (48, 140, 150, 255) if dim else (95, 240, 225, 255)
    d.ellipse(
        [cx - sc(66), cy - sc(66), cx + sc(66), cy + sc(66)],
        outline=ring_colour,
        width=sc(4),
    )
    d.ellipse(
        [cx - sc(56), cy - sc(56), cx + sc(56), cy + sc(56)],
        outline=(40, 105, 115, 220) if dim else (190, 255, 248, 180),
        width=sc(2),
    )

    # rotating marker dots
    for i in range(6):
        angle = 2 * math.pi * (i / 6.0 + phase * 0.35)
        px = cx + int(math.cos(angle) * sc(74))
        py = cy + int(math.sin(angle) * sc(74))
        dot = (14, 32, 38, 255) if dim else (225, 255, 250, int(150 + 100 * pulse))
        d.ellipse([px - sc(4), py - sc(4), px + sc(4), py + sc(4)], fill=dot)

    # hexagonal core
    hex_points = []
    for i in range(6):
        angle = math.pi / 6 + i * math.pi / 3
        hex_points.append((cx + int(math.cos(angle) * sc(43)), cy + int(math.sin(angle) * sc(43))))
    if dim:
        d.polygon(hex_points, fill=(30, 58, 64, 255), outline=(62, 104, 112, 255))
        d.polygon(
            [(cx + int((x - cx) * 0.55), cy + int((y - cy) * 0.55)) for x, y in hex_points],
            fill=(42, 82, 88, 255),
            outline=(86, 134, 142, 220),
        )
    else:
        d.polygon(hex_points, fill=(38, 145, 150, 255), outline=(205, 255, 248, 255))
        d.polygon(
            [(cx + int((x - cx) * 0.55), cy + int((y - cy) * 0.55)) for x, y in hex_points],
            fill=(120, 245, 235, 255),
            outline=(235, 255, 252, 255),
        )
        # inner hot spot
        d.ellipse(
            [cx - sc(13), cy - sc(13), cx + sc(13), cy + sc(13)],
            fill=(245, 255, 253, int(190 + 60 * pulse)),
        )

    # ---- ports ----
    liquid_in = (40, 100, 165, 255)
    liquid_edge = (130, 210, 255, 255)
    gas_in = (36, 135, 125, 255)
    gas_edge = (120, 245, 225, 255)
    power = (160, 120, 30, 255)
    power_edge = (255, 220, 90, 255)

    # liquid input (left, bottom row)
    d.rounded_rectangle([sc(-4), sc(294), sc(36), sc(344)], radius=sc(11), fill=liquid_in, outline=liquid_edge, width=sc(4))
    draw_arrow(d, sc(18), sc(319), +1, (225, 250, 255, 235))
    # liquid output (right, bottom row)
    d.rounded_rectangle([sc(476), sc(294), sc(516), sc(344)], radius=sc(11), fill=liquid_in, outline=liquid_edge, width=sc(4))
    draw_arrow(d, sc(494), sc(319), +1, (225, 250, 255, 235))
    # gas input (left, top row)
    d.rounded_rectangle([sc(-4), sc(40), sc(36), sc(90)], radius=sc(11), fill=gas_in, outline=gas_edge, width=sc(4))
    draw_arrow(d, sc(18), sc(65), +1, (225, 255, 248, 235))
    # gas output (right, top row)
    d.rounded_rectangle([sc(476), sc(40), sc(516), sc(90)], radius=sc(11), fill=gas_in, outline=gas_edge, width=sc(4))
    draw_arrow(d, sc(494), sc(65), +1, (225, 255, 248, 235))
    # power output (bottom, cell 1)
    d.rounded_rectangle([sc(170), sc(352), sc(214), sc(386)], radius=sc(7), fill=power, outline=power_edge, width=sc(3))
    d.polygon(
        [
            (sc(198), sc(356)),
            (sc(186), sc(371)),
            (sc(194), sc(371)),
            (sc(190), sc(382)),
            (sc(204), sc(365)),
            (sc(196), sc(365)),
        ],
        fill=(255, 240, 160, 255),
    )

    # corner bolts
    for x, y in ((34, 40), (478, 40), (34, 344), (478, 344)):
        d.ellipse(
            [sc(x - 7), sc(y - 7), sc(x + 7), sc(y + 7)],
            fill=(92, 112, 132, 255),
            outline=(190, 215, 235, 190),
            width=sc(2),
        )

    return img.resize((FRAME_W, FRAME_H), Image.LANCZOS)


def draw_icon() -> Image.Image:
    size = UI_SIZE * S
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    d.rounded_rectangle(
        [sc(16), sc(16), sc(240), sc(240)],
        radius=sc(36),
        fill=(22, 30, 42, 255),
        outline=(100, 135, 165, 255),
        width=sc(6),
    )
    d.rounded_rectangle(
        [sc(32), sc(32), sc(224), sc(224)],
        radius=sc(26),
        fill=(14, 20, 29, 255),
        outline=(54, 76, 98, 255),
        width=sc(3),
    )

    cx, cy = sc(128), sc(124)
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([cx - sc(64), cy - sc(64), cx + sc(64), cy + sc(64)], fill=(80, 240, 225, 60))
    glow = glow.filter(ImageFilter.GaussianBlur(sc(16)))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)

    d.ellipse([cx - sc(62), cy - sc(62), cx + sc(62), cy + sc(62)], outline=(120, 245, 232, 255), width=sc(4))
    hex_points = []
    for i in range(6):
        angle = math.pi / 6 + i * math.pi / 3
        hex_points.append((cx + int(math.cos(angle) * sc(42)), cy + int(math.sin(angle) * sc(42))))
    d.polygon(hex_points, fill=(44, 160, 162, 255), outline=(225, 255, 250, 255))
    d.polygon(
        [(cx + int((x - cx) * 0.55), cy + int((y - cy) * 0.55)) for x, y in hex_points],
        fill=(130, 250, 238, 255),
    )
    d.ellipse([cx - sc(11), cy - sc(11), cx + sc(11), cy + sc(11)], fill=(250, 255, 253, 255))

    # small input/output markers
    d.rounded_rectangle([sc(28), sc(154), sc(48), sc(176)], radius=sc(5), fill=(40, 100, 165, 255), outline=(130, 210, 255, 255), width=sc(2))
    d.rounded_rectangle([sc(208), sc(154), sc(228), sc(176)], radius=sc(5), fill=(40, 100, 165, 255), outline=(130, 210, 255, 255), width=sc(2))
    d.rounded_rectangle([sc(28), sc(70), sc(48), sc(92)], radius=sc(5), fill=(36, 135, 125, 255), outline=(120, 245, 225, 255), width=sc(2))
    d.rounded_rectangle([sc(208), sc(70), sc(228), sc(92)], radius=sc(5), fill=(36, 135, 125, 255), outline=(120, 245, 225, 255), width=sc(2))

    # power bolt at the bottom
    d.polygon(
        [
            (sc(134), sc(188)),
            (sc(118), sc(212)),
            (sc(128), sc(212)),
            (sc(122), sc(230)),
            (sc(142), sc(204)),
            (sc(132), sc(204)),
        ],
        fill=(255, 220, 90, 255),
        outline=(255, 245, 180, 255),
    )

    return img.resize((UI_SIZE, UI_SIZE), Image.LANCZOS)


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
    out += struct.pack("<i", 4)  # animations

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

    def animation(name: str, symbol_hash: int, bounds, frame_count: int, use_frames: bool) -> None:
        nonlocal out
        out += kstring(name)
        out += struct.pack("<i", symbol_hash)
        out += struct.pack("<f", 6.0)
        out += struct.pack("<i", frame_count)
        for i in range(frame_count):
            out += struct.pack("<4f", *bounds)
            out += struct.pack("<i", 1)
            out += element(symbol_hash, i if use_frames else 0)

    animation("idle", world, WORLD_BOUNDS, COUNT, True)
    animation("off", off, WORLD_BOUNDS, 1, False)
    animation("place", place, WORLD_BOUNDS, 1, False)
    animation("ui", ui, UI_BOUNDS, 1, False)

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

    off_image = draw_frame(0, dim=True)
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

    atlas.save(OUT / "anti_entropy_generator_0.png")
    (OUT / "anti_entropy_generator_build.bytes").write_bytes(
        build_bytes(world_uvs, off_uv, ui_uv)
    )
    (OUT / "anti_entropy_generator_anim.bytes").write_bytes(
        anim_bytes(world_uvs, off_uv, ui_uv)
    )

    preview = ROOT / "tools" / "anti_entropy_generator_preview.png"
    preview.parent.mkdir(parents=True, exist_ok=True)
    atlas.crop((0, 0, FRAME_W, FRAME_H)).save(preview)
    icon.save(ROOT / "tools" / "anti_entropy_generator_icon.png")

    print("wrote", OUT)
    print("wrote", preview)


if __name__ == "__main__":
    main()
