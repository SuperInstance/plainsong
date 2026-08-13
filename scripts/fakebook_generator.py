#!/usr/bin/env python3
"""TapScript fakebook generator.

Uses the DeepSeek API to generate TapScript files in bulk under docs/fakebook/.

Copyright policy (hard-coded, do not loosen):
- mode "full": only for public-domain material (traditional folk, shanties,
  hymns, classical, nursery rhymes). Melody + lyrics allowed.
- mode "chart": copyrighted songs. Chord-chart skeletons ONLY. The prompt
  forbids lyrics/melody, and any Lyrics:/Melody: lines are stripped from the
  output as a safety net before writing.

Commits and pushes every BATCH_COMMIT new files. Safe to re-run: existing
files are skipped.
"""

import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error

REPO = "/home/eileen/projects/tapscript-studio"
OUT_ROOT = os.path.join(REPO, "docs", "fakebook")
API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"
WORKERS = 8
BATCH_COMMIT = 20
MAX_TOKENS_SONG = 700
LOG = os.path.join(REPO, "scripts", "fakebook_generator.log")

# ---------------------------------------------------------------- key

def load_key():
    with open(os.path.expanduser("~/.bashrc")) as f:
        text = f.read()
    m = re.search(r'DEEPSEEK_API_KEY\s*=\s*["\']?([A-Za-z0-9_\-]+)', text)
    if not m:
        sys.exit("DEEPSEEK_API_KEY not found in ~/.bashrc")
    return m.group(1)

KEY = load_key()

# ---------------------------------------------------------------- api

def chat(prompt, max_tokens, temperature=0.8, retries=3):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(API_URL, data=body, headers={
                "Authorization": f"Bearer {KEY}",
                "Content-Type": "application/json",
            })
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.loads(r.read())
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            log(f"API error (attempt {attempt+1}): {e}")
            time.sleep(5 * (attempt + 1))
    return None

# ---------------------------------------------------------------- log

_log_lock = threading.Lock()

def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with _log_lock:
        print(line, flush=True)
        with open(LOG, "a") as f:
            f.write(line + "\n")

# ---------------------------------------------------------------- buckets

# (language, genre, target_count, mode, list_description)
BUCKETS = [
    # English — mode "chart" = copyrighted, chord charts only
    ("english", "folk",        150, "chart", "classic folk and folk-rock songs (1950s-1990s singer-songwriter era)"),
    ("english", "rock",        250, "chart", "classic rock and hard rock songs (1960s-2000s)"),
    ("english", "pop",         250, "chart", "pop hit songs (1960s-2010s)"),
    ("english", "jazz",        150, "chart", "jazz standards from the Great American Songbook"),
    ("english", "blues",       100, "chart", "classic blues songs and 12-bar blues standards"),
    ("english", "country",     150, "chart", "classic country songs (1950s-2000s)"),
    ("english", "hiphop",      100, "chart", "classic hip-hop and rap songs (1980s-2010s)"),
    ("english", "reggae",       50, "chart", "classic reggae songs"),
    ("english", "metal",       100, "chart", "heavy metal and hard rock songs (1970s-2000s)"),
    ("english", "soul-rb",     100, "chart", "classic soul, Motown and R&B songs (1950s-1990s)"),
    ("english", "showtunes",   100, "chart", "famous songs from Broadway and West End musicals"),
    # English — mode "full" = public domain only
    ("english", "classical",   100, "full",  "famous public-domain classical pieces (Baroque, Classical, Romantic eras, composed before 1900)"),
    ("english", "traditional", 100, "full",  "traditional public-domain folk songs (Child ballads, spirituals, old-time, Appalachian)"),
    ("english", "shanties",     50, "full",  "traditional public-domain sea shanties and maritime work songs"),
    ("english", "worship",     100, "full",  "traditional public-domain hymns (written before 1900)"),
    ("english", "kids",        100, "full",  "traditional public-domain nursery rhymes and children's songs"),
    # Other languages — traditional (full) + modern classics (chart)
    ("spanish",    "folk-traditional", 100, "full",  "traditional public-domain Spanish and Latin American folk songs (in Spanish)"),
    ("spanish",    "pop-classics",     100, "chart", "famous Spanish-language pop and rock songs"),
    ("french",     "folk-traditional", 100, "full",  "traditional public-domain French folk songs and chansons (in French)"),
    ("french",     "pop-classics",     100, "chart", "famous French chansons and pop songs (20th century)"),
    ("german",     "folk-traditional", 100, "full",  "traditional public-domain German folk songs and Volkslieder (in German)"),
    ("german",     "pop-classics",     100, "chart", "famous German-language pop, rock and Schlager songs"),
    ("italian",    "folk-traditional", 100, "full",  "traditional public-domain Italian folk songs and canzoni (in Italian)"),
    ("italian",    "pop-classics",     100, "chart", "famous Italian pop songs and canzoni (20th century)"),
    ("portuguese", "folk-traditional", 100, "full",  "traditional public-domain Portuguese and Brazilian folk songs (in Portuguese)"),
    ("portuguese", "pop-classics",     100, "chart", "famous Portuguese-language pop, fado and bossa nova songs"),
    ("japanese",   "folk-traditional", 100, "full",  "traditional public-domain Japanese folk songs, minyo and children's songs (in Japanese, romanized titles)"),
    ("japanese",   "pop-classics",     100, "chart", "famous Japanese pop, enka and city pop songs (romanized titles)"),
    ("chinese",    "folk-traditional", 100, "full",  "traditional public-domain Chinese folk songs (romanized Mandarin titles)"),
    ("chinese",    "pop-classics",     100, "chart", "famous Mandarin and Cantonese pop songs (romanized titles)"),
    ("korean",     "folk-traditional", 100, "full",  "traditional public-domain Korean folk songs, minyo and children's songs (romanized titles)"),
    ("korean",     "pop-classics",     100, "chart", "famous Korean pop, trot and K-pop songs (romanized titles)"),
    ("hindi",      "folk-traditional", 100, "full",  "traditional public-domain Hindi and Indian folk songs, bhajans and regional folk (romanized titles)"),
    ("hindi",      "pop-classics",     100, "chart", "famous Hindi film songs and Indian pop classics (romanized titles)"),
    ("arabic",     "folk-traditional", 100, "full",  "traditional public-domain Arabic folk songs from across the Arab world (romanized titles)"),
    ("arabic",     "pop-classics",     100, "chart", "famous Arabic pop and classic songs (romanized titles)"),
    ("russian",    "folk-traditional", 100, "full",  "traditional public-domain Russian folk songs (romanized titles)"),
    ("russian",    "pop-classics",     100, "chart", "famous Russian and Soviet-era pop and bard songs (romanized titles)"),
]

# ---------------------------------------------------------------- prompts

LIST_PROMPT = (
    "List exactly {n} {desc}. One per line in the format 'Title - Artist' "
    "(use 'Traditional' as artist for traditional pieces). No numbering, no "
    "commentary, no duplicates, no blank lines."
)

FULL_PROMPT = (
    "Transcribe the traditional public-domain piece '{title}' by {artist} into "
    "TapScript notation. This piece is in the public domain; use its real "
    "traditional melody and lyrics.\n"
    "Format exactly like this:\n"
    "**TRACK: Title**\n"
    "[MetaData]\n"
    "key: Am | tempo: 90 | subdivision: 8th\n"
    "time: 4/4 | mood: Gentle\n\n"
    "[V1] (Verse - 4 Bars)\n"
    "Chords: | Am . . . | F . . . |\n"
    "Melody: | A3 . C4 . | F4 . . . |\n"
    "Lyrics: | words aligned to beats |\n"
    "@piano | a2-e3-a3 . . . | f2-a2-c3 . . . | vel: 50\n\n"
    "[CH] (Chorus - 4 Bars)\n"
    "Chords: | C . . . | G . . . |\n"
    "Melody: | E4 . G4 . | B3 . D4 . |\n"
    "Lyrics: | words aligned to beats |\n"
    "@piano | c3-e3-g3 . . . | g2-b2-d3 . . . | vel: 55\n\n"
    "Use 2-3 sections (verse + chorus is enough). Output ONLY the tapscript. "
    "No commentary, no markdown code fences."
)

CHART_PROMPT = (
    "Create a TapScript chord-chart skeleton for the song '{title}' by {artist}.\n"
    "IMPORTANT COPYRIGHT CONSTRAINTS: Do NOT include any lyrics. Do NOT include "
    "a Melody line or any melody notes. Structure and chords ONLY.\n"
    "Format exactly like this:\n"
    "**TRACK: Title**\n"
    "[MetaData]\n"
    "key: Am | tempo: 90 | subdivision: 8th\n"
    "time: 4/4 | mood: Driving\n\n"
    "[V1] (Verse - 4 Bars)\n"
    "Chords: | Am . . . | F . . . |\n"
    "@guitar | a2-e3-a3 . . . | f2-a2-c3 . . . | vel: 55\n\n"
    "[CH] (Chorus - 4 Bars)\n"
    "Chords: | C . . . | G . . . |\n"
    "@guitar | c3-e3-g3 . . . | g2-b2-d3 . . . | vel: 60\n\n"
    "Use the real chord progression and real song structure, 3-5 sections "
    "(verse, chorus, bridge as appropriate). Output ONLY the tapscript. "
    "No commentary, no markdown code fences."
)

# ---------------------------------------------------------------- helpers

def slugify(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-") or "untitled"

def clean_output(text, mode):
    # strip code fences if the model added them anyway
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text.strip())
    text = re.sub(r"\n?```$", "", text.strip())
    lines = []
    for line in text.splitlines():
        if mode == "chart" and re.match(r"\s*(Lyrics|Melody)\s*:", line, re.I):
            continue  # safety net: no lyrics/melody for copyrighted songs
        lines.append(line)
    return "\n".join(lines).strip() + "\n"

def valid(text):
    return "**TRACK:" in text and "Chords:" in text and "[MetaData]" in text

# ---------------------------------------------------------------- git

_git_lock = threading.Lock()
_pending = 0

def git_commit_batch(force=False):
    global _pending
    with _git_lock:
        if not force and _pending < BATCH_COMMIT:
            return
        n = _pending
        _pending = 0
    try:
        subprocess.run(["git", "-C", REPO, "add", "docs/fakebook", "scripts/fakebook_generator.py"],
                       check=True, capture_output=True)
        r = subprocess.run(["git", "-C", REPO, "commit", "-m",
                            f"fakebook: add {n} tapscript transcriptions (batch)"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            p = subprocess.run(["git", "-C", REPO, "push"], capture_output=True, text=True, timeout=120)
            if p.returncode != 0:
                log(f"push failed (will retry next batch): {p.stderr.strip()[:200]}")
            else:
                log(f"committed+pushed batch of {n}")
        else:
            log(f"commit skipped: {r.stderr.strip()[:200]}")
    except Exception as e:
        log(f"git error: {e}")

# ---------------------------------------------------------------- phases

def get_song_list(lang, genre, target, desc):
    out_dir = os.path.join(OUT_ROOT, lang, genre)
    os.makedirs(out_dir, exist_ok=True)
    want = int(target * 1.15) + 10
    songs = []
    seen = set()
    while len(songs) < target:
        n = min(80, want - len(songs) + 20)
        resp = chat(LIST_PROMPT.format(n=n, desc=desc), max_tokens=2000, temperature=0.9)
        if not resp:
            break
        added = 0
        for line in resp.splitlines():
            line = line.strip().strip("-•* ").strip()
            m = re.match(r"^\d+[.)]\s*", line)
            if m:
                line = line[m.end():].strip()
            if " - " not in line:
                continue
            title, artist = line.rsplit(" - ", 1)
            title, artist = title.strip().strip('"'), artist.strip().strip('"')
            if not title or len(title) > 120:
                continue
            slug = slugify(title)
            if slug in seen or os.path.exists(os.path.join(out_dir, slug + ".tap")):
                continue
            seen.add(slug)
            songs.append((title, artist, slug))
            added += 1
        if added == 0:
            break
        log(f"list {lang}/{genre}: {len(songs)}/{target}")
        if len(songs) < target:
            desc = "other " + desc  # nudge for variety on the next round
    return songs[:target]

def transcribe(lang, genre, mode, song):
    title, artist, slug = song
    out_path = os.path.join(OUT_ROOT, lang, genre, slug + ".tap")
    if os.path.exists(out_path):
        return False
    prompt = (FULL_PROMPT if mode == "full" else CHART_PROMPT).format(title=title, artist=artist)
    resp = chat(prompt, max_tokens=MAX_TOKENS_SONG)
    if not resp:
        log(f"FAIL {lang}/{genre}/{slug}: no response")
        return False
    text = clean_output(resp, mode)
    if not valid(text):
        log(f"FAIL {lang}/{genre}/{slug}: invalid output")
        return False
    with open(out_path, "w") as f:
        f.write(text)
    global _pending
    with _git_lock:
        _pending += 1
    git_commit_batch()
    return True

def run_bucket(bucket):
    lang, genre, target, mode, desc = bucket
    out_dir = os.path.join(OUT_ROOT, lang, genre)
    os.makedirs(out_dir, exist_ok=True)
    existing = len([f for f in os.listdir(out_dir) if f.endswith(".tap")])
    if existing >= target:
        log(f"skip {lang}/{genre}: already {existing} files")
        return
    log(f"=== {lang}/{genre}: target {target} ({mode}), have {existing}")
    songs = get_song_list(lang, genre, target - existing + existing, desc)
    # re-filter: only songs not already on disk
    todo = [s for s in songs if not os.path.exists(os.path.join(out_dir, s[2] + ".tap"))]
    log(f"{lang}/{genre}: {len(todo)} to transcribe")
    done = 0
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        futs = {ex.submit(transcribe, lang, genre, mode, s): s for s in todo}
        for fut in cf.as_completed(futs):
            if fut.result():
                done += 1
                if done % 10 == 0:
                    log(f"{lang}/{genre}: {done}/{len(todo)} transcribed")
    git_commit_batch(force=True)
    log(f"=== {lang}/{genre} done: {done} new files")

def main():
    log("fakebook generator starting")
    which = sys.argv[1] if len(sys.argv) > 1 else None
    for bucket in BUCKETS:
        if which and f"{bucket[0]}/{bucket[1]}" != which:
            continue
        try:
            run_bucket(bucket)
        except Exception as e:
            log(f"bucket {bucket[0]}/{bucket[1]} crashed: {e}")
    git_commit_batch(force=True)
    log("ALL DONE")

if __name__ == "__main__":
    main()
