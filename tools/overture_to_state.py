#!/usr/bin/env python3
"""Overture -> game state: the second actualization of one score.

A game grown out of a quilt construct starts with all its state played as
starting notes. The same ``.song`` file that renders as audio also bootstraps
the game: @bass is the terrain seed, Melody: is the player's starting state,
and the Score:/Bg:/Seed: annotation rows are the scoreboard, the scene, and
the explicit RNG constants. The parser keeps unknown ``Name:`` rows as
annotation data -- the same pattern as the Vel: machinery -- so this tool can
read them back out without the compiler ever playing them.

Run it twice on the same file and you get byte-identical JSON: same file,
same world, always.

Usage:
    python3 tools/overture_to_state.py examples/overture-boot.song
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plainsong import pipeline
from plainsong.notation.ir import ROLE_ANNOTATION, ROLE_NOTE, Arrangement, Score
from plainsong.notation.parser import SUSTAIN_TOKENS, split_cells

#: The player row whose note sequence hashes to the world seed.
SEED_VOICE = "bass"

#: Melody tokens are read as semitone offsets above C4 (MIDI 60) and paired
#: big-endian base-12: G#4 E4 is (8, 4) -> 8*12 + 4 = 100. HP one hundred,
#: literally played.
PITCH_BASE = 60

SPACERS = SUSTAIN_TOKENS | {"."}


def _payload(line) -> str:
    """The bar cells of an annotation row, as written after its label."""
    if getattr(line, "cells", None):
        return list(line.cells)
    raw = getattr(line, "raw", "")
    return split_cells(raw.split(":", 1)[1]) if ":" in raw else []


def _tokens(cell) -> list[str]:
    text = cell.text if hasattr(cell, "text") else str(cell)
    return [tok for tok in text.split() if tok not in SPACERS]


def bass_pitches(arrangement: Arrangement) -> list[int]:
    """The seed voice's attacks, in order: the input to the world hash."""
    for track in arrangement.tracks:
        if track.name == SEED_VOICE:
            return [note.pitch for note in track.notes]
    raise ValueError(f"no @{SEED_VOICE} voice in the score; the world has no seed")


def world_seed(pitches: list[int]) -> dict:
    """sha256 over the seed melody's MIDI pitches -> a 64-bit world seed."""
    joined = ",".join(str(p) for p in pitches).encode()
    digest = hashlib.sha256(joined).hexdigest()
    return {
        "seed": int(digest[:16], 16),
        "hash": f"sha256:{digest}",
        "from": joined.decode(),
    }


def player_state(arrangement: Arrangement, score: Score) -> dict:
    """Read HP, lives, position and energy out of the Melody row, bar by bar.

    Bar 1 pairs two pitches base-12 for HP; bar 2 is one pitch for lives;
    bar 3 is the (x, y) start tile; bar 4 pairs two pitches for energy.
    Position is *bars* in the other sense too: the piece's bar count is the
    world's zone count.
    """
    beats = score.meta.meter.beats_per_bar
    bars: list[list[int]] = []
    for track in arrangement.tracks:
        if track.role != "melody":
            continue
        for note in track.notes:
            index = int(note.start // beats)
            while len(bars) <= index:
                bars.append([])
            bars[index].append(note.pitch - PITCH_BASE)
    if len(bars) < 4:
        raise ValueError(f"the Melody row needs 4 bars of player state, found {len(bars)}")
    hp, energy = bars[0], bars[3]
    if len(hp) != 2 or len(energy) != 2:
        raise ValueError("bars 1 and 4 need exactly two notes each (HP and energy)")
    return {
        "hp": hp[0] * 12 + hp[1],
        "lives": bars[1][0],
        "position": bars[2][:2],
        "energy": energy[0] * 12 + energy[1],
    }


def annotation_rows(score: Score) -> dict[str, list[list[str]]]:
    """Every kept annotation row as {name: per-bar token lists}."""
    rows: dict[str, list[list[str]]] = {}
    for section in score.sections:
        for line in section.lines:
            if line.role in (ROLE_NOTE, ROLE_ANNOTATION) and line.name:
                rows.setdefault(line.name.lower(), []).extend(_tokens(c) for c in _payload(line))
    return rows


def overture_state(text: str) -> dict:
    """One .song file -> one boot state. The whole contract of this tool."""
    result = pipeline.compile_text(text)
    if not result.ok or result.arrangement is None:
        raise ValueError("the overture does not compile: " + "; ".join(
            d.message for d in result.score.diagnostics if d.severity == "error"
        ) or "no arrangement")
    arrangement = result.arrangement
    score = result.score
    rows = annotation_rows(score)

    def numbers(name: str) -> list[int]:
        return [int(tok) for cell in rows.get(name, []) for tok in cell if tok.lstrip("-").isdigit()]

    bg = [" ".join(cell) for cell in rows.get("bg", [])]
    rng = {
        cell[0]: int(cell[1])
        for cell in rows.get("seed", [])
        if len(cell) >= 2 and cell[1].lstrip("-").isdigit()
    }
    scores = numbers("score")
    return {
        "world": {
            **world_seed(bass_pitches(arrangement)),
            "zones": max(s.bar_count for s in score.sections),
        },
        "player": player_state(arrangement, score),
        "score": {
            "start": scores[0] if scores else 0,
            "high_scores": scores[1:],
        },
        "background": bg,
        "rng": rng,
        "overture": {
            "title": score.meta.title,
            "key": score.meta.key.name(),
            "tempo": score.meta.tempo,
            "bars": max(s.bar_count for s in score.sections),
        },
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    text = Path(argv[1]).read_text(encoding="utf-8")
    print(json.dumps(overture_state(text), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
