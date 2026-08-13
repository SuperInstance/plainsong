#!/usr/bin/env python3
"""
TapScript v2 — Absolute notation parser, compiler, and web renderer.

A notation system using scientific pitch notation (C4, E4, a2) with
pipe-delimited bars, dot sustains, dash rests, and named player tracks.

Format:
    **TRACK: Title**
    [MetaData]
    key: Am | tempo: 75 | swing: 10% | subdivision: 16th

    [V1] (Verse - 4 Bars)
    Chords:  | Am    .    | F     G    |
    Melody: | E4    . . . | A4    . G4 E4 |
    Lyrics: | I     . . . | write . in code |
    @wesley | e2-a2-c3 . . | f2-a2-c3 g2-b2-d3 | vel: 60

Usage:
    python tapscript_v2.py              # start web server on port 5557
    python tapscript_v2.py --cli file.ts --midi out.mid --wav out.wav
"""

import os
import sys
import re
import json
import math
import uuid
import random
import hashlib
import argparse
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import List, Dict, Optional, Tuple, Any

import numpy as np
from scipy.io import wavfile as wav_io
import pretty_midi

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PORT = 5557
OUTPUT_DIR = os.path.expanduser("~/.openclaw/workspace/output/audio")
os.makedirs(OUTPUT_DIR, exist_ok=True)

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
NOTE_TO_SEMITONE = {n: i for i, n in enumerate(NOTE_NAMES)}

# Flats → sharps mapping
FLATS = {'Bb': 'A#', 'Db': 'C#', 'Eb': 'D#', 'Gb': 'F#', 'Ab': 'G#', 'Cb': 'B', 'Fb': 'E'}

# GM instrument programs
GM_PROGRAMS = {
    'piano': 0, 'acoustic piano': 0, 'grand piano': 0, 'bright piano': 1,
    'electric piano': 4, 'rhodes': 4,
    'guitar': 24, 'acoustic guitar': 24, 'nylon guitar': 24, 'steel guitar': 25,
    'electric guitar': 26, 'clean guitar': 27,
    'bass': 33, 'acoustic bass': 32, 'electric bass': 33, 'upright bass': 32,
    'strings': 48, 'string section': 48, 'violin': 40, 'viola': 41, 'cello': 42,
    'flute': 73, 'piccolo': 72, 'clarinet': 71, 'saxophone': 65,
    'trumpet': 56, 'trombone': 57,
    'pad': 88, 'warm pad': 89, 'synth pad': 88,
    'synth': 80, 'lead synth': 80,
    'vibes': 11, 'marimba': 12, 'organ': 16,
    'harp': 46, 'drums': 0,
}

# Default instrument per player name (fallback)
DEFAULT_PLAYER_INSTRUMENT = 'piano'

# Map player names to instruments based on common names in the examples
PLAYER_INSTRUMENT_MAP = {
    'wesley': 'piano',
    'flash': 'guitar',
    'hermes': 'bass',
}

# ---------------------------------------------------------------------------
# DeepSeek API (optional, for AI composition)
# ---------------------------------------------------------------------------

def load_deepseek_key():
    """Read DEEPSEEK_API_KEY from ~/.bashrc."""
    bashrc = os.path.expanduser("~/.bashrc")
    if not os.path.exists(bashrc):
        return os.environ.get("DEEPSEEK_API_KEY", "")
    with open(bashrc) as f:\n        for line in f:\n            line = line.strip()\n            if line.startswith("export DEEPSEEK_API_KEY="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val
    return os.environ.get("DEEPSEEK_API_KEY", "")

DEEPSEEK_KEY = load_deepseek_key()
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# ---------------------------------------------------------------------------
# Note Parsing — Scientific Pitch Notation
# ---------------------------------------------------------------------------

def parse_absolute_note(token: str) -> Optional[int]:
    """
    Parse a single absolute note name to MIDI number.
    
    'C4' → 60, 'E4' → 64, 'a2' → 45 (lowercase = lowercase octave letter, still scientific)
    'e2-a2-c3' → not handled here (see parse_note_token)
    
    Returns None for '.', '-', and non-note tokens.
    """
    token = token.strip()
    if not token or token == '.' or token == '-':
        return None
    
    # Match note name + octave: [A-Ga-g][#b]?<number>
    m = re.match(r'^([A-Ga-g])([#b]?)(\d+)$', token)
    if not m:\n        return None\n    \n    letter = m.group(1).upper()\n    accidental = m.group(2)\n    octave = int(m.group(3))\n    \n    # Get base semitone\n    semitone = NOTE_TO_SEMITONE[letter]
    
    # Apply accidental
    if accidental == '#':
        semitone += 1
    elif accidental == 'b':
        semitone -= 1
    
    # MIDI: C-1 = 0, C0 = 12, C4 = 60
    midi = 12 + octave * 12 + semitone
    return midi


def parse_note_token(token: str) -> Dict[str, Any]:
    """
    Parse a note token from a Melody or @player line.
    
    Returns a dict:
      {"type": "note", "pitches": [60, 64]}  — one or more MIDI notes
      {"type": "sustain"}                      — dot, hold previous
      {"type": "rest"}                         — dash, silence
    """
    token = token.strip()
    
    if token == '.':
        return {"type": "sustain"}
    if token == '-':
        return {"type": "rest"}
    if not token:
        return {"type": "rest"}
    
    # Handle chord (hyphen-separated notes): e2-a2-c3
    if '-' in token and re.search(r'[A-Ga-g]', token):
        parts = token.split('-')
        pitches = []
        for p in parts:
            p = p.strip()
            if p == '.' or p == '' or p == '-':
                continue
            midi = parse_absolute_note(p)
            if midi is not None:
                pitches.append(midi)
        if pitches:
            return {"type": "note", "pitches": pitches}
        return {"type": "rest"}
    
    # Single note
    midi = parse_absolute_note(token)
    if midi is not None:
        return {"type": "note", "pitches": [midi]}
    
    return {"type": "rest"}


def midi_to_note_name(midi: int) -> str:
    """Convert MIDI number to note name (e.g., 60 → 'C4')."""
    octave = (midi - 12) // 12
    semitone = midi % 12
    return f"{NOTE_NAMES[semitone]}{octave}"


def transpose_midi(midi: int, semitones: int) -> int:
    """Transpose a MIDI note by N semitones."""
    return max(0, min(127, midi + semitones))


# ---------------------------------------------------------------------------
# Key Parsing (for key changes in UI)
# ---------------------------------------------------------------------------

def parse_key_string(key_str: str) -> Tuple[str, str]:
    """
    Parse key string like 'Am', 'C', 'Dm', 'F#', 'Bbm'.
    Returns (root_note, quality) e.g. ('A', 'minor'), ('C', 'major').
    """
    key_str = key_str.strip()
    m = re.match(r'^([A-G][#b]?)(m?)$', key_str)
    if not m:\n        return ('C', 'major')\n    root = m.group(1)\n    minor = m.group(2) == 'm'\n    quality = 'minor' if minor else 'major'\n    \n    # Normalize flats
    if root in FLATS:
        root = FLATS[root]
    
    return (root, quality)


def key_to_semitones(key_str: str) -> int:
    """Get the root semitone (0-11) for a key string."""
    root, _ = parse_key_string(key_str)
    return NOTE_TO_SEMITONE.get(root, 0)


def semitone_difference(from_key: str, to_key: str) -> int:
    """Calculate semitone difference between two keys."""
    return (key_to_semitones(to_key) - key_to_semitones(from_key)) % 12


# ---------------------------------------------------------------------------
# Parser — TapScript v2 Notation
# ---------------------------------------------------------------------------

def parse_tapscript(text: str) -> Dict[str, Any]:
    """
    Parse TapScript v2 notation into a structured composition.
    
    Returns a composition dictionary.
    """
    comp = {
        "title": "",
        "key": "C",
        "key_quality": "major",
        "tempo": 120,
        "swing": 0,
        "subdivision": 16,  # default 16th notes
        "sections": [],
        "raw_text": text,
    }
    
    lines = text.split('\n')
    i = 0
    
    # --- Parse title ---
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        m = re.match(r'\*\*TRACK:\s*(.+?)\*\*', line, re.IGNORECASE)
        if m:\n            comp["title"] = m.group(1).strip()
            i += 1
            break
        # If no title line, try metadata directly
        if line.startswith('[MetaData]'):
            break
        i += 1
    
    # --- Parse metadata block ---
    in_metadata = False
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        
        if line.startswith('[MetaData]'):
            in_metadata = True
            i += 1
            continue
        
        if in_metadata:
            # Check if we've left metadata (hit a section header)
            if line.startswith('[') and not line.startswith('[MetaData]'):
                break
            
            # Parse: key: Am | tempo: 75 | swing: 10% | subdivision: 16th
            # These can be pipe-separated on one line or on separate lines
            parts = line.split('|')
            for part in parts:
                part = part.strip()
                km = re.match(r'key:\s*(\S+)', part, re.IGNORECASE)
                if km:
                    key_str = km.group(1)
                    root, quality = parse_key_string(key_str)
                    comp["key"] = root
                    comp["key_quality"] = quality
                    continue
                tm = re.match(r'tempo:\s*(\d+)', part, re.IGNORECASE)
                if tm:
                    comp["tempo"] = int(tm.group(1))
                    continue
                sm = re.match(r'swing:\s*(\d+)%?', part, re.IGNORECASE)
                if sm:
                    comp["swing"] = int(sm.group(1))
                    continue
                subm = re.match(r'subdivision:\s*(\d+)(?:st|th)?', part, re.IGNORECASE)
                if subm:
                    comp["subdivision"] = int(subm.group(1))
                    continue
            
            i += 1
            continue
        
        i += 1
    
    # --- Parse sections ---
    current_section = None
    
    while i < len(lines):
        raw_line = lines[i]
        line = raw_line.strip()
        
        if not line:
            i += 1
            continue
        
        # Section header: [V1] (Verse - 4 Bars) or [C] (Chorus - Louder)
        sec_m = re.match(r'^\[(\w+)\](?:\s*\((.+?)\))?', line)
        if sec_m:\n            current_section = {\n                "name": sec_m.group(1),
                "description": sec_m.group(2) or "",
                "bars": [],
            }
            comp["sections"].append(current_section)
            i += 1
            continue
        
        # Skip lines outside a section
        if current_section is None:
            i += 1
            continue
        
        # Parse bar content from various line types
        # Each line type: Chords:, Melody:, Lyrics:, @player
        
        # Determine line type and parse bars
        if line.startswith('Chords:'):
            bar_data = _parse_bar_line(line, 'chords')
            _assign_to_bars(current_section, bar_data, 'chords')
        elif line.startswith('Melody:'):
            bar_data = _parse_bar_line(line, 'melody')
            _assign_to_bars(current_section, bar_data, 'melody')
        elif line.startswith('Lyrics:'):
            bar_data = _parse_bar_line(line, 'lyrics')
            _assign_to_bars(current_section, bar_data, 'lyrics')
        elif line.startswith('@'):
            # Named player track: @wesley | notes ... | vel: 60
            player_data = _parse_player_line(line)
            if player_data:
                player_name = player_data["name"]
                bar_data = player_data["bars"]
                vel = player_data["vel"]
                _assign_player_to_bars(current_section, bar_data, player_name, vel)
        
        i += 1
    
    return comp


def _parse_bar_line(line: str, line_type: str) -> List[List[str]]:
    """
    Parse a pipe-delimited line into bar tokens.
    
    'Chords:  | Am    .    | F     G    |'
    → [['Am', '.'], ['F', 'G']]
    
    Returns a list of bars, each bar is a list of token strings.
    """
    # Remove the label prefix
    idx = line.find(':')
    if idx == -1:
        return []
    content = line[idx + 1:]
    
    # Split by pipe
    bars_raw = content.split('|')
    
    bars = []
    for bar_str in bars_raw:
        bar_str = bar_str.strip()
        if not bar_str:
            continue
        tokens = bar_str.split()
        bars.append(tokens)
    
    return bars


def _parse_player_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parse a @player line.
    
    '@wesley | e2-a2-c3 . . | f2-a2-c3 g2-b2-d3 | vel: 60'
    → {"name": "wesley", "bars": [[...]], "vel": 60}
    """
    # Extract player name
    m = re.match(r'^@(\w+)\s*(.*)', line)
    if not m:\n        return None\n    \n    name = m.group(1)\n    rest = m.group(2)\n    \n    # Split by pipe\n    parts = rest.split('|')
    
    bars = []
    vel = 70  # default velocity
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # Check for vel: parameter
        vm = re.match(r'vel:\s*(\d+)', part, re.IGNORECASE)
        if vm:
            vel = int(vm.group(1))
            continue
        
        # It's a bar of notes
        tokens = part.split()
        if tokens:
            bars.append(tokens)
    
    return {"name": name, "bars": bars, "vel": vel}


def _assign_to_bars(section: dict, bar_data: List[List[str]], key: str):
    """Assign parsed bar tokens to the section's bars."""
    for bar_idx, tokens in enumerate(bar_data):
        while len(section["bars"]) <= bar_idx:
            section["bars"].append(_new_bar())
        section["bars"][bar_idx][key] = tokens


def _assign_player_to_bars(section: dict, bar_data: List[List[str]], player_name: str, vel: int):
    """Assign player track data to bars."""
    for bar_idx, tokens in enumerate(bar_data):
        while len(section["bars"]) <= bar_idx:
            section["bars"].append(_new_bar())
        bar = section["bars"][bar_idx]
        if "players" not in bar:
            bar["players"] = {}
        bar["players"][player_name] = {
            "tokens": tokens,
            "vel": vel,
        }


def _new_bar() -> dict:
    return {
        "chords": [],
        "melody": [],
        "lyrics": [],
        "players": {},
    }


# ---------------------------------------------------------------------------
# Transposition
# ---------------------------------------------------------------------------

def transpose_text(text: str, new_key: str) -> str:
    """
    Transpose all absolute notes in a TapScript v2 text to a new key.
    Returns the modified text.
    """
    # Find original key
    orig_key_match = re.search(r'key:\s*(\S+)', text, re.IGNORECASE)
    if not orig_key_match:
        return text
    
    orig_key = orig_key_match.group(1)
    semis = semitone_difference(orig_key, new_key)
    
    if semis == 0:
        # Just update the key label
        return re.sub(r'(key:\s*)\S+', r'\g<1>' + new_key, text, count=1, flags=re.IGNORECASE)
    
    # Transpose all absolute notes
    def transpose_token(m):
        note = m.group(0)
        midi = parse_absolute_note(note)
        if midi is not None:
            new_midi = transpose_midi(midi, semis)
            return midi_to_note_name(new_midi)
        return note
    
    # Replace note patterns: [A-Ga-g][#b]?\d+ but not inside chord names on Chords: lines
    lines = text.split('\n')
    result_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip Chords: lines — those are chord symbols, not absolute notes
        if stripped.startswith('Chords:'):
            result_lines.append(line)
            continue
        # Skip Lyrics: lines
        if stripped.startswith('Lyrics:'):
            result_lines.append(line)
            continue
        # Transpose notes in Melody: and @player lines
        transposed = re.sub(r'[A-Ga-g][#b]?\d+', transpose_token, line)
        result_lines.append(transposed)
    
    result = '\n'.join(result_lines)
    
    # Update key label
    result = re.sub(r'(key:\s*)\S+', r'\g<1>' + new_key, result, count=1, flags=re.IGNORECASE)
    
    return result


# ---------------------------------------------------------------------------
# MIDI Compilation
# ---------------------------------------------------------------------------

def _get_program_for_player(player_name: str) -> int:
    """Get GM program number for a player name."""
    name_lower = player_name.lower()
    
    # Check direct map
    if name_lower in PLAYER_INSTRUMENT_MAP:
        inst = PLAYER_INSTRUMENT_MAP[name_lower]
        return GM_PROGRAMS.get(inst, 0)
    
    # Check if name contains instrument hint
    for key, prog in GM_PROGRAMS.items():
        if key in name_lower:
            return prog
    
    return 0  # default piano


def _get_instrument_name_for_player(player_name: str) -> str:
    """Get instrument name for a player."""
    name_lower = player_name.lower()
    if name_lower in PLAYER_INSTRUMENT_MAP:
        return PLAYER_INSTRUMENT_MAP[name_lower]
    for key in GM_PROGRAMS:
        if key in name_lower:
            return key
    return 'piano'


def _tokens_to_events(tokens: List[str]) -> List[Dict[str, Any]]:
    """Convert a list of token strings to event dicts."""
    events = []
    for token in tokens:
        events.append(parse_note_token(token))
    return events


def compile_to_midi(comp: Dict[str, Any], output_path: Optional[str] = None,
                    tempo_override: Optional[int] = None,
                    swing_override: Optional[int] = None) -> str:
    """
    Compile parsed composition to MIDI.
    Returns path to MIDI file.
    """
    tempo = tempo_override or comp["tempo"]
    swing = swing_override if swing_override is not None else comp["swing"]
    subdivision = comp["subdivision"]
    
    beat_dur = 60.0 / tempo
    
    # Determine beats per bar — assume 4/4 by default
    beats_per_bar = 4
    bar_dur = beats_per_bar * beat_dur
    
    # Subdivision duration: number of slots per beat
    # 8th = 2 slots per beat, 16th = 4 slots per beat
    if subdivision <= 8:
        slots_per_beat = 2
    else:
        slots_per_beat = 4
    
    slot_dur = beat_dur / slots_per_beat
    
    # Apply swing factor (0-100% → 0-0.5 of slot duration offset)
    swing_amount = (swing / 100.0) * slot_dur * 0.5
    
    pm = pretty_midi.PrettyMIDI(initial_tempo=float(tempo))
    
    # Collect all player names across all sections
    all_players = set()
    for section in comp["sections"]:
        for bar in section["bars"]:
            for pname in bar.get("players", {}):
                all_players.add(pname)
    
    # Also check for chord and melody lines
    has_chords = any(
        bar.get("chords")
        for section in comp["sections"]
        for bar in section["bars"]
    )
    has_melody = any(
        bar.get("melody")
        for section in comp["sections"]
        for bar in section["bars"]
    )
    
    rng = random.Random(42)
    
    # Create instrument tracks
    player_instruments = {}
    for pname in sorted(all_players):
        inst_name = _get_instrument_name_for_player(pname)
        program = GM_PROGRAMS.get(inst_name, 0)
        is_drum = (inst_name == 'drums')
        if is_drum:
            inst = pretty_midi.Instrument(program=0, is_drum=True, name=pname)
        else:
            inst = pretty_midi.Instrument(program=program, name=pname)
        pm.instruments.append(inst)
        player_instruments[pname] = inst
    
    # Chord track (piano comping)
    chord_track = None
    if has_chords:
        chord_track = pretty_midi.Instrument(program=0, name="chords")
        pm.instruments.append(chord_track)
    
    # Melody track (lead)
    melody_track = None
    if has_melody:
        melody_track = pretty_midi.Instrument(program=0, name="melody")
        pm.instruments.append(melody_track)
    
    # Process all bars sequentially
    current_time = 0.0
    
    for section in comp["sections"]:
        for bar in section["bars"]:
            # --- Chord track ---
            if chord_track and bar.get("chords"):
                chord_tokens = bar["chords"]
                _render_chord_bar(chord_track, chord_tokens, current_time, bar_dur,
                                  beat_dur, slots_per_beat, slot_dur, swing_amount, rng)
            
            # --- Melody track ---
            if melody_track and bar.get("melody"):
                melody_tokens = bar["melody"]
                _render_melody_bar(melody_track, melody_tokens, current_time, bar_dur,
                                    beat_dur, slots_per_beat, slot_dur, swing_amount, rng, vel_base=80)
            
            # --- Player tracks ---
            for pname, pdata in bar.get("players", {}).items():
                inst = player_instruments.get(pname)
                if inst is None:
                    continue
                tokens = pdata.get("tokens", [])
                vel = pdata.get("vel", 70)
                _render_melody_bar(inst, tokens, current_time, bar_dur,
                                   beat_dur, slots_per_beat, slot_dur, swing_amount, rng, vel_base=vel)
            
            current_time += bar_dur
    
    # Write
    if output_path is None:
        h = hashlib.md5(comp.get("raw_text", "").encode()).hexdigest()[:8]
        output_path = os.path.join(OUTPUT_DIR, f'tapscript_v2_{h}.mid')
    
    pm.write(output_path)
    return output_path


# Chord shape lookup for chord symbols
CHORD_SHAPES = {
    '': [0, 4, 7], 'M': [0, 4, 7],
    'm': [0, 3, 7],
    '7': [0, 4, 7, 10], 'dom7': [0, 4, 7, 10],
    'm7': [0, 3, 7, 10],
    'maj7': [0, 4, 7, 11], 'M7': [0, 4, 7, 11],
    'dim': [0, 3, 6], 'dim7': [0, 3, 6, 9],
    'aug': [0, 4, 8],
    'sus2': [0, 2, 7], 'sus4': [0, 5, 7],
    'add9': [0, 4, 7, 14],
    '6': [0, 4, 7, 9], 'm6': [0, 3, 7, 9],
    '9': [0, 4, 7, 10, 14], 'm9': [0, 3, 7, 10, 14],
}


def _parse_chord_symbol(symbol: str) -> Optional[Tuple[int, List[int]]]:
    """
    Parse a chord symbol like 'Am', 'F', 'Cmaj7', 'Dm7'.
    Returns (root_semitone, intervals).
    """
    symbol = symbol.strip()
    if not symbol or symbol == '.' or symbol == '-':
        return None
    
    # Normalize flats
    for flat, sharp in FLATS.items():
        if symbol.startswith(flat):
            symbol = sharp + symbol[len(flat):]
            break
    
    m = re.match(r'^([A-G])([#b]?)(.*)$', symbol)
    if not m:\n        return None\n    \n    root_letter = m.group(1)\n    accidental = m.group(2)\n    quality = m.group(3).strip()\n    \n    root = NOTE_TO_SEMITONE[root_letter]
    if accidental == '#':
        root += 1
    elif accidental == 'b':
        root -= 1
    
    intervals = CHORD_SHAPES.get(quality)
    if intervals is None:
        # Try common variations
        if quality.lower() == 'maj7':
            intervals = CHORD_SHAPES['maj7']
        elif quality == '':
            intervals = CHORD_SHAPES['']
        else:
            # Try to match prefix
            for q in sorted(CHORD_SHAPES.keys(), key=len, reverse=True):
                if quality.startswith(q):
                    intervals = CHORD_SHAPES[q]
                    break
            else:
                intervals = CHORD_SHAPES['']
    
    return (root, intervals)


def _render_chord_bar(track, tokens, bar_start, bar_dur, beat_dur,
                      slots_per_beat, slot_dur, swing_amount, rng):
    """Render chord tokens for one bar."""
    # Filter out dots and dashes, find chord change points
    events = []
    current_chord = None
    
    for idx, token in enumerate(tokens):
        if token == '.' or token == '-':
            events.append(("sustain" if token == '.' else "rest", None))
        else:
            chord = _parse_chord_symbol(token)
            if chord:
                events.append(("chord", chord))
                current_chord = chord
            else:
                events.append(("sustain", None))
    
    if not events:
        return
    
    # Group: each chord lasts until the next chord or end of bar
    idx = 0
    while idx < len(events):
        etype, chord = events[idx]
        
        if etype == "chord":
            # Find how long this chord lasts
            duration_slots = 1
            for j in range(idx + 1, len(events)):
                if events[j][0] == "chord":
                    break
                duration_slots += 1
            
            slot_idx = idx
            time_start = bar_start + slot_idx * slot_dur
            time_end = bar_start + (slot_idx + duration_slots) * slot_dur
            dur = time_end - time_start
            
            root, intervals = chord
            base_midi = 12 + 4 * 12 + root  # octave 4
            
            for i, iv in enumerate(intervals):
                pitch = base_midi + iv
                vel = max(20, min(127, 70 + rng.randint(-5, 5)))
                offset = i * 0.015  # slight strum
                track.notes.append(pretty_midi.Note(
                    velocity=vel, pitch=pitch,
                    start=time_start + offset,
                    end=time_start + offset + dur * 0.9
                ))
        
        idx += 1


def _render_melody_bar(track, tokens, bar_start, bar_dur, beat_dur,
                       slots_per_beat, slot_dur, swing_amount, rng, vel_base=80):
    """Render melody/player note tokens for one bar."""
    events = _tokens_to_events(tokens)
    
    if not events:
        return
    
    # Track active (sustained) notes for '.' extension
    active_notes = []  # list of (note_obj, start_time)
    
    for idx, ev in enumerate(events):
        slot_time = bar_start + idx * slot_dur
        
        # Apply swing to odd slots (off-beats)
        if slots_per_beat > 1:
            within_beat = idx % slots_per_beat
            if within_beat > 0 and within_beat % 2 == 1:
                slot_time += swing_amount
        
        if ev["type"] == "rest":
            # End any active notes
            for n in active_notes:
                n.end = max(n.end, slot_time)
            active_notes = []
        elif ev["type"] == "sustain":
            # Extend active notes
            for n in active_notes:
                n.end = slot_time + slot_dur
        elif ev["type"] == "note":
            # End previous active notes
            for n in active_notes:
                n.end = max(n.end, slot_time)
            active_notes = []
            
            # Start new notes
            for pitch in ev["pitches"]:
                vel = max(20, min(127, vel_base + rng.randint(-5, 5)))
                note = pretty_midi.Note(
                    velocity=vel,
                    pitch=pitch,
                    start=slot_time,
                    end=slot_time + slot_dur
                )
                track.notes.append(note)
                active_notes.append(note)
    
    # End any remaining active notes at bar end
    bar_end = bar_start + bar_dur
    for n in active_notes:
        n.end = min(n.end, bar_end)


# ---------------------------------------------------------------------------
# WAV Synthesis
# ---------------------------------------------------------------------------

def midi_freq(midi_note: int) -> float:
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


def adsr_envelope(length, sr, attack=0.01, decay=0.1, sustain=0.6, release=0.1):
    """Generate an ADSR envelope."""
    ts = int(length * sr)
    if ts <= 0:
        return np.zeros(1)
    env = np.zeros(ts, dtype=np.float64)
    a = min(max(1, int(attack * sr)), ts)
    r = min(max(1, int(release * sr)), ts)
    d = min(max(1, int(decay * sr)), max(1, ts - a - r))
    s = max(0, ts - a - d - r)
    env[:a] = np.linspace(0, 1, a)
    if d > 0:
        env[a:a+d] = np.linspace(1, sustain, d)
    env[a+d:a+d+s] = sustain
    rs = a + d + s
    ar = ts - rs
    if ar > 0:
        env[rs:] = np.linspace(sustain if s > 0 else 1.0, 0, ar)
    return env


def synth_piano(freq, dur, sr):
    t = np.linspace(0, dur, int(dur * sr), endpoint=False)
    w = np.zeros_like(t)
    for h, a in [(1, 1.0), (2, 0.4), (3, 0.2), (4, 0.1)]:
        w += a * np.sign(np.sin(2 * np.pi * freq * h * t))
    k = np.ones(3) / 3
    w = np.convolve(w, k, mode='same')
    env = adsr_envelope(dur, sr, 0.005, 0.3, 0.3, 0.2)
    return w[:len(env)] * env * 0.5


def synth_bass(freq, dur, sr):
    t = np.linspace(0, dur, int(dur * sr), endpoint=False)
    w = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * freq * 2 * t)
    env = adsr_envelope(dur, sr, 0.02, 0.15, 0.5, 0.1)
    return w[:len(env)] * env * 0.6


def synth_strings(freq, dur, sr):
    t = np.linspace(0, dur, int(dur * sr), endpoint=False)
    w = 2 * (freq * t - np.floor(freq * t + 0.5))
    w += 0.5 * (2 * (freq * 1.005 * t - np.floor(freq * 1.005 * t + 0.5)))
    w += 0.5 * (2 * (freq * 0.995 * t - np.floor(freq * 0.995 * t + 0.5)))
    k = np.ones(5) / 5
    w = np.convolve(w, k, mode='same')
    env = adsr_envelope(dur, sr, 0.15, 0.1, 0.7, 0.3)
    return w[:len(env)] * env * 0.3


def synth_flute(freq, dur, sr):
    t = np.linspace(0, dur, int(dur * sr), endpoint=False)
    vib = 1 + 0.02 * np.sin(2 * np.pi * 5.5 * t)
    w = np.sin(2 * np.pi * freq * vib * t) + 0.15 * np.sin(2 * np.pi * freq * 2 * vib * t)
    env = adsr_envelope(dur, sr, 0.08, 0.05, 0.8, 0.15)
    return w[:len(env)] * env * 0.5


def synth_guitar(freq, dur, sr):
    t = np.linspace(0, dur, int(dur * sr), endpoint=False)
    w = np.zeros_like(t)
    for h, a in [(1, 1.0), (2, 0.5), (3, 0.3), (4, 0.15)]:
        dh = math.exp(-2 * h * 0.5)
        w += a * dh * np.sin(2 * np.pi * freq * h * t)
    env = adsr_envelope(dur, sr, 0.003, 0.4, 0.2, 0.3)
    return w[:len(env)] * env * 0.4


def synth_drum(dur, sr, dtype='kick'):
    n = max(1, int(dur * sr))
    t = np.linspace(0, dur, n, endpoint=False)
    if dtype == 'kick':
        pe = 150 * np.exp(-30 * t) + 50
        phase = np.cumsum(2 * np.pi * pe / sr)
        return np.sin(phase) * np.exp(-8 * t) * 0.7
    elif dtype == 'snare':
        noise = np.random.uniform(-1, 1, n)
        tone = np.sin(2 * np.pi * 180 * t) * 0.5
        w = noise * 0.7 + tone
        k = np.ones(3) / 3
        w = np.convolve(w, k, mode='same')[:n]
        return w * np.exp(-15 * t) * 0.5
    else:
        noise = np.random.uniform(-1, 1, n)
        k = np.ones(5) / 5
        smooth = np.convolve(noise, k, mode='same')[:n]
        w = noise - smooth
        return w * np.exp(-40 * t) * 0.3


SYNTH_FUNCTIONS = {
    'piano': synth_piano,
    'bass': synth_bass,
    'strings': synth_strings,
    'flute': synth_flute,
    'guitar': synth_guitar,
}
DRUM_MAP = {36: 'kick', 38: 'snare', 42: 'hat', 46: 'hat'}


def midi_to_wav(midi_path: str, output_path: Optional[str] = None, sr: int = 44100) -> str:
    """Render a MIDI file to WAV using numpy synthesis."""
    pm = pretty_midi.PrettyMIDI(midi_path)
    end_time = pm.get_end_time() if pm.instruments else 0.0
    total_samples = int(end_time * sr) + sr
    output = np.zeros(total_samples, dtype=np.float64)
    
    for inst in pm.instruments:
        is_drum = inst.is_drum
        inst_name = 'drums' if is_drum else None
        
        if not inst_name:
            # Identify instrument by program number
            for nm, gp in GM_PROGRAMS.items():
                if inst.program == gp:
                    inst_name = nm
                    break
            if not inst_name:
                # Try by track name
                if inst.name:
                    inst_name = _get_instrument_name_for_player(inst.name)
                else:
                    inst_name = 'piano'
        
        for note in inst.notes:
            freq = midi_freq(note.pitch)
            dur = note.end - note.start
            if dur <= 0:
                continue
            sample_start = int(note.start * sr)
            vel = note.velocity / 127.0
            
            if is_drum:
                dt = DRUM_MAP.get(note.pitch, 'hat')
                wave = synth_drum(dur, sr, dt)
            else:
                sf = SYNTH_FUNCTIONS.get(inst_name, synth_piano)
                wave = sf(freq, dur, sr)
            
            wave = wave * vel
            end_sample = sample_start + len(wave)
            if end_sample > len(output):
                wave = wave[:len(output) - sample_start]
                end_sample = len(output)
            if sample_start < len(output):
                output[sample_start:end_sample] += wave[:end_sample - sample_start]
    
    # Normalize
    peak = np.max(np.abs(output))
    if peak > 0:
        output = output / peak * 0.85
    
    if output_path is None:
        output_path = midi_path.replace('.mid', '.wav')
    
    wav_io.write(output_path, sr, (output * 32767).astype(np.int16))
    return output_path


def compile_to_wav(comp: Dict[str, Any], output_path: Optional[str] = None,
                   tempo_override: Optional[int] = None,
                   swing_override: Optional[int] = None) -> str:
    """Compile composition to WAV. Returns path."""
    midi_path = compile_to_midi(comp, tempo_override=tempo_override, swing_override=swing_override)
    if output_path is None:
        h = hashlib.md5(comp.get("raw_text", "").encode()).hexdigest()[:8]
        output_path = os.path.join(OUTPUT_DIR, f'tapscript_v2_{h}.wav')
    return midi_to_wav(midi_path, output_path)


# ---------------------------------------------------------------------------
# Example Compositions
# ---------------------------------------------------------------------------

EXAMPLE_HARBOR_DAWN = """**TRACK: Harbor Dawn**
[MetaData]
key: Am | tempo: 60 | swing: 0% | subdivision: 8th

[V1] (Verse - Fog Lifting - 4 Bars)
Chords:  | Am    .    | .     .    | F     .    | C     .    |
Melody: | A4    .    .   .  | E4    .    F4   .  | C4    .    A3   .  | E4    .    .    .  |
Lyrics: | dawn  .    .   .  | breaks slow       | over still water  | waking the harbor  |
@wesley | a2    .    .   .  | e2    .    f2   .  | c2    .    a1    .  | e2    .    .    .  | vel: 55

[C] (Chorus - Light Spreading - 4 Bars)
Chords:  | Am    F     | C     G     | Am    F     | G     .     |
Melody: | C5    .    A4    .   | A4    .    G4    .   | C5    .    E5    .   | D5    .    .     .  |
Lyrics: | gold   on    the    pier | silver on grey      | morning is      here | day       breaks      clear         |
@wesley | a2    f2    | c2    g2    | a2    f2    | g2    .    | vel: 65
@hermes | a1    .    f1    .   | a1    .    .     .   | f1    .    c1    .   | g1    .    .     .  | vel: 50

[Outro] (Fog Dissolving - 2 Bars)
Chords:  | Am    .    | .     .    |
Melody: | A4    .    .   .  | -     .    .    .  |
Lyrics: | silence...        | ...           |
@wesley | a2    .    .   .  | -     .    .    .  | vel: 40
"""

EXAMPLE_THE_ROOM_IS_SAFE = """**TRACK: The Room Is Safe**
[MetaData]
key: Em | tempo: 68 | swing: 5% | subdivision: 8th

[V1] (Verse - Lullaby - 4 Bars)
Chords:  | Em    .    .      | C     .    .      | G     .    .      | D     .    .      |
Melody: | E4    .   G4   .   | C4    .   E4   .   | D4    .   G4   .   | A4    .   F#4  .   |
Lyrics: | close your eyes    | safe in the room   | nothing can harm   | you are so warm    |
@wesley | e2    .   g2   .   | c2    .   e2   .   | d2    .   g2   .   | a2    .   f#2  .   | vel: 50
@hermes | e1    .   .    .   | c1    .   .    .   | g1    .   .    .   | d1    .   .    .   | vel: 45

[C] (Chorus - Softer - 4 Bars)
Chords:  | C     .    D     .   | Em    .    .    .   | C     .    D     .   | Em    .    .    .   |
Melody: | C5    .    D5    .   | E5    .    D5   .   | C5    .    A4   .   | B4    .    G4   .   |
Lyrics: | sleep  now  drift  off | rest   in    the   | quiet  safe  arms  | of     night          |
@wesley | c2    .    d2    .   | e2    .    d2   .   | c2    .    a2   .   | b2    .    g2   .   | vel: 55
@hermes | c1    .    d1    .   | e1    .    .    .   | c1    .    d1    .   | e1    .    .    .   | vel: 45

[Outro] (Drifting - 2 Bars)
Chords:  | Em    .    .   .   | .     .    .   .   |
Melody: | E4    .    -   .   | -     .    -   .   |
Lyrics: | shhh...             | ...                 |
@wesley | e2    .    -   .   | -     .    -   .   | vel: 35
"""

EXAMPLE_CREATURES_OF_INTERVAL = """**TRACK: Creatures of Interval**
[MetaData]
key: Am | tempo: 85 | swing: 12% | subdivision: 16th

[V1] (Verse - Indie Folk - 4 Bars)
Chords:  | Am    .    F     .    | C     .    G     .    |
Melody: | E4    . . . A4    . . . | G4    . . . E4    . . . |
Lyrics: | we walk in intervals     | counting every step     |
@flash  | a2-c3 . . . f2-a2-c3 . . . | c2-e2 . . . g2-b2-d3 . . . | vel: 75
@hermes | a1    . . . f1    . . . | c1    . . . g1    . . . | vel: 65

[C] (Chorus - Lift - 4 Bars)
Chords:  | F     .    C     .    | G     .    Am    .    |
Melody: | A4    .    C5    .    | D5    .    C5    A4   |
Lyrics: | creatures of the light  | dancing through the night |
@flash  | f2-a2-c3 . . c2-e2-g2 . . | g2-b2-d3 . . a2-c3-e3 . . | vel: 80
@hermes | f1    . . c1    . . | g1    . . a1    . . | vel: 70

[B] (Bridge - Quiet - 2 Bars)
Chords:  | Dm    .    .     .    | Am    .    .     .    |
Melody: | D4    .    .     .    | C4    .    A3    .    |
Lyrics: | hold still              | breathe                  |
@flash  | d2-a2 . . . . . . . . . | a2-e2 . . . . . . . . . | vel: 55
@hermes | d1    . . . . . . . . . | a1    . . . . . . . . . | vel: 45
"""

EXAMPLE_NEON_SHADOWS = """**TRACK: Neon Shadows**
[MetaData]
key: Am | tempo: 75 | swing: 10% | subdivision: 16th

[V1] (Verse - 4 Bars)
Chords:  | Am    .    | F     G    |
Melody: | E4    . . . | A4    . G4 E4 |
Lyrics: | I     . . . | write . in code |
@wesley | e2-a2-c3 . . | f2-a2-c3 g2-b2-d3 | vel: 60

[C] (Chorus - Louder)
Chords:  | Am    F     C     G    | Am    F     C     G    |
Melody: | A4    C5    A4    G4   | A4    C5    D5    E5   |
Lyrics: | This  is    the   new  | syn   -     tax   for  |
@flash  | a2    f2    c2    g2   | a2    f2    c2    g2   | vel: 80
@hermes | a1    .     a1    .    | f1    .     g1    .    | vel: 75
"""

EXAMPLE_DECK_WORK = """**TRACK: Deck Work**
[MetaData]
key: A | tempo: 120 | swing: 8% | subdivision: 16th

[V1] (Verse - Driving - 4 Bars)
Chords:  | A     .    .     .    | D     .    .     .    | A     .    .     .    | E     .    .     .    |
Melody: | A4    . . . E5    . . . | D5    . . . C#5  . . . | A4    . . . B4   . . . | E4    . . . D4   . . . |
Lyrics: | haul and coil           | pull and tie            | work the deck           | the rhythm of sweat     |
@flash  | a2-e3 . . . a2-e3 . . . | d2-a2 . . . d2-a2 . . . | a2-e3 . . . a2-e3 . . . | e2-b2 . . . e2-b2 . . . | vel: 80
@hermes | a1    . . . a1    . . . | d1    . . . d1    . . . | a1    . . . a1    . . . | e1    . . . e1    . . . | vel: 70

[C] (Chorus - Full Pull - 4 Bars)
Chords:  | A     .    D     .    | A     .    E     .    | D     .    A     .    | E     .    A     .    |
Melody: | E5    . . D5    . C#5 . | E5    . . A4    . B4  . | D5    . C#5    . B4  . | C#5   . B4    . A4  . |
Lyrics: | heave                ho | heave                ho | the tide            runs | strong               out   |
@flash  | a2-e3 . . d2-a2 . . . | a2-e3 . . e2-b2 . . . | d2-a2 . . a2-e3 . . . | e2-b2 . . a2-e3 . . . | vel: 85
@hermes | a1    . . d1    . . . | a1    . . e1    . . . | d1    . . a1    . . . | e1    . . a1    . . . | vel: 75
"""


EXAMPLES = {
    'harbor_dawn': ('🌅 Harbor Dawn', EXAMPLE_HARBOR_DAWN),
    'the_room_is_safe': ('🛏️ The Room Is Safe', EXAMPLE_THE_ROOM_IS_SAFE),
    'creatures_of_interval': ('🌲 Creatures of Interval', EXAMPLE_CREATURES_OF_INTERVAL),
    'neon_shadows': ('🌃 Neon Shadows', EXAMPLE_NEON_SHADOWS),
    'deck_work': ('⚓ Deck Work', EXAMPLE_DECK_WORK),
}


# ---------------------------------------------------------------------------
# Web UI
# ---------------------------------------------------------------------------

WEB_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TapScript v2 Studio</title>
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
    --lyric: #7cd4f0;
    --sustain: #555570;
    --error: #f07c7c;
    --success: #7cf0a8;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', 'Cascadia Code', 'Courier New', monospace;
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
    gap: 12px;
    flex-shrink: 0;
    flex-wrap: wrap;
  }
  .logo { font-size: 18px; font-weight: bold; color: var(--accent); letter-spacing: 1px; white-space: nowrap; }
  
  .topbar select, .topbar button, .topbar input[type="number"] {
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
  .controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  .controls label { font-size: 12px; color: var(--text-dim); white-space: nowrap; }
  
  input[type="range"] {
    -webkit-appearance: none;
    height: 4px;
    background: var(--border);
    border-radius: 2px;
    outline: none;
    width: 100px;
  }
  input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 14px;
    height: 14px;
    background: var(--accent);
    border-radius: 50%;
    cursor: pointer;
  }
  
  .main { display: flex; flex: 1; overflow: hidden; }
  .panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-width: 0; }
  .panel-header {
    padding: 8px 16px;
    background: var(--bg-elev);
    border-bottom: 1px solid var(--border);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-dim);
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
    white-space: pre;
    overflow: auto;
  }
  #editor:focus { background: #0d0d14; }
  
  .right-panel { display: flex; flex-direction: column; flex: 1; overflow: hidden; }
  
  .preview-area {
    flex: 1;
    overflow: auto;
    padding: 16px;
  }
  
  .parsed-info {
    padding: 12px 16px;
    background: var(--bg-elev2);
    border-radius: 8px;
    margin-bottom: 12px;
    font-size: 13px;
    color: var(--text-dim);
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
  }
  .parsed-info span b { color: var(--text); }
  
  .audio-area {
    padding: 16px;
    border-top: 1px solid var(--border);
    background: var(--bg-elev);
    flex-shrink: 0;
  }
  
  .status {
    padding: 8px 16px;
    background: var(--bg-elev);
    border-top: 1px solid var(--border);
    font-size: 12px;
    color: var(--text-dim);
    flex-shrink: 0;
  }
  .status.error { color: var(--error); }
  .status.success { color: var(--success); }
  
  audio { width: 100%; margin-top: 8px; }
  
  .notation-display {
    white-space: pre-wrap;
    font-size: 13px;
    line-height: 1.7;
    font-family: inherit;
  }
  .ts-title { color: var(--accent); font-weight: bold; }
  .ts-meta { color: var(--header); }
  .ts-section-label { color: var(--section); font-weight: bold; }
  .ts-chord-line { color: var(--chord); }
  .ts-melody-line { color: var(--note); }
  .ts-lyric-line { color: var(--lyric); }
  .ts-player-line { color: var(--instrument); }
  
  .btn-group { display: flex; gap: 8px; flex-wrap: wrap; }
  
  .download-btn {
    display: inline-block;
    padding: 6px 14px;
    background: var(--accent-dim);
    color: var(--text);
    text-decoration: none;
    border-radius: 6px;
    font-size: 12px;
    border: none;
    cursor: pointer;
    font-family: inherit;
  }
  .download-btn:hover { background: var(--accent); }
  .download-btn:disabled { opacity: 0.4; cursor: default; }
  
  .loading { opacity: 0.6; pointer-events: none; }
  
  .ai-area {
    padding: 12px 16px;
    border-top: 1px solid var(--border);
    background: var(--bg-elev2);
  }
  .ai-area input {
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    padding: 8px 12px;
    border-radius: 6px;
    font-family: inherit;
    font-size: 13px;
    width: calc(100% - 80px);
  }
  .ai-area button {
    background: var(--accent-dim);
    color: var(--text);
    border: none;
    padding: 8px 16px;
    border-radius: 6px;
    font-family: inherit;
    font-size: 13px;
    cursor: pointer;
    margin-left: 4px;
  }
  .ai-area button:hover { background: var(--accent); }
</style>
</head>
<body>
<div class="app">
  <div class="topbar">
    <div class="logo">🎵 TapScript v2</div>
    <select id="exampleSelect">
      <option value="">— Load Example —</option>
      <option value="harbor_dawn">🌅 Harbor Dawn</option>
      <option value="the_room_is_safe">🛏️ The Room Is Safe</option>
      <option value="creatures_of_interval">🌲 Creatures of Interval</option>
      <option value="neon_shadows">🌃 Neon Shadows</option>
      <option value="deck_work">⚓ Deck Work</option>
    </select>
    <div class="spacer"></div>
    <div class="controls">
      <label>Key:</label>
      <select id="keySelect">
        <option value="">Original</option>
        <option value="C">C / Cm</option>
        <option value="C#">C# / C#m</option>
        <option value="D">D / Dm</option>
        <option value="D#">D# / D#m</option>
        <option value="E">E / Em</option>
        <option value="F">F / Fm</option>
        <option value="F#">F# / F#m</option>
        <option value="G">G / Gm</option>
        <option value="G#">G# / G#m</option>
        <option value="A">A / Am</option>
        <option value="A#">A# / A#m</option>
        <option value="B">B / Bm</option>
      </select>
      <label>Tempo:</label>
      <input type="range" id="tempoSlider" min="40" max="200" value="120">
      <span id="tempoValue" style="min-width:30px;text-align:center">120</span>
      <label>Swing:</label>
      <input type="range" id="swingSlider" min="0" max="50" value="0">
      <span id="swingValue" style="min-width:30px;text-align:center">0%</span>
      <button class="primary" id="playBtn">▶ Play</button>
    </div>
  </div>
  <div class="main">
    <div class="panel" style="flex: 1;">
      <div class="panel-header">📝 Notation Editor</div>
      <textarea id="editor" spellcheck="false" placeholder="Type or paste TapScript v2 here..."></textarea>
    </div>
    <div class="panel" style="flex: 1;">
      <div class="panel-header">🎶 Output</div>
      <div class="right-panel">
        <div class="preview-area">
          <div class="parsed-info" id="parsedInfo">— Load an example or start typing —</div>
          <div class="btn-group" style="margin-bottom:12px;">
            <button class="download-btn" id="midiBtn" disabled>⬇ Download MIDI</button>
            <button class="download-btn" id="wavBtn" disabled>⬇ Download WAV</button>
          </div>
        </div>
        <div class="audio-area" id="audioArea">
          <audio id="player" controls style="display:none;"></audio>
        </div>
        <div class="ai-area" id="aiArea" style="display:none;">
          <input type="text" id="aiInput" placeholder="Describe music for AI composition...">
          <button id="aiBtn">✨ Compose</button>
        </div>
      </div>
    </div>
  </div>
  <div class="status" id="status">Ready. Load an example to begin.</div>
</div>

<script>
const $ = id => document.getElementById(id);
const editor = $('editor');
const statusEl = $('status');
const player = $('player');
const keySelect = $('keySelect');
const tempoSlider = $('tempoSlider');
const tempoValue = $('tempoValue');
const swingSlider = $('swingSlider');
const swingValue = $('swingValue');
const midiBtn = $('midiBtn');
const wavBtn = $('wavBtn');

let lastRender = null;
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
    const err = await r.json().catch(() => ({error: r.statusText}));
    throw new Error(err.error || 'Request failed');
  }
  return r.json();
}

async function updatePreview() {
  const text = editor.value;
  if (!text.trim()) {
    $('parsedInfo').textContent = '— Empty —';
    midiBtn.disabled = true;
    wavBtn.disabled = true;
    return;
  }
  try {
    const data = await api('parse', { tapscript: text });
    const players = data.players && data.players.length ? data.players.join(', ') : 'none';
    $('parsedInfo').innerHTML = [
      'Key: <b>' + data.key + '</b>',
      'Tempo: <b>' + data.tempo + '</b> BPM',
      'Swing: <b>' + data.swing + '%</b>',
      'Subdivision: <b>' + data.subdivision + '</b>',
      'Sections: <b>' + data.sections + '</b>',
      'Bars: <b>' + data.bars + '</b>',
      'Players: <b>' + players + '</b>'
    ].join('  •  ');
    midiBtn.disabled = false;
    wavBtn.disabled = false;
    setStatus('Parsed OK.', 'success');
  } catch(e) {
    setStatus('Parse error: ' + e.message, 'error');
  }
}

async function play() {
  let text = editor.value;
  if (!text.trim()) { setStatus('Nothing to play.', 'error'); return; }
  
  // Apply key transposition if selected
  const key = keySelect.value;
  if (key) {
    try {
      const transposed = await api('transpose', { tapscript: text, key: key });
      text = transposed.tapscript;
      editor.value = text;
    } catch(e) {
      setStatus('Transpose error: ' + e.message, 'error');
      return;
    }
  }
  
  const tempo = parseInt(tempoSlider.value);
  const swing = parseInt(swingSlider.value);
  
  setStatus('Rendering audio...');
  document.body.classList.add('loading');
  try {
    const data = await api('compile', { tapscript: text, tempo: tempo, swing: swing });
    if (data.errors && data.errors.length) {
      setStatus('Warnings: ' + data.errors.join('; '), 'error');
    }
    if (data.wav_path) {
      player.src = '/api/download?path=' + encodeURIComponent(data.wav_path) + '&type=wav&t=' + Date.now();
      player.style.display = 'block';
      player.play();
      setStatus('Playing... ▶  MIDI: ' + (data.midi_path || 'N/A'), 'success');
    }
    lastRender = data;
    updatePreview();
  } catch(e) {
    setStatus('Render error: ' + e.message, 'error');
  } finally {
    document.body.classList.remove('loading');
  }
}

async function downloadMidi() {
  const text = editor.value;
  if (!text.trim()) return;
  try {
    const data = await api('compile', { tapscript: text, midi_only: true });
    if (data.midi_path) {
      window.location.href = '/api/download?path=' + encodeURIComponent(data.midi_path) + '&type=mid';
    }
  } catch(e) { setStatus('Error: ' + e.message, 'error'); }
}

async function downloadWav() {
  const text = editor.value;
  if (!text.trim()) return;
  try {
    const data = await api('compile', { tapscript: text, wav_only: true });
    if (data.wav_path) {
      window.location.href = '/api/download?path=' + encodeURIComponent(data.wav_path) + '&type=wav';
    }
  } catch(e) { setStatus('Error: ' + e.message, 'error'); }
}

async function loadExample(name) {
  try {
    const data = await fetch('/api/example/' + name).then(r => r.json());
    editor.value = data.tapscript;
    keySelect.value = '';
    tempoSlider.value = data.tempo || 120;
    tempoValue.textContent = tempoSlider.value;
    swingSlider.value = data.swing || 0;
    swingValue.textContent = (data.swing || 0) + '%';
    updatePreview();
    setStatus('Loaded: ' + data.name, 'success');
  } catch(e) { setStatus('Error loading example: ' + e.message, 'error'); }
}

// Event listeners
editor.addEventListener('input', () => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(updatePreview, 600);
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
    setStatus('Transposed to ' + key, 'success');
  } catch(e) { setStatus('Transpose error: ' + e.message, 'error'); }
});

tempoSlider.addEventListener('input', () => {
  tempoValue.textContent = tempoSlider.value;
});

swingSlider.addEventListener('input', () => {
  swingValue.textContent = swingSlider.value + '%';
});

// Keyboard shortcut: Ctrl+Enter to play
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault();
    play();
  }
});

// AI composition
const aiBtn = $('aiBtn');
const aiInput = $('aiInput');

async function compose() {
  const desc = aiInput.value.trim();
  if (!desc) return;
  setStatus('Asking AI to compose...');
  try {
    const data = await api('compose', { description: desc });
    if (data.tapscript) {
      editor.value = data.tapscript;
      updatePreview();
      setStatus('AI composition ready!', 'success');
    }
  } catch(e) { setStatus('AI error: ' + e.message, 'error'); }
}

aiBtn.addEventListener('click', compose);
aiInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') compose();
});

// Show AI area if DeepSeek key is available
fetch('/api/status').then(r => r.json()).then(data => {
  if (data.deepseek) {
    $('aiArea').style.display = 'block';
  }
}).catch(() => {});

// Load default example
loadExample('neon_shadows');
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send_json(self, data, code=200):
        b = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _send_html(self, html):
        b = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _send_file(self, path, mime, name=None):
        with open(path, 'rb') as f:\n            data = f.read()\n        self.send_response(200)\n        self.send_header("Content-Type", mime)
        if name:
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in ('', '/'):
            self._send_html(WEB_HTML)

        elif path == '/api/status':
            self._send_json({"deepseek": bool(DEEPSEEK_KEY)})

        elif path == '/api/examples':
            self._send_json({
                "examples": [{"id": k, "name": v[0]} for k, v in EXAMPLES.items()]
            })

        elif path.startswith('/api/example/'):
            name = path.split('/')[-1]
            if name in EXAMPLES:
                title, text = EXAMPLES[name]
                comp = parse_tapscript(text)
                self._send_json({
                    "name": title,
                    "tapscript": text,
                    "tempo": comp["tempo"],
                    "swing": comp["swing"],
                })
            else:
                self._send_json({"error": "Example not found"}, 404)

        elif path == '/api/download':
            file_path = qs.get('path', [''])[0]
            file_type = qs.get('type', ['wav'])[0]
            if not file_path or '..' in file_path:
                self._send_json({"error": "Invalid path"}, 400)
                return
            if not os.path.exists(file_path):
                self._send_json({"error": "File not found"}, 404)
                return
            if not file_path.startswith(OUTPUT_DIR):
                self._send_json({"error": "Access denied"}, 403)
                return
            if file_type == 'wav':
                self._send_file(file_path, 'audio/wav', os.path.basename(file_path))
            else:
                self._send_file(file_path, 'audio/midi', os.path.basename(file_path))
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/parse':
            self._handle_parse()
        elif path == '/api/compile':
            self._handle_compile()
        elif path == '/api/transpose':
            self._handle_transpose()
        elif path == '/api/compose':
            self._handle_compose()
        else:
            self.send_error(404)

    def _handle_parse(self):
        body = self._read_body()
        text = body.get('tapscript', '')
        if not text.strip():
            self._send_json({"error": "Empty input"}, 400)
            return
        try:
            comp = parse_tapscript(text)
            # Collect all player names
            players = set()
            total_bars = 0
            for section in comp["sections"]:
                total_bars += len(section["bars"])
                for bar in section["bars"]:
                    for pname in bar.get("players", {}):
                        players.add(pname)

            self._send_json({
                "title": comp["title"],
                "key": comp["key"] + ("m" if comp["key_quality"] == "minor" else ""),
                "tempo": comp["tempo"],
                "swing": comp["swing"],
                "subdivision": comp["subdivision"],
                "sections": len(comp["sections"]),
                "bars": total_bars,
                "players": sorted(players),
            })
        except Exception as e:\n            self._send_json({"error": str(e)}, 500)

    def _handle_compile(self):
        body = self._read_body()
        text = body.get('tapscript', '')
        tempo_override = body.get('tempo')
        swing_override = body.get('swing')
        midi_only = body.get('midi_only', False)
        wav_only = body.get('wav_only', False)

        if not text.strip():
            self._send_json({"error": "Empty input"}, 400)
            return

        try:
            comp = parse_tapscript(text)
            errors = []

            midi_path = compile_to_midi(
                comp,
                tempo_override=tempo_override,
                swing_override=swing_override,
            )

            wav_path = None
            if not midi_only:
                wav_path = midi_to_wav(midi_path)

            result = {
                "success": True,
                "midi_path": midi_path,
                "wav_path": wav_path,
                "errors": errors,
            }
            self._send_json(result)
        except Exception as e:\n            self._send_json({\n                "error": str(e),
                "trace": traceback.format_exc(),
            }, 500)

    def _handle_transpose(self):
        body = self._read_body()
        text = body.get('tapscript', '')
        new_key = body.get('key', 'C')
        if not text.strip():
            self._send_json({"error": "Empty input"}, 400)
            return
        try:
            transposed = transpose_text(text, new_key)
            self._send_json({"tapscript": transposed})
        except Exception as e:\n            self._send_json({"error": str(e)}, 500)

    def _handle_compose(self):
        body = self._read_body()
        description = body.get('description', '')
        if not description.strip():
            self._send_json({"error": "No description"}, 400)
            return
        if not DEEPSEEK_KEY:
            self._send_json({"error": "DeepSeek API key not configured"}, 503)
            return

        try:
            import urllib.request

            system_prompt = (
                "You are a music composer. The user will describe a mood, scene, or feeling. "
                "Respond with a TapScript v2 composition. Use this EXACT format:\n\n"
                "**TRACK: Title**\n"
                "[MetaData]\n"
                "key: Am | tempo: 75 | swing: 10% | subdivision: 16th\n\n"
                "[V1] (Verse - 4 Bars)\n"
                "Chords:  | Am    .    | F     G    |\n"
                "Melody: | E4    . . . | A4    . G4 E4 |\n"
                "Lyrics: | I     . . . | write . in code |\n"
                "@wesley | e2-a2-c3 . . | f2-a2-c3 g2-b2-d3 | vel: 60\n\n"
                "Rules:\n"
                "- Absolute note names: C4=middle C, E4, A4, lowercase for lower octaves (a2, e1)\n"
                "- Dots (.) = sustain, dashes (-) = rest\n"
                "- Pipes (|) separate bars, spaces separate subdivisions\n"
                "- Chord symbols: Am, F, C, G, Dm7, etc.\n"
                "- @player lines: notes, vel: N at end\n"
                "- Hyphenated notes in @player = simultaneous (e2-a2-c3 = chord)\n"
                "- Keep it 2-4 sections, 2-4 bars each\n"
                "- Only output the TapScript, no explanation\n"
            )

            payload = json.dumps({
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": description},
                ],
                "temperature": 0.85,
                "max_tokens": 1500,
                "stream": False,
            }).encode()

            req = urllib.request.Request(DEEPSEEK_URL, data=payload, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {DEEPSEEK_KEY}")

            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                reply = data["choices"][0]["message"]["content"]

            # Extract the tapscript from the reply
            # It might be in a code block or raw
            ts_match = re.search(r'\*\*TRACK:.+?\n.*?(?=\n```|\Z)', reply, re.DOTALL)
            if ts_match:
                tapscript = ts_match.group(0).strip()
            else:
                tapscript = reply.strip()

            self._send_json({"tapscript": tapscript, "raw": reply})
        except Exception as e:\n            self._send_json({"error": str(e)}, 500)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cli_main():
    parser = argparse.ArgumentParser(description='TapScript v2 — absolute notation compiler')
    parser.add_argument('--cli', metavar='FILE', help='Compile a TapScript v2 file')
    parser.add_argument('--midi', metavar='PATH', help='Output MIDI path')
    parser.add_argument('--wav', metavar='PATH', help='Output WAV path')
    parser.add_argument('--example', metavar='NAME', help='Load an example by name')
    parser.add_argument('--port', type=int, default=PORT, help='Web server port')
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

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
        with open(args.cli) as f:\n            text = f.read()\n        comp = parse_tapscript(text)\n        if args.midi:
            print(f'MIDI: {compile_to_midi(comp, args.midi)}')
        if args.wav:
            print(f'WAV: {compile_to_wav(comp, args.wav)}')
        if not args.midi and not args.wav:
            print(f'Title: {comp["title"]}')
            print(f'Key: {comp["key"]}')
            print(f'Tempo: {comp["tempo"]}')
            print(f'Sections: {len(comp["sections"])}')
            wav_path = compile_to_wav(comp)
            print(f'WAV: {wav_path}')
        return

    # Start web server
    print(f"🎵 TapScript v2 Studio starting on port {args.port}")
    print(f"   DeepSeek key: {'✅ Found' if DEEPSEEK_KEY else '⚠️ Not found'}")
    print(f"   Output dir: {OUTPUT_DIR}")
    print(f"   → http://localhost:{args.port}")
    server = HTTPServer(('0.0.0.0', args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
        server.shutdown()


if __name__ == '__main__':
    cli_main()
