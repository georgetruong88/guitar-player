#!/usr/bin/env python3
"""
Guitar Player - strum chords and pick single strings with your laptop keyboard.

Controls:
  1-9, 0, -, =      -> select chord: G C D Em Am E A Dm F Bm C7 G7
  `                 -> Open (all strings open, no chord held)
  Space             -> strum down (low string to high, like a real downstroke)
  Enter             -> strum up (high string to low)
  Q W E R T Y       -> pick a single string (low E, A, D, G, B, high e)
  [ / ]             -> capo down / up (0-12 frets)
  V                 -> toggle acoustic / electric (distorted) tone
  Up / Down         -> volume up / down
  M                 -> mute / unmute
  Esc               -> quit
"""

import os
import time
from collections import deque

# Disable IME hooking for this process only, before SDL/X11 init - see
# keyboard-piano's piano.py for why: input methods that treat plain letters
# as compose keys can silently swallow KEYDOWN events before pygame sees them.
os.environ["XMODIFIERS"] = "@im=none"
os.environ["SDL_IME_SHOW_UI"] = "0"

import numpy as np
import pygame

# ---------------------------------------------------------------- audio ----

SAMPLE_RATE = 44100
pygame.mixer.pre_init(frequency=SAMPLE_RATE, size=-16, channels=1, buffer=256)
pygame.init()
pygame.mixer.set_num_channels(32)

# Standard tuning, low string to high string.
STRING_NAMES = ["E", "A", "D", "G", "B", "e"]
STRING_OPEN_FREQS = [82.41, 110.00, 146.83, 196.00, 246.94, 329.63]
N_STRINGS = len(STRING_OPEN_FREQS)

STRING_PICK_KEYS = [pygame.K_q, pygame.K_w, pygame.K_e, pygame.K_r, pygame.K_t, pygame.K_y]

STRUM_DOWN_KEY = pygame.K_SPACE
STRUM_UP_KEY = pygame.K_RETURN
STRUM_STAGGER = 0.028  # seconds between successive strings in a strum

# Chord shapes: fret per string, low E -> high e. None means muted (not played).
CHORDS = {
    pygame.K_1: ("G", [3, 2, 0, 0, 0, 3]),
    pygame.K_2: ("C", [None, 3, 2, 0, 1, 0]),
    pygame.K_3: ("D", [None, None, 0, 2, 3, 2]),
    pygame.K_4: ("Em", [0, 2, 2, 0, 0, 0]),
    pygame.K_5: ("Am", [None, 0, 2, 2, 1, 0]),
    pygame.K_6: ("E", [0, 2, 2, 1, 0, 0]),
    pygame.K_7: ("A", [None, 0, 2, 2, 2, 0]),
    pygame.K_8: ("Dm", [None, None, 0, 2, 3, 1]),
    pygame.K_9: ("F", [None, None, 3, 2, 1, 1]),
    pygame.K_0: ("Bm", [None, 2, 4, 4, 3, 2]),
    pygame.K_MINUS: ("C7", [None, 3, 2, 3, 1, 0]),
    pygame.K_EQUALS: ("G7", [3, 2, 0, 0, 0, 1]),
}
OPEN_CHORD_KEY = pygame.K_BACKQUOTE
OPEN_SHAPE = [0, 0, 0, 0, 0, 0]
OPEN_NAME = "Open"

MAX_FRET_DISPLAY = 4  # chord diagram shows frets 0..4 (fits every shape above)
MAX_CAPO = 12


def string_freq(string_index, fret, capo):
    """Frequency for a string fretted at `fret` (0 = open) with a capo offset."""
    semitones = fret + capo
    return STRING_OPEN_FREQS[string_index] * (2 ** (semitones / 12))


def karplus_strong_core(freq, duration, decay=0.996, damping=0.5):
    """Plucked-string model: a decaying noise loop through a lowpass filter."""
    n_samples = int(SAMPLE_RATE * duration)
    period = max(2, int(round(SAMPLE_RATE / freq)))
    buf = deque(np.random.uniform(-1, 1, period))
    out = np.empty(n_samples)
    for i in range(n_samples):
        out[i] = buf[0]
        avg = decay * (damping * buf[0] + (1 - damping) * buf[1])
        buf.append(avg)
        buf.popleft()
    return out


def make_acoustic_wave(freq, duration):
    out = karplus_strong_core(freq, duration, decay=0.996, damping=0.5)
    n_samples = len(out)
    attack = int(0.002 * SAMPLE_RATE)
    envelope = np.ones(n_samples)
    envelope[:attack] = np.linspace(0, 1, attack)
    wave = out * envelope
    peak = np.max(np.abs(wave)) or 1.0
    audio = (wave / peak * 0.5 * 32767).astype(np.int16)
    return pygame.sndarray.make_sound(audio)


def make_electric_wave(freq, duration):
    """Overdriven electric tone: the same plucked string pushed through tanh
    waveshaping for distortion grit, plus a thin amp-fizz noise layer, with
    a bit more sustain than the clean tone (distortion compresses/sustains)."""
    out = karplus_strong_core(freq, duration, decay=0.9975, damping=0.42)
    n_samples = len(out)
    t = np.linspace(0, duration, n_samples, endpoint=False)
    driven = np.tanh(out * 6.0)
    fizz = np.random.uniform(-1, 1, n_samples) * 0.03 * np.exp(-2.0 * t / duration)
    wave = driven * 0.8 + fizz

    attack = int(0.001 * SAMPLE_RATE)
    envelope = np.ones(n_samples)
    envelope[:attack] = np.linspace(0, 1, attack)
    wave *= envelope
    peak = np.max(np.abs(wave)) or 1.0
    audio = (wave / peak * 0.55 * 32767).astype(np.int16)
    return pygame.sndarray.make_sound(audio)


def make_wave(freq, duration, electric):
    return make_electric_wave(freq, duration) if electric else make_acoustic_wave(freq, duration)


_sound_cache = {}


def get_string_sound(string_index, fret, capo, electric, sustain):
    duration = 2.6 if sustain else 1.4
    key = (string_index, fret, capo, electric, sustain)
    snd = _sound_cache.get(key)
    if snd is None:
        freq = string_freq(string_index, fret, capo)
        snd = make_wave(freq, duration, electric)
        _sound_cache[key] = snd
    return snd


def play_note(snd, volume, muted):
    channel = snd.play()
    if channel is not None:
        channel.set_volume(0.0 if muted else volume)
    return channel


# ------------------------------------------------------------------ UI -----

WIDTH, HEIGHT = 900, 520
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Guitar Player")
clock = pygame.time.Clock()
font_big = pygame.font.SysFont("dejavusans", 48)
font_mid = pygame.font.SysFont("dejavusans", 24)
font_small = pygame.font.SysFont("dejavusans", 18)

BG = (24, 24, 28)
TEXT = (230, 230, 230)
ACCENT = (120, 200, 255)
STRING_COLOR = (200, 200, 205)
STRING_FLASH_COLOR = (255, 210, 90)
FRET_COLOR = (90, 90, 96)
NUT_COLOR = (230, 230, 230)
DOT_COLOR = (120, 200, 255)
MUTE_MARK_COLOR = (220, 90, 90)
OPEN_MARK_COLOR = (120, 220, 140)

DIAGRAM_X, DIAGRAM_Y = 300, 200
DIAGRAM_W, DIAGRAM_H = 300, 220
STRING_GAP = DIAGRAM_W / (N_STRINGS - 1)
FRET_GAP = DIAGRAM_H / MAX_FRET_DISPLAY


def draw_chord_diagram(shape, string_flash, now):
    # nut / fret lines
    for f in range(MAX_FRET_DISPLAY + 1):
        y = DIAGRAM_Y + f * FRET_GAP
        color = NUT_COLOR if f == 0 else FRET_COLOR
        thickness = 4 if f == 0 else 2
        pygame.draw.line(screen, color, (DIAGRAM_X, y), (DIAGRAM_X + DIAGRAM_W, y), thickness)

    # strings (vertical)
    for i in range(N_STRINGS):
        x = DIAGRAM_X + i * STRING_GAP
        flash_until = string_flash.get(i, 0.0)
        color = STRING_FLASH_COLOR if now < flash_until else STRING_COLOR
        thickness = 3 if i in (0, N_STRINGS - 1) else 2
        pygame.draw.line(screen, color, (x, DIAGRAM_Y), (x, DIAGRAM_Y + DIAGRAM_H), thickness)
        label = font_small.render(STRING_NAMES[i], True, (150, 150, 150))
        screen.blit(label, (x - label.get_width() / 2, DIAGRAM_Y + DIAGRAM_H + 8))

    # per-string marker: X (muted), O (open), or a fretted dot
    for i, fret in enumerate(shape):
        x = DIAGRAM_X + i * STRING_GAP
        if fret is None:
            mark = font_mid.render("X", True, MUTE_MARK_COLOR)
            screen.blit(mark, (x - mark.get_width() / 2, DIAGRAM_Y - 34))
        elif fret == 0:
            mark = font_mid.render("O", True, OPEN_MARK_COLOR)
            screen.blit(mark, (x - mark.get_width() / 2, DIAGRAM_Y - 34))
        else:
            y = DIAGRAM_Y + (fret - 0.5) * FRET_GAP
            flash_until = string_flash.get(i, 0.0)
            dot_color = STRING_FLASH_COLOR if now < flash_until else DOT_COLOR
            pygame.draw.circle(screen, dot_color, (int(x), int(y)), 12)


def draw_volume(volume, muted):
    bar_w, bar_h = 120, 14
    x, y = WIDTH - 40 - bar_w, 28
    pygame.draw.rect(screen, (60, 60, 65), (x, y, bar_w, bar_h), border_radius=4)
    fill_w = 0 if muted else int(bar_w * volume)
    fill_color = (200, 90, 90) if muted else ACCENT
    if fill_w > 0:
        pygame.draw.rect(screen, fill_color, (x, y, fill_w, bar_h), border_radius=4)
    pygame.draw.rect(screen, (10, 10, 10), (x, y, bar_w, bar_h), 2, border_radius=4)
    icon = "MUTE" if muted else "VOL"
    label = font_small.render(icon, True, (150, 150, 150))
    screen.blit(label, (x - label.get_width() - 10, y - 2))


def main():
    chord_name = OPEN_NAME
    shape = list(OPEN_SHAPE)
    capo = 0
    electric = False
    volume = 0.8
    muted = False
    sustain = True

    string_flash = {}  # string_index -> time.time() when highlight should clear
    pending_strums = []  # list of dicts: time, string, fret

    last_action_text = ""

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                elif event.key == OPEN_CHORD_KEY:
                    chord_name, shape = OPEN_NAME, list(OPEN_SHAPE)
                    last_action_text = "Open"

                elif event.key in CHORDS:
                    chord_name, shape = CHORDS[event.key]
                    shape = list(shape)
                    last_action_text = chord_name

                elif event.key == pygame.K_LEFTBRACKET:
                    capo = max(0, capo - 1)
                elif event.key == pygame.K_RIGHTBRACKET:
                    capo = min(MAX_CAPO, capo + 1)

                elif event.key == pygame.K_v:
                    electric = not electric

                elif event.key == pygame.K_UP:
                    volume = min(1.0, round(volume + 0.1, 2))
                elif event.key == pygame.K_DOWN:
                    volume = max(0.0, round(volume - 0.1, 2))
                elif event.key == pygame.K_m:
                    muted = not muted

                elif event.key in STRING_PICK_KEYS:
                    i = STRING_PICK_KEYS.index(event.key)
                    fret = shape[i]
                    if fret is not None:
                        snd = get_string_sound(i, fret, capo, electric, sustain)
                        play_note(snd, volume, muted)
                        string_flash[i] = time.time() + 0.2
                        last_action_text = f"{STRING_NAMES[i]} string, fret {fret + capo}"

                elif event.key in (STRUM_DOWN_KEY, STRUM_UP_KEY):
                    order = range(N_STRINGS) if event.key == STRUM_DOWN_KEY else range(N_STRINGS - 1, -1, -1)
                    now = time.time()
                    step = 0
                    for i in order:
                        fret = shape[i]
                        if fret is None:
                            continue
                        pending_strums.append({"time": now + step * STRUM_STAGGER, "string": i, "fret": fret})
                        step += 1
                    direction = "down" if event.key == STRUM_DOWN_KEY else "up"
                    last_action_text = f"{chord_name} (strum {direction})"

        now = time.time()

        still_pending = []
        for strum in pending_strums:
            if now >= strum["time"]:
                snd = get_string_sound(strum["string"], strum["fret"], capo, electric, sustain)
                play_note(snd, volume, muted)
                string_flash[strum["string"]] = now + 0.2
            else:
                still_pending.append(strum)
        pending_strums = still_pending

        string_flash = {i: t for i, t in string_flash.items() if t > now}

        screen.fill(BG)

        title = font_mid.render("Guitar Player", True, ACCENT)
        screen.blit(title, (40, 20))

        action_surf = font_big.render(last_action_text or "-", True, TEXT)
        screen.blit(action_surf, (40, 60))

        vol_text = "MUTED" if muted else f"{int(volume * 100)}%"
        status = (
            f"Chord: {chord_name}   Capo: {capo}   "
            f"Tone: {'electric' if electric else 'acoustic'}   Vol: {vol_text}"
        )
        status_surf = font_small.render(status, True, TEXT)
        screen.blit(status_surf, (40, 125))

        draw_chord_diagram(shape, string_flash, now)

        help_line1 = font_small.render(
            "1-9/0/-/= chord (G C D Em Am E A Dm F Bm C7 G7)   |   ` open   |   Space strum down   |   Enter strum up",
            True,
            (150, 150, 150),
        )
        help_line2 = font_small.render(
            "Q W E R T Y pick a string   |   [/] capo   |   V acoustic/electric   |   Up/Down volume   |   M mute   |   Esc quit",
            True,
            (150, 150, 150),
        )
        screen.blit(help_line1, (40, 460))
        screen.blit(help_line2, (40, 484))

        draw_volume(volume, muted)

        pygame.display.flip()
        clock.tick(120)

    pygame.quit()


if __name__ == "__main__":
    main()
