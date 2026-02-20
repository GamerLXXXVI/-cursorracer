# POLE POSITION RACER: LLM RACER VERSION

A retro arcade racing game inspired by classic 1980s sprite-scaling racers, built from scratch with Python + Pygame.

## Features

- Animated intro screen with blinking `PRESS ENTER TO START`
- Menu with transmission + default camera settings
- Monaco-inspired pseudo-3D circuit
- 4-lap race with 20 racers total (1 player + 19 AI)
- Quarter-mile checkpoint timer system
- Manual 7-gear transmission with RPM/redline behavior
- Automatic mode (no manual shifting, no nitro, slightly slower)
- Dynamic procedural engine audio that changes with RPM/throttle
- Turbo blow-off / backfire pops on gear shifts
- Individual AI engine voice variation
- Nitro pickup/activation (manual mode only)
- Mandatory pit stop on lap 2 with animated sequence
- Random weather each race:
  - Clear
  - Rain (activate wipers with `1`)
  - Thunderstorm (lightning flashes)
  - Fog
  - Snow (slippery traction)
  - Night (activate headlights with `H`)
- Collision system:
  - AI-player collisions
  - AI-AI collisions
  - Off-track sign impacts and explosion/respawn
  - 3 crashes = eliminated -> spectator mode -> DNF
- Mini-map with racer markers and AI finish-time feed
- End-of-race order/lap times/total time
- Winner name entry + best-lap leaderboard persistence (`leaderboard.json`)
- 20 unique randomized car liveries every race
- Parallax background with arcade city + amusement park motion

## Requirements

- Python 3.10+ (tested with 3.12)
- `pygame`

Install:

```bash
python3 -m pip install -r requirements.txt
```

## Run

```bash
python3 main.py
```

## Controls

### Driving

- `W` / `Up Arrow` - Accelerate
- `S` / `Down Arrow` - Brake
- `A` / `Left Arrow` - Steer Left
- `D` / `Right Arrow` - Steer Right

### Transmission

- `Left Shift` - Shift Up (manual)
- `Right Shift` - Shift Down (manual)

### Systems

- `Insert` - Activate Nitro (manual mode only)
- `Space` - Enter pit lane (lap 2 mandatory pit window)
- `C` - Toggle camera (chase / rear / bumper)
- `T` - Toggle traction control assist
- `1` - Toggle wipers during rain/thunderstorm
- `H` - Toggle headlights during night weather
- `Esc` - Back to menu / quit from menu

## Notes

- This project uses procedural visuals and synthesized retro-style tones (no external sprite/audio packs).
- The game targets smooth 60 FPS on typical desktop hardware.
