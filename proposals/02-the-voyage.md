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

Rows subdivide independently, and non-sounding rows have no time at all:

```
Chords: | Am  .   .   .  |     4 tokens -> quarters
Melody: | A4  .   C5  E5 |     4 tokens -> quarters
Lyrics: | the tide came  |     3 tokens -> thirds

chords   beats [0.0]
melody   beats [0.0, 2.0, 3.0]
lyrics   beats []               <- no position whatsoever
```

`came` is written directly beneath `C5` and sung a twelfth of a bar away from
it. The alignment a reader trusts is a fiction the compiler cannot see, cannot
warn about, and cannot render.

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

### Phase 1 — The time matrix

Build `TimeGrid`. Populate it where the arranger already walks cells. Change no
behaviour.

*Exit:* a lyric has a position; `6321 files compile exactly as recorded` still
passes. If the fingerprint moves, the refactor changed music and is wrong.

### Phase 2 — Lyric binding **[research]**

Deciding how syllables attach is a design choice with real prior art, and I
should read it before inventing. The question I most want answered: **does a `|`
in ABC's `w:` line resynchronise to the barline?** If it does, a miscount
damages one bar instead of the rest of the song — which is exactly the failure
containment this format wants.

*Exit:* a written proposal, then a syntax that survives the existing corpus
unchanged.

### Phase 3 — SVG

A zero-dependency renderer emitting an inline chart: bold chords, proportional
notes, lyrics under the notes they belong to.

The hard constraint is text measurement without a font library. **[research]**
SVG's `textLength` and `lengthAdjust` may let the *browser* do the measuring so
the renderer never needs metrics — if so, that decides the architecture.

*Exit:* the README's own example renders, prints legibly, and embeds in
markdown.

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
