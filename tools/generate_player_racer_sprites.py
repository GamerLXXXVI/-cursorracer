#!/usr/bin/env python3
"""
Generate a Godot-friendly player racer sprite kit:
- Yellow sports car body sprites (rear camera, turning variants)
- Separate sport tire spin animations
- Underbody variants for flip animations
- Transparent PNGs and JSON metadata for compositing
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont


# Output layout
REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = REPO_ROOT / "assets" / "sprites" / "player_racer"
BODY_DIR = OUT_ROOT / "body"
WHEEL_DIR = OUT_ROOT / "wheels"
PREVIEW_DIR = OUT_ROOT / "preview"

# Sprite dimensions
BODY_FRAME_W = 128
BODY_FRAME_H = 128
WHEEL_FRAME_W = 36
WHEEL_FRAME_H = 36
WHEEL_FRAMES = 16

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


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def darken(rgb: Tuple[int, int, int], amount: float) -> Tuple[int, int, int]:
    amount = clamp(amount, 0.0, 1.0)
    return tuple(int(c * (1.0 - amount)) for c in rgb)


def lighten(rgb: Tuple[int, int, int], amount: float) -> Tuple[int, int, int]:
    amount = clamp(amount, 0.0, 1.0)
    return tuple(int(c + (255 - c) * amount) for c in rgb)


def body_geometry(yaw: float) -> Dict[str, float]:
    """Return interpolated body geometry based on yaw in [-1..1]."""
    cx = BODY_FRAME_W / 2
    top_shift = yaw * 18.0

    return {
        "c_spoiler": cx + top_shift * 1.06,
        "c_top": cx + top_shift,
        "c_mid": cx + top_shift * 0.65,
        "c_rear": cx + top_shift * 0.28,
        "c_bottom": cx,
        "w_top": 42 - abs(yaw) * 5,
        "w_mid": 56 - abs(yaw) * 3,
        "w_rear": 66 - abs(yaw) * 1,
        "w_bottom": 72,
        "y_spoiler": 15,
        "y_top": 26,
        "y_mid": 50,
        "y_rear": 79,
        "y_bottom": 112,
    }


def side_points(center: float, width: float, y: float) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    half = width / 2
    return (int(center - half), int(y)), (int(center + half), int(y))


def wheel_anchor_positions(g: Dict[str, float], yaw: float) -> Dict[str, Tuple[int, int]]:
    # Front/rear axle placement in rear-camera perspective
    front_y = int(lerp(g["y_mid"], g["y_rear"], 0.22))
    rear_y = int(lerp(g["y_rear"], g["y_bottom"], 0.34))

    front_center = int(lerp(g["c_mid"], g["c_rear"], 0.32) + yaw * 2.2)
    rear_center = int(lerp(g["c_rear"], g["c_bottom"], 0.6) - yaw * 1.1)

    front_track = 44 - int(abs(yaw) * 10)
    rear_track = 52 - int(abs(yaw) * 14)
    lateral_bias = int(yaw * 4)

    anchors = {
        "front_left": (front_center - front_track // 2 - lateral_bias, front_y),
        "front_right": (front_center + front_track // 2 + lateral_bias, front_y),
        "rear_left": (rear_center - rear_track // 2 - int(lateral_bias * 0.7), rear_y),
        "rear_right": (rear_center + rear_track // 2 + int(lateral_bias * 0.7), rear_y),
    }
    return anchors


def draw_wheel_wells(draw: ImageDraw.ImageDraw, anchors: Dict[str, Tuple[int, int]]) -> None:
    for _, (x, y) in anchors.items():
        box = [x - 15, y - 11, x + 15, y + 12]
        draw.ellipse(box, fill=(14, 14, 16, 175))
        draw.arc(box, start=208, end=332, fill=(80, 80, 88, 180), width=2)


def draw_body_frame(img: Image.Image, yaw: float, underbody: bool) -> Dict[str, Tuple[int, int]]:
    draw = ImageDraw.Draw(img, "RGBA")
    g = body_geometry(yaw)
    anchors = wheel_anchor_positions(g, yaw)

    l_top, r_top = side_points(g["c_top"], g["w_top"], g["y_top"])
    l_mid, r_mid = side_points(g["c_mid"], g["w_mid"], g["y_mid"])
    l_rear, r_rear = side_points(g["c_rear"], g["w_rear"], g["y_rear"])
    l_bottom, r_bottom = side_points(g["c_bottom"], g["w_bottom"], g["y_bottom"])

    body_poly = [r_top, r_mid, r_rear, r_bottom, l_bottom, l_rear, l_mid, l_top]

    if underbody:
        body_base = (62, 62, 66)
        body_outline = (18, 18, 18, 255)
        draw.polygon(body_poly, fill=body_base + (255,), outline=body_outline)

        # Mechanical details for flipped car underbody
        c_x = int(g["c_rear"])
        draw.rounded_rectangle(
            [c_x - 8, int(g["y_top"] + 8), c_x + 8, int(g["y_bottom"] - 8)],
            radius=4,
            fill=(88, 88, 92, 255),
            outline=(32, 32, 32, 255),
            width=2,
        )
        draw.rounded_rectangle(
            [c_x - 20, int(g["y_mid"] + 8), c_x + 20, int(g["y_rear"] + 8)],
            radius=5,
            fill=(76, 76, 80, 255),
            outline=(28, 28, 30, 255),
            width=2,
        )
        draw.rectangle(
            [c_x - 10, int(g["y_bottom"] - 14), c_x + 10, int(g["y_bottom"] - 6)],
            fill=(40, 40, 44, 255),
        )
        for dx in (-17, -11, 11, 17):
            draw.ellipse(
                [c_x + dx - 3, int(g["y_top"] + 25), c_x + dx + 3, int(g["y_top"] + 31)],
                fill=(95, 95, 100, 255),
            )
    else:
        yellow = (255, 212, 20)
        outline = (22, 22, 22, 255)
        draw.polygon(body_poly, fill=yellow + (255,), outline=outline)

        # Side shading to suggest yaw and volume
        center_line = [
            (int(g["c_top"]), int(g["y_top"])),
            (int(g["c_mid"]), int(g["y_mid"])),
            (int(g["c_rear"]), int(g["y_rear"])),
            (int(g["c_bottom"]), int(g["y_bottom"])),
        ]
        if yaw >= 0:
            shade_poly = [l_top, l_mid, l_rear, l_bottom] + list(reversed(center_line))
            highlight_poly = [r_top, r_mid, r_rear, r_bottom] + list(reversed(center_line))
        else:
            shade_poly = [r_top, r_mid, r_rear, r_bottom] + list(reversed(center_line))
            highlight_poly = [l_top, l_mid, l_rear, l_bottom] + list(reversed(center_line))

        draw.polygon(shade_poly, fill=darken(yellow, 0.2) + (120,))
        draw.polygon(highlight_poly, fill=lighten(yellow, 0.15) + (80,))

        # Cabin / rear glass
        c_top = int(g["c_top"] + yaw * 1.4)
        c_mid = int(g["c_mid"] + yaw * 1.2)
        c_bot = int(g["c_rear"] + yaw * 0.8)
        cabin_poly = [
            (c_top + 14, int(g["y_top"] + 10)),
            (c_mid + 16, int(g["y_mid"] + 2)),
            (c_bot + 14, int(g["y_rear"] - 4)),
            (c_bot - 14, int(g["y_rear"] - 4)),
            (c_mid - 16, int(g["y_mid"] + 2)),
            (c_top - 14, int(g["y_top"] + 10)),
        ]
        draw.polygon(cabin_poly, fill=(30, 42, 56, 245), outline=(15, 20, 28, 255))

        # Taillights
        tail_y1 = int(g["y_bottom"] - 18)
        tail_y2 = int(g["y_bottom"] - 9)
        left_tail_x = int(g["c_bottom"] - g["w_bottom"] / 2 + 8)
        right_tail_x = int(g["c_bottom"] + g["w_bottom"] / 2 - 20)
        draw.rounded_rectangle(
            [left_tail_x, tail_y1, left_tail_x + 12, tail_y2],
            radius=2,
            fill=(210, 24, 28, 255),
            outline=(70, 5, 8, 255),
        )
        draw.rounded_rectangle(
            [right_tail_x, tail_y1, right_tail_x + 12, tail_y2],
            radius=2,
            fill=(210, 24, 28, 255),
            outline=(70, 5, 8, 255),
        )

        # Rear vent
        vent_w = int(18 - abs(yaw) * 2)
        vent_cx = int(g["c_rear"])
        draw.rounded_rectangle(
            [vent_cx - vent_w, int(g["y_rear"] + 4), vent_cx + vent_w, int(g["y_rear"] + 10)],
            radius=2,
            fill=(18, 18, 20, 220),
        )

        # Thin center accent line
        draw.line(
            [
                (int(g["c_top"]), int(g["y_top"] + 6)),
                (int(g["c_mid"]), int(g["y_mid"] + 8)),
                (int(g["c_rear"]), int(g["y_rear"] + 4)),
            ],
            fill=(24, 24, 24, 175),
            width=2,
        )

    # Spoiler (black mount + yellow aerofoil with black stripe)
    spoiler_c = g["c_spoiler"]
    spoiler_y = g["y_spoiler"]
    spoiler_w = 48 - abs(yaw) * 8
    spoiler_h = 8
    sx1 = int(spoiler_c - spoiler_w / 2)
    sx2 = int(spoiler_c + spoiler_w / 2)
    sy1 = int(spoiler_y)
    sy2 = int(spoiler_y + spoiler_h)

    draw.rectangle([sx1 + 5, sy1 + 7, sx1 + 8, sy2 + 14], fill=(14, 14, 14, 255))
    draw.rectangle([sx2 - 8, sy1 + 7, sx2 - 5, sy2 + 14], fill=(14, 14, 14, 255))
    draw.rounded_rectangle([sx1, sy1, sx2, sy2], radius=2, fill=(245, 200, 18, 255), outline=(15, 15, 15, 255))
    draw.line([(sx1 + 3, (sy1 + sy2) // 2), (sx2 - 3, (sy1 + sy2) // 2)], fill=(14, 14, 14, 225), width=2)

    draw_wheel_wells(draw, anchors)
    return anchors


def draw_wheel_frame(squash: float, spin_frame: int) -> Image.Image:
    img = Image.new("RGBA", (WHEEL_FRAME_W, WHEEL_FRAME_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")

    cx, cy = WHEEL_FRAME_W // 2, WHEEL_FRAME_H // 2
    h = 30
    w = int(30 * squash)
    x1, y1 = cx - w // 2, cy - h // 2
    x2, y2 = cx + w // 2, cy + h // 2

    # Tire shell
    draw.ellipse([x1, y1, x2, y2], fill=(14, 14, 14, 255), outline=(6, 6, 6, 255), width=2)
    draw.ellipse([x1 + 3, y1 + 3, x2 - 3, y2 - 3], fill=(28, 28, 30, 255))

    # Tread hints
    phase = spin_frame * (360.0 / WHEEL_FRAMES)
    for n in range(12):
        ang = math.radians(phase + n * 30)
        px = cx + math.cos(ang) * (w * 0.42)
        py = cy + math.sin(ang) * (h * 0.42)
        qx = cx + math.cos(ang) * (w * 0.30)
        qy = cy + math.sin(ang) * (h * 0.30)
        alpha = 90 + int((math.sin(math.radians(phase + n * 30)) + 1) * 35)
        draw.line([(px, py), (qx, qy)], fill=(80, 80, 84, alpha), width=2)

    # Rim
    rim = [x1 + 8, y1 + 8, x2 - 8, y2 - 8]
    draw.ellipse(rim, fill=(166, 166, 170, 235), outline=(110, 110, 115, 255), width=1)
    draw.ellipse([rim[0] + 2, rim[1] + 2, rim[2] - 2, rim[3] - 2], fill=(64, 64, 70, 220))

    # Spokes (rotating)
    spoke_len_x = (rim[2] - rim[0]) * 0.28
    spoke_len_y = (rim[3] - rim[1]) * 0.28
    for i in range(5):
        a = math.radians(phase * 1.2 + i * 72)
        ex = cx + math.cos(a) * spoke_len_x
        ey = cy + math.sin(a) * spoke_len_y
        draw.line([(cx, cy), (ex, ey)], fill=(216, 216, 220, 220), width=2)

    # Yellow accent ring and hub
    draw.arc([x1 + 2, y1 + 2, x2 - 2, y2 - 2], start=phase - 18, end=phase + 28, fill=(255, 205, 0, 230), width=2)
    draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(242, 192, 0, 255), outline=(80, 62, 0, 255))

    return img


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
    if ay >= 0.8:
        return "extreme_turn"
    if ay >= 0.35:
        return "turn"
    return "straight"


def generate() -> None:
    ensure_dirs()

    # Body sheets and per-frame exports
    body_sheet = Image.new("RGBA", (BODY_FRAME_W * len(DIRECTIONS), BODY_FRAME_H), (0, 0, 0, 0))
    underbody_sheet = Image.new("RGBA", (BODY_FRAME_W * len(DIRECTIONS), BODY_FRAME_H), (0, 0, 0, 0))

    metadata: Dict[str, object] = {
        "sprite_set": "player_racer",
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
            "recommended_fps": 24,
        },
    }

    body_frames: Dict[str, Image.Image] = {}
    underbody_frames: Dict[str, Image.Image] = {}

    for i, (name, yaw) in enumerate(DIRECTIONS):
        frame = Image.new("RGBA", (BODY_FRAME_W, BODY_FRAME_H), (0, 0, 0, 0))
        anchors = draw_body_frame(frame, yaw=yaw, underbody=False)
        body_sheet.paste(frame, (i * BODY_FRAME_W, 0))
        body_frames[name] = frame
        frame.save(BODY_DIR / "frames" / f"{name}.png")

        uframe = Image.new("RGBA", (BODY_FRAME_W, BODY_FRAME_H), (0, 0, 0, 0))
        draw_body_frame(uframe, yaw=yaw, underbody=True)
        underbody_sheet.paste(uframe, (i * BODY_FRAME_W, 0))
        underbody_frames[name] = uframe
        uframe.save(BODY_DIR / "underbody_frames" / f"{name}_underbody.png")

        profile = wheel_profile_for_yaw(yaw)
        metadata["directions"].append(name)
        metadata["wheel_profiles_by_direction"][name] = profile
        metadata["wheel_anchors"][name] = {k: [int(v[0]), int(v[1])] for k, v in anchors.items()}

    body_sheet_path = BODY_DIR / "player_racer_body_sheet.png"
    underbody_sheet_path = BODY_DIR / "player_racer_underbody_sheet.png"
    body_sheet.save(body_sheet_path)
    underbody_sheet.save(underbody_sheet_path)

    # Wheel sheets (separate animation profiles for turn perspective)
    wheel_profiles = {
        "straight": 1.0,
        "turn": 0.84,
        "extreme_turn": 0.72,
    }
    wheel_sheets: Dict[str, Image.Image] = {}
    for profile_name, squash in wheel_profiles.items():
        sheet = Image.new("RGBA", (WHEEL_FRAME_W * WHEEL_FRAMES, WHEEL_FRAME_H), (0, 0, 0, 0))
        for i in range(WHEEL_FRAMES):
            wframe = draw_wheel_frame(squash=squash, spin_frame=i)
            sheet.paste(wframe, (i * WHEEL_FRAME_W, 0))
        sheet.save(WHEEL_DIR / f"player_racer_wheel_spin_{profile_name}.png")
        wheel_sheets[profile_name] = sheet

    # Composite preview to quickly inspect alignment
    preview = Image.new(
        "RGBA",
        (BODY_FRAME_W * len(DIRECTIONS), BODY_FRAME_H * 2 + 26),
        (26, 26, 30, 255),
    )
    draw = ImageDraw.Draw(preview, "RGBA")
    font = ImageFont.load_default()
    draw.text((8, 4), "Top row: body + wheels | Bottom row: underbody + wheels", fill=(230, 230, 235, 255), font=font)

    for i, (name, _yaw) in enumerate(DIRECTIONS):
        x = i * BODY_FRAME_W
        y_top = 16
        y_bottom = 16 + BODY_FRAME_H

        comp_top = body_frames[name].copy()
        comp_bottom = underbody_frames[name].copy()
        anchors = metadata["wheel_anchors"][name]
        profile = metadata["wheel_profiles_by_direction"][name]
        wheel_sheet = wheel_sheets[profile]
        wheel_frame = extract_frame(wheel_sheet, WHEEL_FRAME_W, (i * 2) % WHEEL_FRAMES)

        for key in ("front_left", "front_right", "rear_left", "rear_right"):
            cx, cy = anchors[key]
            px = int(cx - WHEEL_FRAME_W / 2)
            py = int(cy - WHEEL_FRAME_H / 2)
            comp_top.alpha_composite(wheel_frame, (px, py))
            comp_bottom.alpha_composite(wheel_frame, (px, py))

        preview.alpha_composite(comp_top, (x, y_top))
        preview.alpha_composite(comp_bottom, (x, y_bottom))
        draw.text((x + 20, BODY_FRAME_H * 2 + 8), name, fill=(215, 215, 220, 255), font=font)

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

    # Godot usage note
    readme = OUT_ROOT / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Player Racer Sprite Kit",
                "",
                "Generated assets for a behind-the-car racer with transparent backgrounds.",
                "",
                "## Contents",
                "- `body/player_racer_body_sheet.png`: 9 turning directions (body only)",
                "- `body/player_racer_underbody_sheet.png`: 9 underbody turning directions",
                "- `wheels/player_racer_wheel_spin_straight.png`: 16 wheel spin frames",
                "- `wheels/player_racer_wheel_spin_turn.png`: 16 wheel spin frames (turn perspective)",
                "- `wheels/player_racer_wheel_spin_extreme_turn.png`: 16 wheel spin frames (far turn perspective)",
                "- `player_racer_metadata.json`: direction list + wheel anchor center points",
                "- `preview/player_racer_composite_preview.png`: quick visual validation",
                "",
                "## Godot integration",
                "1. Use one `Sprite2D` (or `AnimatedSprite2D`) for body, and 4 wheel `Sprite2D` children.",
                "2. Set each wheel child position from `wheel_anchors[direction]` in metadata.",
                "3. Pick wheel sheet using `wheel_profiles_by_direction[direction]`.",
                "4. Animate wheel frame index independently from body turning state.",
                "5. For flip states, switch body texture to `player_racer_underbody_sheet.png`.",
                "",
                "All PNG files use transparent backgrounds for clean compositing/splicing.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    generate()
    print("Generated player racer sprite kit in assets/sprites/player_racer")
