#!/usr/bin/env python3
"""
Generate a Godot-friendly player racer sprite kit (v2 quality pass):
- Yellow sports coupe body sprites (behind-the-car camera, turn variants)
- Separate sport tire spin animations
- Underbody variants for vehicle flips
- Transparent PNGs + JSON metadata for compositing in Godot
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont


# Output layout
REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = REPO_ROOT / "assets" / "sprites" / "player_racer"
BODY_DIR = OUT_ROOT / "body"
WHEEL_DIR = OUT_ROOT / "wheels"
PREVIEW_DIR = OUT_ROOT / "preview"

# Sprite dimensions
BODY_FRAME_W = 160
BODY_FRAME_H = 120
WHEEL_FRAME_W = 40
WHEEL_FRAME_H = 40
WHEEL_FRAMES = 24
SUPERSAMPLE = 4

RESAMPLING = Image.Resampling if hasattr(Image, "Resampling") else Image

# Direction set (left -> right)
DIRECTIONS: List[Tuple[str, float]] = [
    ("far_left", -1.0),
    ("hard_left", -0.75),
    ("left", -0.5),
    ("slight_left", -0.25),
    ("straight", 0.0),
    ("slight_right", 0.25),
    ("right", 0.5),
    ("hard_right", 0.75),
    ("far_right", 1.0),
]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def darken(rgb: Tuple[int, int, int], amount: float) -> Tuple[int, int, int]:
    amount = clamp(amount, 0.0, 1.0)
    return tuple(int(c * (1.0 - amount)) for c in rgb)


def lighten(rgb: Tuple[int, int, int], amount: float) -> Tuple[int, int, int]:
    amount = clamp(amount, 0.0, 1.0)
    return tuple(int(c + (255 - c) * amount) for c in rgb)


def sp(v: float) -> int:
    """Scale a scalar to supersampled pixel space."""
    return int(round(v * SUPERSAMPLE))


def spp(point: Tuple[float, float]) -> Tuple[int, int]:
    """Scale a 2D point to supersampled pixel space."""
    return sp(point[0]), sp(point[1])


def spp_list(points: List[Tuple[float, float]]) -> List[Tuple[int, int]]:
    return [spp(p) for p in points]


def sbox(x1: float, y1: float, x2: float, y2: float) -> Tuple[int, int, int, int]:
    return sp(x1), sp(y1), sp(x2), sp(y2)


def body_geometry(yaw: float) -> Dict[str, List[Tuple[float, float]]]:
    """
    Build a stylized rear-camera sports-car profile.
    yaw is in [-1..1] where negative turns left and positive turns right.
    """
    yaw = clamp(yaw, -1.0, 1.0)
    cx = BODY_FRAME_W / 2
    shift = yaw * 20.0
    ay = abs(yaw)

    # Lower camera angle profile (rear racing view) with less top-down taper.
    y_sections = [20, 28, 38, 50, 63, 77, 90, 100]
    width_base = [41, 47, 53, 60, 66, 71, 75, 77]
    width_yaw_cut = [4, 5, 6, 6, 5, 4, 2, 1]
    shift_curve = [1.0, 0.92, 0.8, 0.62, 0.44, 0.28, 0.14, 0.0]

    half_widths = [w - ay * cut for w, cut in zip(width_base, width_yaw_cut)]
    centers = [cx + shift * c for c in shift_curve]

    left = [(c - hw, y) for c, hw, y in zip(centers, half_widths, y_sections)]
    right = [(c + hw, y) for c, hw, y in zip(centers, half_widths, y_sections)]
    centerline = list(zip(centers, y_sections))

    return {
        "left": left,
        "right": right,
        "centerline": centerline,
        "centers": centers,
        "half_widths": half_widths,
        "y_sections": y_sections,
    }


def wheel_anchor_positions(g: Dict[str, List[Tuple[float, float]]], yaw: float) -> Dict[str, Tuple[int, int]]:
    centers = g["centers"]
    ay = abs(yaw)

    front_y = int(76 - ay * 1.5)
    rear_y = int(94)

    front_center = int(lerp(centers[4], centers[5], 0.25) + yaw * 2.6)
    rear_center = int(lerp(centers[6], centers[7], 0.50) + yaw * 1.2)

    front_track = int(104 - ay * 20)
    rear_track = int(118 - ay * 26)
    bias = int(yaw * 4)

    return {
        "front_left": (front_center - front_track // 2 - bias, front_y),
        "front_right": (front_center + front_track // 2 + bias, front_y),
        "rear_left": (rear_center - rear_track // 2 - int(bias * 0.65), rear_y),
        "rear_right": (rear_center + rear_track // 2 + int(bias * 0.65), rear_y),
    }


def draw_wheel_wells(
    draw: ImageDraw.ImageDraw,
    anchors: Dict[str, Tuple[int, int]],
    underbody: bool,
) -> None:
    for key, (x, y) in anchors.items():
        is_rear = key.startswith("rear")
        well_w = 31 if is_rear else 29
        well_h = 18
        fill = (8, 8, 10, 185) if not underbody else (28, 28, 31, 170)
        rim = (90, 90, 95, 185) if not underbody else (120, 120, 128, 165)

        draw.ellipse(
            sbox(x - well_w / 2, y - well_h / 2, x + well_w / 2, y + well_h / 2),
            fill=fill,
        )
        draw.arc(
            sbox(x - (well_w + 2) / 2, y - (well_h + 1) / 2, x + (well_w + 2) / 2, y + (well_h + 1) / 2),
            start=192,
            end=346,
            fill=rim,
            width=sp(1.5),
        )


def draw_body_details(
    draw: ImageDraw.ImageDraw,
    g: Dict[str, List[Tuple[float, float]]],
    yaw: float,
    underbody: bool,
    anchors: Dict[str, Tuple[int, int]],
) -> None:
    left = g["left"]
    right = g["right"]
    centerline = g["centerline"]
    centers = g["centers"]
    half_widths = g["half_widths"]
    y_sections = g["y_sections"]

    body_poly = right + list(reversed(left))
    body_outline = (20, 20, 22, 255)

    if underbody:
        draw.polygon(spp_list(body_poly), fill=(64, 66, 70, 255), outline=body_outline)

        # Inner belly pan
        inner_left = [(x + 10, y) for x, y in left[1:-1]]
        inner_right = [(x - 10, y) for x, y in right[1:-1]]
        draw.polygon(spp_list(inner_right + list(reversed(inner_left))), fill=(82, 84, 90, 255))

        c = centers[-2]

        # Center tunnel and mechanical modules
        draw.rounded_rectangle(
            sbox(c - 11, y_sections[1] + 2, c + 11, y_sections[-2] - 2),
            radius=sp(3),
            fill=(95, 98, 104, 255),
            outline=(40, 40, 44, 255),
            width=sp(0.8),
        )
        draw.rounded_rectangle(
            sbox(c - 24, y_sections[4] - 2, c + 24, y_sections[5] + 6),
            radius=sp(4),
            fill=(76, 78, 84, 255),
            outline=(35, 35, 38, 255),
            width=sp(0.8),
        )
        draw.rounded_rectangle(
            sbox(c - 18, y_sections[2], c + 18, y_sections[3] + 2),
            radius=sp(3),
            fill=(74, 75, 81, 255),
            outline=(34, 34, 37, 255),
            width=sp(0.8),
        )

        # Chassis braces
        for y in (y_sections[3], y_sections[5], y_sections[6]):
            draw.line(
                [spp((left[4][0] + 10, y)), spp((right[4][0] - 10, y))],
                fill=(118, 118, 126, 220),
                width=sp(1.3),
            )

        # Exhaust pipes
        for dx in (-7, 7):
            draw.line(
                [spp((c + dx, y_sections[3] + 3)), spp((c + dx, y_sections[-2] - 4))],
                fill=(144, 144, 149, 235),
                width=sp(1.4),
            )
            draw.ellipse(
                sbox(c + dx - 2.8, y_sections[-2] - 1.5, c + dx + 2.8, y_sections[-2] + 3.5),
                fill=(178, 178, 184, 230),
                outline=(75, 75, 80, 255),
                width=sp(0.8),
            )

        # Yellow side rails to preserve car color identity while flipped.
        rail_l = [(x + 3, y) for x, y in left[2:7]] + [(x + 9, y) for x, y in reversed(left[2:7])]
        rail_r = [(x - 3, y) for x, y in right[2:7]] + [(x - 9, y) for x, y in reversed(right[2:7])]
        draw.polygon(spp_list(rail_l), fill=(232, 184, 16, 220))
        draw.polygon(spp_list(rail_r), fill=(232, 184, 16, 220))

        # Rear diffuser block
        rear_c = centers[-1]
        draw.rounded_rectangle(
            sbox(rear_c - 46, y_sections[-2] + 3, rear_c + 46, y_sections[-1] - 2),
            radius=sp(3),
            fill=(30, 31, 34, 255),
            outline=(18, 18, 20, 255),
            width=sp(1.0),
        )
        for i in range(-4, 5, 2):
            x = rear_c + i * 8
            draw.line(
                [spp((x, y_sections[-2] + 4)), spp((x, y_sections[-1] - 2))],
                fill=(66, 66, 72, 245),
                width=sp(0.8),
            )
    else:
        yellow = (248, 205, 16)
        draw.polygon(spp_list(body_poly), fill=yellow + (255,), outline=body_outline)

        # Side volume shading based on turn direction.
        near_side = right if yaw >= 0 else left
        far_side = left if yaw >= 0 else right
        near_highlight = lighten(yellow, 0.22) + (95,)
        far_shadow = darken(yellow, 0.35) + (142,)
        draw.polygon(spp_list(far_side + list(reversed(centerline))), fill=far_shadow)
        draw.polygon(spp_list(near_side + list(reversed(centerline))), fill=near_highlight)

        # Rear body lip and diffuser
        rear_c = centers[-1]
        draw.rounded_rectangle(
            sbox(rear_c - 51, y_sections[-2] + 2, rear_c + 51, y_sections[-1] - 1),
            radius=sp(4),
            fill=(26, 27, 30, 255),
            outline=(14, 14, 16, 255),
            width=sp(1.0),
        )
        for i in range(-5, 6, 2):
            x = rear_c + i * 7.5
            draw.line(
                [spp((x, y_sections[-2] + 4)), spp((x, y_sections[-1] - 2))],
                fill=(58, 58, 63, 245),
                width=sp(0.8),
            )

        # Ferrari-like dual taillight clusters (two circular lights per side)
        tail_y = y_sections[-2] - 4
        for side in (-1, 1):
            base = rear_c + side * (half_widths[-1] - 16)
            second = base - side * 12
            for tx in (base, second):
                draw.ellipse(
                    sbox(tx - 5, tail_y - 5, tx + 5, tail_y + 5),
                    fill=(212, 25, 28, 255),
                    outline=(82, 8, 9, 255),
                    width=sp(0.9),
                )
                draw.ellipse(
                    sbox(tx - 2.2, tail_y - 2.2, tx + 2.2, tail_y + 2.2),
                    fill=(255, 132, 84, 230),
                )

        # Rear center grille
        draw.rounded_rectangle(
            sbox(rear_c - 26, y_sections[5] + 1, rear_c + 26, y_sections[5] + 10),
            radius=sp(2),
            fill=(14, 14, 16, 235),
            outline=(38, 38, 42, 255),
            width=sp(0.6),
        )
        for i in range(-3, 4):
            x = rear_c + i * 7
            draw.line(
                [spp((x, y_sections[5] + 2)), spp((x, y_sections[5] + 9))],
                fill=(42, 42, 47, 210),
                width=sp(0.6),
            )

        # Exhaust tips
        for dx in (-20, -12, 12, 20):
            draw.ellipse(
                sbox(rear_c + dx - 3.2, y_sections[-1] - 7, rear_c + dx + 3.2, y_sections[-1] - 1),
                fill=(130, 130, 138, 245),
                outline=(44, 44, 49, 255),
                width=sp(0.8),
            )

        # Cabin / rear glass
        cab_top = centerline[1]
        cab_mid = centerline[3]
        cab_low = centerline[4]
        roof = [
            (cab_top[0] - 20, cab_top[1] + 1),
            (cab_top[0] + 20, cab_top[1] + 1),
            (cab_mid[0] + 30, cab_mid[1] + 2),
            (cab_low[0] + 27, cab_low[1] - 2),
            (cab_low[0] - 27, cab_low[1] - 2),
            (cab_mid[0] - 30, cab_mid[1] + 2),
        ]
        draw.polygon(spp_list(roof), fill=(18, 24, 32, 250), outline=(8, 10, 13, 255))

        # Cockpit opening / occupants (stylized, subtle scale)
        cockpit = [
            (cab_top[0] - 15, cab_top[1] + 3),
            (cab_top[0] + 15, cab_top[1] + 3),
            (cab_mid[0] + 21, cab_mid[1] + 5),
            (cab_mid[0] - 21, cab_mid[1] + 5),
        ]
        draw.polygon(spp_list(cockpit), fill=(8, 10, 14, 220))

        driver_x = cab_mid[0] - 7 + yaw * 2.0
        passenger_x = cab_mid[0] + 8 + yaw * 1.3
        head_y = cab_top[1] + 8.5
        draw.ellipse(sbox(driver_x - 3.2, head_y - 3.1, driver_x + 3.2, head_y + 3.1), fill=(240, 196, 90, 235), outline=(58, 42, 18, 220), width=sp(0.5))
        draw.ellipse(sbox(passenger_x - 3.0, head_y - 2.9, passenger_x + 3.0, head_y + 2.9), fill=(216, 168, 78, 230), outline=(52, 36, 16, 210), width=sp(0.5))
        draw.arc(sbox(driver_x - 3.6, head_y - 3.7, driver_x + 3.6, head_y + 1.3), start=185, end=355, fill=(26, 20, 14, 210), width=sp(0.9))
        draw.arc(sbox(passenger_x - 3.2, head_y - 3.4, passenger_x + 3.2, head_y + 1.0), start=180, end=352, fill=(44, 28, 14, 210), width=sp(0.9))

        # Windshield highlight arc
        draw.arc(
            sbox(cab_top[0] - 14, cab_top[1] + 3, cab_top[0] + 14, cab_top[1] + 18),
            start=188,
            end=350,
            fill=(158, 182, 206, 150),
            width=sp(1.0),
        )

        # Rear deck channels
        deck_y0 = y_sections[4] + 1
        deck_y1 = y_sections[6] - 6
        draw.line(
            [spp((centerline[2][0], y_sections[2] + 3)), spp((centerline[4][0], deck_y0)), spp((centerline[5][0], deck_y1))],
            fill=(20, 20, 22, 170),
            width=sp(1.2),
        )

        # Shoulder crease to improve low-angle shape readability.
        draw.line(
            [spp((left[2][0] + 9, y_sections[2] + 1)), spp((centerline[3][0], y_sections[3] + 1)), spp((right[2][0] - 9, y_sections[2] + 1))],
            fill=(255, 223, 94, 130),
            width=sp(0.9),
        )

        # Side intake stripe on near side for sports look.
        near_is_right = yaw >= 0
        side = right if near_is_right else left
        sign = 1 if near_is_right else -1
        inward = -sign
        p3 = side[3]
        p4 = side[4]
        p6 = side[6]
        intake = [
            (p3[0] + inward * 8, p3[1] + 1),
            (p4[0] + inward * 10, p4[1] + 2),
            (p6[0] + inward * 10, p6[1] - 7),
            (p6[0] + inward * 22, p6[1] - 8),
            (p4[0] + inward * 23, p4[1] - 1),
            (p3[0] + inward * 18, p3[1] - 1),
        ]
        draw.polygon(spp_list(intake), fill=(14, 14, 16, 215))
        draw.line(
            [spp((intake[0][0], intake[0][1] - 0.8)), spp((intake[1][0], intake[1][1] - 0.8)), spp((intake[2][0], intake[2][1] - 0.8))],
            fill=(245, 203, 50, 170),
            width=sp(0.7),
        )

    # Shared spoiler (black mounts + yellow wing with black stripe)
    spoiler_center_x = centerline[0][0] + yaw * 4
    spoiler_w = 76 - abs(yaw) * 10
    sx1 = spoiler_center_x - spoiler_w / 2
    sx2 = spoiler_center_x + spoiler_w / 2
    sy1 = y_sections[0] - 5
    sy2 = sy1 + 7

    draw.rectangle(sbox(sx1 + 7, sy1 + 6, sx1 + 11, sy2 + 15), fill=(12, 12, 14, 255))
    draw.rectangle(sbox(sx2 - 11, sy1 + 6, sx2 - 7, sy2 + 15), fill=(12, 12, 14, 255))
    draw.rounded_rectangle(
        sbox(sx1, sy1, sx2, sy2),
        radius=sp(1.8),
        fill=(244, 198, 10, 255),
        outline=(16, 16, 18, 255),
        width=sp(0.8),
    )
    draw.line([spp((sx1 + 3, (sy1 + sy2) / 2)), spp((sx2 - 3, (sy1 + sy2) / 2))], fill=(14, 14, 15, 230), width=sp(1.1))

    draw_wheel_wells(draw, anchors, underbody=underbody)


def draw_body_frame(yaw: float, underbody: bool) -> Tuple[Image.Image, Dict[str, Tuple[int, int]]]:
    g = body_geometry(yaw)
    anchors = wheel_anchor_positions(g, yaw)

    hi = Image.new("RGBA", (BODY_FRAME_W * SUPERSAMPLE, BODY_FRAME_H * SUPERSAMPLE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(hi, "RGBA")
    draw_body_details(draw, g, yaw, underbody, anchors)

    final = hi.resize((BODY_FRAME_W, BODY_FRAME_H), RESAMPLING.LANCZOS)
    return final, anchors


def draw_wheel_frame(squash: float, spin_frame: int) -> Image.Image:
    hi = Image.new("RGBA", (WHEEL_FRAME_W * SUPERSAMPLE, WHEEL_FRAME_H * SUPERSAMPLE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(hi, "RGBA")

    cx = (WHEEL_FRAME_W * SUPERSAMPLE) // 2
    cy = (WHEEL_FRAME_H * SUPERSAMPLE) // 2

    outer_w = (WHEEL_FRAME_W - 4) * squash * SUPERSAMPLE
    outer_h = (WHEEL_FRAME_H - 4) * SUPERSAMPLE
    x1, y1 = cx - outer_w / 2, cy - outer_h / 2
    x2, y2 = cx + outer_w / 2, cy + outer_h / 2

    # Tire shell
    draw.ellipse((int(x1), int(y1), int(x2), int(y2)), fill=(10, 10, 11, 255), outline=(4, 4, 5, 255), width=sp(0.9))
    draw.ellipse((int(x1 + sp(1.0)), int(y1 + sp(1.0)), int(x2 - sp(1.0)), int(y2 - sp(1.0))), fill=(24, 24, 27, 255))

    phase = spin_frame * (360.0 / WHEEL_FRAMES)

    # Tread grooves
    for n in range(18):
        a = math.radians(phase * 1.7 + n * 20)
        rx_outer = outer_w * 0.42
        ry_outer = outer_h * 0.42
        rx_inner = outer_w * 0.31
        ry_inner = outer_h * 0.31
        p1 = (cx + math.cos(a) * rx_outer, cy + math.sin(a) * ry_outer)
        p2 = (cx + math.cos(a) * rx_inner, cy + math.sin(a) * ry_inner)
        alpha = 100 + int((math.sin(math.radians(n * 20 + phase)) + 1.0) * 40)
        draw.line((int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1])), fill=(82, 82, 88, alpha), width=sp(0.8))

    # Motion blur streaks
    streak = Image.new("RGBA", hi.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(streak, "RGBA")
    for n in range(24):
        a = math.radians(phase * 2.6 + n * 15)
        p1 = (cx + math.cos(a) * outer_w * 0.40, cy + math.sin(a) * outer_h * 0.40)
        p2 = (cx + math.cos(a) * outer_w * 0.23, cy + math.sin(a) * outer_h * 0.23)
        alpha = 40 + int((math.sin(math.radians(phase + n * 15)) + 1.0) * 42)
        sdraw.line((int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1])), fill=(180, 180, 190, alpha), width=sp(0.7))
    streak = streak.filter(ImageFilter.GaussianBlur(radius=sp(0.35)))
    hi.alpha_composite(streak)

    # Rim + spokes
    rim = (x1 + sp(3.4), y1 + sp(3.4), x2 - sp(3.4), y2 - sp(3.4))
    draw.ellipse(tuple(int(v) for v in rim), fill=(172, 172, 180, 245), outline=(92, 92, 98, 255), width=sp(0.7))
    inner = (rim[0] + sp(1.3), rim[1] + sp(1.3), rim[2] - sp(1.3), rim[3] - sp(1.3))
    draw.ellipse(tuple(int(v) for v in inner), fill=(56, 56, 62, 235))

    spoke_rx = (inner[2] - inner[0]) * 0.36
    spoke_ry = (inner[3] - inner[1]) * 0.36
    for i in range(6):
        a = math.radians(phase * 1.3 + i * 60)
        ex = cx + math.cos(a) * spoke_rx
        ey = cy + math.sin(a) * spoke_ry
        draw.line((cx, cy, int(ex), int(ey)), fill=(228, 228, 232, 220), width=sp(0.85))

    # Brake caliper hint + yellow accent ring
    caliper_x = cx + int(outer_w * 0.16)
    draw.rounded_rectangle(
        (caliper_x, cy - sp(3.0), caliper_x + sp(2.6), cy + sp(3.0)),
        radius=sp(0.8),
        fill=(190, 38, 34, 230),
    )
    draw.arc((int(x1 + sp(1.4)), int(y1 + sp(1.4)), int(x2 - sp(1.4)), int(y2 - sp(1.4))), start=phase - 18, end=phase + 30, fill=(252, 204, 26, 235), width=sp(0.9))
    draw.ellipse((cx - sp(1.8), cy - sp(1.8), cx + sp(1.8), cy + sp(1.8)), fill=(246, 198, 10, 255), outline=(80, 64, 0, 255), width=sp(0.6))

    return hi.resize((WHEEL_FRAME_W, WHEEL_FRAME_H), RESAMPLING.LANCZOS)


def extract_frame(sheet: Image.Image, frame_w: int, index: int) -> Image.Image:
    return sheet.crop((index * frame_w, 0, (index + 1) * frame_w, sheet.height))


def ensure_dirs() -> None:
    BODY_DIR.mkdir(parents=True, exist_ok=True)
    WHEEL_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    (BODY_DIR / "frames").mkdir(parents=True, exist_ok=True)
    (BODY_DIR / "underbody_frames").mkdir(parents=True, exist_ok=True)


def wheel_profile_for_yaw(yaw: float) -> str:
    ay = abs(yaw)
    if ay >= 0.85:
        return "extreme_turn"
    if ay >= 0.35:
        return "turn"
    return "straight"


def generate() -> None:
    ensure_dirs()

    body_sheet = Image.new("RGBA", (BODY_FRAME_W * len(DIRECTIONS), BODY_FRAME_H), (0, 0, 0, 0))
    underbody_sheet = Image.new("RGBA", (BODY_FRAME_W * len(DIRECTIONS), BODY_FRAME_H), (0, 0, 0, 0))

    metadata: Dict[str, object] = {
        "sprite_set": "player_racer",
        "style_version": "v2",
        "camera_view": "behind_vehicle",
        "godot_notes": {
            "body_and_wheels_are_separate": True,
            "wheel_anchor_positions_are_center_points": True,
            "all_png_backgrounds_transparent": True,
        },
        "body_frame_size": {"w": BODY_FRAME_W, "h": BODY_FRAME_H},
        "directions": [],
        "wheel_profiles_by_direction": {},
        "wheel_anchors": {},
        "wheel_animation": {
            "frame_size": {"w": WHEEL_FRAME_W, "h": WHEEL_FRAME_H},
            "frames": WHEEL_FRAMES,
            "recommended_fps": 30,
        },
    }

    body_frames: Dict[str, Image.Image] = {}
    underbody_frames: Dict[str, Image.Image] = {}

    for i, (name, yaw) in enumerate(DIRECTIONS):
        frame, anchors = draw_body_frame(yaw=yaw, underbody=False)
        body_sheet.paste(frame, (i * BODY_FRAME_W, 0))
        body_frames[name] = frame
        frame.save(BODY_DIR / "frames" / f"{name}.png")

        underbody, _ = draw_body_frame(yaw=yaw, underbody=True)
        underbody_sheet.paste(underbody, (i * BODY_FRAME_W, 0))
        underbody_frames[name] = underbody
        underbody.save(BODY_DIR / "underbody_frames" / f"{name}_underbody.png")

        profile = wheel_profile_for_yaw(yaw)
        metadata["directions"].append(name)
        metadata["wheel_profiles_by_direction"][name] = profile
        metadata["wheel_anchors"][name] = {k: [int(v[0]), int(v[1])] for k, v in anchors.items()}

    body_sheet_path = BODY_DIR / "player_racer_body_sheet.png"
    underbody_sheet_path = BODY_DIR / "player_racer_underbody_sheet.png"
    body_sheet.save(body_sheet_path)
    underbody_sheet.save(underbody_sheet_path)

    # Wheel sheets (perspective-specific profiles)
    wheel_profiles = {
        "straight": 1.0,
        "turn": 0.84,
        "extreme_turn": 0.72,
    }
    wheel_sheets: Dict[str, Image.Image] = {}
    for profile_name, squash in wheel_profiles.items():
        sheet = Image.new("RGBA", (WHEEL_FRAME_W * WHEEL_FRAMES, WHEEL_FRAME_H), (0, 0, 0, 0))
        for i in range(WHEEL_FRAMES):
            frame = draw_wheel_frame(squash=squash, spin_frame=i)
            sheet.paste(frame, (i * WHEEL_FRAME_W, 0))
        sheet.save(WHEEL_DIR / f"player_racer_wheel_spin_{profile_name}.png")
        wheel_sheets[profile_name] = sheet

    # Composite preview for quick visual alignment checks.
    preview = Image.new(
        "RGBA",
        (BODY_FRAME_W * len(DIRECTIONS), BODY_FRAME_H * 2 + 30),
        (20, 20, 24, 255),
    )
    pdraw = ImageDraw.Draw(preview, "RGBA")
    font = ImageFont.load_default()
    pdraw.text((8, 5), "Top: body + wheels | Bottom: underbody + wheels", fill=(230, 230, 236, 255), font=font)

    for i, (name, _yaw) in enumerate(DIRECTIONS):
        x = i * BODY_FRAME_W
        y_top = 18
        y_bottom = 18 + BODY_FRAME_H

        comp_top = body_frames[name].copy()
        comp_bottom = underbody_frames[name].copy()
        anchors = metadata["wheel_anchors"][name]
        profile = metadata["wheel_profiles_by_direction"][name]
        wheel_sheet = wheel_sheets[profile]
        wheel_frame = extract_frame(wheel_sheet, WHEEL_FRAME_W, (i * 3) % WHEEL_FRAMES)

        for key in ("front_left", "front_right", "rear_left", "rear_right"):
            cx, cy = anchors[key]
            px = int(cx - WHEEL_FRAME_W / 2)
            py = int(cy - WHEEL_FRAME_H / 2)
            comp_top.alpha_composite(wheel_frame, (px, py))
            comp_bottom.alpha_composite(wheel_frame, (px, py))

        preview.alpha_composite(comp_top, (x, y_top))
        preview.alpha_composite(comp_bottom, (x, y_bottom))
        pdraw.text((x + 24, BODY_FRAME_H * 2 + 10), name, fill=(214, 214, 220, 255), font=font)

    preview_path = PREVIEW_DIR / "player_racer_composite_preview.png"
    preview.save(preview_path)

    metadata["files"] = {
        "body_sheet": str(body_sheet_path.relative_to(REPO_ROOT)),
        "underbody_sheet": str(underbody_sheet_path.relative_to(REPO_ROOT)),
        "wheel_sheets": {
            k: str((WHEEL_DIR / f"player_racer_wheel_spin_{k}.png").relative_to(REPO_ROOT))
            for k in wheel_profiles
        },
        "preview": str(preview_path.relative_to(REPO_ROOT)),
    }

    metadata_path = OUT_ROOT / "player_racer_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    readme = OUT_ROOT / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Player Racer Sprite Kit",
                "",
                "Generated assets for a behind-the-car racer with transparent backgrounds.",
                "This is the v2 style pass with improved proportions and detailing.",
                "",
                "## Contents",
                "- `body/player_racer_body_sheet.png`: 9 turning directions (body only)",
                "- `body/player_racer_underbody_sheet.png`: 9 underbody turning directions",
                "- `wheels/player_racer_wheel_spin_straight.png`: 24 wheel spin frames",
                "- `wheels/player_racer_wheel_spin_turn.png`: 24 wheel spin frames (turn perspective)",
                "- `wheels/player_racer_wheel_spin_extreme_turn.png`: 24 wheel spin frames (far turn perspective)",
                "- `player_racer_metadata.json`: direction list + wheel anchor center points",
                "- `preview/player_racer_composite_preview.png`: quick visual validation",
                "",
                "## Godot integration",
                "1. Use one `Sprite2D` (or `AnimatedSprite2D`) for body, and 4 wheel `Sprite2D` children.",
                "2. Set each wheel child position from `wheel_anchors[direction]` in metadata.",
                "3. Pick wheel sheet using `wheel_profiles_by_direction[direction]`.",
                "4. Animate wheel frame independently from body turning state.",
                "5. For flip states, swap body texture to `player_racer_underbody_sheet.png`.",
                "",
                "All PNG files use transparent backgrounds for compositing/splicing.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    generate()
    print("Generated player racer sprite kit v2 in assets/sprites/player_racer")
