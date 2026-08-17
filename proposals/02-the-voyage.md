# The voyage

A plan for turning Plainsong from a compiler that works into the notation
people reach for. Written as a first draft on purpose: several sections are
marked **[research]** because the honest answer is that I do not know yet, and
a plan that hides its unknowns is a wish.

## Where we actually are

Not claims — things this repository can demonstrate on demand.

| | |
|---|---|
| Notation compiles | 6,333 sources, 0 errors, including every fenced example in the prose |
| The music is pinned | 6,321 files hashed; CI fails if any file's *notes* change |
| Chord symbols | An open grammar. `C7b9#11` works without being enumerated |
| Voicing | Decided by measurement: 94.4% of named notes survive, against 50.1% |
| Tests | 578, plus 7 specs, on 3.10–3.13 across three operating systems, nothing installed |
| Packaging | Wheel built and exercised in a clean venv outside the tree |

Two properties matter more than the numbers. **Parsing is already whitespace
invariant** — tight, loose, ragged and tab-separated layouts of the same bar
produce byte-identical output, so monospace alignment is a human convention and
not a machine dependency. And **the fingerprint makes change reviewable**: the
rename moved 6,321 files and was proved to alter not one note, by comparing the
note-hash multiset before and after (`d860576193b5504236ab7162`, both sides).

## The finding that reorders everything

Rows subdivide independently, so vertical alignment means nothing:

```
Chords: | Am  .   .   .  |     4 tokens -> quarters
Melody: | A4  .   C5  E5 |     4 tokens -> quarters
Lyrics: | the tide came  |     3 tokens -> thirds

chords   beats [0.0]
melody   beats [0.0, 2.0, 3.0]
lyrics   beats [0.0, 1.333, 2.667]   <- its own subdivision, not the melody's
```

`came` is written directly beneath `C5`. `C5` sounds on beat 2.0 and `came`
lands on beat 2.667, two thirds of a beat later, because the lyric row divided
the bar into three and the melody divided it into four. The alignment a reader
trusts is a fiction: the compiler cannot see it, cannot warn about it, and
cannot render it.

(An earlier draft of this document said lyric rows had no position at all. They
have one — it is simply computed from the wrong thing.)

This is the root of three of the four challenges. A renderer has nothing to lay
lyrics against. A merge tool has no coordinate to detect conflicts in. A linter
has no way to say "this row disagrees with its neighbours". Fix the coordinate
system and all three become tractable; fix them separately and each invents its
own.

## The one structural idea

**Every token in every row gets a position on a common time matrix, whether or
not it makes a sound.**

```python
@dataclass(frozen=True)
class Placement:
    token: str
    row: str        # "chords" | "melody" | "lyrics" | "@bass"
    bar: int
    onset: float    # beats from section start
    width: float
    unit: float     # position within its bar, 0.0-1.0
```

`unit` is the load-bearing field. It is computed identically for a lyric and a
note, which is what lets a renderer put them in the same column and a merger
reason about them in the same space.

Everything downstream is then a projection of one structure:

- **SVG** is `x = unit * bar_width`. A coordinate transform, not a layout engine.
- **Merge** is set intersection on `(row, bar, unit)`. Two agents editing
  different rows *provably* cannot collide, because the row axis is disjoint.
  That is a proof rather than a heuristic, and it is the right foundation for
  the MCP ensemble.
- **Lint** gains a diagnostic the compiler currently cannot express: warn when a
  row's subdivision disagrees with its neighbours — the `came`/`C5` lie.

## Phases

Each phase has an exit criterion that can be checked, not judged.

### Phase 0 — Ship what exists

Publish 1.0.0. Nothing below matters if the thing cannot be installed.

*Exit:* `pip install plainsong` works from a clean machine.

### Phase 1 — The time matrix — **done**

`notation/timegrid.py`. The arranger populates it from positions it has already
computed, in the two places it walks cells: `_place_lyrics` and `_place_row`.

`bar` and `unit` are derived in `TimeGrid.add` and nowhere else, which is the
whole point — a lyric and a note cannot drift apart by being computed in two
places. Rests and sustains are recorded too, before the note dispatch, so a
token that makes no sound still occupies its column; a renderer has to leave
room for it and a merge has to see it as taken.

*Exit, met:* a lyric has a position, and `6321 file(s) compile exactly as
recorded` still passes — the grid observes the arranger and does not steer it.
The `came`/`C5` lie is now something the compiler can state: `C5` sits at
`unit 0.5`, `came` at `unit 0.667`, and `grid.column(0, 0.5)` returns the chord
and melody rows without the lyric that appears to be standing in it.

One thing this phase taught, worth keeping. The first version guarded the bar
boundary twice — rounding the position *and* nudging it before flooring — and
neither mutation could be made to fail a test, because each fixed the case on
its own. Two guards that no test can tell apart are one guard and one piece of
dead code. Collapsed to the nudge, which then failed the suite when removed.

### Phase 2 — Lyric binding — **done**

`notation/lyrics.py`, behind `core.lyrics = "bound"`, defaulting to
`independent` because lyric events reach the MIDI file and the rule is that a
change to how existing notation compiles defaults to the old reading.

*Exit, met:* a syllable sounds on its note, a miscount costs one bar and
recovers at the barline, the corpus fingerprint is unmoved, and
`core.notation/lyric-binding` fails when the binding is disabled.

**One thing below turned out to be wrong, and the corpus is what said so.** The
research concluded that a sustain token in a lyric row should read as a melisma,
by analogy with ABC's `_`. The only file in this repository with lyric rows
writes `| sing . every . |` under `| Bb3 . F4 . |` — two words, two notes, and
the dots are holding the *column* under a sustaining melody. Read as melismas
they each consume a note and `every` falls off the end of the bar. Padding binds
to nothing; a held syllable is written by using fewer words than there are
notes, which is what a lead sheet already does. The analogy was to another
format's spelling, and the notation people write beat it.

### Phase 2 as originally reasoned — **kept for the record**

The research came back and the answer is unusually clean.

**Syllables bind to notes, never to raw time.** That is uncontested across
LilyPond, MusicXML, ABC, MEI and Humdrum — the formats disagree about
*mechanism*, not about the target. So the current behaviour, where a lyric row
subdivides its bar independently of the melody, is not a variant convention. It
is simply wrong, and every other format says so.

Two mechanisms exist. **Attachment** (MusicXML `<lyric>` on `<note>`, MEI
`<verse>`) makes mismatch structurally inexpressible, but requires the lyric to
live inside the note — impossible for a row-based text format. **Counting**
(ABC, LilyPond) walks a flat syllable stream in lockstep against the notes.
That is what Plainsong already is, so counting it is.

**The barline resyncs.** Quoted from the ABC standard: a `w:` line is *"aligned
syllable by syllable below the previous line of notes"*, and *"if there are not
as many syllables as notes in a measure, typing a `|` automatically advances to
the next bar; if there are enough syllables the `|` is just ignored."* Exactly
the fault containment this format wants: a miscount costs one bar and then
recovers, instead of shifting every remaining word in the song. Plainsong
already writes `|` in every row, so the mechanism is present in the syntax
today and merely unhonoured.

**Melisma and skip are already in the vocabulary.** The two special cases are a
syllable held across several notes, and a note with no syllable. Plainsong's
existing token classes already mean exactly those things:

```
sustain  . .. - ~ hold (hold) (sustain) (let ring) (ring)     hold this across  -> melisma
rest     _ 0 r x -- rest (rest) (silence) (x) n.c.            nothing here      -> skip
```

No characters need inventing. The mapping is by *meaning* rather than by
borrowing another format's spelling — worth stressing, because the spellings
conflict: `_` is a skip in LilyPond and a melisma in ABC. Plainsong's own
semantics land on the right side of both.

**The conflict with the run-on rule — decided, and it dissolves rather than
resolves.** Every other format stacks repeated lyric rows as *parallel verses*.
Plainsong's rule is that a repeated row of the same kind *runs on in time*, so
two `Lyrics:` rows mean verse-then-verse sequentially. The draft of this plan
proposed inventing `Lyrics 2:` or `Lyrics(v2):` to get parallel verses without
disturbing the rule.

That is the wrong shape, because the two rules are not in conflict once you
notice what run-on is a statement *about*. **Run-on is a claim about time**: a
repeated row continues where the previous one stopped. Phase 2 establishes that
lyrics do not own time — they bind to notes, and take whatever time those notes
have. A row that owns no time cannot follow on into any, so the run-on rule does
not reach lyrics at all. It is not overridden and it needs no exception clause;
it simply stops applying, for the same reason it says nothing about a `[Stage]`
block.

So, in one sentence, and with no new syntax:

> Every `Melody:` row in a section concatenates into one melodic stream, as it
> does today. Each `Lyrics:` row is a verse sung over that whole stream.

This is unambiguous in the case the draft could not settle. A section with two
`Melody:` rows is eight bars of one tune; two `Lyrics:` rows over it are two
verses of eight bars each, not one verse chopped in half. Words for the second
four bars go in the same row that holds the first four — which is exactly how a
song sheet is written, and why no reader has ever had to be taught it.

Inventing `Lyrics 2:` would have been the worse outcome twice over: a second
spelling for a thing that already has one, and a permanent reminder in the
syntax of a conflict that turned out not to exist.

**What it costs.** Nothing measurable. Not one of the 6,321 `.song` files in
this repository has a section carrying more than one `Lyrics:` row, so no
notation here changes meaning. Lyrics contribute nothing to the fingerprint —
it hashes pitch, position, duration, velocity and the two propagation times —
so this cannot move a note. Files outside this repository could in principle
hold a stacked lyric row, which is why the reading arrives with Phase 2, gated
with the rest of lyric binding rather than on its own.

*Exit:* lyrics have positions taken from the melody; a bar with the wrong
syllable count warns and recovers at the next barline rather than propagating;
the existing corpus compiles unchanged.

### Phase 3 — SVG — **done**

`render/chart.py`, `plainsong chart`, and `tools/extract_font_widths.py` for the
width table. *Exit, met:* a bundled example renders, is legible in light and
dark, and embeds in this repository's README as an `<img>`.

Two things the research did not predict. The bold face needs measuring
separately -- `m`, `b` and `j` differ between the weights and chord symbols are
made of exactly those, so measuring regular and drawing bold makes
`lengthAdjust` smear every glyph. And bar width should be derived from content
rather than fixed: each symbol sits at `unit * width`, so the constraint is
`width >= (advance + gap) / (next_unit - unit)`, and taking the maximum solves
it in one pass. A fixed width either wastes the page or overlaps the symbols,
and which one depends on the song.

### Phase 3 as originally reasoned — **kept for the record**

A zero-dependency renderer emitting a chart: bold chords, proportionally spaced
notes, lyrics under the notes they belong to.

**Text measurement is solved, and it is the thing that decides the design.**
`textLength` and `lengthAdjust` are core SVG *geometry* attributes rather than
CSS or script, so the browser fits the text to a width we declare. The pattern:
compute layout in Python from the Adobe Core-14 AFM width tables — Helvetica,
Arial and Liberation Sans are metric-compatible, so one table serves all three,
and digits are a uniform 0.556 em — then emit `textLength` set to that same
figure. The rendered font then snaps to the width we planned for even when the
viewer substitutes a different one. VexFlow does the same thing with bundled
width tables. No font library, no measurement pass, no drift.

**Everything is expressed in staff spaces**, so the whole chart scales from one
number. Bravura's own `engravingDefaults`, read from
`steinbergmedia/bravura@bravura-1.481` `redist/Bravura.json` rather than from
prose: `thinBarlineThickness` **0.16**, `thickBarlineThickness` **0.5** (the key
that covers a final or repeat barline — there is no key called "final barline"),
`staffLineThickness` **0.13**.

**SMuFL fixes the bridge to type twice, and the draft above quoted the wrong
one.** The specification defines two registrations, and both sentences exist:

| | |
|---|---|
| `scoring-metrics-glyph-registration.html` | *"one staff space = 0.25 em"* — glyphs drawn on a staff |
| `text-metrics-glyph-registration.html` | *"one staff space = 0.2 em"* — glyphs set inline in running prose |

So 0.2 em is not wrong, it is the *text* figure, and this plan never said which
scheme it meant. A chart drawing barlines at Bravura's `engravingDefaults` is
using scoring metrics, so it wants **0.25 em**, `font-size = 4 × staff_space`.
Checked in `w3c/smufl` releases 1.3 and 1.4; both say the same in both files.

**Horizontal spacing, confirmed against LilyPond's source** rather than its
manual. `lily/spacing-options.cc` computes
`(shortest_duration_space + log2(ratio)) * increment`, citing Gourlay 1987 in
the comment, with defaults `shortest-duration-space = 2.0` and
`spacing-increment = 1.2` in `scm/define-grobs.scm`. Distributing that gives the
`2.4 + 1.2·log2(ratio)` written below — **the 2.4 is a product, not a property**,
and anyone reading it back out of LilyPond will find `2.0` and be tempted to
"fix" it. Grace notes use a different pair (`1.6`/`0.8`); do not conflate them.

**Horizontal space is logarithmic in duration, not linear** — a note twice as
long is nowhere near twice as wide. Gourlay (1987) is the root reference and
LilyPond's descendant of it gives usable constants:

```
width = shortest_space + increment · log2(duration / shortest_duration)
        shortest_space = 2.4 staff-spaces
        increment      = 1.2 staff-spaces per doubling
```

**Chords are left-aligned to their beat, not centred on it.** Confirmed against
iReal Pro's documented protocol and working arrangers' practice; the casual
"centred over the beat" phrasing found elsewhere is imprecise and should not be
implemented literally.

**The flat sign is not in the font, and the sharp is.** Read out of
`/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf` by walking its
`cmap` directly: U+266F ♯ is present (glyph 2238), and **U+266D ♭ and U+266E ♮
are absent** — a `cmap` lookup returns glyph 0. So a chart set in the
Arial-metric stack can render `C♯` and cannot render `B♭`, which is the wrong
half to lose: the songbook is full of flats and the parser accepts `E7♭9` today.
The renderer must fold to ASCII `b` and `n` on output, whatever the source
spelled. DejaVu Sans and FreeSans do carry all three, but neither is
Arial-metric, so they do not rescue the width table.

Worth stressing because it is the kind of thing found late and painfully:
nothing about parsing `♭` predicts that drawing it fails.

**"Helvetica, Arial and Liberation Sans are metric-compatible" is not verified.**
No Helvetica AFM exists on this machine to diff against — no ghostscript, no URW
fonts — so what is measured is Liberation Sans and nothing else. One data point
against the premise: Liberation Sans `M` is 833/1000 em, which matches the
commonly cited Arial figure and not Adobe Helvetica's 889. Treat the one-table
claim as unproven, and either measure a real Helvetica before relying on it or
scope the claim to Arial and Liberation Sans.

**There is no AFM to read, but there is a TTF.** Widths come from `head`
(`unitsPerEm` 2048), `hhea` (`numberOfHMetrics` 2620 — every glyph explicit, no
trailing run to unpack), `hmtx`, and a format-4 `cmap`. Roughly 100–200 lines of
stdlib `struct`, which is well inside what this package already does by hand for
MIDI. `fontTools` is not installed and must not become a dependency.

**GitHub strips raw `<svg>` from markdown.** Only `<img src="chart.svg">`
renders, which has three consequences worth designing around rather than
discovering: no external webfonts (an image cannot fetch one), no interactivity
or CSS, and the file must exist at a path or a URL. `textLength` survives it,
being geometry rather than style. This is also the strongest argument yet for
the render-service shape of the worker: an `<img>` pointing at a URL is the only
way a `.song` file embeds in a document on a platform we do not control.

*Exit:* the README's own example renders, prints legibly, and embeds in a
GitHub markdown file as an `<img>`.

### Phase 4 — Agentic merge

Move the ensemble from file locks to the matrix predicate. Row-disjoint edits
merge without a lock, because they cannot conflict by construction.

*Exit:* two agents concurrently rewriting `@bass` and `Melody:` produce a
correct score with no serialisation, demonstrated rather than argued.

### Phase 5 — Syntax sugar **[research]**

Relative octaves in the ABC tradition (`c` versus `C`, `c'`) so a melody's
contour is scannable. Strictly additive, behind a dialect declaration.

*Exit:* every existing file compiles identically. The corpus is the test.

### Phase 6 — Separating the stage

`[Stage]` moves to an `include:` pointing at a `.stage` profile. Smaller than it
looks: staging is already inert without a declaration, so the coupling is
textual rather than semantic.

*Exit:* a `.song` file contains only music; a `.stage` file contains only room.

## Invariants

Non-negotiable, and each one is a scar.

1. **Zero dependencies at module scope.** CI installs nothing.
2. **The fingerprint may only move deliberately.** Never re-record a baseline to
   make CI green — that is the one action that destroys the guarantee entirely.
3. **Below the waterline goes behind a setting.** The test is not "does this need
   a library", it is *"can this change the sound of a file that already
   exists"*. Two things pass the first test and fail the second.
4. **Measure where the decision happens.** Averaging the voicing strategies over
   the whole corpus read 99.4% against 99.9% and was useless, because 99.7% of
   chords are small enough that every strategy agrees. Scored on the 277 chords
   where a note must actually be dropped, it read 50.1% against 94.4%.
5. **A name's prior should point the right way.** For a format read by agents,
   the name *is* the retrieval — a wrong prior yields fluent wrong answers
   rather than a visible dead end.
6. **Absence of imports measures coupling, not life.** `legacy/` was deleted for
   being quiet and turned out to have someone working in it. Read the log.

## Debts, carried openly

- **Three JavaScript implementations.** Python has an open grammar; the demo
  enumerates 18 chord qualities; the worker has its own third table. `CM7` works
  in the CLI and fails in the demo. One JS implementation, shared, inlined into
  the demo at build time.
- **The worker is the wrong shape.** Compiling over HTTP serves nobody. Rendering
  to an image at a URL — so a `.song` embeds in any markdown, which is the
  repository's own stated promise — is server-shaped and undelivered.
- **85 warnings in 12 files.** Malformed generated source, not a parser gap.
- **The MCP server has never had a third-party client connect.**
- **`plainsong/mcp/` is duplicated** in the sibling. Four pieces of technology
  wearing one name; `features.py` is not MCP at all.

## What would make this fail

Worth writing down while it is cheap to say.

Building the renderer before the matrix, so the layout logic accretes its own
private notion of time. Letting the syntax sugar land before the corpus can
prove it non-breaking. Publishing before the demo agrees with the compiler,
because the demo is the front door and a visitor who types `CM7` and gets
silence concludes the whole thing is broken.

And the quiet one: treating this document as decided. Two of its six phases open
with **[research]** because I do not yet know the answer, and the plan is worth
more if those stay honest.
