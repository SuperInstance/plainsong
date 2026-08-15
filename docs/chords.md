# Chords

TapScript reads chord symbols with a grammar, not a lookup table. That
distinction is the whole of this document, so it is worth being concrete about
what it buys.

A table has to contain every spelling anyone might write. The engine this
replaced held about thirty, which meant `C7b9` worked and `C7b9#11` did not --
not because anyone disagreed about what the second one means, but because
nobody had typed that particular combination in. Across the 6,308 charts in
this repository, 102 chords were unreadable, and none of them were exotic.

A grammar reads a symbol as a few decisions and *derives* the notes:

```
C7b9#11   ->  dominant, stack to the seventh, flatten the ninth, raise the eleventh
F13#11    ->  dominant, stack to the thirteenth, raise the eleventh
Bbmaj7#5  ->  major, stack to the seventh, raise the fifth
```

Nothing enumerates those three. They work because the parts compose.

## Ask, rather than guess

```bash
tapscript chord "G7alt" --explain
```

```
ok  G7alt  --  G B F G# C# D#
    root: G (+0 semitones)
    third: B (+4 semitones)
    seventh flattened: F (+10 semitones)
    ninth flattened: G# (+13 semitones)
    eleventh raised: C# (+18 semitones)
    thirteenth flattened: D# (+20 semitones)
    no fifth
    midi at octave 3: [55, 59, 65, 68, 73, 75]
    lowest note G3
```

Take `--json` when something else is reading it. The `no fifth` line matters as
much as the notes above it: what a chord leaves out is often most of what makes
it sound the way it does.

## What it accepts

| family | spellings |
|---|---|
| major | `C` `CM` `Cmaj` `Cma` `Cmj` `CΔ` `C∆` `C^` |
| major seventh | `Cmaj7` `CM7` `Cma7` `CΔ7` `C7M` |
| minor | `Cm` `Cmi` `Cmin` `C-` `Cmoll` |
| minor seventh | `Cm7` `C-7` `Cmi7` `Cmin7` |
| minor-major | `CmMaj7` `Cm(maj7)` `Cm7M` `C-Δ7` |
| dominant | `C7` `C9` `C11` `C13` |
| diminished | `Cdim` `C°` `Co` `Cdim7` `C°7` |
| half-diminished | `Cø` `Cø7` `Cm7b5` `C-7b5` `Cm7-5` |
| augmented | `Caug` `C+` `C+7` `Cmaj7#5` |
| suspended | `Csus` `Csus2` `Csus4` `C7sus4` `C9sus4` |
| sixth | `C6` `Cm6` `C6/9` `C69` |
| added | `Cadd9` `Cadd11` `C2` `C4` |
| altered | `C7b9` `C7#9` `C7b5` `C7#5` `C7#11` `C7b13` `C7b9#11` `C13#11` `C7alt` |
| shell | `C5` `Cno3` |
| over a bass | `C/E` `Cm/Bb` `D/F#` |

Accidentals may be ASCII or Unicode, in the root *and* in an alteration:
`E7♭9` reads the same as `E7b9`. Parentheses are decoration and carry no
meaning of their own, so `G7(b13)` is `G7b13`.

Two of those spellings deserve a note.

**`C7M` is a major seventh.** It is standard in Brazil, from *sétima maior*,
and it was the single largest group of unreadable chords in this repository --
39 of them. Note that `C7M` and `Cm7` differ only in the order of two
characters and are different chords, so the reading is deliberately narrow: an
`M` counts as a major seventh only when a `7` immediately precedes it.

**The two triangles are different characters.** `Δ` is U+0394 GREEK CAPITAL
LETTER DELTA and `∆` is U+2206 INCREMENT. They are indistinguishable on screen
and both occur in real charts. Both are accepted, because knowing only one of
them fails on half the input for a reason you cannot see by looking.

## The rules that a table cannot hold

These are the reason for the grammar. Each is a statement about a *degree*,
which is what makes it composable.

### An alteration displaces its natural form

`C7b9` contains a D♭ and no D. The alteration is not an extra note; it is the
ninth, moved.

### An extension implies the odd degrees below it — except the eleventh

`C13` is C E G B♭ D A. It has a ninth, because a thirteenth implies one. It has
no eleventh, because a natural eleventh sits a semitone above the major third
and fights it.

Change the third and the exception lifts:

```bash
tapscript chord "C13" "Cm13" "C13#11"
```

`Cm13` *does* have its eleventh — a minor third leaves nothing to clash with.
`C13#11` has one too, raised, which puts it a whole tone above the third
instead of a semitone. Same stack, three answers, one rule.

### Naming a degree outranks implying it

`C11` asks for the eleventh on purpose, so it gets one — and the third leaves
instead. Both notes still cannot stay; the resolution just goes the other way
when you named the eleventh yourself.

### Removing a note removes what depended on it

`sus4` takes out the third, which is what made the eleventh an avoid note in
the first place. So `C9sus4` needs no special handling: with no third present,
the fourth is simply a note. A table needs a separate entry for that chord. A
rule does not.

### `alt` subtracts

`C7alt` is a dominant with its middle **replaced**, not one with colour piled
on. The altered scale contains no natural fifth and no natural ninth, so
neither appears. Its `--explain` output says `no fifth` for that reason.

## Changing it

The file is `tapscript/notation/chordsymbol.py`, and it is arranged so that
most changes are one line.

**To accept a new spelling** — add it to `CORE_ALIASES`. That is the whole
change; every extension and alteration already works on it, because they are
applied afterwards and know nothing about spellings.

**To add a chord family** — add a `Core` to `CORES`. A core is four decisions:
which third, which fifth, which seventh it reaches for when a symbol asks for
one without saying which, and whether it carries a major third. That last flag
is what the eleventh rule reads, so setting it correctly is the only subtle
part.

**To change how a degree behaves** — the rules live in `_build`, in the order
they apply: skeleton, stack, `alt`, then modifiers.

Two habits are worth keeping. Anything you add should be expressible as a
statement about a degree; if it is only expressible as a statement about a
named chord, it probably belongs in a core rather than in the rules. And
whatever you change, run the corpus diff below before believing it.

## Compatibility, and how it was established

Accepting more spellings is only safe if it changes none of the ones already
understood. When this landed, every chord token in the repository was parsed
with both the old engine and the new one and the results compared:

```
228 distinct chord tokens, 181,419 occurrences
  identical      181,276
  newly readable      136
  still refused         7   (prose in a chord row: "bass", "guitar", "fade)")
  CHANGED               0
```

Zero. That result is what let the richer vocabulary be the default rather than
something you opt into.

It was not zero on the first attempt. Three chords changed, and all three were
regressions the diff caught:

- **`Bb-7` became a dominant.** A rule meant to read `Cm7-5` as `Cm7b5` was
  also eating the minus in `Bb-7`, which is B-flat *minor* seven in every chart
  ever printed. Twenty-two minor chords in this repository would have turned
  into dominants -- a chart that sounds wrong without looking wrong. A minus now
  reads as an accidental only after a quality has been named, which is why
  `C-9`, `C-11` and `C-13` stay minor.
- **`GbΔ` lost its seventh.** A bare triangle means the seventh chord, unlike a
  bare `M`, which means the triad. That is a property of the spelling rather
  than of the quality, so it could not live in the core table.

The same diff is worth re-running after any change here:

```bash
python3 -m unittest tests.test_chordsymbol
python3 -m tapscript check docs examples tapscript/songbook README.md
```

The warning count on that last command is the blunt instrument: it fell from
185 to 87 when this landed, because 98 chords that had been compiling to
silence started sounding.

## Still open

`tapscript chord` reports which degrees sound. It does not choose a voicing --
register, spacing and which note to drop when there are too many are a separate
decision, because they depend on the instrument and the texture rather than on
the symbol. Chords currently sound as a plain stack from the root, which is
honest but is not what a player would do.

Three places where authorities genuinely disagree, left as they are rather than
settled silently:

- **`C2` and `C4`.** Read as `add9` and `add11`. Both are also written for
  `sus2` and `sus4`, and no source settles it. Taken as adds because that keeps
  the third, and losing a third silently is the worse failure. Write `Csus2` or
  `Csus4` when you mean the other thing.
- **`b13` alongside a natural fifth.** Both are kept. In practice many voicings
  use one or the other, and the ♭13/♯5 distinction is exactly that argument.
- **Lowercase roots are major.** German and Nordic charts use lowercase for
  minor, and `H` for B natural. Not adopted: this corpus writes voicings in
  lowercase, and several thousand files would change meaning. The convention we
  have wins over the one we do not.
