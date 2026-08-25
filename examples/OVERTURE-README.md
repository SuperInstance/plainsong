# The Overture Boot

*One score. Two actualizations. One state.*

```plainsong
@bass   | e2 . a1 . | c2 . g1 . | d2 . a1 . | e2 . a1 . |
Melody: | G#4 E4 . . | Eb4 . . . | F4 C4 . . | G4 D4 . . |
Score:  | 0 . . . | 480 . . . | 360 . . . | 240 . . . |
Bg:     | night . . . | stars . . . | ridge . . . | grid . . . |
Seed:   | spawn 42 . . | drop 1337 . . | weather 777 . . | encounter 9001 . . |
```

## The reverse-actualization move

Ordinary software grows forward: state first, presentation later, and the
title screen is paint applied to a running program. A game grown out of a
quilt construct grows the other way. You imagine the finished software
*functionally* — not its code, but what it does: it spawns a world, it places
a player, it remembers a high-score board, it paints a background, it rolls
dice that look random and aren't. Then you let that imagined thing decompose
itself into elementary cells, and you discover the cells were bars all along.
A world-seed is a melody. A player is a tune. A scoreboard is a row that
nobody plays. Render the cells as interaction and you have a game; render
them as sound and you have an overture. Same cells. That is the whole move.

This file is the proof that the move is not a metaphor. `overture-boot.song`
is one quilt of five rows, and it actualizes twice:

1. **Audio.** `plainsong` compiles it. The compiler plays what it recognizes:
   `@bass` (eight attacks, Am, four bars) and `Melody:` (seven). The
   annotation rows — `Score:`, `Bg:`, `Seed:` — are bar-aligned *data* the
   parser keeps and the arranger skips, the same contract the `Vel:` row
   established for dynamics: a row that marks rather than sounds. The boot
   literally plays: a ten-second minor-key jingle, suspended on a fourth,
   pulling back to the top of the loop the way attract modes do.

2. **State.** `tools/overture_to_state.py` parses the same file and emits
   game-state JSON:

   | row | state | encoding |
   |-----|-------|----------|
   | `@bass` | world seed | sha256 over the MIDI pitch sequence → 64-bit seed |
   | `Melody:` bar 1 | HP | two pitches, big-endian base-12: G#4 E4 = 8·12+4 = **100** |
   | `Melody:` bar 2 | lives | one pitch: Eb4 = **3** |
   | `Melody:` bar 3 | start tile | (F4, C4) = **(5, 0)** |
   | `Melody:` bar 4 | energy | G4 D4 = 7·12+2 = **86** |
   | `Score:` | scoreboard | bar 1 starts at 0; the rest are the high-score board |
   | `Bg:` | background | one scene tag per bar |
   | `Seed:` | RNG constants | named seeds for spawn/drop/weather/encounter dice |

   The piece's bar count is even the world's zone count. Nothing in the file
   is only music; nothing in the state is only numbers.

## Why "apparent-but-repeatable" randomness is the tell

A world seed is a strange object: the terrain must *look* discovered and *be*
authored. A deterministic melody has exactly that shape — you can't hear the
rule in the tune, but the tune is nothing but the rule. So the seed voice is
played, not declared: hash `e2 a1 c2 g1 d2 a1 e2 a1` and the world is
`2883727009972777287`, forever. Change one semitone (`e2`→`f2`) and you are
in a different world — but the player's HP, lives and position do not move,
because the melody is the player and the bass is the world and neither leaks
into the other. That separation is asserted in `tests/test_overture_boot.py`,
along with the two claims the doctrine stands on: parse twice, get the same
state; plant a different seed note, get a different world.

## What this file is for

This is the seed of a longer piece on the doctrine. The shorter claim, worth
keeping in one sentence: **state doesn't need a screen to exist; it needs a
voice.** A boot sequence played as an overture is not a gimmick layered on a
game — it is the game's genome, transcribed for an instrument, and every
actualization (audio, JSON, and eventually the running game itself) is a
rendering of the same cells.

*Run it:*

```console
$ python3 tools/overture_to_state.py examples/overture-boot.song
$ python3 -c "from plainsong import pipeline as p; \
  p.compile_text(open('examples/overture-boot.song').read(), audio='boot.wav')"
```
