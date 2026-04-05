# AGENTS.md

## Cursor Cloud specific instructions

### Overview

This is **Pole Position Racer** — a single-file retro arcade racing game built with Python + Pygame (~2,910 lines in `main.py`). There are no backend services, databases, APIs, or build steps.

### Running the game

```bash
export DISPLAY=:99
export SDL_AUDIODRIVER=dummy
python3 main.py
```

- **Virtual display required**: The cloud VM has no physical display. Start Xvfb first: `Xvfb :99 -screen 0 1280x720x24 &`, then set `DISPLAY=:99`.
- **Audio driver**: Set `SDL_AUDIODRIVER=dummy` to avoid ALSA errors (no sound card in the VM). The game runs fine without audio.
- The game opens a 1280x720 window. Press Enter on the intro screen, then select transmission/camera on the menu, and press Enter to start racing.

### Linting

```bash
python3 -m ruff check main.py
```

No project-level ruff/lint config exists; default rules apply and pass cleanly.

### Testing

There are no automated tests. Manual testing is done by launching the game and interacting with it via the GUI.

### Key files

| File | Purpose |
|------|---------|
| `main.py` | Entire game (single file) |
| `requirements.txt` | Single dependency: `pygame` |
| `spritesheet.png` (+ variants) | Pre-built sprite sheet assets |
| `assets/` | Duplicate sprite sheets for auto-detection |
| `leaderboard.json` | Auto-created at runtime for high scores |
| `race_debug.log` | Auto-created at runtime for telemetry |
