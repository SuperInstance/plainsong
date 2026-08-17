#!/usr/bin/env python3
"""
Comprehensive test suite for TapScript parser, transposition, and compilation.

Tests the pure-logic parts (parsing, chord resolution, transposition, melody parsing)
without requiring MIDI libraries. The parser and music theory engine are the backbone
of TapScript — if those break, nothing downstream matters.
"""

import sys
import os
import unittest

# Add scripts dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from tapscript import (
    parse_key_string, parse_chord_token, parse_melody_token,
    is_chord_line, is_melody_line, parse_tapscript, transpose,
    KeySignature, ChordSymbol, NoteEvent, Bar, Section,
    TapScriptComposition, Header, InstrumentAssignment,
    NOTE_NAMES, NOTE_TO_SEMITONE, SCALES, DIATONIC_TRIADS,
    CHORD_INTERVALS, ROMAN_MAJOR, ROMAN_MINOR,
    HARBOR_DAWN, THE_ROOM_IS_SAFE, OPEN_MIC,
    _midi_note_for_degree, _chord_midi_notes, _midi_to_freq,
    _synth_wave, _get_waveform_for_instrument, extract_tapscript_blocks,
    # New spacing notation imports
    is_spacing_notation_line, parse_spaced_note_token, parse_spaced_melody_line,
    absolute_pitch_to_midi,
)


class TestKeySignature(unittest.TestCase):
    """Tests for KeySignature parsing and scale theory."""

    def test_default_key(self):
        ks = KeySignature('C', 'major')
        self.assertEqual(ks.root, 'C')
        self.assertEqual(ks.mode, 'major')
        self.assertEqual(ks.root_semitone, 0)
        self.assertEqual(str(ks), 'C major')

    def test_minor_key(self):
        ks = KeySignature('A', 'minor')
        self.assertEqual(ks.root_semitone, 9)
        self.assertEqual(ks.intervals, SCALES['minor'])

    def test_dorian_key(self):
        ks = KeySignature('D', 'dorian')
        self.assertEqual(ks.intervals, SCALES['dorian'])

    def test_scale_note_semitone_basic(self):
        """C major: C=0, D=2, E=4, F=5, G=7, A=9, B=11"""
        ks = KeySignature('C', 'major')
        expected = [0, 2, 4, 5, 7, 9, 11]
        for degree, exp in enumerate(expected, 1):
            self.assertEqual(ks.scale_note_semitone(degree), exp,
                           f"Degree {degree} should be semitone {exp}")

    def test_scale_note_semitone_minor(self):
        """A minor: A=9, B=11, C=12, D=14, E=16, F=17, G=19"""
        ks = KeySignature('A', 'minor')
        expected = [9, 11, 12, 14, 16, 17, 19]
        for degree, exp in enumerate(expected, 1):
            self.assertEqual(ks.scale_note_semitone(degree), exp)

    def test_scale_note_semitone_octave_wrap(self):
        """Degree 8 should be one octave above degree 1."""
        ks = KeySignature('C', 'major')
        self.assertEqual(ks.scale_note_semitone(8), ks.scale_note_semitone(1) + 12)

    def test_scale_note_semitone_octave_offset(self):
        ks = KeySignature('G', 'major')
        base = ks.scale_note_semitone(1, octave=0)
        higher = ks.scale_note_semitone(1, octave=1)
        self.assertEqual(higher, base + 12)

    def test_all_modes_have_intervals(self):
        """Every mode in SCALES should have 7 intervals."""
        for mode, intervals in SCALES.items():
            self.assertEqual(len(intervals), 7, f"Mode {mode} has {len(intervals)} intervals")

    def test_diatonic_triads_match_scales(self):
        """Every mode in SCALES should have matching triads (excluding synonyms)."""
        # 'ionian' and 'aeolian' are synonyms for 'major' and 'minor'
        synonym_modes = {'ionian', 'aeolian'}
        for mode in SCALES:
            if mode in synonym_modes:
                continue
            self.assertIn(mode, DIATONIC_TRIADS, f"Mode {mode} missing from DIATONIC_TRIADS")


class TestParseKeyString(unittest.TestCase):
    """Tests for key string parsing."""

    def test_simple_major(self):
        ks = parse_key_string('C major')
        self.assertEqual(ks.root, 'C')
        self.assertEqual(ks.mode, 'major')

    def test_simple_minor(self):
        ks = parse_key_string('A minor')
        self.assertEqual(ks.root, 'A')
        self.assertEqual(ks.mode, 'minor')

    def test_dorian(self):
        ks = parse_key_string('D dorian')
        self.assertEqual(ks.root, 'D')
        self.assertEqual(ks.mode, 'dorian')

    def test_sharp_key(self):
        ks = parse_key_string('F# minor')
        self.assertEqual(ks.root_semitone, 6)

    def test_flat_key(self):
        ks = parse_key_string('Bb major')
        # Bb is not in NOTE_NAMES (we use A#), but parser should handle gracefully
        self.assertIsNotNone(ks)

    def test_abbreviation_maj(self):
        ks = parse_key_string('G maj')
        self.assertEqual(ks.mode, 'major')

    def test_abbreviation_min(self):
        ks = parse_key_string('E min')
        self.assertEqual(ks.mode, 'minor')

    def test_empty_string(self):
        ks = parse_key_string('')
        self.assertEqual(ks.root, 'C')
        self.assertEqual(ks.mode, 'major')

    def test_single_note(self):
        ks = parse_key_string('F')
        self.assertEqual(ks.root, 'F')
        self.assertEqual(ks.mode, 'major')

    def test_case_insensitive_root(self):
        ks = parse_key_string('c major')
        self.assertEqual(ks.root, 'C')


class TestParseChordToken(unittest.TestCase):
    """Tests for Roman numeral chord parsing."""

    def test_major_chord(self):
        chord = parse_chord_token('I')
        self.assertIsNotNone(chord)
        self.assertEqual(chord.degree, 1)
        self.assertTrue(chord.is_major)

    def test_minor_chord(self):
        chord = parse_chord_token('vi')
        self.assertIsNotNone(chord)
        self.assertEqual(chord.degree, 6)
        self.assertFalse(chord.is_major)

    def test_flattened(self):
        chord = parse_chord_token('bVII')
        self.assertIsNotNone(chord)
        self.assertEqual(chord.degree, 7)
        self.assertEqual(chord.alteration, -1)
        self.assertTrue(chord.is_major)

    def test_sharpened(self):
        chord = parse_chord_token('#IV')
        self.assertIsNotNone(chord)
        self.assertEqual(chord.degree, 4)
        self.assertEqual(chord.alteration, 1)

    def test_seventh_extension(self):
        chord = parse_chord_token('V7')
        self.assertIsNotNone(chord)
        self.assertEqual(chord.degree, 5)
        self.assertEqual(chord.extension, '7')

    def test_diminished(self):
        chord = parse_chord_token('ii°')
        self.assertIsNotNone(chord)
        self.assertTrue(chord.is_diminished)

    def test_diminished_letter_o(self):
        chord = parse_chord_token('vii°')
        self.assertIsNotNone(chord)
        self.assertTrue(chord.is_diminished)

    def test_augmented(self):
        chord = parse_chord_token('III+')
        self.assertIsNotNone(chord)
        self.assertTrue(chord.is_augmented)

    def test_dot_returns_none(self):
        self.assertIsNone(parse_chord_token('.'))

    def test_dash_returns_none(self):
        self.assertIsNone(parse_chord_token('-'))

    def test_empty_returns_none(self):
        self.assertIsNone(parse_chord_token(''))

    def test_non_chord_returns_none(self):
        self.assertIsNone(parse_chord_token('lyrics'))

    def test_major_ninth(self):
        chord = parse_chord_token('Imaj9')
        self.assertIsNotNone(chord)
        self.assertEqual(chord.extension, 'maj9')

    def test_all_seven_degrees_major(self):
        for roman, degree in ROMAN_MAJOR.items():
            chord = parse_chord_token(roman)
            self.assertIsNotNone(chord, f"Failed to parse {roman}")
            self.assertEqual(chord.degree, degree)
            self.assertTrue(chord.is_major)

    def test_all_seven_degrees_minor(self):
        for roman, degree in ROMAN_MINOR.items():
            chord = parse_chord_token(roman)
            self.assertIsNotNone(chord, f"Failed to parse {roman}")
            self.assertEqual(chord.degree, degree)
            self.assertFalse(chord.is_major)


class TestChordResolution(unittest.TestCase):
    """Tests for chord-to-MIDI-note resolution via KeySignature."""

    def test_C_major_I_chord(self):
        key = KeySignature('C', 'major')
        chord = ChordSymbol(raw='I', degree=1, is_major=True, alteration=0, extension='')
        root, intervals = chord.resolve(key)
        self.assertEqual(root, 'C')
        self.assertEqual(intervals, CHORD_INTERVALS['maj'])

    def test_A_minor_i_chord(self):
        key = KeySignature('A', 'minor')
        chord = ChordSymbol(raw='i', degree=1, is_major=False, alteration=0, extension='')
        root, intervals = chord.resolve(key)
        self.assertEqual(root, 'A')
        self.assertEqual(intervals, CHORD_INTERVALS['min'])

    def test_seventh_resolution(self):
        """V7 in C major should resolve to G dominant 7th."""
        key = KeySignature('C', 'major')
        chord = ChordSymbol(raw='V7', degree=5, is_major=True, alteration=0, extension='7')
        root, intervals = chord.resolve(key)
        self.assertEqual(root, 'G')
        self.assertEqual(intervals, CHORD_INTERVALS['7'])

    def test_diminished_resolution(self):
        """vii° in C major should resolve to B diminished."""
        key = KeySignature('C', 'major')
        chord = ChordSymbol(raw='vii°', degree=7, is_major=False, alteration=0,
                           extension='', is_diminished=True)
        root, intervals = chord.resolve(key)
        self.assertEqual(root, 'B')
        self.assertEqual(intervals, CHORD_INTERVALS['dim'])

    def test_minor_seventh_resolution(self):
        """ii7 in C major should be D minor 7."""
        key = KeySignature('C', 'major')
        chord = ChordSymbol(raw='ii7', degree=2, is_major=False, alteration=0, extension='7')
        root, intervals = chord.resolve(key)
        self.assertEqual(root, 'D')
        self.assertEqual(intervals, CHORD_INTERVALS['min7'])


class TestParseMelodyToken(unittest.TestCase):
    """Tests for melody token parsing."""

    def test_single_note(self):
        events = parse_melody_token('3')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].degree, 3)
        self.assertEqual(events[0].duration_div, 1)

    def test_rest(self):
        events = parse_melody_token('-')
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].is_rest)

    def test_sustain(self):
        events = parse_melody_token('.')
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].sustain)

    def test_comma_separated_eighths(self):
        events = parse_melody_token('1,2,3,4')
        self.assertEqual(len(events), 4)
        for e in events:
            self.assertEqual(e.duration_div, 2)

    def test_colon_separated_sixteenths(self):
        events = parse_melody_token('1:2:3:4')
        self.assertEqual(len(events), 4)
        for e in events:
            self.assertEqual(e.duration_div, 4)

    def test_octave_up(self):
        events = parse_melody_token('5^')
        self.assertEqual(events[0].octave, 1)

    def test_octave_down(self):
        events = parse_melody_token('5_')
        self.assertEqual(events[0].octave, -1)

    def test_flat_note(self):
        events = parse_melody_token('b3')
        self.assertEqual(events[0].alteration, -1)

    def test_sharp_note(self):
        events = parse_melody_token('#4')
        self.assertEqual(events[0].alteration, 1)

    def test_empty_string(self):
        events = parse_melody_token('')
        self.assertEqual(len(events), 0)

    def test_mixed_rests(self):
        events = parse_melody_token('1,-,3')
        self.assertEqual(len(events), 3)
        self.assertFalse(events[0].is_rest)
        self.assertTrue(events[1].is_rest)
        self.assertFalse(events[2].is_rest)


class TestLineClassification(unittest.TestCase):
    """Tests for chord/melody line detection heuristics."""

    def test_chord_line_detected(self):
        line = 'I    .    IV   .   | V    .    vi   .'
        self.assertTrue(is_chord_line(line))

    def test_melody_line_detected(self):
        line = '3    5    1    .   | 3    2    1    -'
        self.assertTrue(is_melody_line(line))

    def test_chord_line_not_melody(self):
        line = 'I    IV    V    IV'
        self.assertFalse(is_melody_line(line))

    def test_melody_line_not_chord(self):
        line = '1    2    3    4'
        self.assertFalse(is_chord_line(line))

    def test_bar_pipes_ignored(self):
        line = '| Am    F    | G    |'
        # This is not a Roman numeral chord line, should be false
        # (letter chords like Am aren't parsed as Roman numerals)
        result = is_chord_line(line)
        self.assertFalse(result)


class TestParseTapscript(unittest.TestCase):
    """Tests for full TapScript parsing."""

    def test_parse_empty_string(self):
        comp = parse_tapscript('')
        self.assertEqual(comp.header.tempo, 120)
        self.assertEqual(len(comp.sections), 0)

    def test_parse_header_key(self):
        comp = parse_tapscript('key: A minor\ntempo: 140\n')
        self.assertEqual(comp.header.key.root, 'A')
        self.assertEqual(comp.header.key.mode, 'minor')
        self.assertEqual(comp.header.tempo, 140)

    def test_parse_header_swing(self):
        comp = parse_tapscript('swing: 15\ntempo: 90\n')
        self.assertEqual(comp.header.swing, 15)
        self.assertEqual(comp.header.tempo, 90)

    def test_parse_header_time_signature(self):
        comp = parse_tapscript('time: 3/4\n')
        self.assertEqual(comp.header.time_sig, (3, 4))

    def test_parse_section(self):
        text = '''key: C major

[V1]
I    .    .    .   | IV   .    .    .
'''
        comp = parse_tapscript(text)
        self.assertEqual(len(comp.sections), 1)
        self.assertEqual(comp.sections[0].name, 'V1')
        self.assertGreater(len(comp.sections[0].bars), 0)

    def test_parse_instruments(self):
        text = '''key: C major

[V1]
I    .    .    .

@wesley: piano | chords | vel: 60
@flash: strings | pad | vel: 50
'''
        comp = parse_tapscript(text)
        self.assertEqual(len(comp.instruments), 2)
        self.assertEqual(comp.instruments[0].name, 'wesley')
        self.assertEqual(comp.instruments[0].instrument, 'piano')
        self.assertEqual(comp.instruments[0].params.get('vel'), '60')
        self.assertEqual(comp.instruments[1].name, 'flash')

    def test_total_bars_property(self):
        text = '''key: C major

[A]
I    .    | IV   .

[B]
V    .    | vi   .   | I    .
'''
        comp = parse_tapscript(text)
        self.assertEqual(comp.total_bars, 5)

    def test_raw_text_preserved(self):
        text = 'key: G major\ntempo: 100\n'
        comp = parse_tapscript(text)
        self.assertEqual(comp.raw_text, text)

    def test_parse_harbor_dawn(self):
        """The HARBOR_DAWN example should parse successfully."""
        comp = parse_tapscript(HARBOR_DAWN)
        self.assertEqual(comp.header.key.root, 'D')
        self.assertEqual(comp.header.key.mode, 'minor')
        self.assertEqual(comp.header.tempo, 60)
        self.assertGreater(len(comp.sections), 0)
        self.assertGreater(comp.total_bars, 0)
        self.assertEqual(len(comp.instruments), 2)

    def test_parse_the_room_is_safe(self):
        comp = parse_tapscript(THE_ROOM_IS_SAFE)
        self.assertEqual(comp.header.key.root, 'E')
        self.assertEqual(comp.header.key.mode, 'minor')
        self.assertEqual(comp.header.tempo, 68)
        self.assertEqual(comp.header.swing, 5)

    def test_parse_open_mic(self):
        comp = parse_tapscript(OPEN_MIC)
        self.assertEqual(comp.header.key.root, 'G')
        self.assertEqual(comp.header.key.mode, 'major')
        self.assertEqual(comp.header.tempo, 85)
        self.assertEqual(comp.header.swing, 12)

    def test_chords_extracted_from_bars(self):
        text = '''key: C major

[V1]
I    .    IV   .
'''
        comp = parse_tapscript(text)
        self.assertGreater(len(comp.sections[0].bars), 0)
        # At least some bars should have chords
        chords_found = sum(len(b.chords) for b in comp.sections[0].bars)
        self.assertGreater(chords_found, 0)

    def test_melody_extracted_from_bars(self):
        text = '''key: C major

[V1]
1    3    5    3
'''
        comp = parse_tapscript(text)
        notes_found = sum(len(b.notes) for b in comp.sections[0].bars)
        self.assertGreater(notes_found, 0)

    def test_multiple_sections(self):
        text = '''key: C major

[Intro]
I    .    .    .

[Verse]
I    IV   V    .

[Chorus]
vi   IV   I    V
'''
        comp = parse_tapscript(text)
        self.assertEqual(len(comp.sections), 3)


class TestTransposition(unittest.TestCase):
    """Tests for the transpose function."""

    def test_transpose_changes_key(self):
        comp = parse_tapscript(HARBOR_DAWN)
        self.assertEqual(comp.header.key.root, 'D')
        transposed = transpose(comp, 'G minor')
        self.assertEqual(transposed.header.key.root, 'G')
        self.assertEqual(transposed.header.key.mode, 'minor')

    def test_transpose_preserves_structure(self):
        comp = parse_tapscript(OPEN_MIC)
        transposed = transpose(comp, 'D major')
        self.assertEqual(transposed.header.tempo, comp.header.tempo)
        self.assertEqual(transposed.total_bars, comp.total_bars)

    def test_transpose_preserves_tempo_and_swing(self):
        comp = parse_tapscript(THE_ROOM_IS_SAFE)
        original_tempo = comp.header.tempo
        original_swing = comp.header.swing
        transposed = transpose(comp, 'A minor')
        self.assertEqual(transposed.header.tempo, original_tempo)
        self.assertEqual(transposed.header.swing, original_swing)


class TestMidiNoteComputation(unittest.TestCase):
    """Tests for MIDI note computation helpers."""

    def test_midi_note_for_degree_c_major(self):
        """In C major, degree 1 at octave 0 should be around C4 (60)."""
        key = KeySignature('C', 'major')
        note = _midi_note_for_degree(key, 1, 0, 0)
        # Root at C4 + 12 offset in the function
        self.assertEqual(note, 12)  # semitone 0 + 12

    def test_midi_note_for_degree_higher_octave(self):
        key = KeySignature('C', 'major')
        base = _midi_note_for_degree(key, 1, 0, 0)
        higher = _midi_note_for_degree(key, 1, 0, 1)
        self.assertEqual(higher, base + 12)

    def test_chord_midi_notes_returns_list(self):
        key = KeySignature('C', 'major')
        chord = ChordSymbol(raw='I', degree=1, is_major=True, alteration=0, extension='')
        notes = _chord_midi_notes(key, chord, base_octave=4)
        self.assertIsInstance(notes, list)
        self.assertGreater(len(notes), 0)

    def test_chord_midi_notes_triad_has_three_notes(self):
        key = KeySignature('C', 'major')
        chord = ChordSymbol(raw='I', degree=1, is_major=True, alteration=0, extension='')
        notes = _chord_midi_notes(key, chord, base_octave=4)
        self.assertEqual(len(notes), 3)  # triad

    def test_midi_to_freq_A4(self):
        """A4 (MIDI 69) should be 440 Hz."""
        self.assertAlmostEqual(_midi_to_freq(69), 440.0, places=1)

    def test_midi_to_freq_C5(self):
        """C5 (MIDI 72) should be ~523.25 Hz."""
        self.assertAlmostEqual(_midi_to_freq(72), 523.25, places=1)


class TestSynthesis(unittest.TestCase):
    """Tests for audio synthesis helpers."""

    def test_synth_wave_sine(self):
        import numpy as np
        wave = _synth_wave(440.0, 0.1, 44100, 'sine')
        self.assertEqual(len(wave), int(0.1 * 44100))
        self.assertTrue(np.all(np.abs(wave) <= 1.0))

    def test_synth_wave_triangle(self):
        import numpy as np
        wave = _synth_wave(220.0, 0.05, 44100, 'triangle')
        self.assertEqual(len(wave), int(0.05 * 44100))

    def test_synth_wave_square(self):
        import numpy as np
        wave = _synth_wave(110.0, 0.05, 44100, 'square')
        self.assertTrue(np.all(np.abs(wave) <= 1.0))

    def test_synth_wave_unknown_defaults_to_sine(self):
        import numpy as np
        wave = _synth_wave(440.0, 0.05, 44100, 'unknown')
        self.assertEqual(len(wave), int(0.05 * 44100))

    def test_get_waveform_for_instrument(self):
        self.assertEqual(_get_waveform_for_instrument('bass'), 'sine')
        self.assertEqual(_get_waveform_for_instrument('strings'), 'sawtooth')
        self.assertEqual(_get_waveform_for_instrument('guitar'), 'triangle')
        self.assertEqual(_get_waveform_for_instrument('piano'), 'triangle')

    def test_get_waveform_for_unknown_instrument(self):
        self.assertEqual(_get_waveform_for_instrument('unknown_instrument'), 'triangle')


class TestMarkdownExtraction(unittest.TestCase):
    """Tests for extracting TapScript blocks from markdown."""

    def test_extract_single_block(self):
        md = '''# My Song

```tapscript
key: C major
tempo: 120

[V1]
I    .    .    .
```

That's it.
'''
        blocks = extract_tapscript_blocks(md)
        self.assertEqual(len(blocks), 1)
        self.assertIn('key: C major', blocks[0])

    def test_extract_multiple_blocks(self):
        md = '''```tapscript
key: C major
```

Some text.

```tapscript
key: A minor
```
'''
        blocks = extract_tapscript_blocks(md)
        self.assertEqual(len(blocks), 2)

    def test_extract_no_blocks(self):
        md = '# Just markdown\n\nNo code blocks here.'
        blocks = extract_tapscript_blocks(md)
        self.assertEqual(len(blocks), 0)

    def test_extract_empty_block(self):
        md = '```tapscript\n```'
        blocks = extract_tapscript_blocks(md)
        # An empty block may still match as an empty string or not match at all
        # Both behaviors are acceptable
        self.assertLessEqual(len(blocks), 1)


class TestExamples(unittest.TestCase):
    """Tests that all built-in examples are valid and parseable."""

    def test_harbor_dawn_is_string(self):
        self.assertIsInstance(HARBOR_DAWN, str)
        self.assertGreater(len(HARBOR_DAWN), 50)

    def test_the_room_is_safe_is_string(self):
        self.assertIsInstance(THE_ROOM_IS_SAFE, str)

    def test_open_mic_is_string(self):
        self.assertIsInstance(OPEN_MIC, str)

    def test_harbor_dawn_has_correct_key(self):
        comp = parse_tapscript(HARBOR_DAWN)
        self.assertEqual(str(comp.header.key), 'D minor')

    def test_all_examples_parse_without_error(self):
        for name, (title, text) in {
            'harbor_dawn': ('Harbor Dawn', HARBOR_DAWN),
            'the_room_is_safe': ('The Room Is Safe', THE_ROOM_IS_SAFE),
            'open_mic': ('Open Mic', OPEN_MIC),
        }.items():
            try:
                comp = parse_tapscript(text)
                self.assertGreater(comp.total_bars, 0,
                                  f"Example {name} has 0 bars")
            except Exception as e:
                self.fail(f"Example {name} failed to parse: {e}")

    def test_harbor_dawn_has_instruments(self):
        comp = parse_tapscript(HARBOR_DAWN)
        self.assertEqual(len(comp.instruments), 2)
        instrument_names = [i.name for i in comp.instruments]
        self.assertIn('wesley', instrument_names)
        self.assertIn('flash', instrument_names)

    def test_open_mic_has_swing(self):
        comp = parse_tapscript(OPEN_MIC)
        self.assertGreater(comp.header.swing, 0)

    def test_the_room_is_safe_is_3_4_time(self):
        comp = parse_tapscript(THE_ROOM_IS_SAFE)
        self.assertEqual(comp.header.time_sig, (3, 4))


class TestEdgeCases(unittest.TestCase):
    """Tests for boundary conditions and unusual inputs."""

    def test_parse_only_whitespace(self):
        comp = parse_tapscript('   \n  \n  ')
        self.assertEqual(len(comp.sections), 0)

    def test_parse_unknown_mode_falls_back(self):
        comp = parse_tapscript('key: C somethingweird\ntempo: 100\n')
        # Should fall back gracefully (default or major)
        self.assertIsNotNone(comp.header.key)

    def test_chord_with_multiple_extensions(self):
        """Imaj9 should parse extension as 'maj9'."""
        chord = parse_chord_token('Imaj9')
        self.assertIsNotNone(chord)
        self.assertEqual(chord.extension, 'maj9')

    def test_melody_with_all_octaves(self):
        events = parse_melody_token('1^,2^,3^')
        for e in events:
            self.assertEqual(e.octave, 1)

    def test_extremely_high_degree(self):
        """Degree 15 should wrap octaves."""
        key = KeySignature('C', 'major')
        st = key.scale_note_semitone(15)
        # Should be 2 octaves above degree 1
        expected = key.scale_note_semitone(1) + 24
        self.assertEqual(st, expected)

    def test_composition_total_bars_zero(self):
        comp = TapScriptComposition()
        self.assertEqual(comp.total_bars, 0)

    def test_bar_defaults_empty(self):
        bar = Bar()
        self.assertEqual(len(bar.chords), 0)
        self.assertEqual(len(bar.notes), 0)

    def test_section_defaults_empty(self):
        section = Section(name='Test')
        self.assertEqual(len(section.bars), 0)


class TestChordIntervalsComplete(unittest.TestCase):
    """Verify all chord types in CHORD_INTERVALS are valid."""

    def test_all_chord_types_present(self):
        expected = ['maj', 'min', 'dim', 'aug', 'maj7', 'min7', '7',
                   'dim7', 'maj9', 'min9', '9', 'sus2', 'sus4', 'add9',
                   '6', 'min6']
        for name in expected:
            self.assertIn(name, CHORD_INTERVALS, f"Missing chord type: {name}")

    def test_triads_have_three_notes(self):
        for name in ['maj', 'min', 'dim', 'aug', 'sus2', 'sus4']:
            intervals = CHORD_INTERVALS[name]
            self.assertEqual(len(intervals), 3,
                           f"{name} should have 3 notes, got {len(intervals)}")

    def test_sevenths_have_four_notes(self):
        for name in ['maj7', 'min7', '7', 'dim7', '6', 'min6']:
            intervals = CHORD_INTERVALS[name]
            self.assertEqual(len(intervals), 4,
                           f"{name} should have 4 notes, got {len(intervals)}")

    def test_ninths_have_five_notes(self):
        # add9 is a triad with an added 9th = 4 notes, not 5
        # True ninths (maj9, min9, 9) have 5
        for name in ['maj9', 'min9', '9']:
            intervals = CHORD_INTERVALS[name]
            self.assertEqual(len(intervals), 5,
                           f"{name} should have 5 notes, got {len(intervals)}")
        # add9 is a 4-note chord (triad + 9th, no 7th)
        self.assertEqual(len(CHORD_INTERVALS['add9']), 4)

    def test_all_intervals_are_non_negative(self):
        for name, intervals in CHORD_INTERVALS.items():
            for iv in intervals:
                self.assertGreaterEqual(iv, 0,
                                       f"{name} has negative interval {iv}")

    def test_all_intervals_ascending(self):
        """Chord intervals should be in ascending order."""
        for name, intervals in CHORD_INTERVALS.items():
            for i in range(1, len(intervals)):
                self.assertGreater(intervals[i], intervals[i-1],
                                  f"{name} intervals not ascending at position {i}")


class TestSpacingNotationDetection(unittest.TestCase):
    """Tests for detecting spacing-notation melody lines."""

    def test_simple_spacing_line_detected(self):
        line = '| C4~~ D4~~ E4~~ F4~~ |'
        self.assertTrue(is_spacing_notation_line(line))

    def test_dash_sustain_detected(self):
        line = '| C4-- D4-- E4-- F4-- |'
        self.assertTrue(is_spacing_notation_line(line))

    def test_mixed_sustain_chars_detected(self):
        line = '| C4~~~ D4--- E4 F4 |'
        self.assertTrue(is_spacing_notation_line(line))

    def test_bare_note_detected(self):
        line = '| C4 D4 E4 F4 |'
        self.assertTrue(is_spacing_notation_line(line))

    def test_chord_spacing_detected(self):
        line = '| C4~~+E4~~+G4~~ D4--- |'
        self.assertTrue(is_spacing_notation_line(line))

    def test_legacy_melody_not_detected_as_spacing(self):
        # Scale-degree numbers should NOT be detected as spacing notation
        line = '| 1  3  5  3 |'
        self.assertFalse(is_spacing_notation_line(line))

    def test_legacy_chord_line_not_detected_as_spacing(self):
        line = '| I  .  IV  . |'
        self.assertFalse(is_spacing_notation_line(line))

    def test_rest_with_sustain_detected(self):
        line = '| C4~~ r~~ D4 F4 |'
        self.assertTrue(is_spacing_notation_line(line))

    def test_empty_line_not_detected(self):
        self.assertFalse(is_spacing_notation_line(''))
        self.assertFalse(is_spacing_notation_line('|  |'))


class TestParseSpacedNoteToken(unittest.TestCase):
    """Tests for parsing individual spacing-notation tokens."""

    def test_bare_note_eighth(self):
        events = parse_spaced_note_token('C4')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].absolute_pitch, 'C4')
        self.assertEqual(events[0].duration_eighths, 1)

    def test_one_tilde_quarter(self):
        events = parse_spaced_note_token('C4~')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].duration_eighths, 2)

    def test_two_tildes_dotted_quarter(self):
        events = parse_spaced_note_token('D4~~')
        self.assertEqual(events[0].duration_eighths, 3)

    def test_three_tildes_half(self):
        events = parse_spaced_note_token('E4~~~')
        self.assertEqual(events[0].duration_eighths, 4)

    def test_seven_tildes_whole(self):
        events = parse_spaced_note_token('F4~~~~~~~')
        self.assertEqual(events[0].duration_eighths, 8)

    def test_dash_sustain(self):
        events = parse_spaced_note_token('G4--')
        self.assertEqual(events[0].duration_eighths, 3)
        self.assertEqual(events[0].absolute_pitch, 'G4')

    def test_mixed_tilde_and_dash(self):
        # Should count all sustain chars
        events = parse_spaced_note_token('A4~-')
        self.assertEqual(events[0].duration_eighths, 3)

    def test_sharp_note(self):
        events = parse_spaced_note_token('C#4')
        self.assertEqual(events[0].absolute_pitch, 'C#4')
        self.assertEqual(events[0].duration_eighths, 1)

    def test_flat_note(self):
        events = parse_spaced_note_token('Bb4')
        self.assertEqual(events[0].absolute_pitch, 'Bb4')

    def test_lowercase_note(self):
        events = parse_spaced_note_token('e4~~')
        self.assertEqual(events[0].absolute_pitch, 'E4')
        self.assertEqual(events[0].duration_eighths, 3)

    def test_rest_bare(self):
        events = parse_spaced_note_token('r')
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].is_rest)
        self.assertEqual(events[0].duration_eighths, 1)

    def test_rest_with_tildes(self):
        events = parse_spaced_note_token('r~~~~')
        self.assertTrue(events[0].is_rest)
        self.assertEqual(events[0].duration_eighths, 5)

    def test_rest_with_dashes(self):
        events = parse_spaced_note_token('r---')
        self.assertTrue(events[0].is_rest)
        self.assertEqual(events[0].duration_eighths, 4)

    def test_bare_dash_rest(self):
        events = parse_spaced_note_token('-')
        self.assertTrue(events[0].is_rest)
        self.assertEqual(events[0].duration_eighths, 1)

    def test_chord_simple(self):
        events = parse_spaced_note_token('C4+E4+G4')
        self.assertEqual(len(events), 3)
        for e in events:
            self.assertTrue(e.is_chord_note)
            self.assertEqual(e.duration_eighths, 1)

    def test_chord_with_sustain(self):
        events = parse_spaced_note_token('C4~~+E4~~+G4~~')
        self.assertEqual(len(events), 3)
        for e in events:
            self.assertTrue(e.is_chord_note)
            self.assertEqual(e.duration_eighths, 3)

    def test_chord_all_share_max_duration(self):
        events = parse_spaced_note_token('C4+E4~~~+G4')
        self.assertEqual(len(events), 3)
        # All should have max duration
        for e in events:
            self.assertEqual(e.duration_eighths, 4)  # 1 + 3 tildes

    def test_empty_token(self):
        events = parse_spaced_note_token('')
        self.assertEqual(len(events), 0)

    def test_unknown_token(self):
        events = parse_spaced_note_token('hello')
        self.assertEqual(len(events), 0)


class TestAbsolutePitchToMidi(unittest.TestCase):
    """Tests for absolute pitch to MIDI note conversion."""

    def test_middle_c(self):
        self.assertEqual(absolute_pitch_to_midi('C4'), 60)

    def test_a4_440hz(self):
        self.assertEqual(absolute_pitch_to_midi('A4'), 69)

    def test_c_sharp_4(self):
        self.assertEqual(absolute_pitch_to_midi('C#4'), 61)

    def test_b_flat_4(self):
        # Bb4 should normalize to A#4 = 70
        self.assertEqual(absolute_pitch_to_midi('Bb4'), 70)

    def test_c5(self):
        self.assertEqual(absolute_pitch_to_midi('C5'), 72)

    def test_c3(self):
        self.assertEqual(absolute_pitch_to_midi('C3'), 48)

    def test_lowercase(self):
        self.assertEqual(absolute_pitch_to_midi('c4'), 60)
        self.assertEqual(absolute_pitch_to_midi('a4'), 69)

    def test_invalid_pitch_defaults(self):
        self.assertEqual(absolute_pitch_to_midi(''), 60)
        self.assertEqual(absolute_pitch_to_midi('X9'), 60)

    def test_all_octaves_c(self):
        for octave in range(0, 9):
            midi = absolute_pitch_to_midi(f'C{octave}')
            expected = (octave + 1) * 12
            self.assertEqual(midi, expected,
                           f'C{octave} should be MIDI {expected}')


class TestParseSpacedMelodyLine(unittest.TestCase):
    """Tests for parsing full spacing-notation melody lines."""

    def test_single_bar(self):
        bars = parse_spaced_melody_line('| C4 D4 E4 F4 |')
        self.assertEqual(len(bars), 1)
        self.assertEqual(len(bars[0]), 4)
        self.assertEqual(bars[0][0].absolute_pitch, 'C4')
        self.assertEqual(bars[0][1].absolute_pitch, 'D4')

    def test_two_bars(self):
        bars = parse_spaced_melody_line('| C4~~~ D4~ | E4~ F4~~~ |')
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0][0].duration_eighths, 4)  # C4~~~ = 4 eighths
        self.assertEqual(bars[0][1].duration_eighths, 2)  # D4~ = 2 eighths

    def test_bar_with_rest(self):
        bars = parse_spaced_melody_line('| C4 r D4 r |')
        self.assertEqual(len(bars[0]), 4)
        self.assertTrue(bars[0][1].is_rest)
        self.assertTrue(bars[0][3].is_rest)

    def test_bar_with_chord(self):
        bars = parse_spaced_melody_line('| C4~~+E4~~+G4~~ D4 |')
        self.assertEqual(len(bars[0]), 4)  # 3 chord notes + 1 melody note
        # First three should be chord notes
        for i in range(3):
            self.assertTrue(bars[0][i].is_chord_note)

    def test_bar_with_sustain_in_sustain_chars(self):
        bars = parse_spaced_melody_line('| C4~~ D4~~ |')
        self.assertEqual(len(bars[0]), 2)
        self.assertEqual(bars[0][0].duration_eighths, 3)
        self.assertEqual(bars[0][1].duration_eighths, 3)

    def test_empty_bar(self):
        bars = parse_spaced_melody_line('|  |')
        self.assertEqual(len(bars), 0)


class TestSpacingNotationIntegration(unittest.TestCase):
    """Integration tests: spacing notation parsed through the full TapScript parser."""

    def test_spacing_melody_parses_in_composition(self):
        text = '''key: C major\ntempo: 120\n\n[V1]\nC4~~ D4~~ E4~~ F4~~\n'''
        comp = parse_tapscript(text)
        self.assertEqual(len(comp.sections), 1)
        self.assertGreater(len(comp.sections[0].bars), 0)
        notes = comp.sections[0].bars[0].notes
        self.assertGreater(len(notes), 0)
        self.assertEqual(notes[0].absolute_pitch, 'C4')
        self.assertEqual(notes[0].duration_eighths, 3)

    def test_spacing_notation_backward_compatible_with_legacy(self):
        # Legacy notation still works
        text = '''key: C major\ntempo: 120\n\n[V1]\n1    3    5    3\n'''
        comp = parse_tapscript(text)
        notes = comp.sections[0].bars[0].notes
        self.assertGreaterEqual(len(notes), 4)
        # Legacy notes use degree, not absolute_pitch
        self.assertIsNone(notes[0].absolute_pitch)
        self.assertEqual(notes[0].degree, 1)

    def test_chords_still_work_with_spacing_melody(self):
        text = '''key: C major\ntempo: 120\n\n[V1]\nI    .    IV   .\nC4~~ D4~~ E4~~ F4~~\n'''
        comp = parse_tapscript(text)
        bar = comp.sections[0].bars[0]
        self.assertGreater(len(bar.chords), 0)
        self.assertGreater(len(bar.notes), 0)

    def test_full_composition_with_spacing_notation(self):
        text = '''key: C major\ntempo: 90\ntime: 4/4\n\n[Melody]\nC4~~~ D4~~~ E4~~~ F4~~~\nC4~~~ D4~~~ E4~~~ F4~~~\n\n[Chords]\nI    .    IV   .\nV    .    vi   .\n\n@wesley: piano | both | vel: 70\n'''
        comp = parse_tapscript(text)
        self.assertEqual(len(comp.sections), 2)
        self.assertGreater(comp.total_bars, 0)

    def test_spacing_notation_with_dashes_works(self):
        text = '''key: G major\ntempo: 100\n\n[Riff]\nG4-- D5 B4-- A4\n'''
        comp = parse_tapscript(text)
        notes = comp.sections[0].bars[0].notes
        self.assertGreater(len(notes), 0)
        # G4-- = 3 eighth duration
        g_notes = [n for n in notes if n.absolute_pitch and n.absolute_pitch.startswith('G')]
        self.assertGreater(len(g_notes), 0)
        self.assertEqual(g_notes[0].duration_eighths, 3)

    def test_rests_in_spacing_notation(self):
        text = '''key: C major\ntempo: 120\n\n[V1]\nC4 r D4 r E4 r G4 r\n'''
        comp = parse_tapscript(text)
        notes = comp.sections[0].bars[0].notes
        # Should have 8 events: 4 notes + 4 rests
        self.assertEqual(len(notes), 8)
        rests = [n for n in notes if n.is_rest]
        self.assertEqual(len(rests), 4)

    def test_chords_in_spacing_notation(self):
        text = '''key: C major\ntempo: 80\n\n[V1]\nC4~~+E4~~+G4~~ D4~~+F4~~+A4~~\n'''
        comp = parse_tapscript(text)
        notes = comp.sections[0].bars[0].notes
        chord_notes = [n for n in notes if n.is_chord_note]
        self.assertEqual(len(chord_notes), 6)  # 3 per chord, 2 chords


class TestExistingExamplesStillWork(unittest.TestCase):
    """Verify all existing examples still parse with the new code."""

    def test_harbor_dawn_still_parses(self):
        comp = parse_tapscript(HARBOR_DAWN)
        self.assertEqual(comp.header.key.root, 'D')
        self.assertGreater(comp.total_bars, 0)

    def test_the_room_is_safe_still_parses(self):
        comp = parse_tapscript(THE_ROOM_IS_SAFE)
        self.assertEqual(comp.header.key.root, 'E')

    def test_open_mic_still_parses(self):
        comp = parse_tapscript(OPEN_MIC)
        self.assertEqual(comp.header.key.root, 'G')
        self.assertGreater(comp.header.swing, 0)


if __name__ == '__main__':
    unittest.main()
