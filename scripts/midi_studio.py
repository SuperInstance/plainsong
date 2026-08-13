#!/usr/bin/env python3
"""
MIDI Generation Studio — web app for AI-guided MIDI composition.
Port 5556. Dark theme. DeepSeek composer chat + pretty_midi generation + numpy WAV synthesis.
"""

import os, sys, json, time, uuid, random, math, re, base64, urllib.request, traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import numpy as np
from scipy.io import wavfile as wav_io
import pretty_midi

PORT = 5556
OUTPUT_DIR = os.path.expanduser("~/.openclaw/workspace/output/audio")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── DeepSeek API ───────────────────────────────────────────────────────────

def load_deepseek_key():
    """Read DEEPSEEK_API_KEY from ~/.bashrc."""
    bashrc = os.path.expanduser("~/.bashrc")
    if not os.path.exists(bashrc):
        return os.environ.get("DEEPSEEK_API_KEY", "")
    with open(bashrc) as f:
        for line in f:
            line = line.strip()
            if line.startswith("export DEEPSEEK_API_KEY="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val
    return os.environ.get("DEEPSEEK_API_KEY", "")

DEEPSEEK_KEY = load_deepseek_key()
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
COMPOSER_SYSTEM = (
    "You are a music composer AI. When the user describes a mood, scene, or feeling, "
    "respond with a JSON block containing: tempo (BPM), key, scale, instruments (list), "
    "sections (list of {name, bars, chord_progression}). Keep responses concise. "
    "Always include the JSON block when suggesting a composition. "
    "Format the JSON inside triple backticks with a json tag like:\n"
    "```json\n{\"tempo\": 75, \"key\": \"A\", \"scale\": \"minor\", ...}\n```\n"
    "Use simple chord notation like Am, F, C, G."
)

def deepseek_chat(messages):
    if not DEEPSEEK_KEY:
        return "⚠️ No DeepSeek API key found. Set DEEPSEEK_API_KEY in ~/.bashrc"
    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": 1200,
        "stream": False,
    }).encode()
    req = urllib.request.Request(DEEPSEEK_URL, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {DEEPSEEK_KEY}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ DeepSeek API error: {e}"

# ─── Music Theory ────────────────────────────────────────────────────────────

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

SCALES = {
    'major':       [0, 2, 4, 5, 7, 9, 11],
    'minor':       [0, 2, 3, 5, 7, 8, 10],
    'dorian':      [0, 2, 3, 5, 7, 9, 10],
    'mixolydian':  [0, 2, 4, 5, 7, 9, 10],
    'pentatonic':  [0, 2, 4, 7, 9],
    'blues':       [0, 3, 5, 6, 7, 10],
}

GM_PROGRAMS = {
    'piano': 0, 'guitar': 24, 'strings': 48, 'flute': 73, 'drums': 0, 'bass': 33,
}

INSTRUMENT_LABELS = {
    'piano': '🎹 Piano', 'guitar': '🎸 Guitar', 'strings': '🎻 Strings',
    'flute': '🪈 Flute', 'drums': '🥁 Drums', 'bass': '🎵 Bass',
}

CHORD_SHAPES = {
    '': [0, 4, 7], 'm': [0, 3, 7], '7': [0, 4, 7, 10], 'm7': [0, 3, 7, 10],
    'maj7': [0, 4, 7, 11], 'dim': [0, 3, 6], 'aug': [0, 4, 8],
    'sus4': [0, 5, 7], 'sus2': [0, 2, 7], 'add9': [0, 4, 7, 2],
    '9': [0, 4, 7, 10, 14], 'm9': [0, 3, 7, 10, 14],
    '6': [0, 4, 7, 9], 'm6': [0, 3, 7, 9],
}

def note_to_root(note_name):
    note_name = note_name.strip()
    sharp = note_name.replace('b', '#')
    flats_to_sharps = {'Bb':'A#', 'Db':'C#', 'Eb':'D#', 'Gb':'F#', 'Ab':'G#', 'Cb':'B', 'Fb':'E'}
    sharp = flats_to_sharps.get(sharp, sharp)
    if sharp in NOTE_NAMES:
        return NOTE_NAMES.index(sharp)
    return 0

def parse_chord(chord_str):
    chord_str = chord_str.strip()
    if not chord_str:
        return None
    m = re.match(r'^([A-G][#b]?)(.*)$', chord_str)
    if not m:
        return None
    root_name = m.group(1)
    quality = m.group(2).strip()
    root = note_to_root(root_name)
    intervals = CHORD_SHAPES.get(quality, CHORD_SHAPES[''])
    return (root, intervals)

def parse_chord_progression(text):
    tokens = text.replace(',', ' ').split()
    chords = []
    for tok in tokens:
        c = parse_chord(tok)
        if c:
            chords.append(c)
    return chords if chords else [(0, CHORD_SHAPES[''])]

def chord_to_midi_notes(chord, octave=4):
    base = 12 + octave * 12
    root, intervals = chord
    return [base + root + iv for iv in intervals]

def scale_note_offsets(scale_name):
    return SCALES.get(scale_name, SCALES['major'])

def get_scale_notes(key_root, scale_intervals, octave=4, count=2):
    base = 12 + octave * 12 + key_root
    notes = []
    for o in range(count):
        for iv in scale_intervals:
            notes.append(base + o * 12 + iv)
    return notes

# ─── MIDI Generation ─────────────────────────────────────────────────────────

def generate_midi(tempo, key_name, scale_name, layers, bars, chord_progression_text, output_path, swing=0.0):
    pm = pretty_midi.PrettyMIDI(initial_tempo=float(tempo))
    key_root = note_to_root(key_name)
    scale_ivs = scale_note_offsets(scale_name)
    chords = parse_chord_progression(chord_progression_text)
    beats_per_bar = 4

    for layer in layers:
        instr_name = layer.get('instrument', 'piano')
        role = layer.get('role', 'chords')
        volume = layer.get('volume', 80)
        program = GM_PROGRAMS.get(instr_name, 0)
        is_drum = instr_name == 'drums'

        if is_drum:
            inst = pretty_midi.Instrument(program=0, is_drum=True)
        else:
            inst = pretty_midi.Instrument(program=program)

        if is_drum:
            notes = generate_drum_track(bars, tempo, volume, swing)
        elif role == 'bassline':
            notes = generate_bass_track(chords, scale_ivs, key_root, bars, tempo, volume, swing)
        elif role == 'melody':
            notes = generate_melody_track(chords, scale_ivs, key_root, bars, tempo, volume, swing)
        elif role == 'pad':
            notes = generate_pad_track(chords, bars, tempo, volume)
        elif role == 'fingerpicking':
            notes = generate_fingerpicking_track(chords, bars, tempo, volume, swing)
        elif role == 'strumming':
            notes = generate_strumming_track(chords, bars, tempo, volume, swing)
        else:
            notes = generate_chord_track(chords, bars, tempo, volume, swing)

        for n in notes:
            inst.notes.append(n)
        pm.instruments.append(inst)

    pm.write(output_path)
    return output_path

def generate_chord_track(chords, bars, tempo, volume, swing=0.0):
    notes = []
    bpb = 4;spb = 60.0 / tempo;cc = len(chords)
    if cc == 0: return notes
    for bar in range(bars):
        chord = chords[bar % cc];st = bar * bpb * spb;dur = bpb * spb * 0.9
        for i, pitch in enumerate(chord_to_midi_notes(chord, 4)):
            vel = max(20, min(127, volume + random.randint(-8, 8)))
            notes.append(pretty_midi.Note(velocity=vel, pitch=pitch, start=st + i*0.02, end=st + i*0.02 + dur))
    return notes

def generate_pad_track(chords, bars, tempo, volume):
    notes = []
    bpb = 4;spb = 60.0 / tempo;cc = len(chords)
    if cc == 0: return notes
    for bar in range(bars):
        chord = chords[bar % cc];st = bar * bpb * spb;dur = bpb * spb * spb * 2
        for pitch in chord_to_midi_notes(chord, 3):
            vel = max(15, min(127, volume - 10 + random.randint(-5, 5)))
            notes.append(pretty_midi.Note(velocity=vel, pitch=pitch, start=st, end=st + dur))
    return notes

def generate_bass_track(chords, scale_ivs, key_root, bars, tempo, volume, swing=0.0):
    notes = []
    bpb = 4;spb = 60.0 / tempo;cc = len(chords)
    if cc == 0: return notes
    scale_notes = get_scale_notes(key_root, scale_ivs, 2, 2)
    for bar in range(bars):
        chord = chords[bar % cc];root, intervals = chord;bn = 12 + 2*12 + root
        for beat in range(bpb):
            sw = (swing * 0.15) if beat % 2 == 1 else 0.0
            st = (bar * bpb + beat) * spb + sw;dur = spb * 0.8
            if beat < 2: pitch = bn
            elif beat == 2: pitch = bn + (intervals[-1] if len(intervals) > 2 else 7)
            else: pitch = scale_notes[random.randint(0, len(scale_notes)-1)]
            vel = max(20, min(127, volume + random.randint(-6, 6)))
            notes.append(pretty_midi.Note(velocity=vel, pitch=pitch, start=st, end=st+dur))
    return notes

def generate_melody_track(chords, scale_ivs, key_root, bars, tempo, volume, swing=0.0):
    notes = []
    bpb = 4;spb = 60.0 / tempo;cc = len(chords)
    if cc == 0: return notes
    scale_notes = get_scale_notes(key_root, scale_ivs, 5, 2)
    patterns = [[0.0,1.0,2.0,3.0],[0.0,0.5,1.5,2.0,3.0,3.5],[0.0,1.0,1.5,2.5,3.0],[0.0,0.75,1.5,2.25,3.0,3.5]]
    ni = 0
    for bar in range(bars):
        chord = chords[bar % cc];root, intervals = chord
        cp = [12 + 5*12 + root + iv for iv in intervals]
        pat = patterns[bar % len(patterns)]
        for i, bo in enumerate(pat):
            sw = (swing * 0.15) if (int(bo*2) % 2) == 1 else 0.0
            st = bar*bpb*spb + bo*spb + sw
            if random.random() < 0.6 and cp: pitch = random.choice(cp)
            else: pitch = scale_notes[ni % len(scale_notes)];ni += 1
            dur = ((pat[i+1] - bo) if i < len(pat)-1 else (bpb - bo)) * spb * 0.85
            dur = max(0.1, dur)
            vel = max(25, min(127, volume + random.randint(-10, 10)))
            notes.append(pretty_midi.Note(velocity=vel, pitch=pitch, start=st, end=st+dur))
    return notes

def generate_fingerpicking_track(chords, bars, tempo, volume, swing=0.0):
    notes = []
    bpb = 4;spb = 60.0 / tempo;cc = len(chords)
    if cc == 0: return notes
    for bar in range(bars):
        chord = chords[bar % cc];root, intervals = chord;base = 12 + 3*12 + root
        iv1 = intervals[1] if len(intervals) > 1 else 4
        iv_last = intervals[-1]
        pp = [base, base+iv1, base+iv_last, base+iv1, base, base+iv_last, base+iv1, base+12]
        eighth = spb * 0.5
        for i, pitch in enumerate(pp):
            sw = (swing * 0.1) if i % 2 == 1 else 0.0
            st = bar*bpb*spb + i*eighth + sw;dur = eighth * 0.9
            vel = max(20, min(127, volume + random.randint(-8, 8)))
            notes.append(pretty_midi.Note(velocity=vel, pitch=pitch, start=st, end=st+dur))
    return notes

def generate_strumming_track(chords, bars, tempo, volume, swing=0.0):
    notes = []
    bpb = 4;spb = 60.0 / tempo;cc = len(chords)
    if cc == 0: return notes
    strum_pat = [True, True, False, False, True, False]
    positions = [0.0, 1.0, 1.5, 2.0, 2.5, 3.5]
    for bar in range(bars):
        chord = chords[bar % cc];root, intervals = chord
        dn = sorted(chord_to_midi_notes(chord, 3));un = sorted(dn, reverse=True)
        for i, pos in enumerate(positions):
            sw = (swing * 0.12) if (int(pos*2) % 2) == 1 else 0.0
            st = bar*bpb*spb + pos*spb + sw;dur = spb * 0.7
            ns = dn if strum_pat[i % len(strum_pat)] else un
            for j, pitch in enumerate(ns):
                vel = max(20, min(127, volume + random.randint(-6, 6)))
                notes.append(pretty_midi.Note(velocity=vel, pitch=pitch, start=st+j*0.015, end=st+j*0.015+dur))
    return notes

def generate_drum_track(bars, tempo, volume, swing=0.0):
    notes = []
    bpb = 4;spb = 60.0 / tempo
    KICK=36;SNARE=38;HAT=42;OPEN_HAT=46
    for bar in range(bars):
        bs = bar * bpb * spb
        for beat in range(bpb):
            bt = bs + beat * spb
            sw = (swing * 0.12) if beat % 2 == 1 else 0.0;bt += sw
            if beat % 2 == 0:
                vel = max(30, min(127, volume + random.randint(-5, 5)))
                notes.append(pretty_midi.Note(velocity=vel, pitch=KICK, start=bt, end=bt+0.1))
            if beat % 2 == 1:
                vel = max(25, min(127, volume - 5 + random.randint(-5, 5)))
                notes.append(pretty_midi.Note(velocity=vel, pitch=SNARE, start=bt, end=bt+0.1))
            for sub in [0, 0.5]:
                ht = bt + sub * spb
                sw2 = (swing * 0.12) if (int((beat+sub)*2) % 2) == 1 else 0.0;ht += sw2
                vel = max(20, min(110, volume - 20 + random.randint(-5, 5)))
                pitch = OPEN_HAT if (beat == 3 and sub == 0.5) else HAT
                notes.append(pretty_midi.Note(velocity=vel, pitch=pitch, start=ht, end=ht+0.05))
    return notes

# ─── WAV Synthesis ───────────────────────────────────────────────────────────

def midi_freq(midi_note):
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))

def adsr_envelope(length, sr, attack=0.01, decay=0.1, sustain=0.6, release=0.1):
    ts = int(length * sr)
    if ts <= 0: return np.zeros(1)
    env = np.zeros(ts, dtype=np.float64)
    a = min(max(1, int(attack * sr)), ts)
    r = min(max(1, int(release * sr)), ts)
    d = min(max(1, int(decay * sr)), max(1, ts - a - r))
    s = max(0, ts - a - d - r)
    env[:a] = np.linspace(0, 1, a)
    if d > 0: env[a:a+d] = np.linspace(1, sustain, d)
    env[a+d:a+d+s] = sustain
    rs = a + d + s;ar = ts - rs
    if ar > 0: env[rs:] = np.linspace(sustain if s > 0 else 1.0, 0, ar)
    return env

def synth_piano(freq, dur, sr):
    t = np.linspace(0, dur, int(dur*sr), endpoint=False)
    w = np.zeros_like(t)
    for h, a in [(1,1.0),(2,0.4),(3,0.2),(4,0.1)]:
        w += a * np.sign(np.sin(2*np.pi*freq*h*t))
    k = np.ones(3)/3;w = np.convolve(w, k, mode='same')
    env = adsr_envelope(dur, sr, 0.005, 0.3, 0.3, 0.2)
    return w[:len(env)] * env * 0.5

def synth_bass(freq, dur, sr):
    t = np.linspace(0, dur, int(dur*sr), endpoint=False)
    w = np.sin(2*np.pi*freq*t) + 0.3*np.sin(2*np.pi*freq*2*t)
    env = adsr_envelope(dur, sr, 0.02, 0.15, 0.5, 0.1)
    return w[:len(env)] * env * 0.6

def synth_strings(freq, dur, sr):
    t = np.linspace(0, dur, int(dur*sr), endpoint=False)
    w = 2*(freq*t - np.floor(freq*t+0.5))
    w += 0.5*(2*(freq*1.005*t - np.floor(freq*1.005*t+0.5)))
    w += 0.5*(2*(freq*0.995*t - np.floor(freq*0.995*t+0.5)))
    k = np.ones(5)/5;w = np.convolve(w, k, mode='same')
    env = adsr_envelope(dur, sr, 0.15, 0.1, 0.7, 0.3)
    return w[:len(env)] * env * 0.3

def synth_flute(freq, dur, sr):
    t = np.linspace(0, dur, int(dur*sr), endpoint=False)
    vib = 1 + 0.02*np.sin(2*np.pi*5.5*t)
    w = np.sin(2*np.pi*freq*vib*t) + 0.15*np.sin(2*np.pi*freq*2*vib*t)
    env = adsr_envelope(dur, sr, 0.08, 0.05, 0.8, 0.15)
    return w[:len(env)] * env * 0.5

def synth_guitar(freq, dur, sr):
    t = np.linspace(0, dur, int(dur*sr), endpoint=False)
    w = np.zeros_like(t)
    for h, a in [(1,1.0),(2,0.5),(3,0.3),(4,0.15)]:
        dh = math.exp(-2*h*0.5);w += a*dh*np.sin(2*np.pi*freq*h*t)
    env = adsr_envelope(dur, sr, 0.003, 0.4, 0.2, 0.3)
    return w[:len(env)] * env * 0.4

def synth_drum(dur, sr, dtype='kick'):
    n = max(1, int(dur*sr));t = np.linspace(0, dur, n, endpoint=False)
    if dtype == 'kick':
        pe = 150*np.exp(-30*t)+50;phase = np.cumsum(2*np.pi*pe/sr)
        return np.sin(phase)*np.exp(-8*t)*0.7
    elif dtype == 'snare':
        noise = np.random.uniform(-1,1,n);tone = np.sin(2*np.pi*180*t)*0.5
        w = noise*0.7+tone;k=np.ones(3)/3;w=np.convolve(w,k,mode='same')[:n]
        return w*np.exp(-15*t)*0.5
    else:
        noise = np.random.uniform(-1,1,n);k=np.ones(5)/5
        smooth=np.convolve(noise,k,mode='same')[:n];w=noise-smooth
        return w*np.exp(-40*t)*0.3

SYNTH_FUNCTIONS = {'piano':synth_piano,'bass':synth_bass,'strings':synth_strings,'flute':synth_flute,'guitar':synth_guitar}
DRUM_MAP = {36:'kick',38:'snare',42:'hat',46:'hat'}

def midi_to_wav(midi_path, output_path, sr=44100):
    pm = pretty_midi.PrettyMIDI(midi_path)
    et = pm.get_end_time() if pm.instruments else 0.0
    ts = int(et * sr) + sr
    out = np.zeros(ts, dtype=np.float64)
    for inst in pm.instruments:
        is_drum = inst.is_drum
        iname = 'drums' if is_drum else None
        if not iname:
            for nm, gp in GM_PROGRAMS.items():
                if inst.program == gp: iname = nm;break
            if not iname: iname = 'piano'
        for note in inst.notes:
            freq = midi_freq(note.pitch);dur = note.end - note.start
            if dur <= 0: continue
            ss = int(note.start * sr);vel = note.velocity / 127.0
            if is_drum:
                dt = DRUM_MAP.get(note.pitch, 'hat');w = synth_drum(dur, sr, dt)
            else:
                sf = SYNTH_FUNCTIONS.get(iname, synth_piano);w = sf(freq, dur, sr)
            w = w * vel;es = ss + len(w)
            if es > len(out): w = w[:len(out)-ss];es = len(out)
            if ss < len(out): out[ss:es] += w[:es-ss]
    peak = np.max(np.abs(out))
    if peak > 0: out = out / peak * 0.85
    wav_io.write(output_path, sr, (out * 32767).astype(np.int16))
    return output_path

# ─── Presets ─────────────────────────────────────────────────────────────────

PRESETS = {
    "harbor_dawn": {"name":"🌅 Harbor Dawn","tempo":60,"key":"D","scale":"minor",
        "layers":[{"instrument":"piano","role":"chords","bars":8,"volume":70},
                  {"instrument":"strings","role":"pad","bars":8,"volume":55}],
        "chords":"Dm Am C G","desc":"Dawn over a quiet harbor, fog lifting"},
    "tap_midnight": {"name":"🍻 Tap at Midnight","tempo":75,"key":"A","scale":"minor",
        "layers":[{"instrument":"piano","role":"chords","bars":8,"volume":75},
                  {"instrument":"bass","role":"bassline","bars":8,"volume":70},
                  {"instrument":"flute","role":"melody","bars":8,"volume":65}],
        "chords":"Am F C G","desc":"The bar at midnight, amber light, intimate"},
    "watch_3am": {"name":"⚓ 3AM Watch","tempo":50,"key":"E","scale":"minor",
        "layers":[{"instrument":"piano","role":"chords","bars":4,"volume":60},
                  {"instrument":"strings","role":"pad","bars":4,"volume":50}],
        "chords":"Em C G D","desc":"Standing watch when everyone is asleep"},
    "open_mic": {"name":"🎤 Open Mic","tempo":90,"key":"G","scale":"major",
        "layers":[{"instrument":"guitar","role":"fingerpicking","bars":8,"volume":75},
                  {"instrument":"flute","role":"melody","bars":8,"volume":60}],
        "chords":"G C D Em","desc":"Open mic night, someone picks up a guitar"},
    "deck_work": {"name":"⚓ Deck Work","tempo":120,"key":"A","scale":"mixolydian",
        "layers":[{"instrument":"guitar","role":"strumming","bars":8,"volume":75},
                  {"instrument":"bass","role":"bassline","bars":8,"volume":70},
                  {"instrument":"drums","role":"beat","bars":8,"volume":65}],
        "chords":"A D A E","desc":"Working on deck, rhythm of hauling and coiling"},
}

# ─── HTTP Handler ────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send_json(self, data, code=200):
        b = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Content-Length",str(len(b)))
        self.end_headers();self.wfile.write(b)

    def _send_html(self, html):
        b = html.encode()
        self.send_response(200)
        self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Content-Length",str(len(b)))
        self.end_headers();self.wfile.write(b)

    def _send_file(self, path, mime, name=None):
        with open(path,'rb') as f: data = f.read()
        self.send_response(200)
        self.send_header("Content-Type",mime)
        if name: self.send_header("Content-Disposition",f'attachment; filename="{name}"')
        self.send_header("Content-Length",str(len(data)))
        self.end_headers();self.wfile.write(data)

    def _read_body(self):
        l = int(self.headers.get('Content-Length',0))
        if l == 0: return {}
        raw = self.rfile.read(l)
        try: return json.loads(raw)
        except: return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")
        self.end_headers()

    def do_GET(self):
        p = urlparse(self.path).path;qs = parse_qs(urlparse(self.path).query)
        if p in ('','/'): self._send_html(STUDIO_HTML)
        elif p == '/api/presets': self._send_json({"presets":PRESETS})
        elif p == '/api/download':
            fp = qs.get('path',[''])[0];ft = qs.get('type',['mid'])[0]
            if not fp or '..' in fp: self._send_json({"error":"Invalid path"},400);return
            if not os.path.exists(fp): self._send_json({"error":"File not found"},404);return
            if ft == 'wav': self._send_file(fp,'audio/wav',os.path.basename(fp))
            else: self._send_file(fp,'audio/midi',os.path.basename(fp))
        else: self.send_error(404)

    def do_POST(self):
        p = urlparse(self.path).path
        if p == '/api/chat': self._handle_chat()
        elif p == '/api/generate-midi': self._handle_generate_midi()
        elif p == '/api/render-wav': self._handle_render_wav()
        else: self.send_error(404)

    def _handle_chat(self):
        body = self._read_body();msg = body.get('message','')
        if not msg: self._send_json({"error":"No message"},400);return
        reply = deepseek_chat([{"role":"system","content":COMPOSER_SYSTEM},{"role":"user","content":msg}])
        jm = None
        m = re.search(r'```json\s*(\{.*?\})\s*```', reply, re.DOTALL)
        if m: jm = m.group(1)
        else:
            m2 = re.search(r'\{[^{}]*"tempo"[^{}]*\}', reply, re.DOTALL)
            if m2: jm = m2.group(0)
        self._send_json({"reply":reply,"suggestion":jm})

    def _handle_generate_midi(self):
        body = self._read_body()
        try:
            tempo = int(body.get('tempo',75));key_name = body.get('key','C')
            scale_name = body.get('scale','major');bars = int(body.get('bars',8))
            chords_text = body.get('chords','C G Am F')
            layers = body.get('layers',[]);swing = float(body.get('swing',0.0))
            if not layers: layers = [{"instrument":"piano","role":"chords","bars":bars,"volume":75}]
            fid = uuid.uuid4().hex[:8];fn = f"composition_{fid}.mid"
            fp = os.path.join(OUTPUT_DIR, fn)
            generate_midi(tempo, key_name, scale_name, layers, bars, chords_text, fp, swing)
            self._send_json({"success":True,"path":fp,"filename":fn,"url":f"/api/download?path={fp}&type=mid"})
        except Exception as e:
            self._send_json({"error":str(e),"trace":traceback.format_exc()},500)

    def _handle_render_wav(self):
        body = self._read_body()
        try:
            midi_path = body.get('midi_path','')
            if not midi_path or not os.path.exists(midi_path):
                self._send_json({"error":"MIDI file not found"},404);return
            fid = uuid.uuid4().hex[:8]
            wav_fn = midi_path.replace('.mid','') + f"_{fid}.wav"
            wav_path = os.path.join(OUTPUT_DIR, os.path.basename(wav_fn))
            midi_to_wav(midi_path, wav_path)
            self._send_json({"success":True,"path":wav_path,"filename":os.path.basename(wav_path),
                "url":f"/api/download?path={wav_path}&type=wav"})
        except Exception as e:
            self._send_json({"error":str(e),"trace":traceback.format_exc()},500)

# ─── HTML Template (loaded from external file) ───────────────────────────────

STUDIO_HTML = ""

def load_html_template():
    global STUDIO_HTML
    tpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "midi_studio.html")
    if os.path.exists(tpl_path):
        with open(tpl_path) as f:
            STUDIO_HTML = f.read()
    else:
        STUDIO_HTML = '<html><body><h1>midi_studio.html not found</h1></body></html>'

load_html_template()

if __name__ == '__main__':
    print(f"🎵 MIDI Studio starting on port {PORT}")
    print(f"   DeepSeek key: {'✅ Found' if DEEPSEEK_KEY else '⚠️ Not found'}")
    print(f"   Output dir: {OUTPUT_DIR}")
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f"   → http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
        server.shutdown()
