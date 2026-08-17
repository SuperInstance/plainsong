# Lyrics

A word is sung on a note. Plainsong did not know that until 1.2, and the gap
between what a lyric row looks like and what it meant is the subject of this
page.

## The problem, in four lines

```plainsong
[V1] (Verse - 1 Bars)
Melody: | A4  .   C5  E5 |
Lyrics: | the tide came  |
```

`came` is written directly beneath `C5`. It does not sound with it. The melody
row divided the bar into four and the lyric row divided it into three, so `C5`
sounds on beat 2.0 and `came` lands on beat 2.667 — two thirds of a beat later.

That is not a bug in one file. It follows from the rule that makes the notation
work: **a bar is one bar long and the tokens in it divide it**, applied
independently to every row. Alignment is a convention for human eyes, and the
compiler could not see it.

Every other notation format says syllables bind to *notes*. They disagree only
about the mechanism. MusicXML and MEI attach the syllable to the note, which
makes a mismatch inexpressible but needs the lyric to live inside the note —
impossible in a row-based text format. ABC and LilyPond **count**: they walk a
flat syllable stream in lockstep against the notes. Plainsong is already a flat
stream, so counting it is.

## Turning it on

```toml
[core]
lyrics = "bound"
```

`PLAINSONG_CORE_LYRICS` does it for one run. The default is `independent`, which
is the behaviour every existing file already has. This is gated because lyric
events reach the MIDI file as meta events, so binding changes output — and a
change to how existing notation compiles goes behind a setting and defaults to
the old reading, even when the new one is better.

Bound, the example above gives `the` on A4, `tide` on C5, and `came` on E5.

## The barline resyncs

Each bar's syllables bind to that bar's notes. Nothing carries across a `|`.

Write too many syllables in a bar and the extras are reported and not sung; the
next bar is unaffected. Write too few and the remaining notes carry no new
syllable. A miscount costs one bar and recovers, rather than shifting every
remaining word in the song.

This is ABC's rule, and Plainsong already writes `|` in every row, so the
mechanism was in the syntax and merely unhonoured.

## A held syllable needs no mark

Write fewer words than there are notes and the last word carries across them:

```plainsong
[V1] (Verse - 1 Bars)
Melody: | C4 D4 E4 F4 |
Lyrics: | one |
```

`one` is sung on C4 and held for all four notes. `LyricEvent.duration` says how
long — a word lasts until the next word's note. That is a melisma, and it is
written the way a lead sheet already writes it.

## Padding is not melisma

A sustain or rest token in a lyric row binds to nothing:

```plainsong
[V1] (Verse - 1 Bars)
Melody: | Bb3 .   F4    .   |
Lyrics: | sing .   every .   |
```

Two words, two notes: `sing` on Bb3 and `every` on F4.

This is worth stating because the plan for this feature originally said the
opposite. ABC uses `_` for a melisma, so by analogy a sustain token in a lyric
row might mean "hold across this note too". Real notation disagrees — writers
use `.` in a lyric row to hold the *column* under a melody that sustains, which
is exactly what the example above is doing. Read as melismas, the two dots would
each consume a note and `every` would fall off the end of the bar.

So the rule follows the notation people actually write, not the analogy:
**words bind to notes; padding holds a column.**

## When there is nothing to bind to

A `Lyrics:` row with no `Melody:` row in the same section has no notes to sing
on. Those syllables are left exactly where they were written and the situation
is reported. Dropping the words silently is the worst of the available answers.

## Repeated lyric rows are verses

Every `Melody:` row in a section concatenates into one melodic stream, as they
always have. Each `Lyrics:` row is a verse sung over that whole stream.

There is no new syntax for this, and it does not contradict the rule that a
repeated row runs on in time. Run-on is a claim about *time*; a bound lyric row
owns no time of its own, so the rule does not reach it. A section with two
`Melody:` rows is eight bars of one tune, and two `Lyrics:` rows over it are two
verses of eight bars each — which is how a song sheet is written, and why nobody
has to be taught it.

## What this does not do yet

- **The distinction between a melisma and a skip is not represented.** Both
  come out as a word lasting longer. A renderer wanting to draw an extension
  line under a held syllable needs more than `duration` currently carries.
- **Hyphenation is not understood.** `sus - pend` is two words with padding
  between them, not one word split across two notes. Nothing is lost, but
  nothing is gained either.
- **Nothing warns when a row disagrees with its neighbours** under the default
  `independent` mode. `Arrangement.grid.disagreements()` can answer that
  question — see [architecture.md](architecture.md) — but no diagnostic is
  raised from it.
