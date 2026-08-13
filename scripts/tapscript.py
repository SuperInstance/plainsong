#!/usr/bin/env python3
"""
TapScript — Plain-text music notation parser, compiler, and web renderer.

A notation system designed to be embedded in markdown, readable by humans,
theoretically sound (Roman numerals + scale degrees), instantly transposable,
and compilable to MIDI and WAV.

Usage:
    python tapscript.py              # start web server on port 5557
    python tapscript.py --cli file.ts --midi out.mid --wav out.wav
    python tapscript.py --example harbor_dawn --wav harbor.wav
"""

import re
import os
import sys
import json
import math
import struct
import wave
import hashlib
import argparse
import tempfile
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Union
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PORT = 5557
OUTPUT_DIR = Path.home() / ".openclaw" / "workspace" / "output" / "audio"
SF2_PATH = Path.home() / ".sounds" / "sf2" / "General.sf2"

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
NOTE_TO_SEMITONE = {n: i for i, n in enumerate(NOTE_NAMES)}

# Scale intervals (semitones from root for each degree)
SCALES = {
    'major':       [0, 2, 4, 5, 7, 9, 11],
    'ionian':      [0, 2, 4, 5, 7, 9, 11],
    'minor':       [0, 2, 3, 5, 7, 8, 10],
    'aeolian':     [0, 2, 3, 5, 7, 8, 10],
    'dorian':      [0, 2, 3, 5, 7, 9, 10],
    'phrygian':    [0, 1, 3, 5, 7, 8, 10],
    'lydian':      [0, 2, 4, 6, 7, 9, 11],
    'mixolydian':  [0, 2, 4, 5, 7, 9, 10],
    'locrian':     [0, 1, 3, 5, 6, 8, 10],
    'harmonic_minor':  [0, 2, 3, 5, 7, 8, 11],
    'melodic_minor':   [0, 2, 3, 5, 7, 9, 11],
}

# Diatonic chord qualities per scale degree (for triads)
# Each entry: (quality, intervals_from_root)
# quality: 'maj', 'min', 'dim', 'aug'
DIATONIC_TRIADS = {
    'major':    ['maj', 'min', 'min', 'maj', 'maj', 'min', 'dim'],
    'minor':    ['min', 'dim', 'maj', 'min', 'min', 'maj', 'maj'],
    'dorian':   ['min', 'min', 'maj', 'maj', 'min', 'dim', 'maj'],
    'phrygian': ['min', 'maj', 'maj', 'min', 'dim', 'maj', 'min'],
    'lydian':   ['maj', 'maj', 'min', 'dim', 'maj', 'min', 'min'],
    'mixolydian':['maj','min','dim','maj','min','min','maj'],
    'locrian':  ['dim', 'maj', 'min', 'min', 'dim', 'maj', 'maj'],
    'harmonic_minor':  ['min', 'dim', 'aug', 'min', 'maj', 'maj', 'dim'],
    'melodic_minor':   ['min', 'min', 'aug', 'maj', 'maj', 'dim', 'dim'],
}

CHORD_INTERVALS = {
    'maj': [0, 4, 7],
    'min': [0, 3, 7],
    'dim': [0, 3, 6],
    'aug': [0, 4, 8],
    'maj7': [0, 4, 7, 11],
    'min7': [0, 3, 7, 10],
    '7':   [0, 4, 7, 10],
    'dim7': [0, 3, 6, 9],
    'maj9': [0, 4, 7, 11, 14],
    'min9': [0, 3, 7, 10, 14],
    '9':   [0, 4, 7, 10, 14],
    'sus2': [0, 2, 7],
    'sus4': [0, 5, 7],
    'add9': [0, 4, 7, 14],
    '6':   [0, 4, 7, 9],
    'min6': [0, 3, 7, 9],
}

# MIDI note: C4 = 60 (middle C).  We use A4=69 standard tuning.
MIDDLE_C = 60

# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class KeySignature:
    root: str          # e.g. "A", "F#"
    mode: str          # e.g. "minor", "major", "dorian"

    @property
    def root_semitone(self) -> int:
        return NOTE_TO_SEMITONE[self.root]

    @property
    def intervals(self) -> List[int]:
        return SCALES.get(self.mode, SCALES['major'])

    @property
    def triad_qualities(self) -> List[str]:
        return DIATONIC_TRIADS.get(self.mode, DIATONIC_TRIADS['major'])

    def scale_note_semitone(self, degree: int, octave: int = 0) -> int:
        """Return absolute semitone for a scale degree (1-7) with octave offset."""
        idx = (degree - 1) % 7
        octave_offset = (degree - 1) // 7
        base = self.root_semitone + self.intervals[idx]
        return base + (octave + octave_offset) * 12

    def __str__(self):
        return f"{self.root} {self.mode}"


@dataclass
class Header:
    key: KeySignature = field(default_factory=lambda: KeySignature('C', 'major'))
    tempo: int = 120
    swing: int = 0
    time_sig: Tuple[int, int] = (4, 4)


@dataclass
class ChordSymbol:
    """A parsed chord: Roman numeral, quality, extensions, etc."""
    raw: str
    degree: int           # 1-7
    is_major: bool        # True if uppercase / major quality
    alteration: int       # semitone alteration (b=-1, #=+1, 0=none)
    extension: str        # '', '7', 'maj7', '9', etc.
    is_diminished: bool = False
    is_augmented: bool = False

    def resolve(self, key: KeySignature) -> Tuple[str, List[int]]:
        """Return (root_note_name, list of MIDI intervals)."""
        qualities = key.triad_qualities
        diatonic_quality = qualities[(self.degree - 1) % 7]

        # Determine quality from notation
        if self.is_diminished:
            quality_name = 'dim'
        elif self.is_augmented:
            quality_name = 'aug'
        elif self.is_major:
            quality_name = 'maj'
        else:
            quality_name = 'min'

        # Apply extension overrides
        if self.extension:
            ext_lower = self.extension.lower()
            if ext_lower == '7':
                if quality_name == 'maj':
                    quality_name = '7'  # dominant 7th on major
                elif quality_name == 'min':
                    quality_name = 'min7'
                else:
                    quality_name = 'dim7'
            elif ext_lower == 'maj7':
                if quality_name in ('maj', '7'):
                    quality_name = 'maj7'
                else:
                    quality_name = 'maj7'
            elif ext_lower == '9':
                if quality_name in ('maj', '7'):
                    quality_name = '9'
                else:
                    quality_name = 'min9'
            elif ext_lower in CHORD_INTERVALS:
                quality_name = ext_lower

        # Root semitone
        root_st = key.scale_note_semitone(self.degree, 0) + self.alteration
        root_name = NOTE_NAMES[root_st % 12]
        intervals = CHORD_INTERVALS.get(quality_name, CHORD_INTERVALS[quality_name if quality_name in CHORD_INTERVALS else 'maj'])
        return root_name, intervals


@dataclass
class NoteEvent:
    """A parsed melody note."""
    degree: int           # scale degree 1-7
    alteration: int       # chromatic alteration
    octave: int           # -1, 0, +1
    duration_div: int     # duration divisor: 1=quarter, 2=eighth, 4=sixteenth
    is_rest: bool = False
    sustain: bool = False  # '.' = hold previous


@dataclass
class Bar:
    chords: List[ChordSymbol] = field(default_factory=list)
    notes: List[NoteEvent] = field(default_factory=list)


@dataclass
class Section:
    name: str
    bars: List[Bar] = field(default_factory=list)


@dataclass
class InstrumentAssignment:
    name: str
    instrument: str
    role: str
    params: Dict[str, str] = field(default_factory=dict)


@dataclass
class TapScriptComposition:
    header: Header = field(default_factory=Header)
    sections: List[Section] = field(default_factory=list)
    instruments: List[InstrumentAssignment] = field(default_factory=list)
    raw_text: str = ""

    @property
    def total_bars(self) -> int:
        return sum(len(s.bars) for s in self.sections)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

ROMAN_MAJOR = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7}
ROMAN_MINOR = {'i': 1, 'ii': 2, 'iii': 3, 'iv': 4, 'v': 5, 'vi': 6, 'vii': 7}


def parse_key_string(s: str) -> KeySignature:
    """Parse 'A minor', 'F# mixolydian', 'Bb major', etc."""
    parts = s.strip().split()
    if not parts:
        return KeySignature('C', 'major')
    root = parts[0].capitalize()
    # Normalize flats/sharps
    root = root.replace('b', 'b').replace('#', '#')
    # Handle plain note names
    if root not in NOTE_NAMES:
        # Try to resolve
        for name in NOTE_NAMES:
            if name.lower() == root.lower():
                root = name
                break
    mode = 'major'
    if len(parts) > 1:
        m = parts[1].lower()
        if m in SCALES:
            mode = m
        elif m in ('maj',):
            mode = 'major'
        elif m in ('min',):
            mode = 'minor'
    return KeySignature(root, mode)


def parse_chord_token(token: str) -> Optional[ChordSymbol]:
    """Parse a single chord token like 'IV7', 'bVII', 'vi°', 'ii'. Returns None for non-chord tokens."""
    if not token or token == '.' or token == '-':
        return None

    orig = token
    alteration = 0
    # Check for b or # prefix
    if token[0] == 'b':
        alteration = -1
        token = token[1:]
    elif token[0] == '#':
        alteration = 1
        token = token[1:]

    if not token:
        return None

    # Check for diminished/augmented markers
    is_dim = False
    is_aug = False
    if token.endswith('°') or token.endswith('o'):
        is_dim = True
        token = token[:-1]
    elif token.endswith('+'):
        is_aug = True
        token = token[:-1]

    # Try to match Roman numerals (greedy, longest first)
    roman_part = ''
    rest = ''
    for length in range(len(token), 0, -1):
        candidate = token[:length]
        if candidate in ROMAN_MAJOR or candidate in ROMAN_MINOR:
            roman_part = candidate
            rest = token[length:]
            break

    if not roman_part:
        return None

    if roman_part in ROMAN_MAJOR:
        degree = ROMAN_MAJOR[roman_part]
        is_major = True
    else:
        degree = ROMAN_MINOR[roman_part]
        is_major = False

    # If is_dim, force is_major=False for notation purposes
    if is_dim:
        is_major = False

    extension = rest.strip()

    return ChordSymbol(
        raw=orig,
        degree=degree,
        is_major=is_major,
        alteration=alteration,
        extension=extension,
        is_diminished=is_dim,
        is_augmented=is_aug,
    )


def parse_melody_token(token: str) -> List[NoteEvent]:
    """Parse a melody token.  Can be single note, comma-separated eighths, or colon-separated sixteenths."""
    token = token.strip()
    if not token:
        return []

    if token == '-':
        return [NoteEvent(degree=0, alteration=0, octave=0, duration_div=1, is_rest=True)]
    if token == '.':
        return [NoteEvent(degree=0, alteration=0, octave=0, duration_div=1, sustain=True)]

    # Determine divisor from separator
    if ',' in token:
        parts = token.split(',')
        div = 2
    elif ':' in token:
        parts = token.split(':')
        div = 4
    else:
        parts = [token]
        div = 1

    events = []
    for p in parts:
        p = p.strip()
        if not p or p == '-':
            events.append(NoteEvent(degree=0, alteration=0, octave=0, duration_div=div, is_rest=True))
            continue
        if p == '.':
            events.append(NoteEvent(degree=0, alteration=0, octave=0, duration_div=div, sustain=True))
            continue

        alteration = 0
        if p[0] == 'b':
            alteration = -1
            p = p[1:]
        elif p[0] == '#':
            alteration = 1
            p = p[1:]

        octave = 0
        if p.endswith('^'):
            octave = 1
            p = p[:-1]
        elif p.endswith('_'):
            octave = -1
            p = p[:-1]

        try:
            degree = int(p)
        except ValueError:
            continue

        events.append(NoteEvent(
            degree=degree,
            alteration=alteration,
            octave=octave,
            duration_div=div,
        ))
    return events


def is_chord_line(line: str) -> bool:
    """Heuristic: does this line contain chord symbols (Roman numerals)?"""
    tokens = line.split()
    chord_count = 0
    total_tokens = 0
    for t in tokens:
        if t in ('|', '.', '-'):
            continue
        total_tokens += 1
        if parse_chord_token(t) is not None:
            chord_count += 1
    return total_tokens > 0 and chord_count >= total_tokens * 0.5


def is_melody_line(line: str) -> bool:
    """Heuristic: does this line contain melody notes (numbers)?"""
    tokens = line.split()
    note_count = 0
    total_tokens = 0
    for t in tokens:
        if t in ('|', '.', '-'):
            continue
        total_tokens += 1
        # Check if it looks like melody
        cleaned = re.sub(r'[#b^_,:]', '', t)
        if cleaned.isdigit():
            note_count += 1
    return total_tokens > 0 and note_count >= total_tokens * 0.4


def parse_tapscript(text: str) -> TapScriptComposition:
    """Parse a TapScript string into a TapScriptComposition."""
    comp = TapScriptComposition(raw_text=text)

    lines = text.split('\n')
    i = 0

    # Parse header
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # Header fields
        m = re.match(r'key:\s*(.+)', line, re.IGNORECASE)
        if m:
            comp.header.key = parse_key_string(m.group(1))
            i += 1
            continue
        m = re.match(r'tempo:\s*(\d+)', line, re.IGNORECASE)
        if m:
            comp.header.tempo = int(m.group(1))
            i += 1
            continue
        m = re.match(r'swing:\s*(\d+)', line, re.IGNORECASE)
        if m:
            comp.header.swing = int(m.group(1))
            i += 1
            continue
        m = re.match(r'time:\s*(\d+)/(\d+)', line, re.IGNORECASE)
        if m:
            comp.header.time_sig = (int(m.group(1)), int(m.group(2)))
            i += 1
            continue

        # Done with header
        break

    # Parse body: sections, bars, instruments
    current_section: Optional[Section] = None
    pending_chords: List[ChordSymbol] = []

    while i < len(lines):
        raw_line = lines[i]
        line = raw_line.strip()

        if not line:
            i += 1
            continue

        # Section header
        sm = re.match(r'\[(.+?)\]', line)
        if sm:
            current_section = Section(name=sm.group(1))
            comp.sections.append(current_section)
            pending_chords = []
            i += 1
            continue

        # Instrument assignment
        im = re.match(r'@(\w+):\s*(.+)', line)
        if im:
            name = im.group(1)
            rest = im.group(2)
            parts = rest.split('|')
            inst = parts[0].strip() if parts else ''
            role = parts[1].strip() if len(parts) > 1 else ''
            params = {}
            for p in parts[2:]:
                pkv = p.strip().split(':', 1)
                if len(pkv) == 2:
                    params[pkv[0].strip()] = pkv[1].strip()
            comp.instruments.append(InstrumentAssignment(
                name=name, instrument=inst, role=role, params=params
            ))
            i += 1
            continue

        # Musical line
        if current_section is not None and ('|' in line or is_chord_line(line) or is_melody_line(line)):
            # Split by bars
            bar_tokens = line.split('|')
            bar_idx = 0
            line_is_chords = is_chord_line(line)

            for bt in bar_tokens:
                bt = bt.strip()
                if not bt:
                    bar_idx += 1
                    continue

                # Ensure section has enough bars
                while len(current_section.bars) <= bar_idx:
                    current_section.bars.append(Bar())

                bar = current_section.bars[bar_idx]
                tokens = bt.split()

                if line_is_chords:
                    # Parse chords
                    for t in tokens:
                        if t == '|':
                            continue
                        if t == '.':
                            continue  # sustain, handled at compile time
                        chord = parse_chord_token(t)
                        if chord:
                            bar.chords.append(chord)
                else:
                    # Parse melody
                    for t in tokens:
                        if t == '|':
                            continue
                        notes = parse_melody_token(t)
                        bar.notes.extend(notes)

                bar_idx += 1

        i += 1

    return comp


# ---------------------------------------------------------------------------
# Transposition
# ---------------------------------------------------------------------------

def transpose(comp: TapScriptComposition, new_key: str) -> TapScriptComposition:
    """Return a new composition with the key changed."""
    new_ks = parse_key_string(new_key)
    new_text = re.sub(r'key:\s*.+', f'key: {new_key}', comp.raw_text, count=1, flags=re.IGNORECASE)
    new_comp = parse_tapscript(new_text)
    return new_comp


# ---------------------------------------------------------------------------
# MIDI Compilation
# ---------------------------------------------------------------------------

def _midi_note_for_degree(key: KeySignature, degree: int, alteration: int, octave: int) -> int:
    """Get MIDI note number for a scale degree."""
    st = key.scale_note_semitone(degree, octave) + alteration
    return st + 12  # so degree 1 octave 0 is around C4 range; root at octave 4


def _chord_midi_notes(key: KeySignature, chord: ChordSymbol, base_octave: int = 4) -> List[int]:
    """Get MIDI notes for a chord."""
    root_name, intervals = chord.resolve(key)
    root_st = key.scale_note_semitone(chord.degree, 0) + chord.alteration
    root_midi = root_st + (base_octave) * 12
    notes = [root_midi + iv for iv in intervals]
    return notes


def _apply_swing(times: List[float], swing: int, beat_duration: float) -> List[float]:
    """Apply swing to note onset times."""
    if swing <= 0:
        return times
    swing_factor = swing / 100.0  # 0 to 0.30
    result = []
    for t in times:
        beat_pos = (t / beat_duration) % 1.0
        beat_num = int(t / beat_duration)
        # If we're in the second half of the beat, push later
        if beat_pos > 0.4:
            offset = swing_factor * beat_duration * 0.5
            result.append(t + offset)
        else:
            result.append(t)
    return result


def _humanize_velocity(base_vel: int, rng: np.random.RandomState) -> int:
    """Add human variation to velocity."""
    variation = rng.randint(-8, 9)
    return max(1, min(127, base_vel + variation))


def compile_to_midi(comp: TapScriptComposition, output_path: Optional[str] = None) -> str:
    """Compile composition to MIDI file. Returns path to MIDI file."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI()
    tempo = comp.header.tempo
    beat_dur = 60.0 / tempo
    swing = comp.header.swing

    # Determine instrument programs
    instrument_map = {
        'piano': 0, 'acoustic piano': 0, 'grand piano': 0, 'bright piano': 1,
        'electric piano': 4, 'rhodes': 4,
        'guitar': 24, 'acoustic guitar': 24, 'nylon guitar': 24, 'steel guitar': 25,
        'electric guitar': 26, 'clean guitar': 27,
        'bass': 32, 'acoustic bass': 32, 'electric bass': 33, 'upright bass': 32,
        'strings': 48, 'string section': 48, 'violin': 40, 'viola': 41, 'cello': 42,
        'flute': 73, 'piccolo': 72, 'clarinet': 71, 'saxophone': 65, 'sax': 65,
        'trumpet': 56, 'trombone': 57,
        'pad': 88, 'warm pad': 89, 'synth pad': 88,
        'synth': 80, 'lead synth': 80,
        'vibes': 11, 'marimba': 12, 'organ': 16,
        'harp': 46,
    }

    def get_program(inst_name: str) -> int:
        key_lower = inst_name.lower().strip()
        for k, v in instrument_map.items():
            if k in key_lower or key_lower in k:
                return v
        return 0  # default piano

    # Build instrument tracks
    # If no instrument assignments, default to piano
    if not comp.instruments:
        tracks = [('piano', 'piano', 'both', {})]
    else:
        tracks = []
        for ia in comp.instruments:
            vel = int(ia.params.get('vel', '70'))
            tracks.append((ia.name, ia.instrument, ia.role, {'vel': vel}))

    rng = np.random.RandomState(42)

    # Process sections and build a timeline
    # We'll create separate tracks for each instrument
    # Each instrument gets assigned layers in round-robin from the parsed bars

    # Flatten all bars across sections
    all_bars: List[Tuple[str, Bar]] = []
    for section in comp.sections:
        for bar in section.bars:
            all_bars.append((section.name, bar))

    if not all_bars:
        # Empty composition, write a silent file
        if output_path is None:
            output_path = str(OUTPUT_DIR / 'silent.mid')
        pm.write(output_path)
        return output_path

    beats_per_bar = comp.header.time_sig[0]
    bar_duration = beats_per_bar * beat_dur

    # Assign layers to tracks
    # Layer 0 = chords, Layer 1 = melody
    # If only 1 instrument, it plays everything
    # If 2+, alternate

    for track_idx, (track_name, inst_name, role, params) in enumerate(tracks):
        program = get_program(inst_name)
        is_drum = False

        midi_instrument = pretty_midi.Instrument(program=program, name=track_name)
        pm.instruments.append(midi_instrument)

        base_vel = int(params.get('vel', 70))
        current_time = 0.0

        for section_name, bar in all_bars:
            # Determine what this track plays based on role
            play_chords = False
            play_melody = False
            play_bass = False
            play_pad = False

            role_lower = role.lower()
            if track_idx == 0 and len(tracks) == 1:
                play_chords = True
                play_melody = True
            elif 'chord' in role_lower:
                play_chords = True
            elif 'fingerpicking' in role_lower or 'finger' in role_lower:
                play_chords = True
                play_melody = True
            elif 'walking' in role_lower or 'bass' in role_lower:
                play_bass = True
            elif 'pad' in role_lower:
                play_pad = True
            elif 'melody' in role_lower or 'lead' in role_lower:
                play_melody = True
            else:
                # Default: play whatever is available, prefer chords
                if bar.chords:
                    play_chords = True
                if bar.notes and not play_chords:
                    play_melody = True

            # Chord pattern generation
            if play_chords and bar.chords:
                num_chords = len(bar.chords)
                # Distribute chords evenly across the bar
                chord_dur = bar_duration / max(num_chords, 1)

                last_chord = None
                for ci, chord in enumerate(bar.chords):
                    notes = _chord_midi_notes(comp.header.key, chord, base_octave=4)
                    start = current_time + ci * chord_dur
                    for n in notes:
                        vel = _humanize_velocity(base_vel, rng)
                        midi_instrument.notes.append(pretty_midi.Note(
                            velocity=vel, pitch=n,
                            start=start, end=start + chord_dur * 0.95
                        ))

            # Pad pattern: long sustained chords
            if play_pad and bar.chords:
                first_chord = bar.chords[0]
                notes = _chord_midi_notes(comp.header.key, first_chord, base_octave=3)
                for n in notes:
                    vel = _humanize_velocity(base_vel - 10, rng)
                    midi_instrument.notes.append(pretty_midi.Note(
                        velocity=max(1, vel), pitch=n,
                        start=current_time, end=current_time + bar_duration * 0.98
                    ))

            # Walking bass
            if play_bass and bar.chords:
                beats = beats_per_bar
                for beat_i in range(beats):
                    chord_idx = min(int(beat_i * len(bar.chords) / beats), len(bar.chords) - 1)
                    chord = bar.chords[chord_idx]
                    root_name, intervals = chord.resolve(comp.header.key)
                    root_st = comp.header.key.scale_note_semitone(chord.degree, 0) + chord.alteration
                    bass_midi = root_st + 2 * 12  # octave 2-3

                    # Walking: root, fifth, third, approach tone pattern
                    if beat_i == 0:
                        note = bass_midi
                    elif beat_i == 1:
                        note = bass_midi + 7  # fifth
                    elif beat_i == 2:
                        note = bass_midi + (intervals[1] if len(intervals) > 1 else 4)
                    else:
                        # Chromatic approach to next chord root
                        if chord_idx + 1 < len(bar.chords):
                            next_chord = bar.chords[chord_idx + 1]
                            next_root = comp.header.key.scale_note_semitone(next_chord.degree, 0) + next_chord.alteration + 2 * 12
                            note = next_root - 1
                        else:
                            note = bass_midi + 5

                    start = current_time + beat_i * beat_dur
                    vel = _humanize_velocity(base_vel, rng)
                    midi_instrument.notes.append(pretty_midi.Note(
                        velocity=vel, pitch=note,
                        start=start, end=start + beat_dur * 0.9
                    ))

            # Melody
            if play_melody and bar.notes:
                slot_dur = bar_duration / max(len(bar.notes), 1)
                last_degree = 1
                note_start = current_time

                for ni, note_ev in enumerate(bar.notes):
                    if note_ev.is_rest:
                        note_start += slot_dur
                        continue
                    if note_ev.sustain:
                        # Extend last note
                        if midi_instrument.notes:
                            midi_instrument.notes[-1].end = min(
                                note_start + slot_dur,
                                current_time + bar_duration
                            )
                        note_start += slot_dur
                        continue

                    midi_note = _midi_note_for_degree(
                        comp.header.key,
                        note_ev.degree,
                        note_ev.alteration,
                        note_ev.octave
                    )
                    dur = slot_dur
                    vel = _humanize_velocity(base_vel + 10, rng)
                    midi_instrument.notes.append(pretty_midi.Note(
                        velocity=vel, pitch=midi_note,
                        start=note_start, end=note_start + dur * 0.9
                    ))
                    last_degree = note_ev.degree
                    note_start += dur

            # If no specific role matched and bar has chords, play block chords
            elif (play_chords or play_pad or play_bass) and not bar.chords and not bar.notes:
                pass  # empty bar

            current_time += bar_duration

    # Apply tempo
    # pretty_midi handles tempo implicitly

    if output_path is None:
        h = hashlib.md5(comp.raw_text.encode()).hexdigest()[:8]
        output_path = str(OUTPUT_DIR / f'tapscript_{h}.mid')

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pm.write(output_path)
    return output_path


# ---------------------------------------------------------------------------
# WAV Synthesis
# ---------------------------------------------------------------------------

# Synthesis waveforms per instrument type
def _synth_wave(freq: float, duration: float, sr: int, waveform: str = 'triangle') -> np.ndarray:
    """Generate a simple waveform."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)

    if waveform == 'sine':
        wave = np.sin(2 * np.pi * freq * t)
    elif waveform == 'triangle':
        wave = 2 * np.abs(2 * (freq * t - np.floor(freq * t + 0.5))) - 1
    elif waveform == 'sawtooth':
        wave = 2 * (freq * t - np.floor(freq * t + 0.5))
    elif waveform == 'square':
        wave = np.sign(np.sin(2 * np.pi * freq * t))
    else:
        wave = np.sin(2 * np.pi * freq * t)

    # Simple ADSR envelope
    attack = min(0.01, duration * 0.1)
    decay = min(0.1, duration * 0.2)
    sustain_level = 0.7
    release = min(0.2, duration * 0.3)

    env = np.ones_like(t)
    # Attack
    a_samples = int(attack * sr)
    d_samples = int(decay * sr)
    r_samples = int(release * sr)
    s_samples = len(t) - a_samples - d_samples - r_samples

    if s_samples < 0:
        # Very short note, just fade in and out
        fade = min(len(t) // 2, max(1, len(t) // 4))
        env[:fade] = np.linspace(0, 1, fade)
        env[-fade:] = np.linspace(1, 0, fade)
    else:
        env[:a_samples] = np.linspace(0, 1, a_samples)
        if d_samples > 0:
            env[a_samples:a_samples+d_samples] = np.linspace(1, sustain_level, d_samples)
        env[a_samples+d_samples:a_samples+d_samples+s_samples] = sustain_level
        if r_samples > 0:
            env[a_samples+d_samples+s_samples:] = np.linspace(sustain_level, 0, r_samples)

    return wave * env


def _midi_to_freq(midi_note: int) -> float:
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


def _get_waveform_for_instrument(inst_name: str) -> str:
    n = inst_name.lower()
    if 'bass' in n or 'walking' in n:
        return 'sine'
    if 'string' in n or 'pad' in n:
        return 'sawtooth'
    if 'flute' in n or 'wind' in n:
        return 'sine'
    if 'guitar' in n:
        return 'triangle'
    return 'triangle'  # piano default


def midi_to_wav(midi_path: str, output_path: Optional[str] = None, sr: int = 44100) -> str:
    """Render a MIDI file to WAV using numpy synthesis."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(midi_path)
    duration = pm.get_end_time()

    if duration <= 0:
        duration = 1.0

    audio = np.zeros(int(sr * duration) + sr)  # extra second for reverb tail

    for instrument in pm.instruments:
        waveform = 'triangle'  # default
        # Try to guess from instrument name
        if instrument.name:
            waveform = _get_waveform_for_instrument(instrument.name)

        for note in instrument.notes:
            freq = _midi_to_freq(note.pitch)
            note_dur = note.end - note.start
            if note_dur <= 0:
                continue

            samples_start = int(note.start * sr)
            wave_data = _synth_wave(freq, note_dur, sr, waveform)

            # Amplitude from velocity
            amp = (note.velocity / 127.0) * 0.3

            end_idx = samples_start + len(wave_data)
            if end_idx > len(audio):
                wave_data = wave_data[:len(audio) - samples_start]
                end_idx = len(audio)

            if samples_start < len(audio):
                audio[samples_start:end_idx] += wave_data * amp

    # Normalize
    max_val = np.max(np.abs(audio))
    if max_val > 0:
        audio = audio / max_val * 0.85

    # Simple reverb (delay-based)
    delay_samples = int(0.08 * sr)
    feedback = 0.25
    reverb = np.zeros_like(audio)
    reverb[delay_samples:] = audio[:-delay_samples] * feedback
    audio = audio + reverb * 0.3

    # Re-normalize
    max_val = np.max(np.abs(audio))
    if max_val > 0:
        audio = audio / max_val * 0.85

    # Clip
    audio = np.clip(audio, -1.0, 1.0)

    # Convert to 16-bit
    audio_int16 = (audio * 32767).astype(np.int16)

    if output_path is None:
        output_path = midi_path.replace('.mid', '.wav')

    with wave.open(output_path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio_int16.tobytes())

    return output_path


def compile_to_wav(comp: TapScriptComposition, output_path: Optional[str] = None) -> str:
    """Compile composition directly to WAV. Returns path."""
    midi_path = compile_to_midi(comp)
    if output_path is None:
        h = hashlib.md5(comp.raw_text.encode()).hexdigest()[:8]
        output_path = str(OUTPUT_DIR / f'tapscript_{h}.wav')
    return midi_to_wav(midi_path, output_path)


# ---------------------------------------------------------------------------
# Markdown Integration
# ---------------------------------------------------------------------------

def extract_tapscript_blocks(markdown: str) -> List[str]:
    """Extract all ```tapscript ... ``` blocks from markdown."""
    pattern = r'```tapscript\s*\n(.*?)```'
    return re.findall(pattern, markdown, re.DOTALL)


def render_markdown(markdown: str, output_dir: Optional[str] = None) -> str:
    """Process markdown with embedded tapscript blocks.
    Returns HTML with audio players and syntax-highlighted notation."""
    if output_dir is None:
        output_dir = str(OUTPUT_DIR)

    blocks = extract_tapscript_blocks(markdown)

    for i, block in enumerate(blocks):
        comp = parse_tapscript(block)
        wav_path = compile_to_wav(comp)

        # Read WAV as base64 for inline audio
        import base64
        with open(wav_path, 'rb') as f:
            wav_b64 = base64.b64encode(f.read()).decode()

        audio_html = f'<audio controls><source src="data:audio/wav;base64,{wav_b64}" type="audio/wav"></audio>'

        # Highlight the notation
        highlighted = highlight_tapscript(block)

        replacement = f'{audio_html}\n<pre class="tapscript-block">{highlighted}</pre>'
        markdown = markdown.replace(f'```tapscript\n{block}```', replacement, 1)

    return markdown


def highlight_tapscript(text: str) -> str:
    """Simple syntax highlighting for tapscript text."""
    lines = text.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        # Header lines
        if re.match(r'(key|tempo|swing|time):', stripped):
            line_html = f'<span class="ts-header">{line}</span>'
        elif stripped.startswith('[') and stripped.endswith(']'):
            line_html = f'<span class="ts-section">{line}</span>'
        elif stripped.startswith('@'):
            line_html = f'<span class="ts-instrument">{line}</span>'
        else:
            # Highlight chord tokens and melody tokens
            tokens = line.split(' ')
            html_tokens = []
            for t in tokens:
                if parse_chord_token(t):
                    html_tokens.append(f'<span class="ts-chord">{t}</span>')
                elif t in ('.', '-'):
                    html_tokens.append(f'<span class="ts-sustain">{t}</span>')
                elif re.match(r'[#b]?\d', t):
                    html_tokens.append(f'<span class="ts-note">{t}</span>')
                else:
                    html_tokens.append(t)
            line_html = ' '.join(html_tokens)
        result.append(line_html)
    return '\n'.join(result)


# ---------------------------------------------------------------------------
# Example Compositions
# ---------------------------------------------------------------------------

HARBOR_DAWN = """key: D minor
tempo: 60
swing: 0
time: 4/4

[Intro]
  i    .    .    .   | III  .    .    .
  1    .    3    .   | 5    .    .    .

[A]
  i    vi   III  VII | i    .    IV   .
  3    5    1    .   | 3    2    1    -

[C]
  i    .    VI   .   | v    .    IV   .
  5    .    .    3   | 1    .    .    .

[Outro]
  i    .    .    .   | .    .    .    .
  1    .    -    .   | -    .    -    .

@wesley: piano | chords | vel: 60
@flash: strings | pad | vel: 50
"""

THE_ROOM_IS_SAFE = """key: E minor
tempo: 68
swing: 5
time: 3/4

[V1]
  i    .    .   | VI   .    .
  1    3    5   | 3    .    .

[C]
  i    .    .   | VII  .    .   | VI   .    .   | V    .    .
  5    3    1   | 2    .    .   | 3    5    6   | 5    .    .

[V2]
  i    .    .   | III  .    .
  1    3    5   | 7^   5    3

[Outro]
  i    .    .   | .    .    .
  1    -    -   | -    -    -

@wesley: piano | fingerpicking | vel: 55
@hermes: flute | melody | vel: 65
"""

OPEN_MIC = """key: G major
tempo: 85
swing: 12
time: 4/4

[Intro]
  I    .    IV   .   | I    .    V    .
  1,2,3,5    .    4,3,2,1    .   | 5    .    3    .

[V1]
  I    IV   I    V   | I    IV   V    .
  3    5    1    .   | 2    3    5    3

[C]
  I    V    vi   IV  | I    V    vi   IV
  5,3,1,5    .    5,3,1,5    .   | 5,3,1,5    .    5,3,1,5    .

[Solo]
  IV   .    V    .   | vi   .    IV   V
  2    3    5    6^  | 5    4    3    2

@flash: guitar | fingerpicking | vel: 75
@hermes: bass | walking | vel: 80
"""

EXAMPLES = {
    'harbor_dawn': ('Harbor Dawn', HARBOR_DAWN),
    'the_room_is_safe': ('The Room Is Safe', THE_ROOM_IS_SAFE),
    'open_mic': ('Open Mic', OPEN_MIC),
}


# ---------------------------------------------------------------------------
# Web UI HTML
# ---------------------------------------------------------------------------

WEB_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TapScript Studio</title>
<style>
  :root {
    --bg: #0a0a0f;
    --bg-elev: #12121a;
    --bg-elev2: #1a1a26;
    --accent: #7c8cf0;
    --accent-dim: #5a6bc0;
    --text: #e4e4ef;
    --text-dim: #8888a0;
    --border: #2a2a3a;
    --chord: #f0a87c;
    --note: #7cf0a8;
    --section: #f07cd4;
    --header: #7c8cf0;
    --instrument: #f0d47c;
    --sustain: #555570;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', 'Courier New', monospace;
    height: 100vh;
    overflow: hidden;
  }
  .app { display: flex; flex-direction: column; height: 100vh; }
  .topbar {
    background: var(--bg-elev);
    border-bottom: 1px solid var(--border);
    padding: 10px 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    flex-shrink: 0;
  }
  .logo { font-size: 18px; font-weight: bold; color: var(--accent); letter-spacing: 1px; }
  .topbar select, .topbar button, .topbar input {
    background: var(--bg-elev2);
    color: var(--text);
    border: 1px solid var(--border);
    padding: 6px 12px;
    border-radius: 6px;
    font-family: inherit;
    font-size: 13px;
    cursor: pointer;
  }
  .topbar button:hover { border-color: var(--accent); }
  .topbar button.primary {
    background: var(--accent);
    color: var(--bg);
    border-color: var(--accent);
    font-weight: bold;
  }
  .topbar .spacer { flex: 1; }
  .controls { display: flex; gap: 12px; align-items: center; }
  .controls label { font-size: 12px; color: var(--text-dim); }
  .main {
    display: flex;
    flex: 1;
    overflow: hidden;
  }
  .panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .panel-header {
    padding: 8px 16px;
    background: var(--bg-elev);
    border-bottom: 1px solid var(--border);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-dim);
    flex-shrink: 0;
  }
  .divider {
    width: 3px;
    background: var(--border);
    cursor: col-resize;
    flex-shrink: 0;
  }
  #editor {
    flex: 1;
    background: var(--bg);
    color: var(--text);
    border: none;
    padding: 16px;
    font-family: inherit;
    font-size: 14px;
    line-height: 1.6;
    resize: none;
    outline: none;
    tab-size: 2;
  }
  #editor:focus { background: var(--bg-elev); }
  .right-panel { display: flex; flex-direction: column; flex: 1; overflow: hidden; }
  .notation-area {
    flex: 1;
    overflow: auto;
    padding: 16px;
  }
  .audio-area {
    padding: 16px;
    border-top: 1px solid var(--border);
    background: var(--bg-elev);
    flex-shrink: 0;
  }
  .notation {
    white-space: pre-wrap;
    font-size: 14px;
    line-height: 1.7;
  }
  .ts-header { color: var(--header); }
  .ts-section { color: var(--section); font-weight: bold; }
  .ts-instrument { color: var(--instrument); }
  .ts-chord { color: var(--chord); font-weight: bold; }
  .ts-note { color: var(--note); }
  .ts-sustain { color: var(--sustain); }
  .parsed-info {
    padding: 12px 16px;
    background: var(--bg-elev2);
    border-radius: 8px;
    margin-bottom: 12px;
    font-size: 13px;
    color: var(--text-dim);
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
  }
  .parsed-info span b { color: var(--text); }
  .status {
    padding: 8px 16px;
    background: var(--bg-elev);
    border-top: 1px solid var(--border);
    font-size: 12px;
    color: var(--text-dim);
    flex-shrink: 0;
  }
  .status.error { color: #f07c7c; }
  .status.success { color: var(--note); }
  audio { width: 100%; margin-top: 8px; }
  .download-btn {
    display: inline-block;
    margin-top: 8px;
    padding: 6px 14px;
    background: var(--accent-dim);
    color: var(--text);
    text-decoration: none;
    border-radius: 6px;
    font-size: 12px;
    margin-right: 8px;
  }
  .download-btn:hover { background: var(--accent); }
</style>
</head>
<body>
<div class="app">
  <div class="topbar">
    <div class="logo">🎵 TapScript Studio</div>
    <select id="exampleSelect">
      <option value="">— Load Example —</option>
      <option value="harbor_dawn">Harbor Dawn</option>
      <option value="the_room_is_safe">The Room Is Safe</option>
      <option value="open_mic">Open Mic</option>
    </select>
    <div class="spacer"></div>
    <div class="controls">
      <label>Key:</label>
      <select id="keySelect">
        <option value="">Original</option>
        <option value="C major">C major</option>
        <option value="C minor">C minor</option>
        <option value="D major">D major</option>
        <option value="D minor">D minor</option>
        <option value="E minor">E minor</option>
        <option value="F major">F major</option>
        <option value="G major">G major</option>
        <option value="A minor">A minor</option>
        <option value="A major">A major</option>
        <option value="Bb major">Bb major</option>
        <option value="F# minor">F# minor</option>
      </select>
      <label>Tempo:</label>
      <input type="range" id="tempoSlider" min="40" max="200" value="120">
      <span id="tempoValue" style="min-width:35px">120</span>
      <button class="primary" id="playBtn">▶ Play</button>
      <button id="midiBtn">⬇ MIDI</button>
      <button id="wavBtn">⬇ WAV</button>
    </div>
  </div>
  <div class="main">
    <div class="panel" style="flex: 1;">
      <div class="panel-header">Notation Editor</div>
      <textarea id="editor" spellcheck="false" placeholder="Type or paste TapScript here..."></textarea>
    </div>
    <div class="panel" style="flex: 1;">
      <div class="panel-header">Rendered Output</div>
      <div class="right-panel">
        <div class="notation-area">
          <div class="parsed-info" id="parsedInfo">— Parse a composition —</div>
          <pre class="notation" id="notation"></pre>
        </div>
        <div class="audio-area" id="audioArea">
          <audio id="player" controls style="display:none;"></audio>
        </div>
      </div>
    </div>
  </div>
  <div class="status" id="status">Ready.</div>
</div>
<script>
const $ = id => document.getElementById(id);
const editor = $('editor');
const notation = $('notation');
const parsedInfo = $('parsedInfo');
const statusEl = $('status');
const player = $('player');
const audioArea = $('audioArea');
const keySelect = $('keySelect');
const tempoSlider = $('tempoSlider');
const tempoValue = $('tempoValue');

let currentText = '';
let debounceTimer = null;

function setStatus(msg, type) {
  statusEl.textContent = msg;
  statusEl.className = 'status' + (type ? ' ' + type : '');
}

async function api(endpoint, body) {
  const opts = { method: 'POST', headers: {'Content-Type': 'application/json'} };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch('/api/' + endpoint, opts);
  if (!r.ok) {
    const err = await r.text();
    throw new Error(err);
  }
  const ct = r.headers.get('Content-Type') || '';
  if (ct.includes('application/json')) return r.json();
  return r;
}

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function highlight(text) {
  return text.split('\n').map(line => {
    const s = line.trim();
    if (/^(key|tempo|swing|time):/i.test(s))
      return '<span class="ts-header">' + escapeHtml(line) + '</span>';
    if (s.startsWith('[') && s.endsWith(']'))
      return '<span class="ts-section">' + escapeHtml(line) + '</span>';
    if (s.startsWith('@'))
      return '<span class="ts-instrument">' + escapeHtml(line) + '</span>';
    let html = escapeHtml(line);
    // chords (Roman numerals)
    html = html.replace(/\b([IVXLCDM]+[°]?[7-9]?|[ivxlcdm]+[°]?[7-9]?)\b/g, '<span class="ts-chord">$1</span>');
    // melody notes
    html = html.replace(/\b([#b]?\d[\^_]?[:;,]?)*\b/g, m => {
      if (/^\d|^[#b]\d/.test(m.trim()) && m.trim()) return '<span class="ts-note">' + m + '</span>';
      return m;
    });
    // sustain/rest
    html = html.replace(/\s\.\s/g, ' <span class="ts-sustain">.</span> ');
    html = html.replace(/\s-\s/g, ' <span class="ts-sustain">-</span> ');
    return html;
  }).join('\n');
}

async function updatePreview() {
  const text = editor.value;
  if (!text.trim()) {
    notation.innerHTML = '';
    parsedInfo.textContent = '— Empty —';
    return;
  }
  try {
    const data = await api('parse', { tapscript: text });
    notation.innerHTML = highlight(text);
    const parts = [
      'Key: <b>' + data.key + '</b>',
      'Tempo: <b>' + data.tempo + '</b> BPM',
      'Time: <b>' + data.time_sig + '</b>',
      'Swing: <b>' + data.swing + '%</b>',
      'Sections: <b>' + data.sections.length + '</b>',
      'Bars: <b>' + data.total_bars + '</b>',
      'Instruments: <b>' + data.instruments.map(i => i.name).join(', ') + '</b>'
    ];
    parsedInfo.innerHTML = parts.join('  •  ');
    setStatus('Parsed OK.', 'success');
  } catch(e) {
    setStatus('Parse error: ' + e.message, 'error');
  }
}

async function play() {
  let text = editor.value;
  if (!text.trim()) { setStatus('Nothing to play.', 'error'); return; }

  const key = keySelect.value;
  const tempo = parseInt(tempoSlider.value);
  const body = { tapscript: text, key: key || null, tempo: tempo };

  setStatus('Rendering audio...');
  try {
    // Transpose if needed
    if (key) {
      const transposed = await api('transpose', { tapscript: text, key: key });
      text = transposed.tapscript;
      editor.value = text;
    }
    // Adjust tempo
    text = text.replace(/tempo:\s*\d+/i, 'tempo: ' + tempo);
    editor.value = text;

    const data = await api('render', { tapscript: text });
    player.src = '/audio/' + data.wav_filename + '?t=' + Date.now();
    player.style.display = 'block';
    player.play();
    setStatus('Playing... ▶', 'success');
    updatePreview();
  } catch(e) {
    setStatus('Render error: ' + e.message, 'error');
  }
}

async function downloadMidi() {
  const text = editor.value;
  if (!text.trim()) return;
  try {
    const data = await api('compile', { tapscript: text });
    window.location.href = '/audio/' + data.midi_filename;
  } catch(e) { setStatus('Error: ' + e.message, 'error'); }
}

async function downloadWav() {
  const text = editor.value;
  if (!text.trim()) return;
  try {
    const data = await api('render', { tapscript: text });
    window.location.href = '/audio/' + data.wav_filename;
  } catch(e) { setStatus('Error: ' + e.message, 'error'); }
}

async function loadExample(name) {
  try {
    const data = await fetch('/api/example/' + name).then(r => r.json());
    editor.value = data.tapscript;
    keySelect.value = '';
    tempoSlider.value = data.tempo || 120;
    tempoValue.textContent = tempoSlider.value;
    updatePreview();
  } catch(e) { setStatus('Error loading example.', 'error'); }
}

// Event listeners
editor.addEventListener('input', () => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(updatePreview, 500);
});

$('exampleSelect').addEventListener('change', e => {
  if (e.target.value) loadExample(e.target.value);
});

$('playBtn').addEventListener('click', play);
$('midiBtn').addEventListener('click', downloadMidi);
$('wavBtn').addEventListener('click', downloadWav);

keySelect.addEventListener('change', async () => {
  const key = keySelect.value;
  if (!key) return;
  try {
    const data = await api('transpose', { tapscript: editor.value, key: key });
    editor.value = data.tapscript;
    updatePreview();
  } catch(e) { setStatus('Transpose error: ' + e.message, 'error'); }
});

tempoSlider.addEventListener('input', () => {
  tempoValue.textContent = tempoSlider.value;
});

// Load default example
loadExample('harbor_dawn');
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Flask Web Server
# ---------------------------------------------------------------------------

def create_app():
    from flask import Flask, request, jsonify, send_file, Response

    app = Flask(__name__)

    @app.route('/')
    def index():
        return WEB_HTML

    @app.route('/api/parse', methods=['POST'])
    def api_parse():
        data = request.json or {}
        text = data.get('tapscript', '')
        comp = parse_tapscript(text)
        return jsonify({
            'key': str(comp.header.key),
            'tempo': comp.header.tempo,
            'swing': comp.header.swing,
            'time_sig': f'{comp.header.time_sig[0]}/{comp.header.time_sig[1]}',
            'sections': [{'name': s.name, 'bars': len(s.bars)} for s in comp.sections],
            'total_bars': comp.total_bars,
            'instruments': [{'name': i.name, 'instrument': i.instrument, 'role': i.role}
                           for i in comp.instruments],
        })

    @app.route('/api/compile', methods=['POST'])
    def api_compile():
        data = request.json or {}
        text = data.get('tapscript', '')
        comp = parse_tapscript(text)
        midi_path = compile_to_midi(comp)
        return jsonify({
            'midi_path': midi_path,
            'midi_filename': os.path.basename(midi_path),
        })

    @app.route('/api/render', methods=['POST'])
    def api_render():
        data = request.json or {}
        text = data.get('tapscript', '')
        comp = parse_tapscript(text)
        wav_path = compile_to_wav(comp)
        return jsonify({
            'wav_path': wav_path,
            'wav_filename': os.path.basename(wav_path),
        })

    @app.route('/api/transpose', methods=['POST'])
    def api_transpose():
        data = request.json or {}
        text = data.get('tapscript', '')
        new_key = data.get('key', 'C major')
        transposed = transpose(parse_tapscript(text), new_key)
        return jsonify({
            'tapscript': transposed.raw_text,
        })

    @app.route('/api/example', methods=['GET', 'POST'])
    @app.route('/api/example/<name>', methods=['GET'])
    def api_example(name=None):
        if name is None:
            return jsonify({
                'examples': [
                    {'id': k, 'name': v[0]} for k, v in EXAMPLES.items()
                ]
            })
        if name in EXAMPLES:
            title, text = EXAMPLES[name]
            comp = parse_tapscript(text)
            return jsonify({
                'name': title,
                'tapscript': text,
                'tempo': comp.header.tempo,
            })
        return jsonify({'error': 'Not found'}), 404

    @app.route('/audio/<filename>')
    def serve_audio(filename):
        path = OUTPUT_DIR / filename
        if path.exists():
            return send_file(str(path))
        return 'Not found', 404

    return app


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cli_main():
    parser = argparse.ArgumentParser(description='TapScript — music notation compiler')
    parser.add_argument('--cli', metavar='FILE', help='Compile a .ts file')
    parser.add_argument('--midi', metavar='PATH', help='Output MIDI path')
    parser.add_argument('--wav', metavar='PATH', help='Output WAV path')
    parser.add_argument('--example', metavar='NAME', help='Load an example by name')
    parser.add_argument('--port', type=int, default=PORT, help='Web server port')
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.example:
        if args.example in EXAMPLES:
            _, text = EXAMPLES[args.example]
        else:
            print(f'Unknown example: {args.example}')
            print(f'Available: {", ".join(EXAMPLES.keys())}')
            sys.exit(1)
        comp = parse_tapscript(text)
        if args.wav:
            wav_path = compile_to_wav(comp, args.wav)
            print(f'WAV: {wav_path}')
        elif args.midi:
            midi_path = compile_to_midi(comp, args.midi)
            print(f'MIDI: {midi_path}')
        else:
            wav_path = compile_to_wav(comp)
            print(f'WAV: {wav_path}')
        return

    if args.cli:
        with open(args.cli) as f:
            text = f.read()
        comp = parse_tapscript(text)
        if args.midi:
            print(f'MIDI: {compile_to_midi(comp, args.midi)}')
        if args.wav:
            print(f'WAV: {compile_to_wav(comp, args.wav)}')
        if not args.midi and not args.wav:
            print(f'Key: {comp.header.key}')
            print(f'Tempo: {comp.header.tempo}')
            print(f'Sections: {len(comp.sections)}')
            print(f'Bars: {comp.total_bars}')
            print(f'Instruments: {", ".join(i.name for i in comp.instruments)}')
            # Default: generate WAV
            wav_path = compile_to_wav(comp)
            print(f'WAV: {wav_path}')
        return

    # Start web server
    app = create_app()
    print(f'🎵 TapScript Studio running on http://localhost:{args.port}')
    app.run(host='0.0.0.0', port=args.port, debug=False)


if __name__ == '__main__':
    cli_main()
