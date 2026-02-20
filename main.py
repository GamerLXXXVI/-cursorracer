import json
import math
import os
import random
import sys
import colorsys
from array import array
from dataclasses import dataclass

import pygame


WIDTH = 1280
HEIGHT = 720
FPS = 60

TRACK_LENGTH_M = 3337.0
TOTAL_LAPS = 4
TOTAL_RACERS = 20
CHECKPOINT_DISTANCE_M = 402.336  # quarter mile

PLAYER_START_TIME = 60.0
CHECKPOINT_TIME_BONUS = 30.0

SPRITE_SHEET_CANDIDATES = [
    "spritesheet.png",
    "car_spritesheet.png",
    "pole_position_spritesheet.png",
    "assets/spritesheet.png",
    "assets/car_spritesheet.png",
    "assets/pole_position_spritesheet.png",
]


def clamp(value, low, high):
    return max(low, min(high, value))


def lerp(a, b, t):
    return a + (b - a) * t


def signed_track_delta(target_distance, source_distance, track_length):
    delta = (target_distance - source_distance) % track_length
    if delta > track_length * 0.5:
        delta -= track_length
    return delta


def format_time(seconds):
    if seconds is None or seconds == float("inf"):
        return "--:--.--"
    minutes = int(seconds // 60)
    remainder = seconds - minutes * 60
    return f"{minutes:02d}:{remainder:05.2f}"


def generate_unique_palette(count):
    start_hue = random.random()
    hues = [((start_hue + i * 0.61803398875) % 1.0) for i in range(count)]
    random.shuffle(hues)
    palette = []
    for hue in hues:
        sat = random.uniform(0.68, 0.95)
        val = random.uniform(0.76, 1.00)
        r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
        palette.append((int(r * 255), int(g * 255), int(b * 255)))
    return palette


class SpriteBank:
    loaded = False
    loaded_path = None
    car_frames = []
    explosion_frames = []
    background_key = (0, 0, 0)

    @classmethod
    def _is_bg_like(cls, rgb, bg_rgb):
        diff = abs(rgb[0] - bg_rgb[0]) + abs(rgb[1] - bg_rgb[1]) + abs(rgb[2] - bg_rgb[2])
        return diff <= 36

    @classmethod
    def _extract_blobs(cls, surface, bg_rgb):
        width, height = surface.get_size()
        visited = bytearray(width * height)
        boxes = []
        min_area = 64

        for y in range(height):
            for x in range(width):
                idx = y * width + x
                if visited[idx]:
                    continue
                color = surface.get_at((x, y))
                if color.a < 10 or cls._is_bg_like(color[:3], bg_rgb):
                    visited[idx] = 1
                    continue

                stack = [(x, y)]
                visited[idx] = 1
                min_x = x
                max_x = x
                min_y = y
                max_y = y
                area = 0

                while stack:
                    cx, cy = stack.pop()
                    area += 1
                    if cx < min_x:
                        min_x = cx
                    if cx > max_x:
                        max_x = cx
                    if cy < min_y:
                        min_y = cy
                    if cy > max_y:
                        max_y = cy

                    for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                        if nx < 0 or ny < 0 or nx >= width or ny >= height:
                            continue
                        nidx = ny * width + nx
                        if visited[nidx]:
                            continue
                        ncolor = surface.get_at((nx, ny))
                        if ncolor.a < 10 or cls._is_bg_like(ncolor[:3], bg_rgb):
                            visited[nidx] = 1
                            continue
                        visited[nidx] = 1
                        stack.append((nx, ny))

                if area >= min_area:
                    boxes.append((min_x, min_y, max_x, max_y, area))

        boxes.sort(key=lambda box: (box[1], box[0]))
        return boxes

    @classmethod
    def _crop_box(cls, surface, box, pad=1):
        width, height = surface.get_size()
        min_x, min_y, max_x, max_y, _ = box
        x = max(0, min_x - pad)
        y = max(0, min_y - pad)
        w = min(width - x, (max_x - min_x + 1) + pad * 2)
        h = min(height - y, (max_y - min_y + 1) + pad * 2)
        rect = pygame.Rect(x, y, w, h)
        sprite = pygame.Surface(rect.size, pygame.SRCALPHA)
        sprite.blit(surface, (0, 0), rect)
        return sprite

    @classmethod
    def load_optional_sheet(cls):
        if cls.loaded:
            return
        cls.loaded = True

        root = os.path.dirname(__file__)
        for rel_path in SPRITE_SHEET_CANDIDATES:
            path = os.path.join(root, rel_path)
            if not os.path.exists(path):
                continue
            try:
                sheet = pygame.image.load(path).convert_alpha()
            except pygame.error:
                continue

            bg = sheet.get_at((0, 0))[:3]
            cls.background_key = bg
            boxes = cls._extract_blobs(sheet, bg)
            if not boxes:
                continue

            width, height = sheet.get_size()
            car_boxes = []
            explosion_boxes = []
            for box in boxes:
                min_x, min_y, max_x, max_y, area = box
                bw = max_x - min_x + 1
                bh = max_y - min_y + 1
                if min_y <= int(height * 0.76) and 18 <= bw <= 120 and 10 <= bh <= 72 and area >= 120:
                    car_boxes.append(box)
                if min_y >= int(height * 0.54) and area >= 180:
                    explosion_boxes.append(box)

            car_boxes.sort(key=lambda box: (box[1], box[0]))
            explosion_boxes.sort(key=lambda box: (box[0], box[1]))
            cls.car_frames = [cls._crop_box(sheet, box) for box in car_boxes[:40]]
            cls.explosion_frames = [cls._crop_box(sheet, box, pad=2) for box in explosion_boxes[:16]]
            cls.loaded_path = path
            if cls.car_frames:
                return

    @classmethod
    def pick_car_frame(cls, index):
        if not cls.car_frames:
            return None
        return cls.car_frames[index % len(cls.car_frames)]


class SynthAudio:
    def __init__(self):
        self.enabled = True
        self.music_channel = None
        self.sfx_channel = None
        self.engine_channel = None
        self.ai_engine_channel = None
        self.menu_loop = None
        self.race_loop = None
        self.engine_voice_tables = []
        self.player_engine_index = -1
        self.player_engine_voice = 0
        self.ai_engine_index = -1
        self.ai_engine_voice = 0
        self.beep_low = None
        self.beep_mid = None
        self.beep_high = None
        self.crash = None
        self.checkpoint = None
        self.nitro = None
        self.pit = None
        self.shift = None
        self.shift_pop = None
        self.backfire = None

        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            self.music_channel = pygame.mixer.Channel(0)
            self.sfx_channel = pygame.mixer.Channel(1)
            self.engine_channel = pygame.mixer.Channel(2)
            self.ai_engine_channel = pygame.mixer.Channel(3)
            self._build_sounds()
        except pygame.error:
            self.enabled = False

    def _tone(self, frequency, duration, volume=0.4, wave="sine"):
        if not self.enabled:
            return None
        sample_rate = 22050
        sample_count = int(sample_rate * duration)
        buffer = array("h")
        for i in range(sample_count):
            t = i / sample_rate
            if wave == "square":
                value = 1.0 if math.sin(2.0 * math.pi * frequency * t) >= 0 else -1.0
            elif wave == "saw":
                value = (2.0 * ((t * frequency) % 1.0)) - 1.0
            else:
                value = math.sin(2.0 * math.pi * frequency * t)
            buffer.append(int(32767 * volume * value))
        return pygame.mixer.Sound(buffer=buffer.tobytes())

    def _sequence(self, notes, step=0.26, volume=0.18):
        sample_rate = 22050
        buffer = array("h")
        for note_idx, freq in enumerate(notes):
            sample_count = int(sample_rate * step)
            for i in range(sample_count):
                t = i / sample_rate
                base = math.sin(2.0 * math.pi * freq * t)
                overtone = math.sin(2.0 * math.pi * (freq * 2.0) * t + note_idx * 0.3) * 0.40
                sub = math.sin(2.0 * math.pi * (freq * 0.5) * t) * 0.34
                pulse = 1.0 if math.sin(2.0 * math.pi * (freq * 0.25) * t) > 0 else -1.0
                attack = clamp(i / max(1, int(sample_count * 0.14)), 0.0, 1.0)
                release = clamp((sample_count - i) / max(1, int(sample_count * 0.22)), 0.0, 1.0)
                envelope = min(attack, release)
                value = (base * 0.50 + overtone * 0.28 + sub * 0.18 + pulse * 0.04) * volume * envelope
                buffer.append(int(32767 * value))
        return pygame.mixer.Sound(buffer=buffer.tobytes())

    def _noise(self, duration=0.5, volume=0.45):
        sample_rate = 22050
        sample_count = int(sample_rate * duration)
        buffer = array("h")
        for _ in range(sample_count):
            v = random.uniform(-1.0, 1.0) * volume
            buffer.append(int(32767 * v))
        return pygame.mixer.Sound(buffer=buffer.tobytes())

    def _engine_layer(self, base_hz, duration=0.22, detune=1.0, grit=0.20, pulse=0.08):
        sample_rate = 22050
        sample_count = int(sample_rate * duration)
        buffer = array("h")
        for i in range(sample_count):
            t = i / sample_rate
            hz = base_hz * detune
            fundamental = math.sin(2.0 * math.pi * hz * t)
            harmonic2 = math.sin(2.0 * math.pi * hz * 2.02 * t + 0.35) * 0.55
            harmonic3 = math.sin(2.0 * math.pi * hz * 3.07 * t + 0.62) * 0.34
            rasp = ((2.0 * ((t * hz * 1.02) % 1.0)) - 1.0) * grit
            jitter = math.sin(2.0 * math.pi * (hz * 0.12) * t) * pulse
            turbulence = math.sin(2.0 * math.pi * hz * 6.4 * t + math.sin(t * 24.0)) * 0.08
            value = (fundamental * 0.45 + harmonic2 + harmonic3 + rasp + jitter + turbulence) * 0.37
            value = clamp(value, -1.0, 1.0)
            buffer.append(int(32767 * value))
        return pygame.mixer.Sound(buffer=buffer.tobytes())

    def _engine_voice_table(self, voice_idx, layers=18):
        detune = 0.92 + voice_idx * 0.035
        grit = 0.16 + (voice_idx % 4) * 0.03
        pulse = 0.06 + (voice_idx % 3) * 0.02
        return [self._engine_layer(42.0 + i * 8.2, detune=detune, grit=grit, pulse=pulse) for i in range(layers)]

    def _build_sounds(self):
        self.beep_low = self._tone(520, 0.10, 0.45, "square")
        self.beep_mid = self._tone(660, 0.10, 0.42, "square")
        self.beep_high = self._tone(960, 0.16, 0.50, "square")
        self.crash = self._noise(0.6, 0.5)
        self.checkpoint = self._tone(820, 0.12, 0.4, "sine")
        self.nitro = self._tone(320, 0.22, 0.45, "saw")
        self.pit = self._tone(420, 0.18, 0.30, "square")
        self.shift = self._tone(700, 0.06, 0.25, "sine")
        self.shift_pop = self._tone(1120, 0.08, 0.26, "saw")
        self.backfire = self._noise(0.12, 0.32)

        self.menu_loop = self._sequence([130, 196, 220, 175, 147, 220, 247, 196], step=0.24, volume=0.16)
        self.race_loop = self._sequence([110, 147, 131, 165, 147, 196, 165, 131], step=0.30, volume=0.11)
        self.engine_voice_tables = [self._engine_voice_table(idx) for idx in range(8)]

    def play_menu_music(self):
        if self.enabled and self.menu_loop:
            self.music_channel.set_volume(0.34)
            self.music_channel.play(self.menu_loop, loops=-1)
        self.stop_engine()

    def play_race_music(self):
        if self.enabled and self.race_loop:
            self.music_channel.set_volume(0.16)
            self.music_channel.play(self.race_loop, loops=-1)

    def stop_music(self):
        if self.enabled and self.music_channel:
            self.music_channel.stop()

    def stop_engine(self):
        if not self.enabled or not self.engine_channel:
            return
        self.engine_channel.fadeout(100)
        self.player_engine_index = -1
        if self.ai_engine_channel:
            self.ai_engine_channel.fadeout(100)
        self.ai_engine_index = -1

    def _update_engine_channel(self, channel, rpm, throttle, active, crashed, voice_id, state_prefix):
        tables = self.engine_voice_tables
        if not tables:
            return
        table = tables[voice_id % len(tables)]
        index_attr = f"{state_prefix}_engine_index"
        voice_attr = f"{state_prefix}_engine_voice"
        current_index = getattr(self, index_attr)
        current_voice = getattr(self, voice_attr)

        if not active:
            if channel and channel.get_busy():
                channel.fadeout(120)
            setattr(self, index_attr, -1)
            return

        rpm_ratio = clamp(rpm / 9800.0, 0.0, 1.35)
        idx = int((rpm_ratio / 1.35) * (len(table) - 1))
        if throttle:
            idx = min(len(table) - 1, idx + 1)
        if crashed:
            idx = max(0, idx - 4)

        if idx != current_index or voice_id != current_voice or not channel.get_busy():
            channel.play(table[idx], loops=-1, fade_ms=80)
            setattr(self, index_attr, idx)
            setattr(self, voice_attr, voice_id)

        volume = 0.16 + rpm_ratio * 0.58 + (0.10 if throttle else 0.0)
        if crashed:
            volume *= 0.55
        channel.set_volume(clamp(volume, 0.08, 0.90))

    def update_engine(self, rpm, throttle=False, active=True, crashed=False, voice_id=0):
        if not self.enabled or not self.engine_channel or not self.engine_voice_tables:
            return
        self._update_engine_channel(self.engine_channel, rpm, throttle, active, crashed, voice_id, "player")

    def update_ai_engine(self, rpm, throttle=False, active=True, voice_id=1, proximity=1.0):
        if not self.enabled or not self.ai_engine_channel or not self.engine_voice_tables:
            return
        self._update_engine_channel(self.ai_engine_channel, rpm, throttle, active, False, voice_id, "ai")
        self.ai_engine_channel.set_volume(clamp(0.05 + proximity * 0.35, 0.05, 0.42))

    def play_countdown_beep(self, stage):
        if not self.enabled:
            return
        if stage == 3:
            self.sfx_channel.play(self.beep_low)
        elif stage == 2:
            self.sfx_channel.play(self.beep_mid)
        else:
            self.sfx_channel.play(self.beep_high)

    def play_go(self):
        if self.enabled:
            self.sfx_channel.play(self.beep_high)

    def play_crash(self):
        if self.enabled:
            self.sfx_channel.play(self.crash)

    def play_checkpoint(self):
        if self.enabled:
            self.sfx_channel.play(self.checkpoint)

    def play_nitro(self):
        if self.enabled:
            self.sfx_channel.play(self.nitro)

    def play_pit(self):
        if self.enabled:
            self.sfx_channel.play(self.pit)

    def play_shift(self):
        if self.enabled:
            self.sfx_channel.play(self.shift)

    def play_shift_pop(self):
        if self.enabled:
            self.sfx_channel.play(self.shift_pop)

    def play_backfire(self):
        if not self.enabled:
            return
        self.sfx_channel.play(self.backfire)


class Camera:
    MODES = ["CHASE", "REAR", "BUMPER"]

    def __init__(self, start_mode="CHASE"):
        self.mode_index = 0
        if start_mode in self.MODES:
            self.mode_index = self.MODES.index(start_mode)

    @property
    def mode(self):
        return self.MODES[self.mode_index]

    def toggle(self):
        self.mode_index = (self.mode_index + 1) % len(self.MODES)


class Weather:
    TYPES = ["CLEAR", "RAIN", "THUNDERSTORM", "FOG", "SNOW", "NIGHT"]

    def __init__(self, weather_type=None):
        self.name = weather_type or random.choice(self.TYPES)
        self.lightning_timer = random.uniform(2.0, 5.0)
        self.lightning_flash_timer = 0.0
        self.particles = []
        self.wiper_anim = 0.0
        self._build_particles()

    @property
    def traction(self):
        if self.name == "RAIN":
            return 0.86
        if self.name == "THUNDERSTORM":
            return 0.80
        if self.name == "SNOW":
            return 0.73
        return 1.0

    @property
    def steer_response(self):
        if self.name == "SNOW":
            return 0.80
        if self.name in ("RAIN", "THUNDERSTORM"):
            return 0.90
        return 1.0

    @property
    def visibility_distance(self):
        if self.name == "FOG":
            return 290.0
        if self.name == "NIGHT":
            return 330.0
        if self.name == "THUNDERSTORM":
            return 340.0
        return 420.0

    @property
    def ai_speed_factor(self):
        if self.name == "SNOW":
            return 0.88
        if self.name in ("RAIN", "THUNDERSTORM"):
            return 0.92
        if self.name == "FOG":
            return 0.93
        return 1.0

    @property
    def requires_wipers(self):
        return self.name in ("RAIN", "THUNDERSTORM")

    @property
    def requires_headlights(self):
        return self.name == "NIGHT"

    def _build_particles(self):
        self.particles.clear()
        if self.name in ("RAIN", "THUNDERSTORM"):
            for _ in range(180):
                self.particles.append(
                    [
                        random.uniform(0, WIDTH),
                        random.uniform(0, HEIGHT),
                        random.uniform(240, 420),
                    ]
                )
        elif self.name == "SNOW":
            for _ in range(160):
                self.particles.append(
                    [
                        random.uniform(0, WIDTH),
                        random.uniform(0, HEIGHT),
                        random.uniform(30, 90),
                    ]
                )

    def update(self, dt):
        if self.name == "THUNDERSTORM":
            self.lightning_timer -= dt
            if self.lightning_timer <= 0:
                self.lightning_flash_timer = random.uniform(0.08, 0.20)
                self.lightning_timer = random.uniform(2.2, 5.0)
        if self.lightning_flash_timer > 0:
            self.lightning_flash_timer -= dt

        if self.name in ("RAIN", "THUNDERSTORM", "SNOW"):
            for p in self.particles:
                p[1] += p[2] * dt
                if self.name in ("RAIN", "THUNDERSTORM"):
                    p[0] += p[2] * 0.18 * dt
                else:
                    p[0] += math.sin(p[1] * 0.012) * 24 * dt
                if p[1] > HEIGHT:
                    p[0] = random.uniform(0, WIDTH)
                    p[1] = random.uniform(-20, -2)

    def draw_particles(self, screen):
        if self.name in ("RAIN", "THUNDERSTORM"):
            for x, y, speed in self.particles:
                end_x = x - 2
                end_y = y + 8
                pygame.draw.line(screen, (140, 190, 255), (x, y), (end_x, end_y), 1)
        elif self.name == "SNOW":
            for x, y, _ in self.particles:
                pygame.draw.circle(screen, (232, 242, 255), (int(x), int(y)), 2)

    def draw_visibility_overlay(self, screen, wipers_on, headlights_on):
        if self.name == "FOG":
            fog = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            fog.fill((188, 198, 206, 60))
            screen.blit(fog, (0, 0))

        if self.requires_wipers and not wipers_on:
            wet = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            wet.fill((36, 56, 98, 92))
            for i in range(0, WIDTH, 26):
                pygame.draw.line(wet, (150, 182, 236, 70), (i, 0), (i - 140, HEIGHT), 2)
            screen.blit(wet, (0, 0))
        elif self.requires_wipers and wipers_on:
            self.wiper_anim += 0.14
            offset = int(math.sin(self.wiper_anim) * 130)
            wiper = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.line(wiper, (15, 25, 35, 140), (WIDTH // 2 + offset, HEIGHT), (WIDTH // 2 - 140, HEIGHT // 2), 8)
            pygame.draw.line(wiper, (15, 25, 35, 140), (WIDTH // 2 - offset, HEIGHT), (WIDTH // 2 + 140, HEIGHT // 2), 8)
            screen.blit(wiper, (0, 0))

        if self.requires_headlights:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 170))
            if headlights_on:
                beam = [(WIDTH // 2, HEIGHT - 10), (int(WIDTH * 0.24), int(HEIGHT * 0.40)), (int(WIDTH * 0.76), int(HEIGHT * 0.40))]
                pygame.draw.polygon(overlay, (0, 0, 0, 0), beam)
            else:
                pygame.draw.circle(overlay, (0, 0, 0, 0), (WIDTH // 2, HEIGHT - 70), 80)
            screen.blit(overlay, (0, 0))

        if self.lightning_flash_timer > 0:
            flash_alpha = int(240 * (self.lightning_flash_timer / 0.2))
            flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            flash.fill((245, 250, 255, clamp(flash_alpha, 0, 180)))
            screen.blit(flash, (0, 0))


@dataclass
class TrackSegment:
    length: float
    curve: float


class Track:
    def __init__(self):
        self.length = TRACK_LENGTH_M
        self.checkpoint_distance = CHECKPOINT_DISTANCE_M
        self.segments = self._build_monaco_profile()
        self.segment_starts = []
        self.loop_offset = 0.0
        self._precompute_offsets()

        self.pit_entry_start = 145.0
        self.pit_entry_end = 265.0

        self.billboard_slogans = [
            "BULLFIRE ENERGY",
            "BYTE BOLT DRINK",
            "NEON CAFE",
            "BRAIN FUEL MAX",
            "PIXEL POWER",
            "TURBO TONIC",
        ]
        self.roadside_objects = self._generate_roadside_objects()
        self.sign_positions = self._generate_sign_positions()

        self.nitro_pickups = {}
        self.nitro_collected_laps = set()
        self.regenerate_nitro_pickups()

        self.map_path = [
            (0.11, 0.77),
            (0.19, 0.61),
            (0.34, 0.56),
            (0.45, 0.40),
            (0.64, 0.34),
            (0.78, 0.44),
            (0.86, 0.62),
            (0.76, 0.79),
            (0.60, 0.84),
            (0.52, 0.69),
            (0.38, 0.70),
            (0.29, 0.83),
            (0.16, 0.88),
            (0.11, 0.77),
        ]
        self._precompute_map_lengths()
        self.billboard_font = pygame.font.Font(None, 16)
        self.parallax_span = 3600
        self.city_blocks = self._generate_city_blocks()
        self.amusement_items = self._generate_amusement_items()

    def _build_monaco_profile(self):
        blueprint = [
            (190, 0.00),
            (110, 0.26),
            (90, 0.58),
            (160, 0.18),
            (120, -0.25),
            (95, -0.48),
            (140, -0.16),
            (120, 0.10),
            (130, 0.36),
            (95, 0.52),
            (130, 0.06),
            (170, -0.16),
            (140, -0.42),
            (110, -0.52),
            (190, -0.08),
            (170, 0.00),
            (145, 0.22),
            (110, 0.42),
            (90, 0.22),
            (120, -0.35),
            (130, -0.52),
            (90, -0.18),
            (150, 0.10),
            (170, 0.28),
            (100, 0.44),
            (140, 0.16),
            (140, -0.12),
            (150, -0.24),
            (115, -0.42),
            (120, -0.22),
            (130, 0.08),
            (190, 0.18),
            (140, 0.28),
            (130, 0.12),
            (190, -0.08),
            (210, 0.00),
        ]

        total = sum(length for length, _ in blueprint)
        scale = self.length / total
        return [TrackSegment(length * scale, curve) for length, curve in blueprint]

    def _precompute_offsets(self):
        self.segment_starts.clear()
        cumulative_length = 0.0
        cumulative_offset = 0.0
        for segment in self.segments:
            self.segment_starts.append((cumulative_length, cumulative_offset, segment.length, segment.curve))
            cumulative_offset += segment.curve * segment.length * 0.33
            cumulative_length += segment.length
        self.loop_offset = cumulative_offset

    def _precompute_map_lengths(self):
        self.map_lengths = [0.0]
        total = 0.0
        for i in range(len(self.map_path) - 1):
            x1, y1 = self.map_path[i]
            x2, y2 = self.map_path[i + 1]
            total += math.hypot(x2 - x1, y2 - y1)
            self.map_lengths.append(total)
        self.map_total_length = total

    def _generate_city_blocks(self):
        blocks = []
        x = -220
        while x < self.parallax_span + 260:
            w = random.randint(40, 96)
            h = random.randint(45, 130)
            blocks.append((x, w, h, random.randint(3, 8)))
            x += random.randint(46, 104)
        return blocks

    def _generate_amusement_items(self):
        items = []
        for _ in range(8):
            items.append(("FERRIS", random.randint(-260, self.parallax_span + 260), random.randint(90, 130)))
        for _ in range(10):
            items.append(("COASTER", random.randint(-260, self.parallax_span + 260), random.randint(110, 150)))
        for _ in range(10):
            items.append(("TOWER", random.randint(-260, self.parallax_span + 260), random.randint(90, 135)))
        return items

    def map_point(self, fraction):
        if self.map_total_length <= 0:
            return self.map_path[0]
        fraction %= 1.0
        target = fraction * self.map_total_length
        for i in range(len(self.map_path) - 1):
            start_len = self.map_lengths[i]
            end_len = self.map_lengths[i + 1]
            if start_len <= target <= end_len:
                t = 0.0 if end_len == start_len else (target - start_len) / (end_len - start_len)
                x1, y1 = self.map_path[i]
                x2, y2 = self.map_path[i + 1]
                return (lerp(x1, x2, t), lerp(y1, y2, t))
        return self.map_path[-1]

    def regenerate_nitro_pickups(self):
        self.nitro_pickups = {}
        self.nitro_collected_laps = set()
        for lap in range(1, TOTAL_LAPS + 1):
            self.nitro_pickups[lap] = random.uniform(220.0, self.length - 140.0)

    def _generate_roadside_objects(self):
        objects = []
        distance = 75.0
        while distance < self.length:
            side = -1 if random.random() < 0.5 else 1
            kind_roll = random.random()
            if kind_roll < 0.58:
                kind = "PALM"
                text = ""
            else:
                kind = "BILLBOARD"
                text = random.choice(self.billboard_slogans)
            objects.append({"distance": distance, "side": side, "kind": kind, "text": text})
            distance += random.uniform(76.0, 126.0)
        return objects

    def _generate_sign_positions(self):
        signs = []
        d = 120.0
        while d < self.length:
            signs.append((d, random.choice([-1, 1])))
            d += random.uniform(95.0, 155.0)
        return signs

    def segment_index_at(self, distance):
        distance %= self.length
        for idx, (start, _, seg_len, _) in enumerate(self.segment_starts):
            if start <= distance < start + seg_len:
                return idx
        return len(self.segment_starts) - 1

    def curvature_at(self, distance):
        distance %= self.length
        for start, _, seg_len, curve in self.segment_starts:
            if start <= distance < start + seg_len:
                return curve
        return 0.0

    def offset_at(self, distance):
        loops = math.floor(distance / self.length)
        distance %= self.length
        offset = loops * self.loop_offset
        for start, base_offset, seg_len, curve in self.segment_starts:
            end = start + seg_len
            if distance >= end:
                continue
            if distance <= start:
                offset += base_offset
            else:
                offset += base_offset + curve * (distance - start) * 0.33
            return offset
        return offset + self.segment_starts[-1][1]

    def build_projection(self, camera_mode, anchor_distance, anchor_lane, weather):
        reverse = camera_mode == "REAR"
        direction = -1.0 if reverse else 1.0

        horizon = 170 if camera_mode != "BUMPER" else 210
        lookahead = weather.visibility_distance
        if camera_mode == "BUMPER":
            lookahead *= 0.88
        if reverse:
            lookahead *= 0.80

        rows = 120
        bands = []
        anchor_offset = self.offset_at(anchor_distance)
        for i in range(rows):
            t_far = i / rows
            t_near = (i + 1) / rows

            ahead_far = lookahead * ((1.0 - t_far) ** 2)
            ahead_near = lookahead * ((1.0 - t_near) ** 2)

            y_far = horizon + (t_far ** 1.46) * (HEIGHT - horizon)
            y_near = horizon + (t_near ** 1.46) * (HEIGHT - horizon)

            half_far = lerp(52, 530, t_far)
            half_near = lerp(52, 530, t_near)

            distance_far = anchor_distance + direction * ahead_far
            distance_near = anchor_distance + direction * ahead_near

            shift_far = (self.offset_at(distance_far) - anchor_offset) * 1.24
            shift_near = (self.offset_at(distance_near) - anchor_offset) * 1.24

            lane_push_far = anchor_lane * half_far * 0.94
            lane_push_near = anchor_lane * half_near * 0.94

            if reverse:
                center_far = WIDTH * 0.5 + shift_far + lane_push_far
                center_near = WIDTH * 0.5 + shift_near + lane_push_near
            else:
                center_far = WIDTH * 0.5 - shift_far - lane_push_far
                center_near = WIDTH * 0.5 - shift_near - lane_push_near

            seg_idx = self.segment_index_at(distance_near)
            bands.append(
                {
                    "t_far": t_far,
                    "t_near": t_near,
                    "y_far": y_far,
                    "y_near": y_near,
                    "half_far": half_far,
                    "half_near": half_near,
                    "center_far": center_far,
                    "center_near": center_near,
                    "ahead_far": ahead_far,
                    "ahead_near": ahead_near,
                    "segment_index": seg_idx,
                }
            )
        return bands

    def project_from_bands(self, view_delta, lane, bands):
        for band in bands:
            near_d = band["ahead_near"]
            far_d = band["ahead_far"]
            if near_d <= view_delta <= far_d:
                span = max(far_d - near_d, 0.0001)
                u = (view_delta - near_d) / span
                center = lerp(band["center_near"], band["center_far"], u)
                half = lerp(band["half_near"], band["half_far"], u)
                y = lerp(band["y_near"], band["y_far"], u)
                x = center + lane * half * 0.92
                scale = clamp((HEIGHT - y) / (HEIGHT - 120.0), 0.06, 2.4)
                return x, y, scale
        return None

    def _wrap_parallax_x(self, x):
        span = self.parallax_span
        wrapped = ((x + span * 0.5) % span) - span * 0.5
        return int(wrapped + WIDTH * 0.5)

    def _draw_city_layer(self, screen, shift, weather):
        for base_x, width, height, windows in self.city_blocks:
            px = self._wrap_parallax_x(base_x + shift)
            y = 220 - height
            if px < -width - 20 or px > WIDTH + 20:
                continue
            color = (32, 56, 92) if weather.name != "NIGHT" else (24, 36, 70)
            pygame.draw.rect(screen, color, (px, y, width, height))
            for w in range(windows):
                wx = px + 6 + (w % 4) * 12
                wy = y + 8 + (w // 4) * 14
                if wx + 6 < px + width - 3 and wy + 5 < y + height - 3:
                    win_color = (238, 242, 188) if weather.name == "NIGHT" else (88, 136, 196)
                    pygame.draw.rect(screen, win_color, (wx, wy, 6, 5))

    def _draw_amusement_layer(self, screen, shift, race_time):
        for kind, base_x, base_y in self.amusement_items:
            px = self._wrap_parallax_x(base_x + shift)
            if kind == "FERRIS":
                radius = 30
                center = (px, base_y)
                pygame.draw.circle(screen, (228, 240, 255), center, radius, 2)
                for i in range(8):
                    angle = race_time * 0.6 + i * (math.pi / 4)
                    rx = int(center[0] + math.cos(angle) * radius)
                    ry = int(center[1] + math.sin(angle) * radius)
                    pygame.draw.line(screen, (228, 240, 255), center, (rx, ry), 1)
                    pygame.draw.circle(screen, (255, 210, 120), (rx, ry), 3)
                pygame.draw.line(screen, (190, 210, 226), (px - 20, base_y + 34), (px, base_y), 2)
                pygame.draw.line(screen, (190, 210, 226), (px + 20, base_y + 34), (px, base_y), 2)
            elif kind == "COASTER":
                points = []
                for step in range(-80, 81, 16):
                    points.append((px + step, base_y + int(math.sin((step + race_time * 70) * 0.03) * 14)))
                if len(points) >= 2:
                    pygame.draw.lines(screen, (220, 108, 128), False, points, 2)
            else:
                tower_h = 44
                pygame.draw.rect(screen, (220, 236, 252), (px - 4, base_y - tower_h, 8, tower_h))
                pygame.draw.polygon(screen, (255, 120, 90), [(px - 10, base_y - tower_h), (px + 10, base_y - tower_h), (px, base_y - tower_h - 16)])

    def draw_background(self, screen, weather, race_time, parallax_shift=0.0, speed_factor=0.0):
        if weather.name == "NIGHT":
            top = (16, 22, 52)
            bottom = (42, 70, 150)
        else:
            top = (20, 110, 235)
            bottom = (70, 168, 255)

        for y in range(0, 220, 2):
            t = y / 220.0
            color = (
                int(lerp(top[0], bottom[0], t)),
                int(lerp(top[1], bottom[1], t)),
                int(lerp(top[2], bottom[2], t)),
            )
            pygame.draw.line(screen, color, (0, y), (WIDTH, y), 2)

        pygame.draw.rect(screen, (48, 160, 36), (0, 220, WIDTH, HEIGHT - 220))

        skyline_shift = parallax_shift * 0.22 + speed_factor * 0.018
        amuse_shift = parallax_shift * 0.34 + speed_factor * 0.028
        landmark_shift = parallax_shift * 0.28 + speed_factor * 0.020

        self._draw_city_layer(screen, skyline_shift, weather)
        self._draw_amusement_layer(screen, amuse_shift, race_time)

        mountain_color = (65, 82, 84)
        hill_points = [(0, 220)]
        for x in range(0, WIDTH + 1, 90):
            y = 220 - 12 - int(math.sin(x * 0.016 + race_time * 0.2) * 8) - int((math.sin(x * 0.071) + 1.0) * 3.5)
            hill_points.append((x, y))
        hill_points.append((WIDTH, 220))
        pygame.draw.polygon(screen, mountain_color, hill_points)

        self._draw_landmarks(screen, landmark_shift)

    def _draw_landmarks(self, screen, shift):
        silhouette = (20, 42, 70)
        base_y = 210

        # Statue silhouette
        x = self._wrap_parallax_x(shift + 120)
        pygame.draw.rect(screen, silhouette, (x, base_y - 45, 18, 45))
        pygame.draw.polygon(screen, silhouette, [(x + 9, base_y - 72), (x + 2, base_y - 45), (x + 16, base_y - 45)])
        pygame.draw.rect(screen, silhouette, (x - 8, base_y - 18, 34, 18))

        # Leaning tower
        x = self._wrap_parallax_x(shift + 540)
        pygame.draw.polygon(screen, silhouette, [(x, base_y), (x + 20, base_y), (x + 34, base_y - 82), (x + 14, base_y - 82)])
        for i in range(5):
            pygame.draw.line(screen, (34, 58, 92), (x + 8, base_y - 12 - i * 14), (x + 30, base_y - 12 - i * 14), 2)

        # Eiffel tower
        x = self._wrap_parallax_x(shift + 1100)
        pygame.draw.polygon(screen, silhouette, [(x, base_y), (x + 46, base_y), (x + 23, base_y - 110)])
        pygame.draw.line(screen, (35, 58, 92), (x + 8, base_y - 36), (x + 38, base_y - 36), 3)
        pygame.draw.line(screen, (35, 58, 92), (x + 12, base_y - 68), (x + 34, base_y - 68), 2)

        # Christ statue
        x = self._wrap_parallax_x(shift + 1760)
        pygame.draw.rect(screen, silhouette, (x + 14, base_y - 56, 8, 56))
        pygame.draw.rect(screen, silhouette, (x - 8, base_y - 52, 52, 10))
        pygame.draw.polygon(screen, silhouette, [(x + 18, base_y - 74), (x + 11, base_y - 58), (x + 25, base_y - 58)])

    def draw_road(self, screen, bands):
        for band in bands:
            y1 = int(band["y_far"])
            y2 = int(band["y_near"])
            if y2 <= y1:
                continue

            segment_index = band["segment_index"]
            stripe = (segment_index // 2) % 2
            grass = (58, 168, 30) if stripe else (74, 182, 46)
            road_color = (74, 74, 74) if stripe else (66, 66, 66)
            rumble = (232, 46, 42) if stripe else (236, 236, 236)

            pygame.draw.rect(screen, grass, (0, y1, WIDTH, y2 - y1))

            c1 = band["center_far"]
            c2 = band["center_near"]
            h1 = band["half_far"]
            h2 = band["half_near"]
            road_poly = [(c1 - h1, y1), (c1 + h1, y1), (c2 + h2, y2), (c2 - h2, y2)]
            pygame.draw.polygon(screen, road_color, road_poly)

            rumble_w1 = h1 * 0.12
            rumble_w2 = h2 * 0.12
            left_rumble = [(c1 - h1 - rumble_w1, y1), (c1 - h1, y1), (c2 - h2, y2), (c2 - h2 - rumble_w2, y2)]
            right_rumble = [(c1 + h1 + rumble_w1, y1), (c1 + h1, y1), (c2 + h2, y2), (c2 + h2 + rumble_w2, y2)]
            pygame.draw.polygon(screen, rumble, left_rumble)
            pygame.draw.polygon(screen, rumble, right_rumble)

            # Guardrails
            pygame.draw.line(screen, (172, 178, 188), (int(c1 - h1 - rumble_w1 - 3), y1), (int(c2 - h2 - rumble_w2 - 3), y2), 2)
            pygame.draw.line(screen, (172, 178, 188), (int(c1 + h1 + rumble_w1 + 3), y1), (int(c2 + h2 + rumble_w2 + 3), y2), 2)

            # Lane markers
            marker_cond = (segment_index + int(y1 / 6)) % 2 == 0
            if marker_cond:
                for lane_div in (1 / 3, 2 / 3):
                    x1 = lerp(c1 - h1, c1 + h1, lane_div)
                    x2 = lerp(c2 - h2, c2 + h2, lane_div)
                    pygame.draw.line(screen, (240, 240, 240), (int(x1), y1), (int(x2), y2), 2)

    def draw_roadside(self, screen, bands, camera_mode, anchor_distance):
        reverse = camera_mode == "REAR"
        visible = []
        for obj in self.roadside_objects:
            delta = signed_track_delta(obj["distance"], anchor_distance, self.length)
            view_delta = -delta if reverse else delta
            if 14.0 < view_delta < bands[0]["ahead_far"]:
                visible.append((view_delta, obj))
        visible.sort(reverse=True, key=lambda item: item[0])

        for view_delta, obj in visible:
            lane = 1.32 * obj["side"]
            projection = self.project_from_bands(view_delta, lane, bands)
            if projection is None:
                continue
            x, y, scale = projection
            if obj["kind"] == "PALM":
                trunk_h = int(88 * scale)
                trunk_w = int(13 * scale)
                if trunk_h <= 2:
                    continue
                pygame.draw.rect(screen, (112, 68, 26), (int(x - trunk_w * 0.5), int(y - trunk_h), trunk_w, trunk_h))
                leaf_span = int(54 * scale)
                leaf_y = int(y - trunk_h)
                pygame.draw.polygon(
                    screen,
                    (34, 130, 54),
                    [(int(x), leaf_y - int(24 * scale)), (int(x - leaf_span), leaf_y), (int(x + leaf_span), leaf_y)],
                )
                pygame.draw.polygon(
                    screen,
                    (28, 120, 48),
                    [(int(x), leaf_y - int(16 * scale)), (int(x - int(leaf_span * 0.78)), leaf_y + int(8 * scale)), (int(x + int(leaf_span * 0.78)), leaf_y + int(8 * scale))],
                )
            else:
                bw = int(120 * scale)
                bh = int(68 * scale)
                if bw <= 8 or bh <= 6:
                    continue
                rect = pygame.Rect(int(x - bw * 0.5), int(y - bh), bw, bh)
                pygame.draw.rect(screen, (16, 20, 30), rect.inflate(8, 6))
                pygame.draw.rect(screen, (255, 220, 80), rect)
                pygame.draw.rect(screen, (214, 38, 42), (rect.x, rect.y, rect.w, int(rect.h * 0.26)))
                text = self.billboard_font.render(obj["text"], True, (26, 20, 40))
                text_scaled = pygame.transform.smoothscale(text, (int(text.get_width() * scale), max(8, int(text.get_height() * scale))))
                screen.blit(text_scaled, (rect.centerx - text_scaled.get_width() // 2, rect.y + int(rect.h * 0.38)))

    def draw_nitro_pickup(self, screen, bands, camera_mode, anchor_distance, player_lap):
        if player_lap not in self.nitro_pickups or player_lap in self.nitro_collected_laps:
            return
        pickup_distance = self.nitro_pickups[player_lap]
        delta = signed_track_delta(pickup_distance, anchor_distance, self.length)
        view_delta = -delta if camera_mode == "REAR" else delta
        if not (10.0 < view_delta < bands[0]["ahead_far"]):
            return
        projection = self.project_from_bands(view_delta, 0.0, bands)
        if projection is None:
            return
        x, y, scale = projection
        radius = int(14 * scale) + 2
        if radius < 3:
            return
        glow_color = (76, 230, 255)
        pygame.draw.circle(screen, (44, 126, 236), (int(x), int(y - 8 * scale)), radius)
        pygame.draw.circle(screen, glow_color, (int(x), int(y - 8 * scale)), max(2, radius // 2))


class Car:
    number_font = None

    def __init__(self, name, color, number, transmission_mode="manual", is_player=False):
        self.name = name
        self.color = color
        self.number = number
        self.is_player = is_player

        self.transmission_mode = transmission_mode.lower()
        self.distance = 0.0
        self.total_distance = 0.0
        self.lane = 0.0
        self.speed = 0.0  # meters / second

        self.lap = 1
        self.lap_start_time = 0.0
        self.lap_times = []
        self.position = TOTAL_RACERS
        self.finished = False
        self.finish_time = None

        self.gear = 1
        self.rpm = 1300.0
        self.redline = 9000.0
        self.shift_penalty_timer = 0.0
        self.perfect_shift_boost = 0.0

        self.nitro_meter = 0.0
        self.nitro_timer = 0.0

        self.fuel = 100.0
        self.tire = 100.0

        self.crash_timer = 0.0
        self.crash_count = 0
        self.eliminated = False
        self.stranded = False

        self.wipers_on = False
        self.headlights_on = False
        self.snow_slide = 0.0
        self.steer_visual = 0.0
        self.backfire_timer = 0.0
        self.engine_voice = 0

        self.sprite = self._create_car_sprite(color, number, is_player)
        self.sprite_left, self.sprite_right = self._build_sprite_variants(self.sprite)

    @classmethod
    def _ensure_font(cls):
        if cls.number_font is None:
            cls.number_font = pygame.font.Font(None, 18)

    def _create_car_sprite(self, color, number, is_player):
        self._ensure_font()
        frame = SpriteBank.pick_car_frame(number - 1)
        if frame is not None:
            sprite = pygame.transform.smoothscale(frame, (60, 90))
            tint = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
            tint.fill((color[0], color[1], color[2], 255))
            sprite.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            stripe = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
            stripe_color = (min(255, color[0] + 60), min(255, color[1] + 60), min(255, color[2] + 60), 180)
            pygame.draw.rect(stripe, stripe_color, (24, 8, 12, 70))
            sprite.blit(stripe, (0, 0))
        else:
            sprite = pygame.Surface((60, 90), pygame.SRCALPHA)
            c = color
            dark = (max(0, c[0] - 72), max(0, c[1] - 72), max(0, c[2] - 72))
            light = (min(255, c[0] + 46), min(255, c[1] + 46), min(255, c[2] + 46))
            accent = (min(255, c[0] + 90), min(255, c[1] + 18), max(0, c[2] - 12))

            # Wheels and tire blocks
            wheel = (22, 22, 24)
            pygame.draw.rect(sprite, wheel, (2, 12, 12, 26))
            pygame.draw.rect(sprite, wheel, (46, 12, 12, 26))
            pygame.draw.rect(sprite, wheel, (4, 50, 10, 22))
            pygame.draw.rect(sprite, wheel, (46, 50, 10, 22))

            # Rear wing and endplates
            pygame.draw.rect(sprite, dark, (11, 6, 38, 8))
            pygame.draw.rect(sprite, accent, (9, 8, 42, 5))
            pygame.draw.rect(sprite, dark, (7, 5, 4, 11))
            pygame.draw.rect(sprite, dark, (49, 5, 4, 11))

            # Main body and sidepods
            pygame.draw.polygon(sprite, dark, [(18, 14), (42, 14), (38, 60), (22, 60)])
            pygame.draw.polygon(sprite, c, [(20, 16), (40, 16), (36, 58), (24, 58)])
            pygame.draw.polygon(sprite, light, [(22, 18), (38, 18), (34, 34), (26, 34)])
            pygame.draw.rect(sprite, dark, (13, 34, 10, 16))
            pygame.draw.rect(sprite, dark, (37, 34, 10, 16))
            pygame.draw.rect(sprite, accent, (14, 36, 8, 10))
            pygame.draw.rect(sprite, accent, (38, 36, 8, 10))

            # Nose cone and front wing
            pygame.draw.polygon(sprite, c, [(27, 56), (33, 56), (35, 80), (25, 80)])
            pygame.draw.polygon(sprite, light, [(28, 58), (32, 58), (33, 76), (27, 76)])
            pygame.draw.rect(sprite, dark, (10, 78, 40, 5))
            pygame.draw.rect(sprite, accent, (9, 82, 42, 4))

            # Cockpit / driver canopy
            pygame.draw.rect(sprite, (20, 92, 192), (24, 30, 12, 15))
            pygame.draw.rect(sprite, (114, 206, 255), (25, 31, 10, 6))

        # Number on engine cover
        number_text = self.number_font.render(str(number), True, (250, 250, 250))
        sprite.blit(number_text, (30 - number_text.get_width() // 2, 48))

        if is_player:
            pygame.draw.rect(sprite, (250, 240, 90), (23, 22, 14, 4))
        return sprite

    def _build_sprite_variants(self, base_sprite):
        left = pygame.transform.rotozoom(base_sprite, 9, 1.0)
        right = pygame.transform.rotozoom(base_sprite, -9, 1.0)
        return left, right

    @property
    def progress(self):
        if self.finished and self.finish_time is not None:
            return TOTAL_LAPS * TRACK_LENGTH_M + (10000.0 - self.finish_time)
        return (self.lap - 1) * TRACK_LENGTH_M + self.distance

    def reset_for_race(self):
        self.distance = 0.0
        self.total_distance = 0.0
        self.lane = 0.0
        self.speed = 0.0
        self.lap = 1
        self.lap_start_time = 0.0
        self.lap_times.clear()
        self.position = TOTAL_RACERS
        self.finished = False
        self.finish_time = None
        self.gear = 1
        self.rpm = 1300.0
        self.shift_penalty_timer = 0.0
        self.perfect_shift_boost = 0.0
        self.nitro_meter = 0.0
        self.nitro_timer = 0.0
        self.fuel = 100.0
        self.tire = 100.0
        self.crash_timer = 0.0
        self.crash_count = 0
        self.eliminated = False
        self.stranded = False
        self.wipers_on = False
        self.headlights_on = False
        self.snow_slide = 0.0
        self.steer_visual = 0.0
        self.backfire_timer = 0.0

    def _advance_track_progress(self, distance_step, track_length, race_elapsed):
        if distance_step <= 0:
            return
        self.distance += distance_step
        self.total_distance += distance_step
        while self.distance >= track_length:
            self.distance -= track_length
            lap_time = race_elapsed - self.lap_start_time
            if self.lap <= TOTAL_LAPS:
                self.lap_times.append(lap_time)
            self.lap += 1
            self.lap_start_time = race_elapsed
            if self.lap > TOTAL_LAPS and not self.finished:
                self.finished = True
                self.finish_time = race_elapsed
                self.speed = 0.0
                break

    def _auto_shift(self):
        speed_kmh = self.speed * 3.6
        thresholds = self._gear_speed_limits_kmh()
        while self.gear < 7 and speed_kmh > thresholds[self.gear] + 4.0:
            self.gear += 1
        while self.gear > 1 and speed_kmh < thresholds[self.gear - 1] - 10.0:
            self.gear -= 1

    def _gear_speed_limits_kmh(self):
        if self.transmission_mode == "automatic":
            return [0.0, 54.0, 96.0, 142.0, 192.0, 246.0, 300.0, 346.0]
        return [0.0, 60.0, 108.0, 160.0, 220.0, 282.0, 342.0, 402.0]

    def _gear_accel_profile(self):
        if self.transmission_mode == "automatic":
            return [0.0, 32.0, 29.0, 25.0, 22.0, 19.0, 16.0, 14.0]
        return [0.0, 38.0, 35.0, 31.0, 28.0, 25.0, 22.0, 19.0]

    def shift_up(self):
        if self.transmission_mode != "manual":
            return "automatic"
        if self.shift_penalty_timer > 0:
            return "locked"
        if self.gear >= 7:
            return "max"
        rough_shift = False
        perfect_shift = False
        if self.rpm > self.redline * 1.10:
            self.shift_penalty_timer = random.uniform(2.6, 3.4)
            rough_shift = True
        elif self.redline * 0.88 <= self.rpm <= self.redline * 1.01:
            self.perfect_shift_boost = max(self.perfect_shift_boost, 1.25)
            perfect_shift = True
        self.gear += 1
        self.rpm *= 0.66
        self.backfire_timer = 0.18 if rough_shift else 0.08
        if rough_shift:
            return "overrev"
        if perfect_shift:
            return "perfect"
        return "ok"

    def shift_down(self):
        if self.transmission_mode != "manual":
            return "automatic"
        if self.shift_penalty_timer > 0:
            return "locked"
        if self.gear <= 1:
            return "min"
        self.gear -= 1
        self.rpm *= 1.12
        if self.rpm > self.redline * 1.16:
            self.shift_penalty_timer = max(self.shift_penalty_timer, 1.0)
        self.backfire_timer = max(self.backfire_timer, 0.05)
        return "ok"

    def grant_nitro(self):
        self.nitro_meter = 1.0

    def activate_nitro(self):
        if self.transmission_mode != "manual":
            return False
        if self.nitro_timer > 0 or self.nitro_meter <= 0.0 or self.crash_timer > 0:
            return False
        self.nitro_timer = random.uniform(5.0, 10.0)
        self.nitro_meter = 0.0
        return True

    def start_crash(self):
        if self.crash_timer > 0 or self.finished:
            return False
        self.crash_timer = 5.0
        self.crash_count += 1
        self.speed = 0.0
        self.nitro_timer = 0.0
        self.perfect_shift_boost = 0.0
        if self.crash_count >= 3:
            self.eliminated = True
        return True

    def _update_rpm(self, dt, throttle):
        limits = self._gear_speed_limits_kmh()
        high_limit = limits[self.gear] / 3.6
        speed_ratio = clamp(self.speed / max(high_limit, 0.1), 0.0, 1.35)

        target_rpm = 920.0 + speed_ratio * (self.redline - 920.0) * 0.98
        if throttle:
            target_rpm += 420.0
        if self.nitro_timer > 0:
            target_rpm += 240.0
        if self.shift_penalty_timer > 0:
            target_rpm = min(target_rpm, self.redline * 0.78)

        response = 10.0 if throttle else 7.0
        self.rpm += (target_rpm - self.rpm) * dt * response
        self.rpm = clamp(self.rpm, 850.0, 11200.0)

    def update_player(self, dt, track, weather, throttle, brake, steer, allow_drive, race_elapsed, traction_control=True):
        if self.finished:
            return

        self.backfire_timer = max(0.0, self.backfire_timer - dt)

        if self.crash_timer > 0:
            self.crash_timer -= dt
            if self.crash_timer <= 0 and not self.eliminated:
                self.lane = 0.0
                self.speed = 18.0
            return

        if self.shift_penalty_timer > 0:
            self.shift_penalty_timer = max(0.0, self.shift_penalty_timer - dt)

        if self.transmission_mode == "automatic":
            self._auto_shift()

        traction = weather.traction * (0.62 + (self.tire / 100.0) * 0.38)
        traction = clamp(traction, 0.35, 1.1)

        speed_limits = [limit / 3.6 for limit in self._gear_speed_limits_kmh()]
        gear_accel = self._gear_accel_profile()

        max_speed = speed_limits[7]
        if self.transmission_mode == "automatic":
            max_speed *= 0.95
        if self.perfect_shift_boost > 0:
            max_speed *= 1.11
            self.perfect_shift_boost = max(0.0, self.perfect_shift_boost - dt)
        if self.nitro_timer > 0:
            max_speed *= 1.30
            self.nitro_timer = max(0.0, self.nitro_timer - dt)

        if self.fuel <= 0 or self.tire <= 0:
            self.stranded = True
            self.speed = max(0.0, self.speed - 42.0 * dt)
            self._update_rpm(dt, False)
            self._advance_track_progress(self.speed * dt, track.length, race_elapsed)
            return

        effective_throttle = throttle and allow_drive and self.shift_penalty_timer <= 0.0
        if effective_throttle:
            gear_cap = speed_limits[self.gear]
            cap_ratio = clamp(1.0 - (self.speed / max(gear_cap, 0.01)), 0.32, 1.12)
            accel_force = gear_accel[self.gear] * cap_ratio * traction
            if traction_control:
                accel_force *= 1.0 - max(0.0, 1.0 - traction) * 0.45
            if self.speed > gear_cap:
                accel_force *= 0.48
            self.speed += accel_force * dt
        elif allow_drive:
            self.speed -= (2.2 + self.speed * 0.020) * dt

        if brake and allow_drive:
            brake_force = 52.0 + self.speed * 0.10
            self.speed -= brake_force * dt

        drag = 1.2 + self.speed * 0.014 + (self.speed * self.speed) * 0.00035
        if not effective_throttle:
            drag *= 1.12
        self.speed -= drag * dt

        off_road = abs(self.lane) > 1.05
        if off_road:
            self.speed -= (11.0 + self.speed * 0.09) * dt

        self.speed = clamp(self.speed, 0.0, max_speed)

        if allow_drive:
            speed_ratio = clamp(self.speed / max(max_speed, 0.01), 0.0, 1.0)
            steer_force = weather.steer_response * dt * (0.92 - speed_ratio * 0.42)
            if traction_control:
                steer_force *= 0.86 + traction * 0.18
            self.lane += steer * steer_force
            if weather.name == "SNOW":
                self.snow_slide += steer * dt * 0.78
                self.snow_slide *= max(0.0, 1.0 - 1.4 * dt)
                self.lane += self.snow_slide
            if not traction_control and effective_throttle:
                slip = max(0.0, 1.0 - traction)
                self.lane += math.sin(race_elapsed * 19.0 + self.speed) * slip * dt * 0.30

        self.steer_visual += (steer - self.steer_visual) * min(1.0, dt * 10.0)

        self.lane = clamp(self.lane, -1.48, 1.48)
        self._update_rpm(dt, effective_throttle)

        fuel_rate = 0.025 + self.speed * 0.0048 + (0.045 if effective_throttle else 0.0)
        tire_rate = 0.045 + abs(steer) * self.speed * 0.008 + (1.0 - traction) * 0.35 + (0.07 if off_road else 0.0)
        if self.nitro_timer > 0:
            tire_rate += 0.10

        self.fuel = max(0.0, self.fuel - fuel_rate * dt)
        self.tire = max(0.0, self.tire - tire_rate * dt)

        distance_step = self.speed * dt if allow_drive else 0.0
        self._advance_track_progress(distance_step, track.length, race_elapsed)

    def draw(self, screen, x, y, scale, show_flames=False, show_backfire=False):
        if scale <= 0:
            return
        sprite = self.sprite
        if self.steer_visual < -0.24:
            sprite = self.sprite_left
        elif self.steer_visual > 0.24:
            sprite = self.sprite_right

        w = max(8, int(sprite.get_width() * scale))
        h = max(8, int(sprite.get_height() * scale))
        scaled = pygame.transform.smoothscale(sprite, (w, h))
        screen.blit(scaled, (int(x - w * 0.5), int(y - h * 0.9)))
        if show_flames or show_backfire:
            flame_w = max(4, int(8 * scale))
            flame_h = max(5, int(13 * scale))
            fx = int(x)
            fy = int(y + h * 0.08)
            if show_backfire and not show_flames:
                flame_w = max(3, int(5 * scale))
                flame_h = max(3, int(7 * scale))
            pygame.draw.polygon(
                screen,
                (255, 122, 28),
                [(fx - flame_w, fy), (fx, fy + flame_h), (fx + flame_w, fy)],
            )
            pygame.draw.polygon(
                screen,
                (255, 210, 62),
                [(fx - flame_w // 2, fy), (fx, fy + int(flame_h * 0.72)), (fx + flame_w // 2, fy)],
            )


class AIDriver(Car):
    def __init__(self, name, color, number, skill, aggression):
        super().__init__(name, color, number, transmission_mode="automatic", is_player=False)
        self.skill = skill
        self.aggression = aggression
        self.preferred_lane = random.uniform(-0.65, 0.65)
        self.wobble_phase = random.uniform(0, 6.28)
        self.finish_logged = False
        self.engine_voice = random.randint(1, 7)

    def update_ai(self, dt, track, weather, racers, race_elapsed):
        if self.finished:
            self.speed = max(0.0, self.speed - 10.0 * dt)
            return

        if self.crash_timer > 0:
            self.crash_timer -= dt
            if self.crash_timer <= 0:
                self.lane = 0.0
            return

        curve_now = track.curvature_at(self.distance + 20.0)
        curve_ahead = track.curvature_at(self.distance + 55.0)

        target_lane = clamp(-curve_ahead * 0.95 + self.preferred_lane * 0.7 + math.sin(race_elapsed * 0.9 + self.wobble_phase) * 0.12, -0.95, 0.95)
        for other in racers:
            if other is self or other.finished:
                continue
            delta = signed_track_delta(other.distance, self.distance, track.length)
            if 0.0 < delta < 21.0 and abs(other.lane - self.lane) < 0.22:
                target_lane += 0.55 if self.lane <= other.lane else -0.55
                break

        target_lane = clamp(target_lane, -1.1, 1.1)
        lane_error = target_lane - self.lane
        lane_step = clamp(lane_error, -1.0, 1.0) * dt * (0.45 + self.speed / 140.0) * weather.steer_response
        self.lane += lane_step
        self.steer_visual += (clamp(lane_error * 2.5, -1.0, 1.0) - self.steer_visual) * min(1.0, dt * 6.0)
        self.lane = clamp(self.lane, -1.38, 1.38)

        base_speed = 70.0 + self.skill * 27.0
        curve_penalty = 1.0 - min(0.44, abs(curve_now) * 0.60 + abs(curve_ahead) * 0.35)
        target_speed = base_speed * curve_penalty * weather.ai_speed_factor
        if abs(self.lane) > 1.05:
            target_speed *= 0.75

        if self.speed < target_speed:
            self.speed += (14.0 + self.aggression * 8.0) * dt
        else:
            self.speed -= (11.0 + (1.0 - self.aggression) * 6.0) * dt

        self.speed -= (4.6 + self.speed * 0.045) * dt
        self.speed = clamp(self.speed, 22.0, 96.0)

        self.rpm = 1200.0 + self.speed * (1.5 + self.gear * 0.2) * 40.0
        self._auto_shift()
        self._advance_track_progress(self.speed * dt, track.length, race_elapsed)


class PitSystem:
    def __init__(self, track):
        self.track = track
        self.mandatory_lap = 2
        self.completed = False
        self.active = False
        self.timer = 0.0
        self.failure_mode = False
        self.sequence_steps = ["JACKING CAR", "TIRES SWAP", "REFUELING", "WING CHECK", "RELEASE"]

    def can_enter(self, player):
        if self.completed or player.lap != self.mandatory_lap:
            return False
        return self.track.pit_entry_start <= player.distance <= self.track.pit_entry_end

    def try_enter(self, player):
        if not self.can_enter(player):
            return False
        self.active = True
        self.timer = 10.0
        player.speed = 0.0
        return True

    def update(self, dt, player):
        if self.active:
            self.timer = max(0.0, self.timer - dt)
            player.speed = 0.0
            if self.timer <= 0:
                self.active = False
                self.completed = True
                player.fuel = 100.0
                player.tire = min(100.0, player.tire + 35.0)
                return "PIT STOP COMPLETE!"
            return None

        if player.lap > self.mandatory_lap and not self.completed:
            self.failure_mode = True
            player.fuel = max(0.0, player.fuel - 8.0 * dt)
            player.tire = max(0.0, player.tire - 6.5 * dt)
            if player.fuel <= 0 or player.tire <= 0:
                player.stranded = True
                player.speed = max(0.0, player.speed - 55.0 * dt)
        return None

    def draw_overlay(self, screen):
        if not self.active:
            return
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((10, 18, 28, 155))
        screen.blit(overlay, (0, 0))

        panel = pygame.Rect(WIDTH // 2 - 280, HEIGHT // 2 - 100, 560, 200)
        pygame.draw.rect(screen, (26, 34, 54), panel, border_radius=10)
        pygame.draw.rect(screen, (222, 230, 242), panel, 2, border_radius=10)

        big = pygame.font.Font(None, 46)
        small = pygame.font.Font(None, 30)
        stage_index = min(len(self.sequence_steps) - 1, int((10.0 - self.timer) / 2.0))
        stage_text = self.sequence_steps[stage_index]

        title = big.render("PIT STOP IN PROGRESS", True, (246, 246, 246))
        screen.blit(title, (panel.centerx - title.get_width() // 2, panel.y + 24))

        stage = small.render(stage_text, True, (255, 220, 82))
        screen.blit(stage, (panel.centerx - stage.get_width() // 2, panel.y + 88))

        progress = clamp((10.0 - self.timer) / 10.0, 0.0, 1.0)
        bar = pygame.Rect(panel.x + 54, panel.y + 142, panel.w - 108, 24)
        pygame.draw.rect(screen, (18, 22, 32), bar)
        pygame.draw.rect(screen, (66, 212, 120), (bar.x, bar.y, int(bar.w * progress), bar.h))
        pygame.draw.rect(screen, (255, 255, 255), bar, 2)


class CollisionSystem:
    def update(self, player, ai_cars, track):
        crashed = False

        if player.crash_timer <= 0 and not player.finished:
            for ai in ai_cars:
                if ai.finished:
                    continue
                delta = signed_track_delta(ai.distance, player.distance, track.length)
                lane_gap = abs(ai.lane - player.lane)
                if abs(delta) < 4.6 and lane_gap < 0.21:
                    relative_speed = abs(ai.speed - player.speed)
                    impact = relative_speed + player.speed * 0.32
                    severe_contact = player.speed > 18.0 and (impact > 23.0 or abs(delta) < 1.9)
                    if severe_contact or abs(player.lane) > 1.18:
                        crashed = player.start_crash() or crashed
                    else:
                        shove = 0.16 if ai.lane >= player.lane else -0.16
                        player.lane -= shove * 0.8
                        ai.lane += shove * 0.7
                        player.speed = max(0.0, player.speed - 7.0)
                        ai.speed = max(0.0, ai.speed - 4.0)

            if player.speed > 14.0:
                for sign_distance, sign_side in track.sign_positions:
                    delta = signed_track_delta(sign_distance, player.distance, track.length)
                    if 0.0 < delta < 3.0 and sign_side * player.lane > 1.22:
                        crashed = player.start_crash() or crashed
                        break

        # AI-to-AI collisions
        for i, first in enumerate(ai_cars):
            for second in ai_cars[i + 1 :]:
                if first.finished or second.finished:
                    continue
                delta = signed_track_delta(second.distance, first.distance, track.length)
                if abs(delta) < 3.4 and abs(second.lane - first.lane) < 0.14:
                    first.speed = max(18.0, first.speed - 2.5)
                    second.speed = max(18.0, second.speed - 2.5)
                    push = 0.07 if first.lane <= second.lane else -0.07
                    first.lane -= push
                    second.lane += push
        return crashed


class HUD:
    def __init__(self):
        self.font_small = pygame.font.Font(None, 24)
        self.font_medium = pygame.font.Font(None, 30)
        self.font_large = pygame.font.Font(None, 40)

    def _draw_bar(self, screen, rect, ratio, fill_color, border_color=(255, 255, 255)):
        ratio = clamp(ratio, 0.0, 1.0)
        pygame.draw.rect(screen, (18, 22, 30), rect)
        inner = pygame.Rect(rect.x, rect.y, int(rect.w * ratio), rect.h)
        pygame.draw.rect(screen, fill_color, inner)
        pygame.draw.rect(screen, border_color, rect, 2)

    def draw(self, screen, game):
        player = game.player

        hud_panel = pygame.Rect(18, 16, 410, 198)
        pygame.draw.rect(screen, (10, 14, 22, 165), hud_panel, border_radius=6)
        pygame.draw.rect(screen, (234, 244, 255), hud_panel, 2, border_radius=6)

        speed_kmh = int(player.speed * 3.6)
        timer_color = (255, 90, 90) if game.race_timer <= 12 else (240, 240, 240)
        lap_text = self.font_medium.render(f"LAP {min(player.lap, TOTAL_LAPS)}/{TOTAL_LAPS}", True, (255, 255, 255))
        pos_text = self.font_medium.render(f"POS {player.position:02d}/{TOTAL_RACERS}", True, (255, 234, 112))
        speed_text = self.font_large.render(f"{speed_kmh:03d} km/h", True, (168, 244, 246))
        timer_text = self.font_large.render(f"TIME {int(max(game.race_timer, 0)):02d}", True, timer_color)
        gear_label = "A" if player.transmission_mode == "automatic" else str(player.gear)
        tc_label = "ON" if game.traction_control_enabled else "OFF"

        screen.blit(lap_text, (hud_panel.x + 14, hud_panel.y + 10))
        screen.blit(pos_text, (hud_panel.x + 226, hud_panel.y + 10))
        screen.blit(speed_text, (hud_panel.x + 14, hud_panel.y + 46))
        screen.blit(timer_text, (hud_panel.x + 230, hud_panel.y + 48))

        gear_text = self.font_medium.render(f"GEAR {gear_label}", True, (255, 255, 255))
        screen.blit(gear_text, (hud_panel.x + 14, hud_panel.y + 95))
        tc_color = (102, 232, 138) if game.traction_control_enabled else (255, 148, 102)
        tc_text = self.font_small.render(f"TC {tc_label} (T)", True, tc_color)
        screen.blit(tc_text, (hud_panel.x + 14, hud_panel.y + 140))

        if player.transmission_mode == "manual":
            rpm_ratio = clamp(player.rpm / player.redline, 0.0, 1.25)
            rpm_color = (248, 72, 72) if rpm_ratio > 0.95 else (248, 206, 82)
            rpm_value = self.font_small.render(f"RPM {int(player.rpm):05d}", True, rpm_color)
            screen.blit(rpm_value, (hud_panel.x + 150, hud_panel.y + 98))
            self._draw_bar(screen, pygame.Rect(hud_panel.x + 150, hud_panel.y + 124, 236, 16), rpm_ratio, rpm_color)
        else:
            auto_text = self.font_small.render("AUTO SHIFT ENABLED (NO NITRO)", True, (182, 208, 248))
            screen.blit(auto_text, (hud_panel.x + 150, hud_panel.y + 104))

        self._draw_bar(screen, pygame.Rect(hud_panel.x + 14, hud_panel.y + 156, 122, 18), player.fuel / 100.0, (78, 216, 120))
        self._draw_bar(screen, pygame.Rect(hud_panel.x + 144, hud_panel.y + 156, 122, 18), player.tire / 100.0, (255, 158, 72))
        nitro_color = (72, 206, 255) if player.transmission_mode == "manual" else (80, 92, 120)
        self._draw_bar(screen, pygame.Rect(hud_panel.x + 274, hud_panel.y + 156, 122, 18), player.nitro_meter, nitro_color)

        screen.blit(self.font_small.render("FUEL", True, (235, 235, 235)), (hud_panel.x + 50, hud_panel.y + 176))
        screen.blit(self.font_small.render("TIRES", True, (235, 235, 235)), (hud_panel.x + 176, hud_panel.y + 176))
        screen.blit(self.font_small.render("NITRO", True, (235, 235, 235)), (hud_panel.x + 308, hud_panel.y + 176))

        self._draw_minimap(screen, game)

        # race messages
        y = 16
        for text, ttl in game.messages[:3]:
            if ttl <= 0:
                continue
            msg = self.font_medium.render(text, True, (255, 244, 136))
            screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, y))
            y += 30

    def _draw_minimap(self, screen, game):
        rect = pygame.Rect(WIDTH - 248, 18, 228, 188)
        pygame.draw.rect(screen, (10, 14, 22, 165), rect, border_radius=6)
        pygame.draw.rect(screen, (226, 236, 245), rect, 2, border_radius=6)

        title = self.font_small.render("MONACO MAP", True, (255, 255, 255))
        screen.blit(title, (rect.x + 68, rect.y + 8))

        map_rect = pygame.Rect(rect.x + 10, rect.y + 30, rect.w - 20, 106)
        pygame.draw.rect(screen, (24, 30, 42), map_rect)
        pygame.draw.rect(screen, (92, 110, 136), map_rect, 1)

        path_points = []
        for x_norm, y_norm in game.track.map_path:
            x = map_rect.x + int(x_norm * map_rect.w)
            y = map_rect.y + int(y_norm * map_rect.h)
            path_points.append((x, y))
        if len(path_points) > 2:
            pygame.draw.lines(screen, (190, 196, 210), False, path_points, 2)

        # player marker
        p_fraction = (game.player.distance % game.track.length) / game.track.length
        px_norm, py_norm = game.track.map_point(p_fraction)
        px = map_rect.x + int(px_norm * map_rect.w)
        py = map_rect.y + int(py_norm * map_rect.h)
        pygame.draw.circle(screen, (245, 245, 245), (px, py), 4)

        # AI markers (disappear when finished)
        for ai in game.ai_cars:
            if ai.finished:
                continue
            frac = (ai.distance % game.track.length) / game.track.length
            nx, ny = game.track.map_point(frac)
            mx = map_rect.x + int(nx * map_rect.w)
            my = map_rect.y + int(ny * map_rect.h)
            pygame.draw.circle(screen, ai.color, (mx, my), 3)

        y = rect.y + 142
        for idx, (name, f_time) in enumerate(game.ai_finish_log[:3]):
            line = self.font_small.render(f"{idx + 1}. {name} {format_time(f_time)}", True, (180, 224, 250))
            screen.blit(line, (rect.x + 10, y))
            y += 14


class PolePositionRacerGame:
    def __init__(self):
        pygame.mixer.pre_init(22050, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("POLE POSITION RACER: LLM RACER VERSION")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.running = True

        SpriteBank.load_optional_sheet()
        self.audio = SynthAudio()
        self.track = Track()
        self.weather = Weather()
        self.camera = Camera("CHASE")
        self.hud = HUD()
        self.pit_system = PitSystem(self.track)
        self.collision_system = CollisionSystem()

        self.transmission_setting = "manual"
        self.default_camera_mode = "CHASE"
        self.traction_control_enabled = True

        self.player = Car("PLAYER", (236, 90, 50), 20, transmission_mode=self.transmission_setting, is_player=True)
        self.ai_cars = []

        self.state = "intro"
        self.intro_timer = 0.0
        self.menu_index = 0
        self.menu_items = ["START RACE", "TRANSMISSION", "DEFAULT CAMERA", "QUIT"]
        self.countdown_timer = 3.2
        self.countdown_display = 3

        self.race_elapsed = 0.0
        self.race_timer = PLAYER_START_TIME
        self.checkpoint_index = 0
        self.messages = []
        self.ai_finish_log = []
        self.finish_order = []

        self.result_dnf = False
        self.player_won = False
        self.spectator_timer = 0.0

        self.name_entry = ""
        self.leaderboard_path = os.path.join(os.path.dirname(__file__), "leaderboard.json")
        self.leaderboard = self._load_leaderboard()

        self._spawn_ai_grid()
        self.audio.play_menu_music()

    def _spawn_ai_grid(self):
        self.ai_cars.clear()
        palette = generate_unique_palette(TOTAL_RACERS)

        self.player.reset_for_race()
        self.player.transmission_mode = self.transmission_setting
        self.player.distance = 0.0
        self.player.total_distance = 0.0
        self.player.lane = 0.0
        self.player.color = palette[0]
        self.player.sprite = self.player._create_car_sprite(self.player.color, self.player.number, True)
        self.player.sprite_left, self.player.sprite_right = self.player._build_sprite_variants(self.player.sprite)
        self.player.engine_voice = 0

        for idx in range(19):
            skill = random.uniform(0.45, 1.00)
            aggression = random.uniform(0.30, 1.00)
            ai = AIDriver(f"AI-{idx + 1:02d}", palette[idx + 1], idx + 1, skill, aggression)
            ai.distance = 26.0 + idx * 9.2
            ai.total_distance = ai.distance
            ai.lane = ((idx % 4) - 1.5) * 0.26 + random.uniform(-0.05, 0.05)
            self.ai_cars.append(ai)

    def _load_leaderboard(self):
        if not os.path.exists(self.leaderboard_path):
            return []
        try:
            with open(self.leaderboard_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                return data
        except (OSError, json.JSONDecodeError):
            pass
        return []

    def _save_leaderboard(self):
        try:
            with open(self.leaderboard_path, "w", encoding="utf-8") as fh:
                json.dump(self.leaderboard[:10], fh, indent=2)
        except OSError:
            pass

    def _reset_race(self):
        self.track.regenerate_nitro_pickups()
        self.weather = Weather()
        self.camera = Camera(self.default_camera_mode)
        self.pit_system = PitSystem(self.track)
        self._spawn_ai_grid()

        self.race_elapsed = 0.0
        self.race_timer = PLAYER_START_TIME
        self.checkpoint_index = 0
        self.messages.clear()
        self.ai_finish_log.clear()
        self.finish_order.clear()
        self.result_dnf = False
        self.player_won = False
        self.spectator_timer = 0.0
        self.name_entry = ""

        self.countdown_timer = 3.2
        self.countdown_display = 3
        self.state = "countdown"

        self.audio.play_race_music()

    def _add_message(self, text, ttl=2.4):
        self.messages.append([text, ttl])

    def _update_messages(self, dt):
        for msg in self.messages:
            msg[1] -= dt
        self.messages = [msg for msg in self.messages if msg[1] > 0]

    def _compute_positions(self):
        racers = [self.player] + self.ai_cars
        racers.sort(key=lambda car: car.progress, reverse=True)
        for idx, car in enumerate(racers):
            car.position = idx + 1
        return racers

    def _build_finish_order(self):
        racers = [self.player] + self.ai_cars
        finished = [car for car in racers if car.finished]
        unfinished = [car for car in racers if not car.finished]
        finished.sort(key=lambda c: c.finish_time if c.finish_time is not None else float("inf"))
        unfinished.sort(key=lambda c: c.progress, reverse=True)
        order = []
        for car in finished + unfinished:
            status = "FINISHED" if car.finished else "DNF"
            time_value = car.finish_time if car.finished else None
            order.append((car.name, status, time_value, car))
        self.finish_order = order

    def _enter_post_race(self, dnf=False):
        self.result_dnf = dnf
        self._compute_positions()
        self._build_finish_order()
        self.audio.play_menu_music()
        if not dnf and self.player.finished and self.player.position == 1:
            self.player_won = True
            self.state = "name_entry"
        else:
            self.player_won = False
            self.state = "post_race"

    def _handle_global_events(self, events):
        for event in events:
            if event.type == pygame.QUIT:
                self.running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if self.state in ("race", "countdown", "spectator"):
                    self.state = "menu"
                    self.audio.play_menu_music()
                elif self.state == "menu":
                    self.running = False

    def _update_intro(self, dt, events):
        self.intro_timer += dt
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                self.state = "menu"
                return
        if self.intro_timer > 8.0:
            self.state = "menu"

    def _update_menu(self, events):
        for event in events:
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_UP:
                self.menu_index = (self.menu_index - 1) % len(self.menu_items)
            elif event.key == pygame.K_DOWN:
                self.menu_index = (self.menu_index + 1) % len(self.menu_items)
            elif event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_RETURN):
                if self.menu_index == 0 and event.key == pygame.K_RETURN:
                    self._reset_race()
                elif self.menu_index == 1:
                    self.transmission_setting = "automatic" if self.transmission_setting == "manual" else "manual"
                elif self.menu_index == 2:
                    mode_cycle = ["CHASE", "REAR", "BUMPER"]
                    idx = mode_cycle.index(self.default_camera_mode)
                    self.default_camera_mode = mode_cycle[(idx + 1) % len(mode_cycle)]
                elif self.menu_index == 3 and event.key == pygame.K_RETURN:
                    self.running = False

    def _update_countdown(self, dt):
        prior = int(math.ceil(self.countdown_timer))
        self.countdown_timer -= dt
        self.player._update_rpm(dt, False)
        current = int(math.ceil(max(self.countdown_timer, 0.0)))
        if current < prior:
            if current > 0:
                self.audio.play_countdown_beep(current)
            else:
                self.audio.play_go()
                self._add_message("GO GO GO!", 2.0)
        if self.countdown_timer <= 0:
            self.state = "race"
        self.audio.update_engine(self.player.rpm, throttle=False, active=True, crashed=False, voice_id=self.player.engine_voice)
        self.audio.update_ai_engine(0.0, active=False)

    def _process_race_keydowns(self, events):
        for event in events:
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_c:
                self.camera.toggle()
            elif event.key == pygame.K_INSERT:
                if self.player.activate_nitro():
                    self.audio.play_nitro()
                    self._add_message("NITRO BOOST!", 1.4)
            elif event.key == pygame.K_SPACE:
                if self.pit_system.try_enter(self.player):
                    self.audio.play_pit()
                    self._add_message("PIT LANE ENTRY", 1.8)
            elif event.key == pygame.K_LSHIFT:
                outcome = self.player.shift_up()
                if outcome == "ok":
                    self.audio.play_shift()
                    self.audio.play_shift_pop()
                elif outcome == "perfect":
                    self.audio.play_shift()
                    self.audio.play_shift_pop()
                    self._add_message("PERFECT SHIFT BOOST!", 1.2)
                elif outcome == "overrev":
                    self.audio.play_backfire()
                    self._add_message("ROUGH SHIFT! POWER LOSS", 1.4)
                elif outcome == "locked":
                    self._add_message("OVER-REV! SHIFT LOCK", 1.8)
            elif event.key == pygame.K_RSHIFT:
                outcome = self.player.shift_down()
                if outcome == "ok":
                    self.audio.play_shift()
                    self.audio.play_shift_pop()
            elif event.key == pygame.K_h and self.weather.requires_headlights:
                self.player.headlights_on = not self.player.headlights_on
                if self.player.headlights_on:
                    self._add_message("HEADLIGHTS ON", 1.4)
                else:
                    self._add_message("HEADLIGHTS OFF", 1.4)
            elif event.key == pygame.K_t:
                self.traction_control_enabled = not self.traction_control_enabled
                tc_state = "ON" if self.traction_control_enabled else "OFF"
                self._add_message(f"TRACTION CONTROL {tc_state}", 1.4)
            elif event.key == pygame.K_1 and self.weather.requires_wipers:
                self.player.wipers_on = not self.player.wipers_on
                if self.player.wipers_on:
                    self._add_message("WIPERS ON", 1.2)
                else:
                    self._add_message("WIPERS OFF", 1.2)

    def _update_race(self, dt, events, keys):
        self._process_race_keydowns(events)
        self.weather.update(dt)
        self._update_messages(dt)

        throttle = keys[pygame.K_UP] or keys[pygame.K_w]
        brake = keys[pygame.K_DOWN] or keys[pygame.K_s]
        steer = 0.0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            steer -= 1.0
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            steer += 1.0

        self.race_elapsed += dt

        # pit logic can lock the car for 10 seconds
        pit_message = self.pit_system.update(dt, self.player)
        if pit_message:
            self._add_message(pit_message, 2.0)

        allow_drive = not self.pit_system.active and not self.player.eliminated
        self.player.update_player(
            dt,
            self.track,
            self.weather,
            throttle,
            brake,
            steer,
            allow_drive,
            self.race_elapsed,
            traction_control=self.traction_control_enabled,
        )

        racers_for_ai = [self.player] + self.ai_cars
        for ai in self.ai_cars:
            ai.update_ai(dt, self.track, self.weather, racers_for_ai, self.race_elapsed)
            if ai.finished and not ai.finish_logged:
                ai.finish_logged = True
                self.ai_finish_log.append((ai.name, ai.finish_time))

        crashed = self.collision_system.update(self.player, self.ai_cars, self.track)
        if crashed:
            self.audio.play_crash()
            self._add_message("BOOM! CRASH!", 1.8)

        if self.player.eliminated and self.state == "race":
            self.state = "spectator"
            self.spectator_timer = 5.0
            self._add_message("ELIMINATED - SPECTATOR MODE", 2.5)

        # Checkpoint system
        new_checkpoint = int(self.player.total_distance / self.track.checkpoint_distance)
        while new_checkpoint > self.checkpoint_index:
            self.checkpoint_index += 1
            self.race_timer += CHECKPOINT_TIME_BONUS
            self.audio.play_checkpoint()
            self._add_message(f"CHECKPOINT +{int(CHECKPOINT_TIME_BONUS)}s", 1.4)

        # Nitro pickup (one each lap)
        lap = self.player.lap
        if lap in self.track.nitro_pickups and lap not in self.track.nitro_collected_laps:
            delta = signed_track_delta(self.track.nitro_pickups[lap], self.player.distance, self.track.length)
            if abs(delta) < 3.0 and abs(self.player.lane) < 0.85:
                self.track.nitro_collected_laps.add(lap)
                if self.player.transmission_mode == "manual":
                    self.player.grant_nitro()
                    self._add_message("NITRO PICKUP COLLECTED", 1.4)
                else:
                    self._add_message("AUTO MODE: NITRO DISABLED", 1.4)

        # race timer and fail states
        if self.state == "race":
            self.race_timer -= dt
            if self.race_timer <= 0:
                self._enter_post_race(dnf=True)
                return
            if self.player.stranded:
                self._enter_post_race(dnf=True)
                return

        self._compute_positions()

        throttle_audio = throttle and allow_drive and self.player.shift_penalty_timer <= 0.0
        engine_active = not self.player.eliminated and not self.player.finished
        self.audio.update_engine(
            self.player.rpm,
            throttle=throttle_audio,
            active=engine_active,
            crashed=self.player.crash_timer > 0,
            voice_id=self.player.engine_voice,
        )

        nearby_ai = None
        nearest_delta = float("inf")
        for ai in self.ai_cars:
            if ai.finished:
                continue
            delta = abs(signed_track_delta(ai.distance, self.player.distance, self.track.length))
            if delta < nearest_delta:
                nearest_delta = delta
                nearby_ai = ai
        if nearby_ai and nearest_delta < 95.0:
            proximity = 1.0 - clamp(nearest_delta / 95.0, 0.0, 1.0)
            self.audio.update_ai_engine(nearby_ai.rpm, throttle=True, active=True, voice_id=nearby_ai.engine_voice, proximity=proximity)
        else:
            self.audio.update_ai_engine(0.0, active=False)

        if self.player.finished:
            self._enter_post_race(dnf=False)

    def _update_spectator(self, dt, events):
        self.weather.update(dt)
        self._update_messages(dt)
        self.race_elapsed += dt

        racers = [self.player] + self.ai_cars
        for ai in self.ai_cars:
            ai.update_ai(dt, self.track, self.weather, racers, self.race_elapsed)
            if ai.finished and not ai.finish_logged:
                ai.finish_logged = True
                self.ai_finish_log.append((ai.name, ai.finish_time))

        self._compute_positions()
        leader = sorted(self.ai_cars, key=lambda car: car.progress, reverse=True)[0]
        self.audio.update_engine(leader.rpm, throttle=True, active=True, crashed=False, voice_id=leader.engine_voice)
        self.audio.update_ai_engine(0.0, active=False)
        self.spectator_timer -= dt
        done = self.spectator_timer <= 0
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                done = True
        if done:
            self._enter_post_race(dnf=True)

    def _update_name_entry(self, events):
        for event in events:
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_BACKSPACE:
                self.name_entry = self.name_entry[:-1]
            elif event.key == pygame.K_RETURN:
                name = self.name_entry.strip() or "LLM RACER"
                best_lap = min(self.player.lap_times) if self.player.lap_times else float("inf")
                self.leaderboard.append({"name": name[:16], "best_lap": best_lap})
                self.leaderboard.sort(key=lambda item: item["best_lap"])
                self.leaderboard = self.leaderboard[:10]
                self._save_leaderboard()
                self.state = "post_race"
            else:
                if event.unicode.isprintable() and len(self.name_entry) < 16:
                    self.name_entry += event.unicode

    def _update_post_race(self, events):
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                self.state = "menu"

    def update(self, dt, events, keys):
        self._handle_global_events(events)
        if not self.running:
            return

        if self.state == "intro":
            self._update_intro(dt, events)
            self.audio.update_engine(0.0, active=False)
            self.audio.update_ai_engine(0.0, active=False)
        elif self.state == "menu":
            self._update_menu(events)
            self.audio.update_engine(0.0, active=False)
            self.audio.update_ai_engine(0.0, active=False)
        elif self.state == "countdown":
            self._update_countdown(dt)
            self._update_messages(dt)
            self.weather.update(dt)
        elif self.state == "race":
            self._update_race(dt, events, keys)
        elif self.state == "spectator":
            self._update_spectator(dt, events)
        elif self.state == "name_entry":
            self._update_name_entry(events)
            self.audio.update_engine(0.0, active=False)
            self.audio.update_ai_engine(0.0, active=False)
        elif self.state == "post_race":
            self._update_post_race(events)
            self.audio.update_engine(0.0, active=False)
            self.audio.update_ai_engine(0.0, active=False)

    def _draw_intro(self):
        self.screen.fill((8, 12, 20))
        for y in range(0, HEIGHT, 4):
            c = 18 + int(22 * math.sin((self.intro_timer * 2.2) + y * 0.015))
            color = (
                clamp(c, 0, 255),
                clamp(c + 10, 0, 255),
                clamp(c + 26, 0, 255),
            )
            pygame.draw.line(self.screen, color, (0, y), (WIDTH, y))

        logo_font = pygame.font.Font(None, 84)
        sub_font = pygame.font.Font(None, 36)
        blink_font = pygame.font.Font(None, 44)

        title = logo_font.render("POLE POSITION RACER", True, (255, 228, 118))
        subtitle = sub_font.render("LLM RACER VERSION", True, (98, 226, 255))
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 220))
        self.screen.blit(subtitle, (WIDTH // 2 - subtitle.get_width() // 2, 292))

        if int(self.intro_timer * 2) % 2 == 0:
            blink = blink_font.render("PRESS ENTER TO START", True, (242, 242, 242))
            self.screen.blit(blink, (WIDTH // 2 - blink.get_width() // 2, 390))

        hint = sub_font.render("ARCADE SYNTH RACING CHAOS", True, (255, 124, 132))
        self.screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, 460))

    def _draw_menu(self):
        self.screen.fill((14, 20, 32))
        self.track.draw_background(self.screen, self.weather, self.race_elapsed, parallax_shift=0.0, speed_factor=0.0)

        panel = pygame.Rect(WIDTH // 2 - 300, 96, 600, 518)
        pygame.draw.rect(self.screen, (10, 14, 24, 210), panel, border_radius=10)
        pygame.draw.rect(self.screen, (224, 236, 245), panel, 2, border_radius=10)

        title_font = pygame.font.Font(None, 64)
        menu_font = pygame.font.Font(None, 42)
        small_font = pygame.font.Font(None, 28)

        title = title_font.render("POLE POSITION RACER", True, (255, 224, 114))
        subtitle = small_font.render("LLM RACER VERSION", True, (102, 226, 255))
        self.screen.blit(title, (panel.centerx - title.get_width() // 2, panel.y + 34))
        self.screen.blit(subtitle, (panel.centerx - subtitle.get_width() // 2, panel.y + 86))

        for idx, item in enumerate(self.menu_items):
            color = (255, 244, 126) if idx == self.menu_index else (244, 244, 244)
            suffix = ""
            if item == "TRANSMISSION":
                suffix = f": {self.transmission_setting.upper()}"
            elif item == "DEFAULT CAMERA":
                suffix = f": {self.default_camera_mode}"
            text = menu_font.render(item + suffix, True, color)
            self.screen.blit(text, (panel.x + 80, panel.y + 160 + idx * 66))

        controls = [
            "ARROWS / WASD - DRIVE",
            "LEFT SHIFT / RIGHT SHIFT - MANUAL GEARS",
            "INSERT - NITRO (MANUAL ONLY)",
            "SPACE - PIT STOP ENTRY (MANDATORY LAP 2)",
            "C - CAMERA TOGGLE   H - HEADLIGHTS   1 - WIPERS",
            "T - TRACTION CONTROL TOGGLE",
        ]
        for i, line in enumerate(controls):
            txt = small_font.render(line, True, (188, 212, 242))
            self.screen.blit(txt, (panel.x + 40, panel.y + 378 + i * 28))

        tc_state = "ON" if self.traction_control_enabled else "OFF"
        tc_color = (114, 246, 150) if self.traction_control_enabled else (255, 160, 120)
        tc_info = small_font.render(f"TRACTION CONTROL DEFAULT: {tc_state}", True, tc_color)
        self.screen.blit(tc_info, (panel.x + 40, panel.y + 548))

        sprite_state = "LOADED" if SpriteBank.loaded_path else "PROCEDURAL"
        sprite_color = (130, 236, 255) if SpriteBank.loaded_path else (196, 214, 232)
        sprite_info = small_font.render(f"SPRITESHEET: {sprite_state}", True, sprite_color)
        self.screen.blit(sprite_info, (panel.x + 352, panel.y + 548))

    def _draw_countdown_lights(self):
        center_x = WIDTH // 2
        y = 108
        colors = [(168, 36, 36), (188, 166, 30), (42, 196, 72)]
        active = 0
        if self.countdown_timer < 2.0:
            active = 1
        if self.countdown_timer < 1.0:
            active = 2
        for i in range(3):
            color = colors[i] if i == active else (46, 46, 46)
            pygame.draw.circle(self.screen, color, (center_x - 60 + i * 60, y), 20)
            pygame.draw.circle(self.screen, (230, 230, 230), (center_x - 60 + i * 60, y), 20, 2)

        count_num = max(1, int(math.ceil(self.countdown_timer)))
        if self.countdown_timer <= 0:
            label = "GO!"
            text_color = (90, 255, 126)
        else:
            label = str(count_num)
            text_color = (255, 234, 136)
        font = pygame.font.Font(None, 84)
        text = font.render(label, True, text_color)
        self.screen.blit(text, (WIDTH // 2 - text.get_width() // 2, 140))

    def _draw_explosion(self, x, y, timer):
        if SpriteBank.explosion_frames:
            progress = 1.0 - clamp(timer / 5.0, 0.0, 1.0)
            frame_idx = int(progress * (len(SpriteBank.explosion_frames) - 1))
            frame_idx = clamp(frame_idx, 0, len(SpriteBank.explosion_frames) - 1)
            frame = SpriteBank.explosion_frames[int(frame_idx)]
            scale = 1.0 + progress * 2.0
            w = max(24, int(frame.get_width() * scale))
            h = max(24, int(frame.get_height() * scale))
            img = pygame.transform.smoothscale(frame, (w, h))
            self.screen.blit(img, (int(x - w * 0.5), int(y - h * 0.5)))
            return

        progress = 1.0 - clamp(timer / 5.0, 0.0, 1.0)
        radius = int(38 + progress * 120)
        pygame.draw.circle(self.screen, (220, 28, 20), (int(x), int(y)), radius)
        pygame.draw.circle(self.screen, (246, 140, 34), (int(x), int(y)), max(8, int(radius * 0.62)))
        pygame.draw.circle(self.screen, (252, 242, 180), (int(x), int(y)), max(5, int(radius * 0.35)))
        for _ in range(8):
            angle = random.uniform(0, math.pi * 2.0)
            dist = random.uniform(radius * 0.5, radius * 1.0)
            px = int(x + math.cos(angle) * dist)
            py = int(y + math.sin(angle) * dist)
            pygame.draw.circle(self.screen, (255, 84, 40), (px, py), max(2, int(radius * 0.08)))

    def _draw_race(self, anchor_car):
        curve_now = self.track.curvature_at(anchor_car.distance + 20.0)
        parallax_shift = anchor_car.lane * 360.0 + curve_now * 520.0
        self.track.draw_background(
            self.screen,
            self.weather,
            self.race_elapsed,
            parallax_shift=parallax_shift,
            speed_factor=anchor_car.speed * 3.6,
        )
        bands = self.track.build_projection(self.camera.mode, anchor_car.distance, anchor_car.lane, self.weather)
        self.track.draw_road(self.screen, bands)
        self.track.draw_roadside(self.screen, bands, self.camera.mode, anchor_car.distance)
        self.track.draw_nitro_pickup(self.screen, bands, self.camera.mode, anchor_car.distance, self.player.lap)

        # draw AI + player depending on camera anchor
        racers = [self.player] + self.ai_cars
        drawables = []
        reverse = self.camera.mode == "REAR"
        for racer in racers:
            if racer is anchor_car:
                continue
            delta = signed_track_delta(racer.distance, anchor_car.distance, self.track.length)
            view_delta = -delta if reverse else delta
            if 1.5 < view_delta < bands[0]["ahead_far"]:
                proj = self.track.project_from_bands(view_delta, racer.lane, bands)
                if proj:
                    x, y, scale = proj
                    drawables.append((view_delta, racer, x, y, scale))

        drawables.sort(reverse=True, key=lambda item: item[0])
        for _, racer, x, y, scale in drawables:
            racer.draw(self.screen, x, y, scale, show_flames=False, show_backfire=racer.backfire_timer > 0)

        if anchor_car is self.player and self.camera.mode != "BUMPER":
            player_x = WIDTH // 2
            if self.camera.mode == "REAR":
                player_x = WIDTH // 2 + int(self.player.lane * 90)
            else:
                player_x = WIDTH // 2 - int(self.player.lane * 90)
            player_y = HEIGHT - 56
            self.player.draw(
                self.screen,
                player_x,
                player_y,
                1.85,
                show_flames=self.player.nitro_timer > 0,
                show_backfire=self.player.backfire_timer > 0,
            )
            if self.player.crash_timer > 0:
                self._draw_explosion(player_x, player_y - 40, self.player.crash_timer)

        if anchor_car is not self.player:
            label_font = pygame.font.Font(None, 36)
            txt = label_font.render("SPECTATOR MODE", True, (248, 236, 124))
            self.screen.blit(txt, (WIDTH // 2 - txt.get_width() // 2, 18))

        self.weather.draw_particles(self.screen)
        self.weather.draw_visibility_overlay(self.screen, self.player.wipers_on, self.player.headlights_on)
        self.hud.draw(self.screen, self)
        if self.pit_system.active:
            self.pit_system.draw_overlay(self.screen)

    def _draw_name_entry(self):
        self.screen.fill((10, 12, 18))
        title_font = pygame.font.Font(None, 62)
        med_font = pygame.font.Font(None, 40)
        small = pygame.font.Font(None, 30)

        title1 = title_font.render("CONGRATULATIONS YOU HAVE WON 1st PLACE!", True, (255, 232, 112))
        title2 = med_font.render("WINNER WINNER CHICKEN DINNER!", True, (126, 238, 255))
        self.screen.blit(title1, (WIDTH // 2 - title1.get_width() // 2, 120))
        self.screen.blit(title2, (WIDTH // 2 - title2.get_width() // 2, 184))

        prompt = med_font.render("ENTER YOUR NAME:", True, (240, 240, 240))
        self.screen.blit(prompt, (WIDTH // 2 - prompt.get_width() // 2, 294))

        box = pygame.Rect(WIDTH // 2 - 220, 344, 440, 54)
        pygame.draw.rect(self.screen, (20, 26, 40), box)
        pygame.draw.rect(self.screen, (255, 255, 255), box, 2)
        name_text = med_font.render(self.name_entry + ("_" if int(pygame.time.get_ticks() / 300) % 2 == 0 else ""), True, (252, 252, 252))
        self.screen.blit(name_text, (box.x + 14, box.y + 12))

        best_lap = min(self.player.lap_times) if self.player.lap_times else float("inf")
        info = small.render(f"BEST LAP: {format_time(best_lap)}", True, (190, 220, 245))
        self.screen.blit(info, (WIDTH // 2 - info.get_width() // 2, 430))

        hint = small.render("PRESS ENTER TO SAVE AND CONTINUE", True, (255, 212, 120))
        self.screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, 500))

    def _draw_post_race(self):
        self.screen.fill((10, 14, 22))
        title_font = pygame.font.Font(None, 64)
        med = pygame.font.Font(None, 34)
        small = pygame.font.Font(None, 26)

        if self.result_dnf:
            title = title_font.render("DNF - DID NOT FINISH", True, (255, 92, 92))
        elif self.player.position == 1:
            title = title_font.render("RACE COMPLETE - VICTORY!", True, (255, 228, 102))
        else:
            title = title_font.render("RACE COMPLETE", True, (220, 236, 248))
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 34))

        info = med.render(f"TOTAL RACE TIME: {format_time(self.race_elapsed)}", True, (188, 222, 248))
        self.screen.blit(info, (WIDTH // 2 - info.get_width() // 2, 96))

        order_panel = pygame.Rect(70, 140, 560, 480)
        pygame.draw.rect(self.screen, (18, 24, 36), order_panel)
        pygame.draw.rect(self.screen, (232, 240, 250), order_panel, 2)
        header = med.render("FINISHING ORDER", True, (255, 255, 255))
        self.screen.blit(header, (order_panel.centerx - header.get_width() // 2, order_panel.y + 12))

        for idx, (name, status, finish_time, car_ref) in enumerate(self.finish_order[:20]):
            y = order_panel.y + 56 + idx * 20
            label = f"{idx + 1:02d}. {name:<10} {status:<8} {format_time(finish_time)}"
            color = (255, 224, 122) if car_ref is self.player else (214, 228, 244)
            line = small.render(label, True, color)
            self.screen.blit(line, (order_panel.x + 14, y))

        stats_panel = pygame.Rect(670, 140, 540, 480)
        pygame.draw.rect(self.screen, (18, 24, 36), stats_panel)
        pygame.draw.rect(self.screen, (232, 240, 250), stats_panel, 2)
        stats_title = med.render("PLAYER LAP TIMES", True, (255, 255, 255))
        self.screen.blit(stats_title, (stats_panel.centerx - stats_title.get_width() // 2, stats_panel.y + 12))

        if self.player.lap_times:
            for i, lap_time in enumerate(self.player.lap_times[:TOTAL_LAPS]):
                line = small.render(f"LAP {i + 1}: {format_time(lap_time)}", True, (202, 240, 255))
                self.screen.blit(line, (stats_panel.x + 22, stats_panel.y + 60 + i * 28))
        else:
            line = small.render("NO COMPLETED LAPS", True, (220, 172, 172))
            self.screen.blit(line, (stats_panel.x + 22, stats_panel.y + 60))

        lb_title = med.render("BEST LAP LEADERBOARD", True, (255, 238, 144))
        self.screen.blit(lb_title, (stats_panel.x + 22, stats_panel.y + 220))
        for idx, row in enumerate(self.leaderboard[:8]):
            line = small.render(f"{idx + 1:02d}. {row['name']:<16} {format_time(row['best_lap'])}", True, (228, 236, 246))
            self.screen.blit(line, (stats_panel.x + 22, stats_panel.y + 260 + idx * 24))

        footer = small.render("PRESS ENTER TO RETURN TO MENU", True, (255, 214, 128))
        self.screen.blit(footer, (WIDTH // 2 - footer.get_width() // 2, HEIGHT - 42))

    def render(self):
        if self.state == "intro":
            self._draw_intro()
        elif self.state == "menu":
            self._draw_menu()
        elif self.state == "countdown":
            self._draw_race(self.player)
            self._draw_countdown_lights()
        elif self.state == "race":
            self._draw_race(self.player)
        elif self.state == "spectator":
            leader = sorted(self.ai_cars, key=lambda car: car.progress, reverse=True)[0]
            self._draw_race(leader)
        elif self.state == "name_entry":
            self._draw_name_entry()
        elif self.state == "post_race":
            self._draw_post_race()
        pygame.display.flip()

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            events = pygame.event.get()
            keys = pygame.key.get_pressed()
            self.update(dt, events, keys)
            self.render()
        pygame.quit()
        return 0


def main():
    game = PolePositionRacerGame()
    return game.run()


if __name__ == "__main__":
    sys.exit(main())
