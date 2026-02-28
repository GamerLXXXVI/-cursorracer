# Player Racer Sprite Kit

Generated assets for a behind-the-car racer with transparent backgrounds.

## Contents
- `body/player_racer_body_sheet.png`: 9 turning directions (body only)
- `body/player_racer_underbody_sheet.png`: 9 underbody turning directions
- `wheels/player_racer_wheel_spin_straight.png`: 16 wheel spin frames
- `wheels/player_racer_wheel_spin_turn.png`: 16 wheel spin frames (turn perspective)
- `wheels/player_racer_wheel_spin_extreme_turn.png`: 16 wheel spin frames (far turn perspective)
- `player_racer_metadata.json`: direction list + wheel anchor center points
- `preview/player_racer_composite_preview.png`: quick visual validation

## Godot integration
1. Use one `Sprite2D` (or `AnimatedSprite2D`) for body, and 4 wheel `Sprite2D` children.
2. Set each wheel child position from `wheel_anchors[direction]` in metadata.
3. Pick wheel sheet using `wheel_profiles_by_direction[direction]`.
4. Animate wheel frame index independently from body turning state.
5. For flip states, switch body texture to `player_racer_underbody_sheet.png`.

All PNG files use transparent backgrounds for clean compositing/splicing.
