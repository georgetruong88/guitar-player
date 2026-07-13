"""Drives the real main() event loop with synthetic pygame events - the same
technique used manually throughout development to verify features live.
Covers the interactive loop's branches without needing to refactor main()
into smaller testable pieces."""

import threading
import time

import pygame

import guitar


def post(key, down=True, mod=0):
    ev = pygame.event.Event(pygame.KEYDOWN if down else pygame.KEYUP, key=key, mod=mod, unicode="")
    pygame.event.post(ev)


def tap(key, mod=0):
    post(key, True, mod)
    post(key, False)


def test_main_loop_exercises_full_event_handling(monkeypatch):
    # main() calls pygame.quit() on exit, which would tear down the shared
    # mixer/display for every other test in this process - no-op it here.
    monkeypatch.setattr(guitar.pygame, "quit", lambda: None)

    def driver():
        time.sleep(0.15)

        # open strings, then every chord shape (including ones with muted
        # strings, e.g. C/D/Am/A/Dm/F/Bm/C7)
        tap(guitar.OPEN_CHORD_KEY)
        for key in guitar.CHORDS:
            tap(key)

        # capo up/down
        tap(pygame.K_RIGHTBRACKET)
        tap(pygame.K_LEFTBRACKET)

        # tone toggle
        tap(pygame.K_v)
        tap(pygame.K_v)

        # volume / mute
        tap(pygame.K_UP)
        tap(pygame.K_DOWN)
        tap(pygame.K_m)
        tap(pygame.K_m)  # unmute again

        # pick every string under the current (last-selected) chord
        for key in guitar.STRING_PICK_KEYS:
            tap(key)

        # select a chord with a muted string, then pick that muted string -
        # exercises the "fret is None" skip branch in the pick handler
        c_key = next(k for k, (name, _shape) in guitar.CHORDS.items() if name == "C")
        tap(c_key)
        tap(guitar.STRING_PICK_KEYS[0])  # low E is muted in the C shape

        # strum down, then up, giving the main loop time to drain the
        # staggered pending_strums queue across several frames
        tap(guitar.STRUM_DOWN_KEY)
        time.sleep(0.25)
        tap(guitar.STRUM_UP_KEY)
        time.sleep(0.25)

        time.sleep(0.1)
        post(pygame.K_ESCAPE, True)

    t = threading.Thread(target=driver, daemon=True)
    t.start()
    guitar.main()
    t.join(timeout=2)
    assert not t.is_alive()


def test_main_loop_handles_quit_event(monkeypatch):
    monkeypatch.setattr(guitar.pygame, "quit", lambda: None)

    def driver():
        time.sleep(0.1)
        pygame.event.post(pygame.event.Event(pygame.QUIT))

    t = threading.Thread(target=driver, daemon=True)
    t.start()
    guitar.main()
    t.join(timeout=2)
    assert not t.is_alive()
