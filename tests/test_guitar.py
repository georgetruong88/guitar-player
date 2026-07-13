import numpy as np
import pytest

import guitar


# --------------------------------------------------------------- pitch math

def test_string_freq_open_low_e():
    assert guitar.string_freq(0, 0, 0) == pytest.approx(82.41, abs=0.01)


def test_string_freq_open_high_e():
    assert guitar.string_freq(5, 0, 0) == pytest.approx(329.63, abs=0.01)


def test_string_freq_fret_raises_pitch_by_semitones():
    open_freq = guitar.string_freq(0, 0, 0)
    fretted = guitar.string_freq(0, 12, 0)
    assert fretted == pytest.approx(open_freq * 2, rel=1e-6)


def test_string_freq_capo_adds_to_fret():
    assert guitar.string_freq(0, 2, 3) == pytest.approx(guitar.string_freq(0, 5, 0), rel=1e-6)


# -------------------------------------------------------------------- chords

def test_every_chord_shape_has_one_entry_per_string():
    for name, shape in guitar.CHORDS.values():
        assert len(shape) == guitar.N_STRINGS, f"{name} shape has wrong length"


def test_every_chord_fret_within_display_window():
    for name, shape in guitar.CHORDS.values():
        for fret in shape:
            if fret is not None:
                assert 0 <= fret <= guitar.MAX_FRET_DISPLAY, f"{name} fret {fret} out of range"


def test_open_shape_has_no_muted_strings():
    assert all(fret == 0 for fret in guitar.OPEN_SHAPE)


def test_chord_keys_are_unique():
    assert len(guitar.CHORDS) == len(set(guitar.CHORDS.keys()))


def test_string_pick_keys_match_string_count():
    assert len(guitar.STRING_PICK_KEYS) == guitar.N_STRINGS


# ------------------------------------------------------------- sound synth

def test_karplus_strong_core_output_shape_and_bounds():
    out = guitar.karplus_strong_core(220.0, 0.1)
    assert isinstance(out, np.ndarray)
    assert len(out) == int(guitar.SAMPLE_RATE * 0.1)
    assert np.max(np.abs(out)) <= 1.0 + 1e-6


def test_make_wave_acoustic_and_electric_produce_sound():
    for electric in (False, True):
        snd = guitar.make_wave(guitar.string_freq(0, 0, 0), 0.2, electric)
        assert snd is not None
        assert snd.get_length() > 0


def test_get_string_sound_is_cached():
    guitar._sound_cache.clear()
    snd1 = guitar.get_string_sound(0, 0, 0, False, True)
    snd2 = guitar.get_string_sound(0, 0, 0, False, True)
    assert snd1 is snd2
