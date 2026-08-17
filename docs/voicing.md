# Voicing

A chord symbol names more notes than a texture usually wants. Something has to
decide what to leave out, and for a long time this decided by taking the lowest
four:

```
D9   written  D  F#  A  C  E
     played   D  F#  A  C
```

Which is `D7`. The one note that makes `D9` worth writing was the one thrown
away. `E7#9` — the chord an entire Hendrix record is built on — came out as
`E7`. `G7alt` came out as four notes that are not a chord anybody would name.

## The rule

**Give up the fifth first, the root second.** Keep the third and the seventh,
because they are what separate major from minor from dominant. Keep whatever
extension the symbol was written for, because that is why it was written that
way.

One addition: **an altered degree counts as identity, not decoration.** A
`C7#5` that loses its sharp fifth is a `C7`. The drop order treats any degree
sitting away from its natural place as undroppable, which is what stops the
ordinary rank of "fifth" from throwing away the point of the chord.

That is the whole rule. Everything below is how it was chosen.

## It was measured, not argued

Five strategies were implemented and scored over every chord in the repository.
Reproduce with `python3 -m plainsong voicing --compare`.

The first attempt measured across all 125,375 chord occurrences and produced
almost no signal — 99.4% against 99.9% — because 99.7% of the corpus is triads
and sevenths, where the cap never bites and every strategy agrees. Averaging
over the cases where nothing happens hides the case where something does.

Scored only on the occurrences where a note actually has to be dropped — 277
across the whole repository, 95 within the packaged library, which is the set
`--compare` reaches and why its numbers differ from these by a few tenths:

| strategy | names the symbol keeps | guide tones kept | muddy intervals |
|---|---|---|---|
| `stack` (the old behaviour) | **50.1%** | 100% | 0 |
| **`guide`** (the default) | **94.4%** | 100% | 0 |
| `shell` | 88.8% | 100% | 0 |
| `drop2` | 94.4% | 100% | **36** |
| `spread` | 94.4% | 100% | 0 |

*"Names the symbol keeps"* is the fraction of degrees the symbol explicitly
promises — its top extension plus every alteration — that survive into the
sounding chord. *"Muddy"* counts intervals narrower than a minor third below
C3, where they stop being heard as two pitches.

`guide` wins outright: it keeps the named note nearly twice as often as the old
behaviour, never loses a guide tone, adds no muddiness, and — measured
separately — leaves voice-leading smoothness unchanged at 2.18 semitones of
mean motion between chords, exactly matching `stack`. `drop2` and `spread`
match it on fidelity but move notes into the register where they stop being
distinguishable.

It does not reach 100%, and cannot. `G7alt` names a third, a seventh and three
alterations; five into four does not go.

## What it produces

Nothing here was written into a table. These fall out of the drop order alone:

```
C13     written  C  E  G  Bb D  A
        played      E     Bb D  A      rootless, the Bill Evans A form
E7#9    played   E  Ab    D     G      the actual Hendrix chord
G7alt   played      B     F  Ab Db     third, seventh, b13, b9
Cmaj9   played   C  E     B  D
```

`C13 → E Bb D A` is the standard rootless jazz voicing. It was not aimed at; it
is what "drop the fifth, then the root" produces when you ask for four notes.

## What changed, exactly

71 files out of 6,321. The blast radius was checked against a prediction rather
than eyeballed: the set of files that moved was compared to the set containing a
chord of more than four notes. Every predicted file moved, and two moved that
were not predicted — both recordings of *Corcovado*, which turned out to be a
second and separate defect:

**A slash bass was counted against the chord.** `Am7/G` put the bass note in
the list and *then* truncated to four, so the chord lost its seventh to make
room for its own bass and sounded like `Am/G`. A slash bass is an additional
voice below the chord, not one of its four. Five files, +20 notes across the
whole corpus.

So: 66 files where the same number of notes sound and some of them are
different, and 5 where a slash chord got its seventh back.

## Changing it

`render.voicing` selects a strategy: `guide`, `stack`, `shell`, `drop2`,
`spread`. `stack` restores the old behaviour exactly, for anyone whose
recordings depend on it.

The strategies live in `plainsong/notation/voicing.py` and are each a few lines,
because they all operate on the same thing: a **degree map**, scale degree onto
semitones above the root, carried down from the parser. A voicer cannot decide
what to drop from a bare list of intervals — dropping the fifth is free and
dropping the seventh destroys the chord, and those are indistinguishable once
the degree labels are gone. That is why the map exists.

To add a strategy, write a function taking `(degrees, root, limit)` and add it
to `STRATEGIES`. Then run the comparison and show that it wins something.

## Still open

**Register.** This chooses *which* notes sound, not *where*. Chords still sit in
a fixed octave. Real placement depends on the melody it has to stay out of, the
bass instrument's territory, and the low interval limits that make close
intervals unusable underneath about C3 — none of which this looks at yet.

**Voice leading between chords.** Each chord is voiced without reference to the
one before it, so nothing holds common tones or minimises motion. The measured
2.18 semitones is what falls out of fixed-position voicing, not what a player
would do.
